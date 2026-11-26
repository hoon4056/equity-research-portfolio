#!/usr/bin/env python3
"""ROKAF Track Record Fund — 제3자 검증 스크립트 (한 번에 전부 재현).

    git clone https://github.com/hoon4056/equity-research-portfolio.git
    cd equity-research-portfolio
    python3 verify.py                # 계산 재현 + 표기 일치 + 스냅샷 해시 체인 + OTS 증명
    python3 verify.py --live-prices  # 최근 종가를 공개 시세 소스와 대조(네트워크 필요)
    python3 verify.py --json         # 결과를 JSON으로(CI 로그용)

검증 항목
  1. 재현   : 원값(일별 종가·KOSPI)만으로 일별/누적 수익률, 벤치마크, 일일·누적 Alpha,
              MDD, Beta, Sharpe, Information Ratio, 추적오차를 다시 계산해 저장값과 대조.
  2. 표기   : 재계산 값이 data/portfolio.json, data/trade_log.csv, index.html(대시보드),
              README.md(팩트시트)의 표기와 0.01%p(2자리 표기) 이내로 일치하는지 확인.
  3. 봉인   : audit/snapshots/*.json 의 SHA-256 과 audit/hash_chain.jsonl 의 해시 체인,
              audit/seals.jsonl 의 OpenTimestamps 증명(.ots)을 검증.
  4. 시세   : --live-prices 일 때만. 마지막 거래일 종가를 다음금융·Yahoo·네이버와 대조.

종료코드: 0 = 전체 통과, 1 = 불일치 발견, 2 = 검증 불가(파일 누락 등)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "tools"))

import audit_engine as eng  # noqa: E402
import timestamp as ots  # noqa: E402

TOL = 0.005          # 2자리 표기 반올림 오차 허용치(0.01%p 미만)
TOL_ABS = 0.011      # 가격·지수 절대 오차


class Report:
    def __init__(self, quiet: bool = False):
        self.sections: list[dict] = []
        self.quiet = quiet
        self.max_dev = 0.0
        self.max_dev_where = ""

    def section(self, name: str) -> dict:
        s = {"name": name, "ok": True, "errors": [], "warnings": [], "details": {}}
        self.sections.append(s)
        return s

    def fail(self, s: dict, msg: str) -> None:
        s["ok"] = False
        s["errors"].append(msg)

    def warn(self, s: dict, msg: str) -> None:
        s["warnings"].append(msg)

    def track(self, dev: float, where: str) -> None:
        if abs(dev) > self.max_dev:
            self.max_dev = abs(dev)
            self.max_dev_where = where

    @property
    def ok(self) -> bool:
        return all(s["ok"] for s in self.sections)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "sections": self.sections,
                "max_deviation": round(self.max_dev, 6), "max_deviation_where": self.max_dev_where,
                "passed": sum(1 for s in self.sections if s["ok"]), "total": len(self.sections)}

    def render(self) -> str:
        lines = []
        for s in self.sections:
            mark = "PASS" if s["ok"] else "FAIL"
            lines.append(f"[{mark}] {s['name']}")
            for k, v in s["details"].items():
                lines.append(f"       · {k}: {v}")
            for e in s["errors"]:
                lines.append(f"       ✗ {e}")
            for w in s["warnings"]:
                lines.append(f"       ! {w}")
        verdict = "PASS — 전 항목 일치" if self.ok else "FAIL — 위 항목을 확인할 것"
        lines.append("")
        lines.append(f"== {verdict} | 최대 편차 {self.max_dev:.4f} ({self.max_dev_where}) ==")
        return "\n".join(lines)


def close(a, b, tol=TOL) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def audit_hash(date: str, code: str, price: float, kospi: float) -> str:
    """trade_log.csv 검증해시 — tracker.py `audit_hash`와 동일 규칙."""
    import hashlib
    return hashlib.sha256(f"{date}|{code}|{price:.0f}|{kospi:.2f}".encode()).hexdigest()[:7]


# --------------------------------------------------------------------------- #
# 1. 재현
# --------------------------------------------------------------------------- #
def check_recompute(rep: Report) -> tuple[list[dict], list[dict], dict, dict]:
    s = rep.section("1. 계산 재현 (원값 → 지표 전부 재계산)")
    series = eng.load_series()
    portfolio = eng.load_portfolio()
    entry_price, entry_index = eng.entry_of(portfolio)
    rows = eng.recompute_rows(series, entry_price, entry_index)
    summ = eng.summary(series, rows)
    s["details"].update({
        "거래일": len(series),
        "기간": f"{series[0]['date']} ~ {series[-1]['date']}",
        "편입 기준가": f"{entry_price:,.0f}원 / KOSPI {entry_index:,.2f}pt",
        "재계산 결과": (f"ITD {summ['itd_return_pct']:+.2f}% · KOSPI {summ['kospi_return_pct']:+.2f}% · "
                    f"Alpha {summ['alpha_pct']:+.2f}%p · MDD {summ['mdd_pct']:.2f}% · Beta {summ['beta']:.4f} · "
                    f"IR {summ['ir_ann']:.4f} · Sharpe {summ['sharpe_ann']:+.4f} · TE {summ['te_ann_pct']:.2f}%"),
    })
    keys = ["glovis_ret_pct", "kospi_ret_pct", "alpha_pct", "glovis_rebased", "kospi_rebased",
            "glovis_drawdown_pct", "kospi_drawdown_pct"]
    for stored, calc in zip(series, rows):
        for k in keys:
            if k not in stored:
                rep.fail(s, f"{stored['date']} 저장값에 {k} 없음")
                continue
            if not close(stored[k], calc[k]):
                rep.fail(s, f"{stored['date']} {k}: 저장 {stored[k]} vs 재계산 {calc[k]}")
            rep.track(float(stored[k]) - float(calc[k]), f"{stored['date']} {k}")
    for a, b in zip(series, series[1:]):
        gap = dt.date.fromisoformat(b["date"]) - dt.date.fromisoformat(a["date"])
        if gap.days <= 0:
            rep.fail(s, f"날짜 정렬 오류: {a['date']} → {b['date']}")
        if gap.days > 5:
            rep.warn(s, f"{a['date']} → {b['date']} 거래일 공백 {gap.days}일")
    return series, rows, summ, portfolio


# --------------------------------------------------------------------------- #
# 2. 표기 일치 (요약 JSON · 거래로그 · 대시보드 · README)
# --------------------------------------------------------------------------- #
def check_display(rep: Report, series: list[dict], rows: list[dict], summ: dict, portfolio: dict) -> None:
    s = rep.section("2. 표기 수치 일치 (portfolio.json · trade_log.csv · index.html · README.md)")
    meta, h = portfolio["fund_metadata"], portfolio["holdings"][0]
    last = rows[-1]
    upside = round((float(h["target_price"]) / last["glovis_price"] - 1) * 100, 2)
    stop_margin = round((last["glovis_price"] / float(h["stop_loss_price"]) - 1) * 100, 2)

    pairs = [
        ("portfolio.json last_updated", meta.get("last_updated"), summ["as_of"], 0),
        ("portfolio.json portfolio_return_pct", meta.get("portfolio_return_pct"), summ["itd_return_pct"], TOL),
        ("portfolio.json benchmark_return_pct", meta.get("benchmark_return_pct"), summ["kospi_return_pct"], TOL),
        ("portfolio.json cumulative_alpha_pct", meta.get("cumulative_alpha_pct"), summ["alpha_pct"], TOL),
        ("portfolio.json portfolio_mdd_pct", meta.get("portfolio_mdd_pct"), summ["mdd_pct"], TOL),
        ("portfolio.json benchmark_mdd_pct", meta.get("benchmark_mdd_pct"), summ["bench_mdd_pct"], TOL),
        ("portfolio.json portfolio_beta", meta.get("portfolio_beta"), round(summ["beta"], 2), 0.0001),
        ("portfolio.json information_ratio", meta.get("information_ratio"), round(summ["ir_ann"], 2), 0.0001),
        ("portfolio.json sharpe_ratio", meta.get("sharpe_ratio"), round(summ["sharpe_ann"], 2), 0.0001),
        ("portfolio.json tracking_error_pct", meta.get("tracking_error_pct"), round(summ["te_ann_pct"], 2), 0.0001),
        ("portfolio.json benchmark_current_index", meta.get("benchmark_current_index"), summ["kospi_index"], TOL_ABS),
        ("holdings current_price", h.get("current_price"), last["glovis_price"], TOL_ABS),
        ("holdings return_pct", h.get("return_pct"), last["glovis_ret_pct"], TOL),
        ("holdings alpha_pct", h.get("alpha_pct"), last["alpha_pct"], TOL),
        ("holdings upside_left_pct", h.get("upside_left_pct"), upside, TOL),
        ("holdings stop_margin_pct", h.get("stop_margin_pct"), stop_margin, TOL),
        ("holdings period_mdd_pct", h.get("period_mdd_pct"), summ["mdd_pct"], TOL),
    ]
    for name, got, want, tol in pairs:
        if tol == 0:
            if got != want:
                rep.fail(s, f"{name}: {got} vs 재계산 {want}")
        elif not close(got, want, tol):
            rep.fail(s, f"{name}: {got} vs 재계산 {want}")
        else:
            try:
                rep.track(float(got) - float(want), name)
            except (TypeError, ValueError):
                pass

    # trade_log.csv
    with eng.TRADE_LOG.open(encoding="utf-8") as fh:
        tl = list(csv.DictReader(fh))[0]
    tl_pairs = [
        ("trade_log 현재가", tl["현재가(원)"], last["glovis_price"], TOL_ABS),
        ("trade_log 수익률", tl["수익률(%)"], last["glovis_ret_pct"], TOL),
        ("trade_log KOSPI수익률", tl["KOSPI수익률(%)"], last["kospi_ret_pct"], TOL),
        ("trade_log Alpha", tl["Alpha(%p)"], last["alpha_pct"], TOL),
        ("trade_log KOSPI현재가", tl["KOSPI현재가"], last["kospi_index"], TOL_ABS),
    ]
    for name, got, want, tol in tl_pairs:
        if not close(got, want, tol):
            rep.fail(s, f"{name}: {got} vs 재계산 {want}")
    want_hash = audit_hash(last["date"], h["code"], last["glovis_price"], last["kospi_index"])
    if tl["검증해시"] != want_hash:
        rep.fail(s, f"trade_log 검증해시: {tl['검증해시']} vs {want_hash}")

    # index.html 대시보드 KPI
    html = eng.INDEX_HTML.read_text(encoding="utf-8")
    expect = {
        "대시보드 누적 Alpha": (rf"누적 Alpha \(초과수익\)</div>\s*<div class=\"kpi-value[^\"]*\">([^<]+)</div>",
                            f"{summ['alpha_pct']:+.2f}%p"),
        "대시보드 수익률": (rf"포트폴리오 수익률</div>\s*<div class=\"kpi-value[^\"]*\">([^<]+)</div>",
                        f"{summ['itd_return_pct']:+.2f}%"),
        "대시보드 MDD": (rf"최대 낙폭 \(MDD 방어\)</div>\s*<div class=\"kpi-value[^\"]*\">([^<]+)</div>",
                       f"{summ['mdd_pct']:+.2f}%"),
        "대시보드 IR": (rf"Information Ratio / Beta</div>\s*<div class=\"kpi-value[^\"]*\">([^<]+)</div>",
                      f"{round(summ['ir_ann'], 2):.2f}"),
        "대시보드 Beta": (r"Beta:\s*([0-9.]+)", f"{round(summ['beta'], 2):.2f}"),
        "대시보드 TE": (r"TE\s*([0-9.]+)%", f"{round(summ['te_ann_pct'], 2):.2f}"),
        "대시보드 상승여력": (r"[0-9.]+k \(([+-][0-9.]+%)\)", f"{upside:+.2f}%"),
    }
    for name, (pat, want) in expect.items():
        m = re.search(pat, html)
        if not m:
            rep.fail(s, f"{name}: 대시보드에서 해당 표기를 찾지 못함")
            continue
        got = m.group(1).strip()
        if got != want:
            rep.fail(s, f"{name}: 대시보드 {got} vs 재계산 {want}")

    # README 팩트시트
    readme = eng.README.read_text(encoding="utf-8")
    readme_expect = {
        "README 누적 수익률·알파": (rf"\*\*누적 수익률 \(ITD\)\*\* \| \*\*([+-][0-9.]+%)\*\* \| \*\*([+-][0-9.]+%)\*\* \| \*\*`([+-][0-9.]+%p)`\*\*",
                            [f"{summ['itd_return_pct']:+.2f}%", f"{summ['kospi_return_pct']:+.2f}%",
                             f"{summ['alpha_pct']:+.2f}%p"]),
        "README MDD": (r"\*\*최대 낙폭 \(MDD\)\*\* \| \*\*([+-][0-9.]+%)\*\* \| \*\*([+-][0-9.]+%)\*\*",
                       [f"{summ['mdd_pct']:+.2f}%", f"{summ['bench_mdd_pct']:+.2f}%"]),
        "README IR": (r"\*\*Information Ratio \(IR\)\*\* \| \*\*([0-9.]+)\*\*",
                      [f"{round(summ['ir_ann'], 2):.2f}"]),
        "README Beta": (r"\*\*포트폴리오 Beta\*\* \| \*\*([0-9.]+)\*\*",
                        [f"{round(summ['beta'], 2):.2f}"]),
        "README 상승여력": (r"\*\*목표가 잔여 상승여력\*\* \| \*\*([+-][0-9.]+%)\*\*",
                         [f"{upside:+.2f}%"]),
    }
    for name, (pat, want) in readme_expect.items():
        m = re.search(pat, readme)
        if not m:
            rep.fail(s, f"{name}: README에서 해당 표기를 찾지 못함")
            continue
        for got, exp in zip(m.groups(), want):
            if got.strip() != exp:
                rep.fail(s, f"{name}: README {got} vs 재계산 {exp}")
    m = re.search(r"\*\*최근 갱신일자\*\*: ([0-9]{4})년 ([0-9]{1,2})월 ([0-9]{1,2})일 \((\d+)거래일\)", readme)
    if m:
        got_date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        if got_date != summ["as_of"]:
            rep.fail(s, f"README 최근 갱신일자: {got_date} vs {summ['as_of']}")
        if int(m.group(4)) != summ["trading_days"]:
            rep.fail(s, f"README 거래일수: {m.group(4)} vs {summ['trading_days']}")
    else:
        rep.fail(s, "README 최근 갱신일자 표기를 찾지 못함")

    s["details"]["검증 기준일"] = f"{summ['as_of']} · {summ['trading_days']}거래일"


# --------------------------------------------------------------------------- #
# 3. 스냅샷 · 해시 체인 · OTS
# --------------------------------------------------------------------------- #
def check_seals(rep: Report, upgrade: bool = False) -> None:
    s = rep.section("3. 스냅샷 해시 체인 (audit/hash_chain.jsonl)")
    chain = eng.verify_chain(check_series=True)
    for e in chain["errors"]:
        rep.fail(s, e)
    for w in chain["warnings"]:
        rep.warn(s, w)
    head = chain.get("head") or {}
    s["details"].update({
        "체인 항목": f"{chain['entries']}건 / 거래일 {chain.get('days', 0)}일",
        "체인 헤드": f"seq {head.get('seq')} · {head.get('date')} · {str(head.get('chain_sha256'))[:16]}…",
        "최근 봉인": head.get("sealed_at"),
    })

    t = rep.section("4. OpenTimestamps 블록체인 타임스탬프 (audit/ots)")
    records = eng.seals()
    if not records:
        rep.fail(t, "audit/seals.jsonl 이 비어 있다")
        return
    pending = 0
    attested = 0
    for rec in records:
        if not rec.get("ots"):
            rep.warn(t, f"{rec['date']} OTS 증명 없음(봉인 실패) — 재시도: python3 tools/timestamp.py stamp {rec['file']}")
            continue
        path = REPO / rec["file"]
        ots_path = REPO / rec["ots"]
        if not path.exists() or not ots_path.exists():
            rep.fail(t, f"{rec['date']} 증명 파일 누락: {rec['ots']}")
            continue
        res = ots.verify_file(path, ots_path)
        if not res["ok"]:
            rep.fail(t, f"{rec['date']} 증명 불일치: {'; '.join(res['errors'])}")
            continue
        if eng.sha256_file(path) != rec.get("file_sha256"):
            rep.fail(t, f"{rec['date']} 봉인 이후 파일 변경: {rec['file']}")
        kinds = {a["kind"] for a in res["attestations"]}
        if "block" in kinds:
            attested += 1
            heights = [a["block_height"] for a in res["attestations"] if a["kind"] == "block"]
            s_extra = f"비트코인 블록 {heights}"
        else:
            pending += 1
            s_extra = "캘린더 접수(pending) — 블록 확정 대기"
        if upgrade and not res["bitcoin_attested"]:
            up = ots.upgrade_file(ots_path)
            s_extra += f" / 승격 시도: +{up['upgraded_attestations']}건"
            if up["upgraded_attestations"]:
                res = ots.verify_file(path, ots_path)
    t["details"].update({
        "봉인 기록": f"{len(records)}건 (비트코인 블록 확정 {attested} · 캘린더 접수 {pending})",
        "캘린더": "a/b.pool.opentimestamps.org, ots.btc.catallaxy.com",
    })
    if pending:
        rep.warn(t, f"{pending}건은 아직 캘린더 접수 단계다. 비트코인 블록 확정 후 "
                    "`python3 tools/timestamp.py upgrade audit/ots/*.ots`로 승격되며, "
                    "증명 자체는 제출 시점 이후 무변조를 이미 보장한다(접수 사실은 각 캘린더가 보관).")


# --------------------------------------------------------------------------- #
# 4. 라이브 시세 대조
# --------------------------------------------------------------------------- #
def check_live(rep: Report, series: list[dict], portfolio: dict) -> None:
    s = rep.section("5. 공개 시세 대조 (--live-prices)")
    try:
        import price_sources
    except Exception as exc:  # noqa: BLE001
        rep.fail(s, f"tools/price_sources.py 로드 실패: {exc}")
        return
    h = portfolio["holdings"][0]
    date = series[-1]["date"]
    price = float(series[-1]["glovis_price"])
    kospi = float(series[-1]["kospi_index"])
    try:
        data = price_sources.collect(h["code"], h.get("ticker") or f"{h['code']}.KS",
                                     dt.date.fromisoformat(date) - dt.timedelta(days=12),
                                     dt.date.fromisoformat(date))
    except Exception as exc:  # noqa: BLE001
        rep.fail(s, f"시세 조회 실패: {type(exc).__name__}: {exc}")
        return
    quotes = data.get("quotes", {})
    s["details"]["조회 기준일"] = date
    seen = {}
    for src, values in sorted(quotes.items()):
        if date in values:
            seen[src] = values[date]
    if not seen:
        rep.warn(s, f"{date} 종가가 어떤 소스에도 없다(휴장일이거나 소스 지연). "
                    "각 소스 최근값: " + (", ".join(f"{k}={max(v)}" for k, v in quotes.items() if v) or "없음"))
        return
    s["details"]["소스별 종가"] = ", ".join(f"{k} {v:,.0f}원" for k, v in seen.items())
    s["details"]["기록 종가"] = f"{date} {price:,.0f}원 (KOSPI {kospi:,.2f}pt)"
    for src, v in seen.items():
        dev = abs(v - price) / price * 100
        rep.track(dev, f"live {src}")
        if dev > 3.0:
            rep.fail(s, f"{src} {v:,.0f}원 vs 기록 {price:,.0f}원 — 괴리 {dev:.2f}% (3% 초과)")
        elif dev > 0.5:
            rep.warn(s, f"{src} {v:,.0f}원 vs 기록 {price:,.0f}원 — 괴리 {dev:.2f}% "
                        "(대체거래소 시간외 체결가 혼입 가능)")


# --------------------------------------------------------------------------- #
def main() -> int:
    p = argparse.ArgumentParser(description="ROKAF Track Record Fund 제3자 검증")
    p.add_argument("--live-prices", action="store_true", help="최근 종가를 공개 시세 소스와 대조")
    p.add_argument("--upgrade-ots", action="store_true", help="pending 증명을 블록 확정으로 승격 시도")
    p.add_argument("--json", action="store_true", help="결과를 JSON으로 출력")
    p.add_argument("--quiet", action="store_true", help="PASS 섹션 상세 생략")
    args = p.parse_args()

    try:
        rep = Report(quiet=args.quiet)
        series, rows, summ, portfolio = check_recompute(rep)
        check_display(rep, series, rows, summ, portfolio)
        check_seals(rep, upgrade=args.upgrade_ots)
        if args.live_prices:
            check_live(rep, series, portfolio)
    except FileNotFoundError as exc:
        print(f"[verify] 검증 불가 — 파일 누락: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"[verify] 검증 불가 — {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(rep.render())
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
