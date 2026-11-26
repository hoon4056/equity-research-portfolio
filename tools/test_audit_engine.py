#!/usr/bin/env python3
"""감사 엔진·OpenTimestamps 모듈 테스트 (전부 오프라인).

    python3 -m unittest tools.test_audit_engine -v      (레포 루트에서 실행)

검증하는 것
  * recompute_rows 가 저장된 시계열과 2자리까지 일치하는가
  * summary 가 data/portfolio.json 표기와 일치하는가
  * 커밋된 audit/ 의 해시 체인·스냅샷이 무결한가
  * 스냅샷 1바이트 변조를 체인 검증이 잡아내는가
  * .ots 생성·파싱·변조 탐지가 동작하는가(네트워크 없이 합성 트리로)
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import audit_engine as eng  # noqa: E402
import timestamp as ots  # noqa: E402


class RecomputeTest(unittest.TestCase):
    def setUp(self):
        self.portfolio = eng.load_portfolio()
        self.series = eng.load_series()
        self.entry_price, self.entry_index = eng.entry_of(self.portfolio)
        self.rows = eng.recompute_rows(self.series, self.entry_price, self.entry_index)

    def test_rows_match_stored(self):
        keys = ["glovis_ret_pct", "kospi_ret_pct", "alpha_pct", "glovis_rebased",
                "kospi_rebased", "glovis_drawdown_pct", "kospi_drawdown_pct"]
        for stored, calc in zip(self.series, self.rows):
            for k in keys:
                self.assertAlmostEqual(float(stored[k]), float(calc[k]), delta=0.005,
                                       msg=f"{stored['date']} {k}")

    def test_first_row_is_baseline(self):
        first = self.rows[0]
        self.assertEqual(first["glovis_ret_pct"], 0.0)
        self.assertEqual(first["kospi_ret_pct"], 0.0)
        self.assertEqual(first["alpha_pct"], 0.0)

    def test_summary_matches_portfolio_json(self):
        s = eng.summary(self.series, self.rows)
        meta = self.portfolio["fund_metadata"]
        self.assertAlmostEqual(meta["portfolio_return_pct"], s["itd_return_pct"], delta=0.005)
        self.assertAlmostEqual(meta["benchmark_return_pct"], s["kospi_return_pct"], delta=0.005)
        self.assertAlmostEqual(meta["cumulative_alpha_pct"], s["alpha_pct"], delta=0.005)
        self.assertAlmostEqual(meta["portfolio_mdd_pct"], s["mdd_pct"], delta=0.005)
        self.assertAlmostEqual(meta["benchmark_mdd_pct"], s["bench_mdd_pct"], delta=0.005)
        self.assertAlmostEqual(meta["information_ratio"], round(s["ir_ann"], 2), delta=1e-9)
        self.assertAlmostEqual(meta["portfolio_beta"], round(s["beta"], 2), delta=1e-9)
        self.assertAlmostEqual(meta["tracking_error_pct"], round(s["te_ann_pct"], 2), delta=1e-9)

    def test_mdd_is_min_of_drawdowns(self):
        s = eng.summary(self.series, self.rows)
        self.assertEqual(s["mdd_pct"], min(r["glovis_drawdown_pct"] for r in self.rows))
        self.assertLessEqual(s["mdd_pct"], 0.0)


class ChainTest(unittest.TestCase):
    def test_committed_audit_is_intact(self):
        res = eng.verify_chain(check_series=True)
        self.assertTrue(res["ok"], msg="; ".join(res["errors"]))
        self.assertGreaterEqual(res["entries"], len(eng.load_series()))

    def test_tampered_snapshot_breaks_chain(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            # 최소 2일짜리 체인을 임시 디렉터리에 만든다
            snap_dir = tmp / "snapshots"
            snap_dir.mkdir(parents=True)
            chain = tmp / "hash_chain.jsonl"
            prev = "0" * 64
            shas = []
            for i, d in enumerate(["2026-01-02", "2026-01-05"], start=1):
                body = eng.dumps_canonical({"date": d, "schema": eng.SCHEMA, "n": i})
                (snap_dir / f"{d}.json").write_bytes(body)
                sha = eng.sha256_bytes(body)
                ch = eng.chain_hash(prev, i, d, "seal", sha)
                chain.write_text(chain.read_text() + json.dumps(
                    {"seq": i, "date": d, "kind": "seal", "snapshot_sha256": sha,
                     "prev_chain_sha256": prev, "chain_sha256": ch}, ensure_ascii=False) + "\n"
                    if chain.exists() else json.dumps(
                    {"seq": i, "date": d, "kind": "seal", "snapshot_sha256": sha,
                     "prev_chain_sha256": prev, "chain_sha256": ch}, ensure_ascii=False) + "\n",
                    encoding="utf-8")
                shas.append(sha)
                prev = ch

            old = (eng.SNAPSHOTS, eng.CHAIN, eng.MANIFEST)
            eng.SNAPSHOTS, eng.CHAIN, eng.MANIFEST = snap_dir, chain, tmp / "manifest.json"
            try:
                self.assertTrue(eng.verify_chain(check_series=False)["ok"])
                (snap_dir / "2026-01-02.json").write_bytes(
                    eng.dumps_canonical({"date": "2026-01-02", "schema": eng.SCHEMA, "n": 9}))
                res = eng.verify_chain(check_series=False)
                self.assertFalse(res["ok"])
                self.assertTrue(any("변조" in e or "체인" in e for e in res["errors"]))
            finally:
                eng.SNAPSHOTS, eng.CHAIN, eng.MANIFEST = old
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TimestampTest(unittest.TestCase):
    def _tree(self, digest: bytes):
        root = ots.Node(digest)
        child = ots.Node(ots.apply_op(0xF0, b"nonce-1", digest))
        child.attestations.add((ots.ATT_PENDING, ots._write_varbytes(b"https://example.org")))
        root.children[(0xF0, b"nonce-1")] = child
        return root

    def test_roundtrip_and_verify(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            f = tmp / "snapshot.json"
            f.write_bytes(eng.dumps_canonical({"hello": "world"}))
            digest = ots.hashlib.sha256(f.read_bytes()).digest()
            ots.write_ots(tmp / "snapshot.json.ots", digest, self._tree(digest))
            res = ots.verify_file(f, tmp / "snapshot.json.ots")
            self.assertTrue(res["ok"], msg=str(res["errors"]))
            self.assertEqual(res["digest"], digest.hex())
            self.assertEqual(res["pending"], ["https://example.org"])
            self.assertFalse(res["bitcoin_attested"])

            # 재직렬화 결과가 동일해야 한다(직렬화기 회귀 방지)
            raw = (tmp / "snapshot.json.ots").read_bytes()
            tree = ots.read_ots(tmp / "snapshot.json.ots")["tree"]
            self.assertEqual(raw, ots.MAGIC + bytes([1, 0x08]) + digest + ots._serialize(tree))

            # 파일 변조는 잡아야 한다
            f.write_bytes(eng.dumps_canonical({"hello": "tampered"}))
            self.assertFalse(ots.verify_file(f, tmp / "snapshot.json.ots")["ok"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_bitcoin_attestation_parsed(self):
        height = 920000
        payload = ots._write_varuint(height)
        self.assertEqual(ots.describe_attestation(ots.ATT_BITCOIN, payload),
                         {"kind": "block", "chain": "bitcoin", "block_height": height})


if __name__ == "__main__":
    unittest.main()
