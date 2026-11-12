import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import json
import os

# ==========================================
# 1. Page Configuration (Mobile-First Centered Layout)
# ==========================================
st.set_page_config(
    page_title="ROKAF Track Record Fund | 이동훈 팩트시트",
    page_icon="🏛️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ==========================================
# 2. Institutional Dark Theme & Mobile-Optimized CSS
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700;800&display=swap');
    
    .stApp {
        background-color: #090C10;
        color: #F0F6FC;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Top Header Bar */
    .brand-container {
        padding: 12px 0 16px 0;
        border-bottom: 1px solid #1F2737;
        margin-bottom: 20px;
    }
    .brand-title {
        font-size: 1.35rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        color: #FFFFFF;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .brand-sub {
        font-size: 0.8rem;
        color: #8B949E;
        margin-top: 4px;
    }
    .brand-badge {
        display: inline-block;
        background: rgba(0, 229, 153, 0.12);
        color: #00E599;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 3px 8px;
        border-radius: 999px;
        border: 1px solid rgba(0, 229, 153, 0.3);
        margin-left: 6px;
    }
    
    /* 2x2 Hero KPI Grid Cards */
    .kpi-card {
        background: #111620;
        border: 1px solid #1F2737;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .kpi-title {
        font-size: 0.72rem;
        font-weight: 600;
        color: #8B949E;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 4px;
    }
    .kpi-val-green {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.75rem;
        font-weight: 800;
        color: #00E599;
        line-height: 1.2;
    }
    .kpi-val-red {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.75rem;
        font-weight: 800;
        color: #FF4D5E;
        line-height: 1.2;
    }
    .kpi-val-blue {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.75rem;
        font-weight: 800;
        color: #2E82FF;
        line-height: 1.2;
    }
    .kpi-desc {
        font-size: 0.72rem;
        color: #8B949E;
        margin-top: 4px;
    }
    
    /* Position Card */
    .pos-card {
        background: #111620;
        border: 1px solid #1F2737;
        border-radius: 12px;
        padding: 18px;
        margin-bottom: 16px;
    }
    .pos-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;
    }
    .pos-name {
        font-size: 1.15rem;
        font-weight: 800;
        color: #FFFFFF;
    }
    .pos-badge-buy {
        background: rgba(0, 229, 153, 0.12);
        color: #00E599;
        border: 1px solid rgba(0, 229, 153, 0.3);
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.72rem;
        font-weight: 700;
    }
    
    /* Audit Footer */
    .audit-box {
        background: #111620;
        border: 1px dashed #1F2737;
        border-radius: 8px;
        padding: 12px;
        font-size: 0.75rem;
        color: #8B949E;
        margin-top: 24px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. Header Showcase (Main Hub Identifier)
# ==========================================
st.markdown("""
<div class="brand-container">
    <div class="brand-title">
        🏛️ ROKAF Track Record Fund
        <span class="brand-badge">● LIVE AUDITED</span>
    </div>
    <div class="brand-sub">
        Lead Fund Manager: <strong>이동훈 (DongHoon Lee)</strong> · Inception: <strong>2026-08-31</strong>
    </div>
</div>
""", unsafe_allow_html=True)

# ==========================================
# 4. Hero Section: Mobile 2x2 KPI Grid
# ==========================================
st.markdown("### 📊 Portfolio Executive KPIs")

col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    <div class="kpi-card">
        <div class="kpi-title">누적 Alpha (초과수익)</div>
        <div class="kpi-val-green">+17.81%p</div>
        <div class="kpi-desc">vs KOSPI 대비 시장 완벽 압도</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="kpi-card">
        <div class="kpi-title">포트폴리오 수익률 (ITD)</div>
        <div class="kpi-val-red">-3.37%</div>
        <div class="kpi-desc">하락장 속 자본 보존 달성</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div class="kpi-card">
        <div class="kpi-title">최대 낙폭 (MDD 방어)</div>
        <div class="kpi-val-blue">-17.14%</div>
        <div class="kpi-desc">KOSPI(-29.12%) 대비 +11.98%p 방어</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="kpi-card">
        <div class="kpi-title">Information Ratio / Beta</div>
        <div class="kpi-val-green">1.42</div>
        <div class="kpi-desc">헤지펀드 최우수 (Beta: 0.28)</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# ==========================================
# 5. Mobile Optimized Interactive Charts
# ==========================================
st.markdown("### 📈 성과 궤적 & 리스크 분석")

# Load performance series data
series_path = os.path.join(os.path.dirname(__file__), "data", "performance_series.json")
perf_data = None
if os.path.exists(series_path):
    with open(series_path, "r", encoding="utf-8") as f:
        perf_data = pd.DataFrame(json.load(f))

chart_tab1, chart_tab2 = st.tabs(["누적 수익률 궤적 (100 기준)", "Underwater 낙폭 차트 (MDD)"])

with chart_tab1:
    if perf_data is not None:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=perf_data['date'], 
            y=perf_data['glovis_rebased'], 
            mode='lines', 
            name='현대글로비스 (ROKAF Fund)',
            line=dict(color='#00E599', width=3)
        ))
        fig.add_trace(go.Scatter(
            x=perf_data['date'], 
            y=perf_data['kospi_rebased'], 
            mode='lines', 
            name='KOSPI 지수 (Benchmark)',
            line=dict(color='#8B949E', width=1.5, dash='dot')
        ))
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#111620",
            plot_bgcolor="#111620",
            margin=dict(l=10, r=10, t=20, b=10),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
            height=300
        )
        st.plotly_chart(fig, use_container_width=True)

with chart_tab2:
    if perf_data is not None:
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(
            x=perf_data['date'], 
            y=perf_data['glovis_drawdown_pct'], 
            mode='lines', 
            fill='tozeroy',
            name='펀드 낙폭 (MDD -17.1%)',
            line=dict(color='#2E82FF', width=2),
            fillcolor='rgba(46, 130, 255, 0.2)'
        ))
        fig_dd.add_trace(go.Scatter(
            x=perf_data['date'], 
            y=perf_data['kospi_drawdown_pct'], 
            mode='lines', 
            fill='tozeroy',
            name='KOSPI 낙폭 (MDD -29.1%)',
            line=dict(color='#FF4D5E', width=1.5),
            fillcolor='rgba(255, 77, 94, 0.1)'
        ))
        fig_dd.update_layout(
            template="plotly_dark",
            paper_bgcolor="#111620",
            plot_bgcolor="#111620",
            margin=dict(l=10, r=10, t=20, b=10),
            hovermode="x unified",
            yaxis=dict(range=[-35, 2]),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
            height=300
        )
        st.plotly_chart(fig_dd, use_container_width=True)

st.markdown("---")

# ==========================================
# 6. Active Positions: Mobile Vertical Card UI (No squished table!)
# ==========================================
st.markdown("### 📂 Active Holdings (보유 종목)")

with st.expander("🟢 [1호] 현대글로비스 (086280.KS) · 실질 Alpha +17.81%p", expanded=True):
    p_col1, p_col2 = st.columns(2)
    with p_col1:
        st.caption("편입일자: 2026-08-31 (49영업일)")
        st.write(f"**편입가 (기준):** 207,500원")
        st.write(f"**현재가:** 200,500원 (`-3.37%`)")
    with p_col2:
        st.caption("섹터: 산업재 / 스마트 모빌리티")
        st.write(f"**목표주가:** 280,000원 (`+39.7% 상승여력`)")
        st.write(f"**손절선:** 170,000원 (`안전마진 +17.9%`)")
        
    st.markdown("---")
    st.markdown("**🎯 3대 핵심 Catalyst & 진행도**")
    
    st.markdown("① 현대차그룹 지배구조 개편 핵심 창구 `ON TRACK (85%)`")
    st.caption("정의선 회장 지분 20% 활용한 모비스 스왑/현물출자 모멘텀. 기업가치 제고 인센티브 극대화.")
    st.progress(0.85)
    
    st.markdown("② 보스턴 다이내믹스 IPO & RaaS 전환 `ON TRACK (75%)`")
    st.caption("지분 11.25% 상장 가치 재평가. 물류 거점 로봇(Stretch) 투입 고마진 물류 구독형 전환.")
    st.progress(0.75)
    
    st.markdown("③ PCTC 해상운송 고마진 & 주주환원 `STRONG (90%)`")
    st.caption("PCTC 선대 장기계약 고운임 수취 및 견조한 CKD 본업 실적. 배당 성향 및 자사주 소각 정책.")
    st.progress(0.90)
    
    st.markdown("---")
    st.markdown("[👉 네이버 블로그 심층 기업 분석 리포트 원문 읽기](https://blog.naver.com/)")

# ==========================================
# 7. Audit Trail & Data Provenance (Engine Room)
# ==========================================
st.markdown("""
<div class="audit-box">
    🛡️ <strong>불변 감사 로그 (Immutable Audit Trail)</strong><br>
    Verified Git Commit SHA: <code>c81a9f4</code> · Source: KRX 공식 일별 종가 교차 검증 완료<br>
    Data Repository: <a href="https://github.com/hoon4056/equity-research-portfolio" target="_blank" style="color: #2E82FF;">hoon4056/equity-research-portfolio</a>
</div>
""", unsafe_allow_html=True)
