import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px

# Streamlit Page Config
st.set_page_config(
    page_title="AI Equity Research Track Record",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Title & Header
st.title("📈 AI 주식 리서치 포트폴리오 & 트랙 레코드")
st.caption("네이버 블로그 리서치 포스팅 실시간 성과 및 KOSPI 대비 Alpha(초과수익률) 측정 대시보드")
st.markdown("---")

# Sidebar - Settings & Config
st.sidebar.header("⚙️ 대시보드 설정")
sheet_url = st.sidebar.text_input(
    "Google Sheets 웹 게시 CSV URL",
    placeholder="https://docs.google.com/spreadsheets/d/e/.../pub?output=csv",
    help="구글 시트 -> 파일 -> 공유 -> 웹에 게시 -> CSV 형태로 게시된 URL을 입력하세요."
)

st.sidebar.markdown("---")
st.sidebar.info(
    "💡 **사용법 Guide**\n"
    "1. 구글 시트를 '웹에 게시(CSV)'로 설정합니다.\n"
    "2. 생성된 URL을 위 입력창에 붙여넣습니다.\n"
    "3. 실시간 주가 API(yfinance)가 자동으로 Alpha와 수익률을 계산합니다."
)

# Demo / Sample Data Function
@st.cache_data(ttl=300)
def get_sample_data():
    return pd.DataFrame([
        {
            "No": 1,
            "매수일자": "2026-08-31",
            "종목명": "현대글로비스",
            "티커": "086280.KS",
            "매수가(원)": 207500,
            "목표가(원)": 280000,
            "KOSPI기준가": 3200.0,
            "상태": "보유중",
            "핵심 Thesis": "지배구조 개편 핵심 및 보스턴다이내믹스 RaaS 재평가",
            "블로그 URL": "https://blog.naver.com/"
        }
    ])

# Data Fetching Function
@st.cache_data(ttl=300)
def load_data(url):
    if not url:
        return get_sample_data()
    try:
        df = pd.read_csv(url)
        return df
    except Exception as e:
        st.error(f"구글 시트 불러오기 실패: {e}")
        return get_sample_data()

# Main App Execution
df_raw = load_data(sheet_url)

if df_raw is not None and not df_raw.empty:
    tickers = df_raw['티커'].unique().tolist()
    
    # Fetch live price data via yfinance
    with st.spinner("실시간 주가 및 KOSPI 지수 수집 중..."):
        try:
            # Download live prices
            live_data = yf.download(tickers + ['^KS11'], period='1d', progress=False)['Close']
            
            # Extract latest price
            def get_latest_price(ticker):
                if ticker in live_data.columns:
                    val = live_data[ticker].dropna().iloc[-1]
                    return float(val)
                return 0.0
            
            kospi_live = get_latest_price('^KS11') if '^KS11' in live_data.columns else 3200.0
            
            df = df_raw.copy()
            df['현재가(원)'] = df['티커'].apply(get_latest_price)
            df['KOSPI현재가'] = kospi_live
            
            # Calculations
            df['수익률(%)'] = ((df['현재가(원)'] - df['매수가(원)']) / df['매수가(원)']) * 100
            df['KOSPI수익률(%)'] = ((df['KOSPI현재가'] - df['KOSPI기준가']) / df['KOSPI기준가']) * 100
            df['Alpha(%)'] = df['수익률(%)'] - df['KOSPI수익률(%)']
            df['목표가 달성률(%)'] = ((df['현재가(원)'] - df['매수가(원)']) / (df['목표가(원)'] - df['매수가(원)'])) * 100

        except Exception as e:
            st.warning(f"실시간 주가 조회 중 일시적 오류 발생. 기본 데이터를 표시합니다: {e}")
            df = df_raw.copy()
            df['현재가(원)'] = df['매수가(원)']
            df['KOSPI현재가'] = df['KOSPI기준가']
            df['수익률(%)'] = 0.0
            df['KOSPI수익률(%)'] = 0.0
            df['Alpha(%)'] = 0.0
            df['목표가 달성률(%)'] = 0.0

    # Key Metrics Overview
    avg_return = df['수익률(%)'].mean()
    avg_kospi_return = df['KOSPI수익률(%)'].mean()
    avg_alpha = df['Alpha(%)'].mean()
    win_rate = (df['Alpha(%)'] > 0).mean() * 100 if len(df) > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📊 평균 포트폴리오 수익률", f"{avg_return:.2f}%")
    col2.metric("🏛️ 평균 KOSPI 수익률", f"{avg_kospi_return:.2f}%")
    col3.metric("🚀 평균 Alpha (초과수익)", f"{avg_alpha:.2f}%p", delta=f"{avg_alpha:.2f}%p")
    col4.metric("🎯 Alpha 승률 (Win Rate)", f"{win_rate:.1f}%")

    st.markdown("---")

    # Detailed Table
    st.subheader("📌 종목별 트랙 레코드 (Track Record)")
    
    display_cols = [
        'No', '매수일자', '종목명', '티커', '매수가(원)', '현재가(원)', 
        '목표가(원)', '수익률(%)', 'KOSPI수익률(%)', 'Alpha(%)', '상태', '핵심 Thesis', '블로그 URL'
    ]
    
    valid_cols = [c for c in display_cols if c in df.columns]
    
    st.dataframe(
        df[valid_cols].style.format({
            '매수가(원)': '{:,.0f}',
            '현재가(원)': '{:,.0f}',
            '목표가(원)': '{:,.0f}',
            '수익률(%)': '{:+.2f}%',
            'KOSPI수익률(%)': '{:+.2f}%',
            'Alpha(%)': '{:+.2f}%p'
        }),
        use_container_width=True
    )

    # Visualization
    st.markdown("---")
    st.subheader("📊 종목별 KOSPI 대비 Alpha 비교")
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df['종목명'],
        y=df['수익률(%)'],
        name='종목 수익률 (%)',
        marker_color='#1f77b4'
    ))
    fig.add_trace(go.Bar(
        x=df['종목명'],
        y=df['KOSPI수익률(%)'],
        name='KOSPI 수익률 (%)',
        marker_color='#ff7f0e'
    ))
    fig.update_layout(
        barmode='group',
        title="포트폴리오 vs KOSPI 수익률 비교",
        xaxis_title="종목명",
        yaxis_title="수익률 (%)",
        legend_title="구분",
        template="plotly_white"
    )
    st.plotly_chart(fig, use_container_width=True)
