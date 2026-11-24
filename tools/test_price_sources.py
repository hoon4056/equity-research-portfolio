#!/usr/bin/env python3
"""price_sources 교차검증 로직 테스트(오프라인 픽스처 + 선택적 실네트워크).

    python3 -m unittest tools.test_price_sources -v     (레포 루트에서 실행)

네트워크 테스트는 KRX 종가가 확정된 과거일(2026-11-20)을 사용하며,
응답이 없으면 건너뛴다.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import price_sources as ps  # noqa: E402

D = "2026-11-20"


class CrosscheckRules(unittest.TestCase):
    def test_all_sources_agree_is_confirmed(self):
        q = {"naver": {D: 204500.0}, "daum": {D: 204500.0}, "yahoo": {D: 204500.0}}
        r = ps.crosscheck(D, q)
        self.assertEqual(r["status"], "confirmed")
        self.assertEqual(r["close"], 204500.0)
        self.assertEqual(r["price_source"], "krx")
        self.assertEqual(r["warnings"], [])

    def test_naver_nxt_mismatch_prefers_krx(self):
        # 2026-11-20 실제 상황: 네이버(NXT 포함) 202,500 vs KRX 204,500
        q = {"naver": {D: 202500.0}, "daum": {D: 204500.0}, "yahoo": {D: 204500.0}}
        r = ps.crosscheck(D, q)
        self.assertEqual(r["status"], "krx_priority")
        self.assertEqual(r["close"], 204500.0)
        self.assertTrue(any("naver" in w for w in r["warnings"]))
        self.assertAlmostEqual(r["spread_pct"], 0.9877, places=3)

    def test_regular_sources_disagree_blocks(self):
        q = {"naver": {D: 204500.0}, "daum": {D: 204500.0}, "yahoo": {D: 207000.0}}
        r = ps.crosscheck(D, q)
        self.assertEqual(r["status"], "blocked")
        self.assertIsNone(r["close"])

    def test_large_spread_blocks(self):
        q = {"naver": {D: 190000.0}, "daum": {D: 204500.0}, "yahoo": {D: 204500.0}}
        r = ps.crosscheck(D, q)
        self.assertEqual(r["status"], "blocked")
        self.assertIsNone(r["close"])

    def test_large_spread_exposes_krx_candidate_only(self):
        # 2026-11-24 실제 상황: 네이버(NXT 포함) 200,000 vs KRX 206,500 (괴리 3.25%)
        q = {"naver": {D: 200000.0}, "daum": {D: 206500.0}, "yahoo": {D: 206500.0}}
        r = ps.crosscheck(D, q)
        self.assertEqual(r["status"], "blocked")            # 기본값은 여전히 차단
        self.assertIsNone(r["close"])
        self.assertEqual(r["krx_close"], 206500.0)
        self.assertEqual(set(r["krx_sources"]), {"daum", "yahoo"})

    def test_regular_disagreement_has_no_candidate(self):
        q = {"naver": {D: 190000.0}, "daum": {D: 204500.0}, "yahoo": {D: 207000.0}}
        r = ps.crosscheck(D, q)
        self.assertEqual(r["status"], "blocked")
        self.assertNotIn("krx_close", r)                     # 확인 확정도 불가
        with self.assertRaises(ValueError):
            ps.confirm_blocked(r, "확인")

    def test_confirm_blocked_uses_krx_close_and_keeps_evidence(self):
        q = {"naver": {D: 200000.0}, "daum": {D: 206500.0}, "yahoo": {D: 206500.0}}
        r = ps.crosscheck(D, q)
        c = ps.confirm_blocked(r, "Google Finance 15:30 정규장 종가·코스콤 피드 206,500원 대조")
        self.assertEqual(c["status"], "krx_priority_confirmed")
        self.assertEqual(c["close"], 206500.0)
        self.assertEqual(c["price_source"], "krx")
        self.assertEqual(c["sources"]["naver"], 200000.0)   # 괴리 원값 보존
        self.assertTrue(c["spread_pct"])
        self.assertTrue(any("확인 확정" in w for w in c["warnings"]))

    def test_confirm_blocked_requires_reason(self):
        q = {"naver": {D: 200000.0}, "daum": {D: 206500.0}, "yahoo": {D: 206500.0}}
        with self.assertRaises(ValueError):
            ps.confirm_blocked(ps.crosscheck(D, q), "  ")

    def test_single_source_is_flagged(self):
        q = {"naver": {D: 202500.0}}
        r = ps.crosscheck(D, q)
        self.assertEqual(r["status"], "single_source")
        self.assertEqual(r["close"], 202500.0)
        self.assertTrue(r["warnings"])

    def test_missing_date_blocks(self):
        r = ps.crosscheck(D, {"naver": {}, "daum": {}, "yahoo": {}})
        self.assertEqual(r["status"], "blocked")
        self.assertIsNone(r["close"])

    def test_small_rounding_difference_is_tolerated(self):
        # 통화 단위(1원) 이내 반올림 차이는 불일치로 보지 않는다
        q = {"naver": {D: 204500.0}, "daum": {D: 204500.0}, "yahoo": {D: 204501.0}}
        r = ps.crosscheck(D, q)
        self.assertEqual(r["status"], "confirmed")
        self.assertEqual(r["close"], 204500.0)


@unittest.skipIf(os.environ.get("SKIP_LIVE") == "1", "live network test skipped")
class LiveSources(unittest.TestCase):
    """실제 소스 응답 확인(2026-11-20은 KRX 확정 종가가 공표된 과거일)."""

    def test_2026_11_20_krx_close(self):
        try:
            res = ps.verify("086280", "086280.KS", D)
        except Exception as exc:  # noqa: BLE001 - 네트워크 불가 환경
            self.skipTest(f"network unavailable: {exc}")
        self.assertEqual(res["close"], 204500.0)
        self.assertEqual(res["price_source"], "krx")
        self.assertIn(res["status"], {"confirmed", "krx_priority"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
