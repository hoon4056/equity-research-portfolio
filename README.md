# 🏛️ ROKAF Military Service Track Record Fund
> **대한민국 공군 복무 기간 중 자본시장 실무 감각 유지 및 전역 후 전문 투자학회/자산운용사 진입을 위한 기관급 퀀트 알파 운용 트랙 레코드**

[![Live Dashboard](https://img.shields.io/badge/Live%20Dashboard-GitHub%20Pages-00E599?style=for-the-badge&logo=github)](https://hoon4056.github.io/equity-research-portfolio/)
[![Streamlit App](https://img.shields.io/badge/Streamlit-App%20Cloud-FF4B4B?style=for-the-badge&logo=streamlit)](https://hoon4056-equity-research-portfolio.streamlit.app/)
[![Audit Status](https://img.shields.io/badge/Audit%20Status-Verified%20a5c6ecc-2E82FF?style=for-the-badge)](data/trade_log.csv)

---

## 📊 펀드 핵심 성과 요약 (Executive Factsheet)
- **운용역 (Lead Fund Manager)**: 이동훈 (DongHoon Lee)
- **설정일자 (Inception Date)**: 2026년 8월 31일
- **최근 갱신일자**: 2026년 11월 18일 (54거래일)
- **비교 벤치마크**: KOSPI 지수 (편입 기준일 종가: 6,820.02 pt)
- **운용 전략**: Long-Only Catalyst & Value Alpha (지배구조 개편, 모빌리티 로보틱스 RaaS, 배당 가치주)

| 핵심 지표 (Metrics) | 펀드 성과 (Fund) | 벤치마크 (KOSPI) | 초과 성과 (Alpha) | 비고 |
| :--- | :---: | :---: | :---: | :--- |
| **누적 수익률 (ITD)** | **-2.65%** | **-25.70%** | **`+23.05%p`** | 하락장 속 시장 아웃퍼폼 (당일 알파 -0.89%p) |
| **최대 낙폭 (MDD)** | **-17.14%** | **-29.83%** | **`+12.69%p 방어`** | 고점 대비 하방 경직성 증명 |
| **Information Ratio (IR)** | **2.99** | — | — | 연율화 액티브 수익 / 추적오차 42.89% |
| **포트폴리오 Beta** | **0.59** | 1.00 | — | 일간 수익률 회귀 (KOSPI 상관 0.57) |
| **목표가 잔여 상승여력** | **+38.61%** | — | — | 목표주가: 280,000원 |
| **손절선 안전마진** | **+18.82%** | — | — | 손절선(170,000원) 대비, 현재가에서 -15.84% |

> 누적 Alpha(%p)는 누적 수익률의 단순 차이입니다. 펀드 누적 수익률(-2.65%)이 0 근처라 지수가 반등하는 날 펀드가 지수만큼 오르지 못하면 `%p` 격차는 줄어들 수 있으며(11-17 +23.44%p → 11-18 +23.05%p), 상대지수(펀드/KOSPI = 97.35/74.30 = 1.310배) 기준 초과 상태는 유지되고 있습니다.

---

## 📌 보유 종목 현황 (Holdings Detail)

### [1호] 현대글로비스 (086280.KS)
- **편입일 / 기준단가**: 2026-08-31 / 207,500원
- **현재주가 (2026-11-18)**: 202,000원 (-2.65%, 당일 +1.10%)
- **목표주가**: 280,000원 (+38.61% 상승 여력 / Target PER 13.6배)
- **손절선 (Thesis Breaker)**: 170,000원 (손절선 대비 안전마진 +18.82%, 현재가에서 -15.84%)
- **투자의견 / 상태**: BUY / HOLD (보유 유지)
- **3대 핵심 Thesis & Catalyst**:
  1. **현대차그룹 지배구조 개편 핵심 창구 (진행도: 85%)**: 정의선 회장 개인 지분 20.00%를 활용한 모비스 지분 스왑/현물출자 모멘텀.
  2. **보스턴 다이내믹스 IPO & 물류 RaaS 전환 (진행도: 75%)**: 지분 12.47%로 확대(2026-09 말), BD는 그룹 100% 자회사 체제 완성(11-17 보도). 알티올 지분 100% 편입(11-18 보도)으로 스마트물류 기술 내재화. 로봇 부문 손실 축소가 관건.
  3. **PCTC 완성차 해상운송 고마진 & 주주환원 (진행도: 90%)**: 장기계약 고운임 수취 및 안정적 CKD 실적, 배당 성향·자사주 소각 등 주주가치 제고 정책.
- **최근 공시 (2026-11-18 확인)**: 당일 신규 공시 없음(최신 접수는 11-16 분기보고서 2026.09). 11-18 보도 — 물류자동화기업 알티올 잔여지분 30.16%(약 81억 700만원)를 취득해 지분 100% 완전자회사로 편입. 11-17 보도 — 소프트뱅크 잔여지분 인수 완료로 보스턴다이내믹스 그룹 지분 100% 확보(글로비스 12.47%). 배당·무상증자·액면분할 등 권리변동 공시는 없음.

---

## 🛡️ 사후 조작 불가능한 불변 감사 체계 (Audit Trail)
- 본 포트폴리오는 사후적인 끼워맞추기식 기록을 원천 배제하기 위해, 편입 시점의 타임스탬프와 Git Commit Hash(`a5c6ecc`), 그리고 네이버 금융·한국거래소(KRX) 일별시세 확정 종가를 3각 교차 검증합니다.
- 정산은 `python3 portfolio/tracker.py settle --date YYYY-MM-DD`로만 수행하며(거래일당 1건, 멱등), `python3 portfolio/tracker.py audit`이 시계열·정산로그·포트폴리오 JSON·거래로그·팩트시트의 모든 수치를 0.01 허용오차로 재검산합니다.
- 모든 일별 주가와 알파 계산 로그는 `data/trade_log.csv` 및 `data/performance_series.json`에 영구 기록됩니다.

---

## 💻 대시보드 바로가기
- **[🌐 GitHub Pages 인터랙티브 대시보드 열기](https://hoon4056.github.io/equity-research-portfolio/)**
- **[📱 Streamlit Cloud 대시보드 열기](https://hoon4056-equity-research-portfolio.streamlit.app/)**
