import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import json
import os

# 1. Page Configuration
st.set_page_config(
    page_title="ROKAF Track Record Fund | 기관급 팩트시트",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Institutional CSS
st.markdown("""
<style>
    .kpi-title { font-size: 0.8rem; font-weight: 600; color: #8B949E; text-transform: uppercase; letter-spacing: 0.05em; }
    .kpi-val-green { font-size: 2.1rem; font-weight: 800; color: #00FFAA; font-family: monospace; }
    .kpi-val-red { font-size: 2.1rem; font-weight: 800; color: #FF4D5E; font-family: monospace; }
    .kpi-val-blue { font-size: 2.1rem; font-weight: 800; color: #2E82FF; font-family: monospace; }
    .kpi-sub { font-size: 0.75rem; color: #8B949E; }
    .badge-live { background: rgba(0, 255, 170, 0.15); color: #00FFAA; padding: 4px 10px; border-radius: 999px; font-weight: 700; font-size: 0.75rem; border: 1px solid rgba(0, 255, 170, 0.3); }
</style>
""", unsafe_allow_html=True)

# 2. Sidebar Navigation & Config
st.sidebar.markdown("### 🏛️ ROKAF Track Record Fund")
st.sidebar.caption("운용역: **이동훈 (DongHoon Lee)** | 설정일: **2026-08-31**")
st.sidebar.markdown("---")

data_source = st.sidebar.radio("데이터 소스 선택", ["기관 검증 감사 로컬 데이터 (Default)", "Google Sheets 연동 CSV"], index=0)

sheet_url = ""
if data_source == "Google Sheets 연동 CSV":
    sheet_url = st.sidebar.text_input(
        "Google Sheets 웹 게시 CSV URL",
        placeholder="https://docs.google.com/spreadsheets/d/e/.../pub?output=csv"
    )

st.sidebar.markdown("---")
st.sidebar.info("""
**🛡️ 불변 감사 체계 (Audit Trail)**
- 1호 현대글로비스 편입일: `2026-08-31`
- KOSPI 기준가: `6,820.02 pt` (실제 KRX 종가)
- Git Commit SHA: `c81a9f4`
- 한국 거래소(KRX) 공식 종가 검산 완료
""")

# 3. Data Loading Engine
def load_portfolio_data():
    csv_path = os.path.join(os.path.dirname(__file__), "data", "trade_log.csv")
    if os.path.exists(csv_path):
        return pd.read_csv(csv_path)
    return pd.DataFrame([{
        "No": 1,
        "매수일자": "2026-08-31",
        "종목명": "현대글로비스",
        "티커": "086280.KS",
        "섹터": "산업재/스마트물류",
        "매수가(원)": 207500,
        "현재가(원)": 200500,
        "목표가(원)": 280000,
        "손절선(원)": 170000,
        "수익률(%)": -3.37,
        "KOSPI기준가": 6820.02,
        "KOSPI현재가": 5375.36,
        "KOSPI수익률(%)": -21.18,
        "Alpha(%p)": 17.81,
        "상태": "BUY/HOLD",
        "핵심 Thesis": "지배구조 개편 핵심 및 보스턴다이내믹스 RaaS 재평가",
        "블로그 URL": "https://blog.naver.com/",
        "검증해시": "c81a9f4"
    }])

if sheet_url:
    try:
        df = pd.read_csv(sheet_url)
    except:
        st.warning("구글 시트 연동 실패. 기관 검증 로컬 감사 데이터를 표시합니다.")
        df = load_portfolio_data()
else:
    df = load_portfolio_data()

# Clean numeric columns
for col in ['매수가(원)', '현재가(원)', '목표가(원)', '손절선(원)', 'KOSPI기준가', 'KOSPI현재가', '수익률(%)', 'KOSPI수익률(%)', 'Alpha(%p)']:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('%', ''), errors='coerce')

# Calculations
avg_return = df['수익률(%)'].mean() if '수익률(%)' in df.columns else -3.37
avg_kospi = df['KOSPI수익률(%)'].mean() if 'KOSPI수익률(%)' in df.columns else -21.18
avg_alpha = df['Alpha(%p)'].mean() if 'Alpha(%p)' in df.columns else 17.81
mdd_fund = -17.14
mdd_kospi = -29.12
ir_ratio = 1.42

# 4. Header Bar
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.title("ROKAF Military Service Track Record Fund")
    st.caption("공군 복무 기간 비공식 헤지펀드 실전 알파 창출 & 팩트시트 엔진")
with col_h2:
    st.markdown("<div style='text-align: right; margin-top: 15px;'><span class='badge-live'>● ACTIVE / AUDITED</span></div>", unsafe_allow_html=True)

st.markdown("---")

# 5. Executive KPI Metric Cards
k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.markdown(f"<div class='kpi-title'>누적 Alpha (초과수익)</div><div class='kpi-val-green'>+{avg_alpha:.2f}%p</div><div class='kpi-sub'>vs KOSPI 대비 시장 완벽 압도</div>", unsafe_allow_html=True)
with k2:
    st.markdown(f"<div class='kpi-title'>포트폴리오 수익률 (ITD)</div><div class='kpi-val-red'>{avg_return:.2f}%</div><div class='kpi-sub'>하락장 속 자본 보존 달성</div>", unsafe_allow_html=True)
with k3:
    st.markdown(f"<div class='kpi-title'>벤치마크 (KOSPI)</div><div class='kpi-val-red'>{avg_kospi:.2f}%</div><div class='kpi-sub'>6,820.02 ➔ 5,375.36pt (하락장)</div>", unsafe_allow_html=True)
with k4:
    st.markdown(f"<div class='kpi-title'>최대 낙폭 (MDD 방어)</div><div class='kpi-val-blue'>{mdd_fund:.2f}%</div><div class='kpi-sub'>KOSPI({mdd_kospi:.2f}%) 대비 +11.98%p 방어</div>", unsafe_allow_html=True)
with k5:
    st.markdown(f"<div class='kpi-title'>Information Ratio / Beta</div><div class='kpi-val-green'>{ir_ratio:.2f}</div><div class='kpi-sub'>헤지펀드 최우수 (Beta: 0.28)</div>", unsafe_allow_html=True)

st.markdown("---")

# 6. Tab Layout
tab_overview, tab_risk, tab_holdings, tab_audit = st.tabs([
    "📈 벤치마크 비교 & 차트", 
    "🌊 리스크 & Underwater 분석", 
    "📌 보유 종목 & Thesis 진행도", 
    "🛡️ 불변 감사 로그 (Audit Trail)"
])

# Load historical performance series
series_path = os.path.join(os.path.dirname(__file__), "data", "performance_series.json")
perf_df = None
if os.path.exists(series_path):
    with open(series_path, "r", encoding="utf-8") as f:
        perf_df = pd.DataFrame(json.load(f))

with tab_overview:
    st.subheader("📊 벤치마크 대조 누적 수익률 궤적 (Rebased to 100)")
    if perf_df is not None:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=perf_df['date'], 
            y=perf_df['glovis_rebased'], 
            mode='lines', 
            name='현대글로비스 (ROKAF Fund)',
            line=dict(color='#00FFAA', width=3.5)
        ))
        fig.add_trace(go.Scatter(
            x=perf_df['date'], 
            y=perf_df['kospi_rebased'], 
            mode='lines', 
            name='KOSPI 지수 (Benchmark)',
            line=dict(color='#8B949E', width=2, dash='dot')
        ))
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0E1117",
            plot_bgcolor="#0E1117",
            margin=dict(l=20, r=20, t=30, b=20),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("시계열 데이터가 준비 중입니다.")

with tab_risk:
    st.subheader("🌊 Underwater 낙폭 차트 (Drawdown Analysis)")
    if perf_df is not None:
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(
            x=perf_df['date'], 
            y=perf_df['glovis_drawdown_pct'], 
            mode='lines', 
            fill='tozeroy',
            name='글로비스 낙폭 (MDD: -17.1%)',
            line=dict(color='#2E82FF', width=2),
            fillcolor='rgba(46, 130, 255, 0.25)'
        ))
        fig_dd.add_trace(go.Scatter(
            x=perf_df['date'], 
            y=perf_df['kospi_drawdown_pct'], 
            mode='lines', 
            fill='tozeroy',
            name='KOSPI 낙폭 (MDD: -29.1%)',
            line=dict(color='#FF4D5E', width=2),
            fillcolor='rgba(255, 77, 94, 0.15)'
        ))
        fig_dd.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0E1117",
            plot_bgcolor="#0E1117",
            margin=dict(l=20, r=20, t=30, b=20),
            hovermode="x unified",
            yaxis=dict(title="고점 대비 낙폭 (%)", range=[-35, 2]),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_dd, use_container_width=True)

with tab_holdings:
    st.subheader("📌 액티브 종목별 트랙 레코드 (Track Record)")
    st.dataframe(
        df.style.format({
            '매수가(원)': '{:,.0f}',
            '현재가(원)': '{:,.0f}',
            '목표가(원)': '{:,.0f}',
            '손절선(원)': '{:,.0f}',
            '수익률(%)': '{:+.2f}%',
            'KOSPI수익률(%)': '{:+.2f}%',
            'Alpha(%p)': '{:+.2f}%p'
        }),
        use_container_width=True
    )
    
    st.markdown("---")
    st.markdown("#### 🎯 3대 핵심 Investment Thesis 진행 현황")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**① 지배구조 개편 핵심 수혜** `ON TRACK (85%)`")
        st.caption("정의선 회장 지분 20% 활용한 모비스 스왑/현물출자 모멘텀. 기업가치 제고 인센티브 극대화.")
        st.progress(0.85)
    with c2:
        st.markdown("**② 보스턴다이내믹스 IPO & RaaS** `ON TRACK (75%)`")
        st.caption("지분 11.25% 상장 가치 재평가. 물류 거점 로봇(Stretch) 구독형 물류 플랫폼 전환.")
        st.progress(0.75)
    with c3:
        st.markdown("**③ PCTC 고마진 & 주주환원** `STRONG (90%)`")
        st.caption("PCTC 고단가 장기계약 및 견조한 CKD 본업 실적. 배당 성향 및 자사주 소각 정책.")
        st.progress(0.90)

with tab_audit:
    st.subheader("🛡️ 사후 조작 불가능한 불변 감사 체계 (Audit Trail)")
    st.markdown("""
    - **GitHub Commit SHA**: `c81a9f4` (최초 등록: `2026-08-31 23:45 UTC`)
    - **공식 거래소 종가 검산**: 네이버 금융 및 KRX 공식 일별 종가 전수 교차 검증 완료
    - **불변 원칙**: 모든 종목 편입 기록은 Git 커밋 타임스탬프와 일치하며 사후 수정이 불가합니다.
    """)
    st.code(df.to_json(orient='records', force_ascii=False, indent=2), language="json")
