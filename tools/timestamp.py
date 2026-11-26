#!/usr/bin/env python3
"""ROKAF Track Record Fund — OpenTimestamps 블록체인 타임스탬프 모듈 (표준 라이브러리만 사용).

무엇을 하는가
  * 파일의 SHA-256 다이제스트를 OpenTimestamps 공개 캘린더(a/b.pool.opentimestamps.org 등)에
    제출하고, 캘린더가 돌려준 증명을 표준 `.ots`(DetachedTimestampFile) 형식으로 저장한다.
  * 저장된 `.ots`의 헤더·해시 알고리즘·다이제스트가 대상 파일과 일치하는지, 어떤
    어테스테이션(캘린더 접수 / 비트코인 블록)이 들어 있는지 파싱해 검증한다.
  * `upgrade` — 접수(pending) 상태인 증명을 캘린더에 다시 조회해, 캘린더가 비트코인
    블록에 커밋한 뒤에는 비트코인 블록 어테스테이션(블록 높이)으로 승격한다.

`.ots` 파일 구조 (OpenTimestamps 명세, python-opentimestamps 0.5.0 구현과 동일)
  매직(31B) + 버전(0x01) + 파일 해시 연산 태그(0x08=sha256) + 다이제스트(32B) + 타임스탬프 트리
  트리   = (0xff 브랜치)* + (0x00 어테스테이션 | 연산 + 하위 트리)
  어테스테이션 = 8B 태그 + varbytes(페이로드)
    · 접수(pending)  83dfe30d2ef90c8e : varbytes(캘린더 URL)
    · 비트코인 블록  0588960d73d71901 : varuint(블록 높이)
    · 라이트코인 블록 06869a0d73d71b45 : varuint(블록 높이)
  연산   = 0x02 sha1 / 0x03 ripemd160 / 0x08 sha256 / 0x67 keccak256 / 0xf0 append / 0xf1 prepend

CLI
  python3 tools/timestamp.py stamp    audit/snapshots/2026-11-25.json
  python3 tools/timestamp.py verify   audit/snapshots/2026-11-25.json [--ots audit/ots/2026-11-25.ots]
  python3 tools/timestamp.py upgrade  audit/ots/*.ots
  python3 tools/timestamp.py show     audit/ots/2026-11-25.ots

  종료코드: 0 = 검증 통과, 1 = 검증 실패, 2 = 네트워크/캘린더 오류
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
VERSION = 1
MAX_MSG = 4096
MAX_ATT_PAYLOAD = 8192
MAX_RESPONSE = 10000
UA = "rokaftf-audit/1.0 (+https://github.com/hoon4056/equity-research-portfolio)"

DEFAULT_CALENDARS = [
    "https://a.pool.opentimestamps.org",
    "https://b.pool.opentimestamps.org",
    "https://ots.btc.catallaxy.com",
]

HASH_OPS = {0x02: "sha1", 0x03: "ripemd160", 0x08: "sha256", 0x67: "keccak256"}
UNARY_OPS = {0x02, 0x03, 0x08, 0x67, 0xF2, 0xF3}
BIN_OPS = {0xF0: "append", 0xF1: "prepend"}
OP_NAMES = {**{k: v for k, v in HASH_OPS.items()}, 0xF0: "append", 0xF1: "prepend",
            0xF2: "reverse", 0xF3: "hexlify"}

ATT_PENDING = bytes.fromhex("83dfe30d2ef90c8e")
ATT_BITCOIN = bytes.fromhex("0588960d73d71901")
ATT_LITECOIN = bytes.fromhex("06869a0d73d71b45")


# --------------------------------------------------------------------------- #
# 직렬화 기본기 (LEB128 varuint, varbytes)
# --------------------------------------------------------------------------- #
def _write_varuint(value: int) -> bytes:
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _read_varuint(data: bytes, off: int) -> tuple[int, int]:
    value, shift = 0, 0
    for _ in range(9):
        if off >= len(data):
            raise ValueError("varuint 잘림")
        b = data[off]
        off += 1
        value |= (b & 0x7F) << shift
        if not b & 0x80:
            return value, off
        shift += 7
    raise ValueError("varuint 이 9바이트를 초과")


def _write_varbytes(value: bytes) -> bytes:
    return _write_varuint(len(value)) + value


def _read_varbytes(data: bytes, off: int, max_len: int, min_len: int = 0) -> tuple[bytes, int]:
    length, off = _read_varuint(data, off)
    if length > max_len or length < min_len:
        raise ValueError(f"varbytes 길이 범위 위반: {length}")
    if off + length > len(data):
        raise ValueError("varbytes 잘림")
    return data[off:off + length], off + length


# --------------------------------------------------------------------------- #
# 연산
# --------------------------------------------------------------------------- #
def apply_op(tag: int, arg: bytes | None, msg: bytes) -> bytes:
    if len(msg) > MAX_MSG:
        raise ValueError("메시지가 너무 길다")
    if tag == 0x02:
        return hashlib.sha1(msg).digest()
    if tag == 0x03:
        out = hashlib.new("ripemd160")
        out.update(msg)
        return out.digest()
    if tag == 0x08:
        return hashlib.sha256(msg).digest()
    if tag == 0x67:
        try:
            from Crypto.Hash import keccak  # pycryptodome (선택 의존성)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("keccak256 연산은 pycryptodome이 필요하다") from exc
        h = keccak.new(digest_bits=256)
        h.update(msg)
        return h.digest()
    if tag == 0xF0:
        return msg + (arg or b"")
    if tag == 0xF1:
        return (arg or b"") + msg
    if tag == 0xF2:
        return msg[::-1]
    if tag == 0xF3:
        return msg.hex().encode()
    raise ValueError(f"알 수 없는 연산 태그 0x{tag:02x}")


class Node:
    """타임스탬프 트리의 한 노드 = 한 메시지에 대한 연산·어테스테이션 묶음."""
    __slots__ = ("msg", "attestations", "children")

    def __init__(self, msg: bytes):
        self.msg = bytes(msg)
        self.attestations: set[tuple[bytes, bytes]] = set()
        self.children: dict[tuple[int, bytes | None], "Node"] = {}

    def walk(self, indent: int = 0):
        yield self, indent
        for key in sorted(self.children, key=lambda k: (k[0], k[1] or b"")):
            yield from self.children[key].walk(indent + 1)


def _parse(data: bytes, off: int, msg: bytes, depth: int = 0) -> tuple[Node, int]:
    if depth > 256:
        raise ValueError("타임스탬프 트리 깊이 초과")
    node = Node(msg)
    tag = data[off]
    off += 1
    while tag == 0xFF:
        off = _branch(data, off, node, depth)
        tag = data[off]
        off += 1
    off = _branch(data, off, node, depth, tag)
    return node, off


def _branch(data: bytes, off: int, node: Node, depth: int = 0, tag: int | None = None) -> int:
    if tag is None:
        if off >= len(data):
            raise ValueError("브랜치 태그 잘림")
        tag = data[off]
        off += 1
    if tag == 0x00:  # 어테스테이션
        atag = data[off:off + 8]
        off += 8
        payload, off = _read_varbytes(data, off, MAX_ATT_PAYLOAD)
        node.attestations.add((atag, payload))
        return off
    if tag in BIN_OPS:
        arg, off = _read_varbytes(data, off, MAX_MSG, min_len=1)
    elif tag in UNARY_OPS:
        arg = None
    else:
        raise ValueError(f"알 수 없는 태그 0x{tag:02x}")
    child, off = _parse(data, off, apply_op(tag, arg, node.msg), depth=depth + 1)
    node.children[(tag, arg)] = child
    return off


def _serialize(node: Node) -> bytes:
    if not node.attestations and not node.children:
        raise ValueError("빈 노드는 직렬화할 수 없다")
    out = bytearray()

    def att(a: tuple[bytes, bytes]) -> bytes:
        return a[0] + _write_varbytes(a[1])

    ats = sorted(node.attestations)
    if len(ats) > 1:
        for a in ats[:-1]:
            out += b"\xff\x00" + att(a)
    if not node.children:
        out += b"\x00" + att(ats[-1])
        return bytes(out)
    if ats:
        out += b"\xff\x00" + att(ats[-1])
    ops = sorted(node.children.items(), key=lambda kv: (kv[0][0], kv[0][1] or b""))
    for (tag, arg), child in ops[:-1]:
        out.append(0xFF)
        out.append(tag)
        if arg is not None:
            out += _write_varbytes(arg)
        out += _serialize(child)
    tag, arg = ops[-1][0]
    out.append(tag)
    if arg is not None:
        out += _write_varbytes(arg)
    out += _serialize(ops[-1][1])
    return bytes(out)


def merge(dst: Node, src: Node) -> None:
    if dst.msg != src.msg:
        raise ValueError("서로 다른 메시지의 타임스탬프는 합칠 수 없다")
    dst.attestations |= src.attestations
    for key, child in src.children.items():
        if key in dst.children:
            merge(dst.children[key], child)
        else:
            clone = Node(child.msg)
            merge(clone, child)
            dst.children[key] = clone


# --------------------------------------------------------------------------- #
# .ots 파일
# --------------------------------------------------------------------------- #
def read_ots(path: Path) -> dict:
    """`.ots` 파일을 파싱해 {version, hash_op, digest, tree} 를 돌려준다."""
    data = path.read_bytes()
    if not data.startswith(MAGIC):
        raise ValueError("OpenTimestamps 매직 불일치")
    off = len(MAGIC)
    version = data[off]
    off += 1
    if version != VERSION:
        raise ValueError(f"지원하지 않는 .ots 버전 {version}")
    op_tag = data[off]
    off += 1
    if op_tag not in HASH_OPS:
        raise ValueError(f"파일 해시 연산이 해시 함수가 아니다(0x{op_tag:02x})")
    digest_len = {"sha1": 20, "ripemd160": 20, "sha256": 32, "keccak256": 32}[HASH_OPS[op_tag]]
    digest = data[off:off + digest_len]
    off += digest_len
    tree, off = _parse(data, off, digest)
    if off != len(data):
        raise ValueError("트리 뒤에 남은 바이트가 있다")
    return {"version": version, "hash_op": HASH_OPS[op_tag], "digest": digest, "tree": tree}


def write_ots(path: Path, digest: bytes, tree: Node, hash_op_tag: int = 0x08) -> None:
    body = MAGIC + bytes([VERSION, hash_op_tag]) + digest + _serialize(tree)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def describe_attestation(tag: bytes, payload: bytes) -> dict:
    try:
        if tag == ATT_PENDING:
            uri, _ = _read_varbytes(payload, 0, 1000)
            return {"kind": "pending", "calendar": uri.decode("utf-8", "replace")}
        if tag in (ATT_BITCOIN, ATT_LITECOIN):
            height, _ = _read_varuint(payload, 0)
            chain = "bitcoin" if tag == ATT_BITCOIN else "litecoin"
            return {"kind": "block", "chain": chain, "block_height": height}
    except ValueError:
        pass
    return {"kind": "unknown", "tag": tag.hex(), "payload": payload.hex()}


def attestations_of(tree: Node) -> list[dict]:
    out = []
    for node, _ in tree.walk():
        for tag, payload in sorted(node.attestations):
            rec = describe_attestation(tag, payload)
            rec["commitment"] = node.msg.hex()
            out.append(rec)
    return out


def verify_file(path: Path, ots_path: Path | None = None) -> dict:
    """대상 파일과 `.ots` 증명의 일치 여부 + 어테스테이션 종류를 돌려준다."""
    ots_path = ots_path or path.with_suffix(path.suffix + ".ots")
    result = {"file": str(path), "ots": str(ots_path), "ok": False, "errors": [],
              "digest": None, "digest_match": False, "attestations": [],
              "bitcoin_attested": False, "pending": []}
    try:
        parsed = read_ots(ots_path)
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"{type(exc).__name__}: {exc}")
        return result
    data = path.read_bytes()
    hash_name = parsed["hash_op"]
    actual = hashlib.new(hash_name, data).digest() if hash_name != "keccak256" else None
    result["digest"] = parsed["digest"].hex()
    result["hash_op"] = hash_name
    result["digest_match"] = actual == parsed["digest"]
    if not result["digest_match"]:
        result["errors"].append(
            f"다이제스트 불일치: 파일 {actual.hex() if actual else '?'} vs 증명 {parsed['digest'].hex()}")
    atts = attestations_of(parsed["tree"])
    result["attestations"] = atts
    result["bitcoin_attested"] = any(a["kind"] == "block" and a.get("chain") == "bitcoin" for a in atts)
    result["pending"] = [a["calendar"] for a in atts if a["kind"] == "pending"]
    if not atts:
        result["errors"].append("어테스테이션이 하나도 없다")
    result["ok"] = result["digest_match"] and bool(atts) and not result["errors"]
    return result


# --------------------------------------------------------------------------- #
# 네트워크: 캘린더 제출 / 승격
# --------------------------------------------------------------------------- #
def _request(url: str, data: bytes | None = None, timeout: int = 30) -> bytes:
    headers = {"Accept": "application/vnd.opentimestamps.v1", "User-Agent": UA}
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {url}")
        body = resp.read(MAX_RESPONSE + 1)
    if len(body) > MAX_RESPONSE:
        raise RuntimeError(f"응답이 너무 크다({len(body)}B) {url}")
    return body


def submit(calendar: str, digest: bytes, timeout: int = 30) -> Node:
    """다이제스트를 캘린더에 제출하고, 캘린더가 돌려준 타임스탬프 트리를 파싱한다."""
    body = _request(urllib.parse.urljoin(calendar.rstrip("/") + "/", "digest"), data=digest, timeout=timeout)
    tree, off = _parse(body, 0, digest)
    if off != len(body):
        raise ValueError("캘린더 응답에 남은 바이트가 있다")
    return tree


def get_timestamp(calendar: str, commitment: bytes, timeout: int = 30) -> Node | None:
    """캘린더에서 특정 커밋먼트의 최신 타임스탬프를 가져온다(없으면 None)."""
    url = urllib.parse.urljoin(calendar.rstrip("/") + "/", "timestamp/" + commitment.hex())
    try:
        body = _request(url, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    tree, off = _parse(body, 0, commitment)
    if off != len(body):
        raise ValueError("캘린더 응답에 남은 바이트가 있다")
    return tree


def stamp_file(path: Path, out: Path | None = None, calendars: list[str] | None = None,
               timeout: int = 30) -> dict:
    """파일 해시를 공개 캘린더들에 제출하고 병합된 `.ots` 증명을 저장한다."""
    calendars = calendars or DEFAULT_CALENDARS
    out = out or path.with_suffix(path.suffix + ".ots")
    digest = hashlib.sha256(path.read_bytes()).digest()
    root = Node(digest)
    per: dict[str, str] = {}
    for cal in calendars:
        try:
            tree = submit(cal, digest, timeout=timeout)
            merge(root, tree)
            per[cal] = "submitted"
        except Exception as exc:  # noqa: BLE001 — 캘린더 하나가 죽어도 나머지로 봉인
            per[cal] = f"failed: {type(exc).__name__}: {exc}"
    ok = [c for c, s in per.items() if s == "submitted"]
    if not ok:
        raise RuntimeError("모든 캘린더 제출 실패: " + json.dumps(per, ensure_ascii=False))
    write_ots(out, digest, root)
    return {"ots": str(out), "calendars": per, "ots_status": "stamped",
            "digest": digest.hex(), "attestations": attestations_of(root)}


def upgrade_file(ots_path: Path, timeout: int = 30) -> dict:
    """접수(pending) 증명을 캘린더에 다시 조회해 블록 어테스테이션으로 승격 시도."""
    parsed = read_ots(ots_path)
    tree = parsed["tree"]
    tried, upgraded = [], 0
    for node, _ in list(tree.walk()):
        pendings = [(t, p) for (t, p) in node.attestations if t == ATT_PENDING]
        if not pendings or any(t in (ATT_BITCOIN, ATT_LITECOIN) for (t, _) in node.attestations):
            continue
        for _, payload in pendings:
            cal = "?"
            try:
                uri, _ = _read_varbytes(payload, 0, 1000)
                cal = uri.decode("utf-8", "replace")
                fresh = get_timestamp(cal, node.msg, timeout=timeout)
                if fresh is None:
                    tried.append({"calendar": cal, "commitment": node.msg.hex(), "result": "not_found"})
                    continue
                before = len([1 for a in attestations_of(tree) if a["kind"] == "block"])
                merge(node, fresh)
                after = len([1 for a in attestations_of(tree) if a["kind"] == "block"])
                tried.append({"calendar": cal, "commitment": node.msg.hex(),
                              "result": "upgraded" if after > before else "still_pending"})
                upgraded += max(0, after - before)
            except Exception as exc:  # noqa: BLE001
                tried.append({"calendar": cal,
                              "result": f"error: {type(exc).__name__}: {exc}"})
    if upgraded:
        write_ots(ots_path, parsed["digest"], tree, hash_op_tag={"sha256": 0x08, "sha1": 0x02,
                                                                "ripemd160": 0x03,
                                                                "keccak256": 0x67}[parsed["hash_op"]])
    return {"ots": str(ots_path), "upgraded_attestations": upgraded, "attempts": tried,
            "attestations": attestations_of(tree)}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> int:
    p = argparse.ArgumentParser(description="OpenTimestamps 봉인/검증 (표준 라이브러리 구현)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("stamp", help="파일을 공개 캘린더에 제출하고 .ots 저장")
    s.add_argument("file")
    s.add_argument("--out", default=None)
    s.add_argument("--calendar", action="append", default=None, help="캘린더 URL(반복 지정 가능)")
    s.add_argument("--timeout", type=int, default=30)

    v = sub.add_parser("verify", help="파일과 .ots 증명 대조(로컬, 네트워크 없음)")
    v.add_argument("file")
    v.add_argument("--ots", default=None)

    u = sub.add_parser("upgrade", help="pending 증명을 블록 어테스테이션으로 승격")
    u.add_argument("files", nargs="+")
    u.add_argument("--timeout", type=int, default=30)

    w = sub.add_parser("show", help=".ots 증명 내용 출력")
    w.add_argument("file")

    a = p.parse_args()
    if a.cmd == "stamp":
        info = stamp_file(Path(a.file), Path(a.out) if a.out else None,
                          calendars=a.calendar, timeout=a.timeout)
        print(json.dumps({**info, "attestations": info["attestations"]}, ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "verify":
        res = verify_file(Path(a.file), Path(a.ots) if a.ots else None)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["ok"] else 1
    if a.cmd == "upgrade":
        rc = 0
        for f in a.files:
            try:
                res = upgrade_file(Path(f), timeout=a.timeout)
                print(json.dumps({"ots": res["ots"], "upgraded": res["upgraded_attestations"],
                                  "attestations": res["attestations"]}, ensure_ascii=False, indent=2))
            except Exception as exc:  # noqa: BLE001
                print(f"[upgrade] {f}: {type(exc).__name__}: {exc}", file=sys.stderr)
                rc = 2
        return rc
    if a.cmd == "show":
        parsed = read_ots(Path(a.file))
        print(json.dumps({"version": parsed["version"], "hash_op": parsed["hash_op"],
                          "digest": parsed["digest"].hex(),
                          "attestations": attestations_of(parsed["tree"])},
                         ensure_ascii=False, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
