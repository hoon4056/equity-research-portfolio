#!/usr/bin/env python3
"""ROKAF Track Record Fund — 종가 다중 소스 교차검증 모듈.

배경
  정산 엔진이 네이버 금융 일별시세 한 곳만 신뢰했고, 2026-11-20 정산에서
  네이버 종가(202,500원, -0.49%)와 거래소 공표 종가(204,500원, +0.49%)가
  방향까지 반대로 갈렸다. 원인은 네이버·다음금융의 "종가"가 대체거래소(NXT)
  시간외 마지막 체결가를 포함하는 반면, 거래소 공표 종가는 정규장(15:30)
  종가이기 때문이다.

원칙
  1. 종가는 최소 2개 이상 독립 소스에서 받아 교차검증한다.
  2. 거래소(KRX) 정규장 공표 종가 계열(다음금융·Yahoo Finance)이 일치하면
     그 값을 확정치로 채택한다(정산·평가의 기준 소스).
  3. 네이버 일별시세는 NXT 시간외 포함 계열로 보고, 괴리가 있으면 숨기지 않고
     기록·경고한다. 괴리 폭이 비정상(기본 3%)이면 정산을 차단한다.
  4. 소스가 1개뿐이면 정산은 하되 상태를 '단일소스'로 표시해 감사로그에 남긴다.

CLI
  python3 tools/price_sources.py --code 086280 --date 2026-11-20
      종료코드 0 = 확정(일치 또는 KRX 우선 확정), 2 = 차단(데이터 이상)
  python3 tools/price_sources.py --code 086280 --date 2026-11-20 --json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 정규장 공표 종가 계열(신뢰 1군) / NXT 시간외 포함 계열(참고 2군)
REGULAR_SOURCES = ("daum", "yahoo")
REFERENCE_SOURCES = ("naver",)
ALL_SOURCES = REGULAR_SOURCES + REFERENCE_SOURCES
MAX_SPREAD_PCT = 3.0  # 이보다 벌어지면 시세 자체가 이상 → 정산 차단


def _get(url: str, referer: str | None = None, timeout: int = 25, retries: int = 2) -> str:
    headers = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    if referer:
        headers["Referer"] = referer
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001 - 일시 오류(429 등)는 짧게 재시도
            last = exc
            if attempt + 1 < retries:
                time.sleep(1.5)
    raise last  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# 소스별 일별 종가
# --------------------------------------------------------------------------- #
def fetch_naver(symbol: str, start: dt.date, end: dt.date) -> dict[str, float]:
    """네이버 금융 일별시세. (NXT 시간외 마지막 체결가 포함 가능)"""
    url = ("https://api.finance.naver.com/siseJson.naver?"
           f"symbol={urllib.parse.quote(symbol)}&requestType=1"
           f"&startTime={start:%Y%m%d}&endTime={end:%Y%m%d}&timeframe=day")
    raw = _get(url, referer="https://finance.naver.com/")
    out: dict[str, float] = {}
    for day, close in re.findall(r'\["(\d{8})",\s*[\d.]+,\s*[\d.]+,\s*[\d.]+,\s*([\d.]+)', raw):
        out[f"{day[:4]}-{day[4:6]}-{day[6:]}"] = float(close)
    return out


def fetch_daum(symbol: str, pages: int = 3) -> dict[str, float]:
    """다음금융 일별 시세(KRX 정규장 종가 계열). symbol 예: 086280"""
    code = symbol if symbol.startswith("A") else f"A{symbol}"
    out: dict[str, float] = {}
    for page in range(1, pages + 1):
        url = (f"https://finance.daum.net/api/quote/{code}/days?"
               f"symbol={code}&page={page}&perPage=60&pagination=true")
        data = json.loads(_get(url, referer=f"https://finance.daum.net/quotes/{code}"))
        rows = data.get("data") or []
        if not rows:
            break
        for row in rows:
            out[row["date"][:10]] = float(row["tradePrice"])
    return out


def fetch_yahoo(ticker: str, rng: str = "6mo") -> dict[str, float]:
    """Yahoo Finance 일별 종가(KRX 정규장 종가 계열). ticker 예: 086280.KS"""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(ticker)}?range={rng}&interval=1d")
    data = json.loads(_get(url))
    result = data["chart"]["result"][0]
    kst = dt.timezone(dt.timedelta(hours=9))
    out: dict[str, float] = {}
    for ts, close in zip(result["timestamp"], result["indicators"]["quote"][0]["close"]):
        if close is None:
            continue
        out[dt.datetime.fromtimestamp(ts, kst).date().isoformat()] = round(float(close), 2)
    return out


def collect(symbol: str, ticker: str, start: dt.date, end: dt.date) -> dict[str, dict[str, float]]:
    """모든 소스에서 받은 {source: {date: close}}. 실패한 소스는 errors에 남기고 제외."""
    sources: dict[str, dict[str, float]] = {}
    errors: dict[str, str] = {}
    try:
        sources["naver"] = fetch_naver(symbol, start, end)
    except Exception as exc:  # noqa: BLE001 - 소스 장애는 치명적이지 않다
        errors["naver"] = f"{type(exc).__name__}: {exc}"
    try:
        sources["daum"] = fetch_daum(symbol)
    except Exception as exc:  # noqa: BLE001
        errors["daum"] = f"{type(exc).__name__}: {exc}"
    try:
        sources["yahoo"] = fetch_yahoo(ticker)
    except Exception as exc:  # noqa: BLE001
        errors["yahoo"] = f"{type(exc).__name__}: {exc}"
    return {"quotes": sources, "errors": errors}


# --------------------------------------------------------------------------- #
# 교차검증
# --------------------------------------------------------------------------- #
def crosscheck(date: str, quotes: dict[str, dict[str, float]],
               tolerance_pct: float = 0.05, max_spread_pct: float = MAX_SPREAD_PCT) -> dict:
    """지정일 종가를 소스 간 비교해 확정치와 상태를 돌려준다.

    반환: {date, close, price_source, status, sources, spread_pct, warnings}
      status: confirmed  — 모든 소스 일치
              krx_priority — 정규장 계열 2개 일치, 참고 소스와 괴리(KRX 채택)
              single_source — 소스 1개뿐(정산은 하되 표시)
              blocked      — 정규장 계열 불일치 또는 괴리 과다(정산 차단)
    """
    got = {src: q[date] for src, q in quotes.items() if date in q}
    warnings: list[str] = []
    if not got:
        return {"date": date, "close": None, "price_source": None, "status": "blocked",
                "sources": {}, "spread_pct": None,
                "warnings": ["모든 소스에서 해당일 종가를 받지 못했습니다."]}

    regular = {s: v for s, v in got.items() if s in REGULAR_SOURCES}
    closes = sorted(got.values())
    spread_pct = (closes[-1] - closes[0]) / closes[0] * 100 if closes[0] else None

    def agree(a: float, b: float) -> bool:
        return abs(a - b) <= max(abs(b) * tolerance_pct / 100, 1.0)

    if len(got) == 1:
        src, close = next(iter(got.items()))
        warnings.append(f"단일 소스({src})만 응답 — 교차검증 미완료, 감사로그에 그대로 남깁니다.")
        return {"date": date, "close": close, "price_source": src, "status": "single_source",
                "sources": got, "spread_pct": 0.0, "warnings": warnings}

    if spread_pct is not None and spread_pct > max_spread_pct:
        warnings.append(f"소스 간 괴리 {spread_pct:.2f}% > 허용 {max_spread_pct}% — 시세 이상, 정산 차단.")
        return {"date": date, "close": None, "price_source": None, "status": "blocked",
                "sources": got, "spread_pct": round(spread_pct, 4), "warnings": warnings}

    if len(regular) >= 2:
        vals = list(regular.values())
        if not agree(vals[0], vals[1]):
            warnings.append("정규장 계열 소스(다음금융·Yahoo)가 서로 불일치 — 확정 불가, 정산 차단.")
            return {"date": date, "close": None, "price_source": None, "status": "blocked",
                    "sources": got, "spread_pct": round(spread_pct or 0, 4), "warnings": warnings}
        krx_close = vals[0]
        others = {s: v for s, v in got.items() if s not in regular}
        if not others:
            return {"date": date, "close": krx_close, "price_source": "krx",
                    "status": "confirmed", "sources": got, "spread_pct": round(spread_pct or 0, 4),
                    "warnings": warnings}
        for src, val in others.items():
            if not agree(val, krx_close):
                diff = val - krx_close
                warnings.append(
                    f"{src} {val:,.0f}원 vs KRX {krx_close:,.0f}원 (괴리 {diff:+,.0f}원, "
                    f"{diff / krx_close * 100:+.2f}%) — KRX 정규장 종가 채택"
                    f"({'NXT 시간외 체결가 포함 추정' if src == 'naver' else '참고 소스 차이'}).")
        status = "krx_priority" if warnings else "confirmed"
        return {"date": date, "close": krx_close, "price_source": "krx", "status": status,
                "sources": got, "spread_pct": round(spread_pct or 0, 4), "warnings": warnings}

    # 정규장 계열이 1개 이하 → 남은 소스 중 다수값 채택
    counts: dict[float, int] = {}
    for val in got.values():
        key = round(val, 2)
        counts[key] = counts.get(key, 0) + 1
    best = max(counts.items(), key=lambda kv: kv[1])[0]
    warnings.append("정규장 계열 소스 부족 — 가용 소스 다수값으로 대체했습니다.")
    return {"date": date, "close": best, "price_source": "fallback", "status": "fallback",
            "sources": got, "spread_pct": round(spread_pct or 0, 4), "warnings": warnings}


def verify(code: str, ticker: str, date: str, lookback_days: int = 20) -> dict:
    """단일 종목·단일일 종가 교차검증(편의 함수)."""
    d = dt.date.fromisoformat(date)
    data = collect(code, ticker, d - dt.timedelta(days=lookback_days), d)
    result = crosscheck(date, data["quotes"])
    result["fetch_errors"] = data["errors"]
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="종가 다중 소스 교차검증")
    ap.add_argument("--code", required=True, help="종목코드(예: 086280)")
    ap.add_argument("--ticker", default=None, help="Yahoo 티커(기본: {code}.KS)")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = ap.parse_args()
    ticker = args.ticker or f"{args.code}.KS"
    res = verify(args.code, ticker, args.date)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(f"[crosscheck] {args.code} {args.date}")
        for src, val in sorted(res["sources"].items()):
            print(f"  {src:<6} {val:>12,.0f}")
        if res["close"] is None:
            print("  확정 불가")
        else:
            print(f"  확정 종가 {res['close']:,.0f}원 ({res['price_source']})")
        print(f"  상태 {res['status']} · 괴리 {res['spread_pct']}%")
        for w in res["warnings"]:
            print(f"  ! {w}")
        for k, v in (res.get("fetch_errors") or {}).items():
            print(f"  (소스 장애) {k}: {v}")
    return 0 if res["status"] in {"confirmed", "krx_priority", "single_source", "fallback"} else 2


if __name__ == "__main__":
    sys.exit(main())
