#!/usr/bin/env python3
"""ROKAF Track Record Fund — 재현·봉인 감사 엔진 (공개 재현용).

이 모듈은 정산 엔진(`portfolio/tracker.py`, 비공개 작업공간)에서 쓰는 계산식을
그대로 옮겨 온 **공개판**이다. 제3자는 저장소를 clone 한 뒤 `python verify.py`
한 번으로 다음을 직접 재현할 수 있다.

  1. 원값(`data/performance_series.json`의 일별 종가·KOSPI 지수)만 가지고
     일별 수익률, 누적 수익률, KOSPI 벤치마크 수익률, 일일/누적 Alpha,
     MDD, Beta, Sharpe, Information Ratio, 추적오차를 처음부터 다시 계산한다.
  2. 재계산 값이 저장된 시계열·`data/portfolio.json`·대시보드(`index.html`)의
     표기 수치와 0.01%p 이내로 일치하는지 확인한다.
  3. `audit/snapshots/*.json`의 SHA-256 해시와 `audit/hash_chain.jsonl`의
     해시 체인(직전 해시 연결)이 그대로인지 확인한다. 한 바이트라도 바뀌면
     체인이 끊어져 검증이 실패한다.

설계 원칙
  * 반올림 누적 오차를 막기 위해 파생 수치는 **원값에서 계산한 뒤** 마지막에
    반올림한다. (tracker.py와 같은 규칙)
  * 스냅샷은 "그날 우리가 주장한 값"을 고정한다. 봉인 시점 이후 원본 데이터가
    바뀌면 스냅샷 해시가 달라져 체인 검증이 실패한다.
  * 이미 봉인된 날짜의 스냅샷이 (소급 정정 등으로) 바뀌면 과거 체인을 고쳐 쓰지
    않고 **개정(revision) 항목을 새로 덧붙인다**. 과거 봉인 기록은 지워지지 않는다.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import statistics as st
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SERIES = REPO / "data" / "performance_series.json"
PORTFOLIO = REPO / "data" / "portfolio.json"
TRADE_LOG = REPO / "data" / "trade_log.csv"
INDEX_HTML = REPO / "index.html"
README = REPO / "README.md"
AUDIT = REPO / "audit"
SNAPSHOTS = AUDIT / "snapshots"
CHAIN = AUDIT / "hash_chain.jsonl"
SEALS = AUDIT / "seals.jsonl"
MANIFEST = AUDIT / "manifest.json"
OTS_DIR = AUDIT / "ots"

SCHEMA = "rokaftf.snapshot/1"
CHAIN_SCHEMA = "rokaftf.hashchain/1"

# 신뢰 구간 경계 (README·대시보드·스냅샷 표기와 동일해야 한다)
PHASE_BOUNDARIES = {
    "Phase 1": ("2026-08-31", "2026-11-11"),
    "Phase 2": ("2026-11-12", "2026-11-25"),
    "Phase 3": ("2026-11-26", "9999-12-31"),
}


# --------------------------------------------------------------------------- #
# 기본 유틸
# --------------------------------------------------------------------------- #
def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_canonical(obj).decode("utf-8"), encoding="utf-8")


def dumps_canonical(obj) -> bytes:
    """바이트 단위로 항상 같은 결과가 나오는 JSON 직렬화(해시 대상)."""
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def phase_of(date: str) -> str:
    for name, (start, end) in PHASE_BOUNDARIES.items():
        if start <= date <= end:
            return name
    return "Phase 3"


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def load_series() -> list[dict]:
    return load_json(SERIES)


def load_portfolio() -> dict:
    return load_json(PORTFOLIO)


def entry_of(portfolio: dict) -> tuple[float, float]:
    h = portfolio["holdings"][0]
    entry_price = float(h["entry_price"])
    entry_index = float(h.get("benchmark_entry_index") or portfolio["fund_metadata"]["benchmark_entry_index"])
    return entry_price, entry_index


# --------------------------------------------------------------------------- #
# 재계산 (tracker.py와 동일한 정의)
# --------------------------------------------------------------------------- #
def risk_metrics(series: list[dict], rf_annual: float = 0.0) -> dict:
    """일간 수익률 기반 기관 지표 — tracker.py `risk_metrics`와 같은 정의."""
    rp = [b["glovis_price"] / a["glovis_price"] - 1 for a, b in zip(series, series[1:])]
    rb = [b["kospi_index"] / a["kospi_index"] - 1 for a, b in zip(series, series[1:])]
    n = len(rp)
    if n < 2:
        return {}
    mp, mb = sum(rp) / n, sum(rb) / n
    cov = sum((x - mp) * (y - mb) for x, y in zip(rp, rb)) / (n - 1)
    var_b = sum((y - mb) ** 2 for y in rb) / (n - 1)
    sd_p, sd_b = st.stdev(rp), st.stdev(rb)
    active = [x - y for x, y in zip(rp, rb)]
    sd_a = st.stdev(active)
    ann = math.sqrt(252)
    return {
        "n_returns": n,
        "beta": cov / var_b,
        "corr": cov / (sd_p * sd_b),
        "te_ann_pct": sd_a * ann * 100,
        "ir_ann": (sum(active) / n) / sd_a * ann,
        "vol_ann_pct": sd_p * ann * 100,
        "sharpe_ann": (mp - rf_annual / 252) / sd_p * ann,
        "avg_daily_active_bp": (sum(active) / n) * 10000,
    }


def recompute_rows(series: list[dict], entry_price: float, entry_index: float) -> list[dict]:
    """원값(종가·지수)만으로 각 행의 파생 수치를 처음부터 다시 계산한다."""
    rows: list[dict] = []
    peak_p = peak_b = None
    for row in series:
        price, index = float(row["glovis_price"]), float(row["kospi_index"])
        peak_p = price if peak_p is None else max(peak_p, price)
        peak_b = index if peak_b is None else max(peak_b, index)
        ret = (price / entry_price - 1) * 100
        bm = (index / entry_index - 1) * 100
        rows.append({
            "date": row["date"],
            "glovis_price": price,
            "kospi_index": index,
            "glovis_rebased": round(price / entry_price * 100, 2),
            "kospi_rebased": round(index / entry_index * 100, 2),
            "glovis_ret_pct": round(ret, 2),
            "kospi_ret_pct": round(bm, 2),
            "alpha_pct": round(ret - bm, 2),
            "glovis_drawdown_pct": round((price / peak_p - 1) * 100, 2),
            "kospi_drawdown_pct": round((index / peak_b - 1) * 100, 2),
        })
    return rows


def peak_trough(rows: list[dict]) -> dict:
    """rows는 recompute_rows 결과(또는 같은 키를 가진 행)를 받는다."""
    peak = max(rows, key=lambda r: r["glovis_price"])
    trough = min(rows, key=lambda r: r["glovis_price"])
    bpeak = max(rows, key=lambda r: r["kospi_index"])
    btrough = min(rows, key=lambda r: r["kospi_index"])
    return {
        "period_high": peak["glovis_price"], "period_high_date": peak["date"],
        "period_low": trough["glovis_price"], "period_low_date": trough["date"],
        "bench_high": bpeak["kospi_index"], "bench_high_date": bpeak["date"],
        "bench_low": btrough["kospi_index"], "bench_low_date": btrough["date"],
        "mdd_pct": min(r["glovis_drawdown_pct"] for r in rows),
        "bench_mdd_pct": min(r["kospi_drawdown_pct"] for r in rows),
    }


def summary(series: list[dict], rows: list[dict], rf_annual: float = 0.0) -> dict:
    """전 구간 요약 지표(원값 재계산)."""
    last = rows[-1]
    m = risk_metrics(series, rf_annual=rf_annual)
    pt = peak_trough(rows)
    return {
        "as_of": last["date"],
        "trading_days": len(rows),
        "price": last["glovis_price"],
        "kospi_index": last["kospi_index"],
        "itd_return_pct": last["glovis_ret_pct"],
        "kospi_return_pct": last["kospi_ret_pct"],
        "alpha_pct": last["alpha_pct"],
        "mdd_pct": pt["mdd_pct"],
        "bench_mdd_pct": pt["bench_mdd_pct"],
        "beta": round(m["beta"], 4),
        "corr": round(m["corr"], 4),
        "sharpe_ann": round(m["sharpe_ann"], 4),
        "ir_ann": round(m["ir_ann"], 4),
        "te_ann_pct": round(m["te_ann_pct"], 4),
        "vol_ann_pct": round(m["vol_ann_pct"], 2),
        **{k: pt[k] for k in ("period_high", "period_high_date", "period_low", "period_low_date",
                              "bench_high", "bench_high_date", "bench_low", "bench_low_date")},
    }


# --------------------------------------------------------------------------- #
# 스냅샷 · 해시 체인
# --------------------------------------------------------------------------- #
def build_snapshot(date: str, series: list[dict], rows: list[dict], portfolio: dict,
                   mode: str, sealed_at: str | None = None) -> dict:
    """해당일 스냅샷 = 원값 + 재계산 지표 + 저장 표기값.

    봉인 시각은 스냅샷 본문에 넣지 않는다(해시 대상에서 제외). 봉인 시각은
    `audit/hash_chain.jsonl`의 항목에 남기며, 같은 날짜를 다시 봉인했을 때
    본문이 같으면 해시도 같도록 하기 위함이다.
    """
    idx = next(i for i, r in enumerate(rows) if r["date"] == date)
    row, calc = series[idx], rows[idx]
    entry_price, entry_index = entry_of(portfolio)
    h = portfolio["holdings"][0]
    return {
        "schema": SCHEMA,
        "fund": portfolio["fund_metadata"]["fund_name"],
        "date": date,
        "phase": phase_of(date),
        "seq": idx + 1,
        "inputs": {
            "entry_price": entry_price,
            "benchmark_entry_index": entry_index,
            "glovis_price": float(row["glovis_price"]),
            "kospi_index": float(row["kospi_index"]),
            "price_source": row.get("price_source"),
            "crosscheck_status": row.get("crosscheck_status"),
            "verified_at": row.get("verified_at"),
        },
        "recomputed": {
            "glovis_rebased": calc["glovis_rebased"],
            "kospi_rebased": calc["kospi_rebased"],
            "glovis_ret_pct": calc["glovis_ret_pct"],
            "kospi_ret_pct": calc["kospi_ret_pct"],
            "alpha_pct": calc["alpha_pct"],
            "glovis_drawdown_pct": calc["glovis_drawdown_pct"],
            "kospi_drawdown_pct": calc["kospi_drawdown_pct"],
        },
        "stored": {
            "glovis_rebased": row.get("glovis_rebased"),
            "kospi_rebased": row.get("kospi_rebased"),
            "glovis_ret_pct": row.get("glovis_ret_pct"),
            "kospi_ret_pct": row.get("kospi_ret_pct"),
            "alpha_pct": row.get("alpha_pct"),
            "glovis_drawdown_pct": row.get("glovis_drawdown_pct"),
            "kospi_drawdown_pct": row.get("kospi_drawdown_pct"),
        },
        "policy": {
            "target_price": h.get("target_price"),
            "stop_loss_price": h.get("stop_loss_price"),
            "upside_left_pct": round((float(h["target_price"]) / float(row["glovis_price"]) - 1) * 100, 2),
            "stop_margin_pct": round((float(row["glovis_price"]) / float(h["stop_loss_price"]) - 1) * 100, 2),
        },
        "seal": {"mode": mode},
    }


def chain_entries() -> list[dict]:
    if not CHAIN.exists():
        return []
    out = []
    for line in CHAIN.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def chain_hash(prev: str, seq: int, date: str, kind: str, snapshot_sha: str) -> str:
    payload = f"{prev}\n{seq}\n{date}\n{kind}\n{snapshot_sha}".encode("utf-8")
    return sha256_bytes(payload)


def seals() -> list[dict]:
    if not SEALS.exists():
        return []
    return [json.loads(l) for l in SEALS.read_text(encoding="utf-8").splitlines() if l.strip()]


def _append_line(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")


def seal_day(date: str, mode: str | None = None, stamp: bool = True,
             portfolio: dict | None = None) -> dict:
    """지정일 스냅샷을 만들고 해시 체인에 잇고(필요 시) OpenTimestamps로 봉인한다.

    멱등: 이미 같은 내용으로 봉인된 날짜는 건너뛴다. 내용이 달라졌으면 개정 항목을
    덧붙인다(과거 봉인 기록은 보존).
    """
    portfolio = portfolio or load_portfolio()
    series = load_series()
    entry_price, entry_index = entry_of(portfolio)
    rows = recompute_rows(series, entry_price, entry_index)
    # 봉인일 == 해당 거래일이면 정규 봉인(daily), 아니면 소급 봉인(retroactive)
    mode = mode or ("daily" if date == dt.date.today().isoformat() else "retroactive")
    if date not in {r["date"] for r in rows}:
        raise ValueError(f"{date} 는 시계열에 없는 거래일이다")

    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    sealed_at = now_iso()
    snap = build_snapshot(date, series, rows, portfolio, mode)
    path = SNAPSHOTS / f"{date}.json"
    new_bytes = dumps_canonical(snap)
    new_sha = sha256_bytes(new_bytes)

    entries = chain_entries()
    same_date = [e for e in entries if e["date"] == date]
    if same_date and same_date[-1]["snapshot_sha256"] == new_sha:
        path.write_bytes(new_bytes)  # 바이트 동일 — 다시 써도 해시 불변
        result = {"date": date, "status": "unchanged", "seq": same_date[-1]["seq"],
                  "chain_sha256": same_date[-1]["chain_sha256"], "snapshot_sha256": new_sha}
        if stamp and not any(r.get("seq") == same_date[-1]["seq"] and r.get("kind") != "genesis"
                             for r in seals()):
            result.update(_stamp_snapshot(date, path, same_date[-1]))
        write_manifest()
        return result

    kind = "revision" if same_date else "seal"
    seq = (entries[-1]["seq"] + 1) if entries else 1
    prev = entries[-1]["chain_sha256"] if entries else "0" * 64
    ch = chain_hash(prev, seq, date, kind, new_sha)
    if kind == "revision":
        snap["seal"]["revises_seq"] = same_date[-1]["seq"]
        snap["seal"]["revises_sha256"] = same_date[-1]["snapshot_sha256"]
        new_bytes = dumps_canonical(snap)
        new_sha = sha256_bytes(new_bytes)
        ch = chain_hash(prev, seq, date, kind, new_sha)
    path.write_bytes(new_bytes)

    entry = {
        "schema": CHAIN_SCHEMA,
        "seq": seq,
        "date": date,
        "kind": kind,
        "phase": phase_of(date),
        "snapshot_sha256": new_sha,
        "prev_chain_sha256": prev,
        "chain_sha256": ch,
        "sealed_at": sealed_at,
    }
    _append_line(CHAIN, entry)

    result = {"date": date, "status": kind, "seq": seq, "chain_sha256": ch,
              "snapshot_sha256": new_sha, "snapshot": str(path.relative_to(REPO))}
    if stamp:
        result.update(_stamp_snapshot(date, path, entry))
    write_manifest()
    return result


def _stamp_snapshot(date: str, path: Path, entry: dict) -> dict:
    """스냅샷 파일을 OpenTimestamps 공개 캘린더에 제출하고 .ots를 저장한다.

    네트워크·캘린더 장애는 정산을 막지 않는다. 실패하면 경고만 남기고
    `python3 tools/timestamp.py stamp audit/snapshots/<date>.json`으로 재시도할 수 있다.
    """
    import timestamp as ots  # 같은 tools/ 디렉터리

    OTS_DIR.mkdir(parents=True, exist_ok=True)
    same_date = [e for e in chain_entries() if e["date"] == date]
    rev = len(same_date) - 1
    out = OTS_DIR / (f"{date}.ots" if rev == 0 else f"{date}-r{entry['seq']}.ots")
    try:
        if out.exists():
            chk = ots.verify_file(path, out)
            if chk["ok"] and chk["digest"] == sha256_file(path):
                info = {"ots": str(out.relative_to(REPO)), "ots_status": "existing"}
            else:
                out.unlink()
                info = ots.stamp_file(path, out)
                info = {"ots": str(out.relative_to(REPO)), **{k: v for k, v in info.items() if k != "ots"}}
        else:
            info = ots.stamp_file(path, out)
            info = {"ots": str(out.relative_to(REPO)), **{k: v for k, v in info.items() if k != "ots"}}
    except Exception as exc:  # noqa: BLE001 — 봉인 실패는 정산을 막지 않는다
        print(f"[audit] ! OpenTimestamps 봉인 실패({date}): {type(exc).__name__}: {exc}")
        print(f"[audit]   재시도: python3 tools/timestamp.py stamp audit/snapshots/{date}.json")
        return {"ots": None, "ots_status": "failed", "ots_error": f"{type(exc).__name__}: {exc}"}

    _append_line(SEALS, {
        "sealed_at": entry["sealed_at"],
        "kind": "snapshot",
        "date": date,
        "seq": entry["seq"],
        "chain_sha256": entry["chain_sha256"],
        "file": str(path.relative_to(REPO)),
        "file_sha256": sha256_file(path),
        "ots": info.get("ots"),
        "ots_calendars": info.get("calendars"),
        "ots_status": info.get("ots_status", "stamped"),
    })
    return info


def upgrade_pending(limit: int = 8, timeout: int = 20) -> list[dict]:
    """아직 블록 확정이 아닌 `.ots` 증명의 승격을 시도한다(정산 파이프라인이 매일 호출).

    성공한 항목은 파일을 덮어써 비트코인 블록 어테스테이션이 추가된다. 실패는 조용히 넘긴다.
    """
    import timestamp as ots

    done: list[dict] = []
    seen: set[str] = set()
    for rec in reversed(seals()):
        path = rec.get("ots")
        if not path or path in seen or rec.get("kind") == "failed":
            continue
        seen.add(path)
        target = REPO / path
        if not target.exists():
            continue
        try:
            res = ots.verify_file(REPO / rec["file"], target)
            if res.get("bitcoin_attested"):
                continue
            up = ots.upgrade_file(target, timeout=timeout)
            if up["upgraded_attestations"]:
                print(f"[audit] OTS 승격: {path} → 비트코인 블록 {up['upgraded_attestations']}건")
                done.append({"ots": path, "upgraded": up["upgraded_attestations"]})
        except Exception as exc:  # noqa: BLE001
            print(f"[audit] OTS 승격 시도 실패({path}): {type(exc).__name__}: {exc}")
        if len(done) >= limit:
            break
    return done


def write_manifest() -> dict:
    entries = chain_entries()
    head = entries[-1] if entries else {}
    manifest = {
        "schema": CHAIN_SCHEMA,
        "generated_at": now_iso(),
        "days": len({e["date"] for e in entries}),
        "entries": len(entries),
        "chain_head_seq": head.get("seq"),
        "chain_head_date": head.get("date"),
        "chain_head_sha256": head.get("chain_sha256"),
        "hash_algorithm": "sha256",
        "chain_rule": "chain_sha256 = sha256(prev_chain_sha256 + '\\n' + seq + '\\n' + date + '\\n' + kind + '\\n' + snapshot_sha256)",
        "snapshot_schema": SCHEMA,
        "snapshot_canonicalization": "json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + '\\n' (UTF-8)",
        "phases": {k: {"start": v[0], "end": v[1]} for k, v in PHASE_BOUNDARIES.items()},
    }
    save_json(MANIFEST, manifest)
    return manifest


def seal_all(stamp: bool = True, upto: str | None = None) -> list[dict]:
    """시계열의 모든 거래일 스냅샷을 만들고 체인에 잇는다(최초 봉인·복구용)."""
    portfolio = load_portfolio()
    series = load_series()
    out = []
    for row in series:
        if upto and row["date"] > upto:
            continue
        out.append(seal_day(row["date"], stamp=stamp, portfolio=portfolio))
    write_manifest()
    return out


def seal_genesis(upto: str, label: str | None = None, stamp: bool = True) -> dict:
    """전 구간 스냅샷을 한 번에 묶는 창세 봉인 파일을 만들어 OTS로 박제한다.

    개별 일별 `.ots` 대신 하나의 파일로 묶어 공개 캘린더 부하를 줄이면서,
    체인 헤드 해시로 모든 거래일 스냅샷을 동시에 커밋한다.
    """
    import timestamp as ots  # 같은 tools/ 디렉터리

    label = label or dt.date.today().isoformat()
    entries = [e for e in chain_entries() if e["date"] <= upto]
    if not entries:
        raise ValueError("봉인할 체인 항목이 없다")
    head = entries[-1]
    latest_by_date: dict[str, dict] = {}
    for e in entries:
        latest_by_date[e["date"]] = e
    genesis = {
        "schema": "rokaftf.genesis/1",
        "fund": load_portfolio()["fund_metadata"]["fund_name"],
        "range": {"start": entries[0]["date"], "end": upto},
        "days": len(latest_by_date),
        "chain_head_seq": head["seq"],
        "chain_head_sha256": head["chain_sha256"],
        "chain_rule": "sha256(prev_chain_sha256 + '\\n' + seq + '\\n' + date + '\\n' + kind + '\\n' + snapshot_sha256)",
        "snapshots": [{"seq": e["seq"], "date": d, "kind": e["kind"],
                       "snapshot_sha256": e["snapshot_sha256"],
                       "chain_sha256": e["chain_sha256"]} for d, e in sorted(latest_by_date.items())],
        "note": ("Phase 3 이전(Phase 1~2) 기록은 Phase 3 개시 시점에 소급 봉인되었다. "
                 "이 파일의 OTS 증명은 위 체인 헤드가 그 시점에 이미 존재했음을 증명하며, "
                 "이후 어떤 스냅샷·시계열이 바뀌면 체인 검증이 실패한다."),
    }
    path = AUDIT / f"genesis-{label}.json"
    save_json(path, genesis)
    record = {"sealed_at": now_iso(), "date": upto, "kind": "genesis",
              "seq": head["seq"], "chain_sha256": head["chain_sha256"],
              "file": str(path.relative_to(REPO)), "file_sha256": sha256_file(path),
              "ots": None, "ots_status": "not_stamped"}
    if stamp:
        out = OTS_DIR / f"genesis-{label}.ots"
        try:
            info = ots.stamp_file(path, out)
            record.update({"ots": str(out.relative_to(REPO)),
                           "ots_calendars": info.get("calendars"), "ots_status": "stamped"})
        except Exception as exc:  # noqa: BLE001
            print(f"[audit] ! 창세 봉인 OTS 실패: {type(exc).__name__}: {exc}")
            record["ots_status"] = "failed"
    _append_line(SEALS, record)
    write_manifest()
    return record


# --------------------------------------------------------------------------- #
# 표기 동기화 (대시보드 · README 수치를 재계산 값으로 맞춘다)
# --------------------------------------------------------------------------- #
def sync_display(portfolio: dict | None = None) -> list[str]:
    """index.html·README.md에 박혀 있는 핵심 수치를 현재 재계산 값으로 교체한다.

    숫자만 바꾸고 문장·서사는 건드리지 않는다. 패턴을 찾지 못하면 경고만 남긴다
    (파일을 손상시키지 않음). 반환값은 변경 내역 문자열 목록.
    """
    import re

    portfolio = portfolio or load_portfolio()
    series = load_series()
    entry_price, entry_index = entry_of(portfolio)
    rows = recompute_rows(series, entry_price, entry_index)
    summ = summary(series, rows)
    h = portfolio["holdings"][0]
    last = rows[-1]
    upside = (float(h["target_price"]) / last["glovis_price"] - 1) * 100
    stop_margin = (last["glovis_price"] / float(h["stop_loss_price"]) - 1) * 100
    changes: list[str] = []

    def sub(text: str, pattern: str, repl: str, label: str) -> str:
        new, n = re.subn(pattern, repl, text, count=1)
        if n:
            if new != text:
                changes.append(label)
            return new
        print(f"[display] ! 패턴 미발견: {label}")
        return text

    if INDEX_HTML.exists():
        html = INDEX_HTML.read_text(encoding="utf-8")
        html = sub(html, r"(누적 Alpha \(초과수익\)</div>\s*<div class=\"kpi-value[^\"]*\">)[^<]+(</div>)",
                   rf"\g<1>{summ['alpha_pct']:+.2f}%p\g<2>", "index.html 누적 Alpha")
        html = sub(html, r"(포트폴리오 수익률</div>\s*<div class=\"kpi-value[^\"]*\">)[^<]+(</div>)",
                   rf"\g<1>{summ['itd_return_pct']:+.2f}%\g<2>", "index.html 수익률")
        html = sub(html, r"(최대 낙폭 \(MDD 방어\)</div>\s*<div class=\"kpi-value[^\"]*\">)[^<]+(</div>)",
                   rf"\g<1>{summ['mdd_pct']:+.2f}%\g<2>", "index.html MDD")
        html = sub(html, r"(Information Ratio / Beta</div>\s*<div class=\"kpi-value[^\"]*\">)[^<]+(</div>)",
                   rf"\g<1>{summ['ir_ann']:.2f}\g<2>", "index.html IR")
        html = sub(html, r"Beta:\s*[0-9.]+\s*·\s*TE\s*[0-9.]+%",
                   f"Beta: {summ['beta']:.2f} · TE {summ['te_ann_pct']:.2f}%", "index.html Beta·TE")
        html = sub(html, r"(<span class=\"val\" style=\"color: var\(--accent-green\);\">)[^<]+(</span>)",
                   rf"\g<1>{summ['alpha_pct']:+.2f}%p\g<2>", "index.html 보유종목 Alpha")
        html = sub(html, r"(<span class=\"lbl\">편입가 / 현재가</span>\s*<span class=\"val\">)[^<]+(</span>)",
                   rf"\g<1>{entry_price / 1000:.1f}k / {last['glovis_price'] / 1000:.1f}k\g<2>",
                   "index.html 편입가/현재가")
        html = sub(html, r"([0-9.]+k \()[+-][0-9.]+%(\))",
                   rf"\g<1>{upside:+.2f}%\g<2>", "index.html 상승여력")
        INDEX_HTML.write_text(html, encoding="utf-8")

    if README.exists():
        md = README.read_text(encoding="utf-8")
        md = sub(md, r"(\*\*누적 수익률 \(ITD\)\*\* \| \*\*)[+-][0-9.]+%",
                 rf"\g<1>{summ['itd_return_pct']:+.2f}%", "README 누적 수익률")
        md = sub(md, r"(\*\*누적 수익률 \(ITD\)\*\* \| \*\*[+-][0-9.]+%\*\* \| \*\*)[+-][0-9.]+%",
                 rf"\g<1>{summ['kospi_return_pct']:+.2f}%", "README KOSPI 수익률")
        md = sub(md, r"(\*\*누적 수익률 \(ITD\)\*\* \| \*\*[+-][0-9.]+%\*\* \| \*\*[+-][0-9.]+%\*\* \| \*\*`)[+-][0-9.]+%p(`\*\*)",
                 rf"\g<1>{summ['alpha_pct']:+.2f}%p\g<2>", "README 누적 Alpha")
        md = sub(md, r"(\*\*최대 낙폭 \(MDD\)\*\* \| \*\*)[+-][0-9.]+%",
                 rf"\g<1>{summ['mdd_pct']:+.2f}%", "README MDD")
        md = sub(md, r"(\*\*최대 낙폭 \(MDD\)\*\* \| \*\*[+-][0-9.]+%\*\* \| \*\*)[+-][0-9.]+%",
                 rf"\g<1>{summ['bench_mdd_pct']:+.2f}%", "README 벤치 MDD")
        md = sub(md, r"(\*\*Information Ratio \(IR\)\*\* \| \*\*)[0-9.]+(\*\*)",
                 rf"\g<1>{summ['ir_ann']:.2f}\g<2>", "README IR")
        md = sub(md, r"(\*\*포트폴리오 Beta\*\* \| \*\*)[0-9.]+(\*\*)",
                 rf"\g<1>{summ['beta']:.2f}\g<2>", "README Beta")
        md = sub(md, r"(\*\*목표가 잔여 상승여력\*\* \| \*\*)[+-][0-9.]+%",
                 rf"\g<1>{upside:+.2f}%", "README 상승여력")
        md = sub(md, r"(\*\*손절선 안전마진\*\* \| \*\*)[+-][0-9.]+%",
                 rf"\g<1>{stop_margin:+.2f}%", "README 손절 안전마진")
        md = sub(md, r"(\*\*최근 갱신일자\*\*: )[0-9]{4}년 [0-9]{1,2}월 [0-9]{1,2}일 \([0-9]+거래일\)",
                 rf"\g<1>{summ['as_of'][:4]}년 {int(summ['as_of'][5:7])}월 {int(summ['as_of'][8:10])}일 ({summ['trading_days']}거래일)",
                 "README 갱신일자")
        README.write_text(md, encoding="utf-8")
    return changes


# --------------------------------------------------------------------------- #
# 체인 검증
# --------------------------------------------------------------------------- #
def verify_chain(check_series: bool = True) -> dict:
    """해시 체인·스냅샷 무결성 검증.

    반환: {"ok": bool, "errors": [...], "warnings": [...], "entries": n, "head": {...}}
    """
    errors: list[str] = []
    warnings: list[str] = []
    entries = chain_entries()
    if not entries:
        return {"ok": False, "errors": ["audit/hash_chain.jsonl 이 비어 있다"], "warnings": [],
                "entries": 0, "head": None}

    prev = "0" * 64
    for i, e in enumerate(entries, start=1):
        if e["seq"] != i:
            errors.append(f"체인 seq 불연속: {i}번째 항목 seq={e['seq']}")
        if e["prev_chain_sha256"] != prev:
            errors.append(f"체인 끊김: seq {e['seq']} prev 불일치")
        want = chain_hash(e["prev_chain_sha256"], e["seq"], e["date"], e["kind"], e["snapshot_sha256"])
        if want != e["chain_sha256"]:
            errors.append(f"체인 해시 불일치: seq {e['seq']} ({e['date']})")
        prev = e["chain_sha256"]

    # 각 날짜의 최신 스냅샷 파일 해시 == 체인의 최신 항목 해시
    latest: dict[str, dict] = {}
    for e in entries:
        latest[e["date"]] = e
    for date, e in sorted(latest.items()):
        path = SNAPSHOTS / f"{date}.json"
        if not path.exists():
            errors.append(f"스냅샷 없음: {date}")
            continue
        actual = sha256_file(path)
        if actual != e["snapshot_sha256"]:
            errors.append(f"스냅샷 변조 의심: {date} 파일 {actual[:12]}… vs 체인 {e['snapshot_sha256'][:12]}…")
            continue
        snap = load_json(path)
        if snap.get("date") != date:
            errors.append(f"스냅샷 날짜 불일치: {date}")
        if snap.get("schema") != SCHEMA:
            errors.append(f"스냅샷 스키마 불일치: {date}")
        for key in ("price_source", "crosscheck_status"):
            if key in snap.get("inputs", {}) and snap["inputs"].get(key) is None:
                warnings.append(f"{date} inputs.{key} 없음")

    # 스냅샷의 재계산 값이 현재 시계열 재계산과 일치하는가(가격 소급 정정 탐지)
    if check_series:
        portfolio = load_portfolio()
        entry_price, entry_index = entry_of(portfolio)
        rows = {r["date"]: r for r in recompute_rows(load_series(), entry_price, entry_index)}
        for date, e in sorted(latest.items()):
            path = SNAPSHOTS / f"{date}.json"
            if not path.exists():
                continue
            snap = load_json(path)
            row = rows.get(date)
            if row is None:
                errors.append(f"{date}: 현재 시계열에 없는 날짜의 스냅샷")
                continue
            for key, want in row.items():
                if key in ("date",):
                    continue
                if key in snap["recomputed"] and abs(float(snap["recomputed"][key]) - float(want)) > 0.01:
                    errors.append(f"{date} {key}: 스냅샷 {snap['recomputed'][key]} vs 재계산 {want}")
            for key in ("glovis_price", "kospi_index"):
                if abs(float(snap["inputs"][key]) - float(row[key])) > 1e-6:
                    errors.append(f"{date} {key}: 스냅샷 {snap['inputs'][key]} vs 시계열 {row[key]}")

    # 매니페스트 (있으면) 헤드 일치
    if MANIFEST.exists():
        man = load_json(MANIFEST)
        head = entries[-1]
        if man.get("chain_head_sha256") != head["chain_sha256"]:
            errors.append("manifest.json 헤드 해시가 체인 최신 항목과 다르다")
        if man.get("entries") != len(entries):
            warnings.append("manifest.json 항목 수가 체인 길이와 다르다(봉인 후 갱신 필요)")

    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "entries": len(entries), "days": len(latest), "head": entries[-1]}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="감사 엔진 — 스냅샷 봉인·해시 체인·표기 동기화")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("seal-all", help="모든 거래일 스냅샷을 만들고 체인에 잇는다")
    a.add_argument("--stamp", action="store_true", help="각 날짜를 OTS로 봉인(기본: 생략)")
    a.add_argument("--upto", default=None)

    d = sub.add_parser("seal", help="지정일 봉인")
    d.add_argument("date")
    d.add_argument("--stamp", action="store_true")
    d.add_argument("--mode", default=None, help="daily | retroactive (기본: 봉인일 기준 자동)")

    g = sub.add_parser("genesis", help="전 구간 창세 봉인 파일 생성(+OTS)")
    g.add_argument("upto", help="여기까지의 거래일을 묶는다")
    g.add_argument("--label", default=None, help="파일 이름에 쓸 봉인 날짜(기본: 오늘)")
    g.add_argument("--no-stamp", action="store_true")

    sub.add_parser("manifest", help="manifest.json 재생성")
    sub.add_parser("sync-display", help="index.html·README 수치를 재계산 값으로 동기화")
    sub.add_parser("verify", help="해시 체인 검증")

    args = p.parse_args()
    if args.cmd == "seal-all":
        out = seal_all(stamp=args.stamp, upto=args.upto)
        print(json.dumps({"sealed": len(out), "head": out[-1] if out else None}, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "seal":
        print(json.dumps(seal_day(args.date, mode=args.mode, stamp=args.stamp), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "genesis":
        print(json.dumps(seal_genesis(args.upto, label=args.label, stamp=not args.no_stamp), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "manifest":
        print(json.dumps(write_manifest(), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "sync-display":
        print(json.dumps({"changed": sync_display()}, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "verify":
        res = verify_chain()
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["ok"] else 1
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
