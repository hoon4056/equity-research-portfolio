import streamlit as st
import pandas as pd
import yfinance as yf

# Streamlit Page Config
st.set_page_config(
    page_title="AI Equity Research Track Record",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📈 AI 주식 리서치 포트폴리오 & 트랙 레코드")
st.caption("네이버 블로그 리서치 포스팅 실시간 성과 및 KOSPI 대비 Alpha(초과수익률) 측정 대시보드")
st.markdown("---")

# Sidebar
st.sidebar.header("⚙️ 대시보드 설정")
sheet_url = st.sidebar.text_input(
    "Google Sheets 웹 게시 CSV URL",
    placeholder="https://docs.google.com/spreadsheets/d/e/.../pub?output=csv"
)

# 쉼표(,) 및 문자열을 안전하게 숫자로 변환하는 함수
def to_float(val, default=0.0):
    if pd.isna(val):
        return default
    try:
        cleaned = str(val).replace(',', '').replace('%', '').strip()
        return float(cleaned)
    except:
        return default

@st.cache_data(ttl=300)
def load_data(url):
    if not url:
        return None
    try:
        df = pd.read_csv(url)
        return df
    except Exception as e:
        st.error(f"구글 시트 로드 실패: {e}")
        return None

df_raw = load_data(sheet_url)

if df_raw is not None and not df_raw.empty:
    df = df_raw.copy()

    # 1. 숫자 컬럼 정제 (쉼표 및 텍스트 자동 제거)
    num_cols = ['매수가(원)', '현재가(원)', '목표가(원)', 'KOSPI기준가', 'KOSPI현재가']
    for col in num_cols:
        if col in df.columns:
            df[col] = df[col].apply(to_float)

    # 2. 실시간 시세 데이터 가져오기 (yfinance)
    tickers = df['티커'].dropna().unique().tolist()
    
    with st.spinner("실시간 주가 수집 중..."):
        try:
            download_list = tickers + ['^KS11']
            live_data = yf.download(download_list, period='5d', progress=False)['Close']
            
            def fetch_price(t):
                try:
                    if t in live_data.columns:
                        series = live_data[t].dropna()
                        if not series.empty:
                            return float(series.iloc[-1])
                except:
                    pass
                return 0.0

            # 종목 실시간 주가 반영
            for idx, row in df.iterrows():
                t = row['티커']
                live_p = fetch_price(t)
                if live_p > 0:
                    df.at[idx, '현재가(원)'] = live_p
                elif df.at[idx, '현재가(원)'] == 0:
                    df.at[idx, '현재가(원)'] = df.at[idx, '매수가(원)']

            # KOSPI 실시간 지수 반영
            kospi_p = fetch_price('^KS11')
            if kospi_p > 0:
                df['KOSPI현재가'] = kospi_p
            else:
                df['KOSPI현재가'] = df['KOSPI기준가']

        except Exception as e:
            st.warning(f"실시간 시세 연동 안내: {e}")
            if '현재가(원)' not in df.columns or df['현재가(원)'].sum() == 0:
                df['현재가(원)'] = df['매수가(원)']
            if 'KOSPI현재가' not in df.columns or df['KOSPI현재가'].sum() == 0:
                df['KOSPI현재가'] = df['KOSPI기준가']

    # 3. 수익률 및 Alpha(초과수익률) 파이썬 직접 재계산
    df['수익률(%)'] = ((df['현재가(원)'] - df['매수가(원)']) / df['매수가(원)'].replace(0, 1)) * 100
    df['KOSPI수익률(%)'] = ((df['KOSPI현재가'] - df['KOSPI기준가']) / df['KOSPI기준가'].replace(0, 1)) * 100
    df['Alpha(%)'] = df['수익률(%)'] - df['KOSPI수익률(%)']

    # Overview Metrics
    avg_return = df['수익률(%)'].mean()
    avg_kospi = df['KOSPI수익률(%)'].mean()
    avg_alpha = df['Alpha(%)'].mean()
    win_rate = (df['Alpha(%)'] > 0).mean() * 100 if len(df) > 0 else 0.0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📊 평균 포트폴리오 수익률", f"{avg_return:.2f}%")
    col2.metric("🏛️ 평균 KOSPI 수익률", f"{avg_kospi:.2f}%")
    col3.metric("🚀 평균 Alpha (초과수익)", f"{avg_alpha:.2f}%p", delta=f"{avg_alpha:.2f}%p")
    col4.metric("🎯 Alpha 승률 (Win Rate)", f"{win_rate:.1f}%")

    st.markdown("---")
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
