import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="퀀트 투자 시뮬레이터 📈", page_icon="💹", layout="wide")

st.title("💰 퀀트 투자 시뮬레이터")
st.write("단순 이동평균(MA) 전략을 사용한 퀀트 시뮬레이션 예제입니다.")

# 🧮 사용자 입력
ticker = st.text_input("종목 코드 입력 (예: AAPL, 005930.KS)", value="AAPL")
start_date = st.date_input("시작일", pd.to_datetime("2020-01-01"))
end_date = st.date_input("종료일", pd.to_datetime("2023-12-31"))
short_ma = st.slider("단기 이동평균 기간", 5, 50, 20)
long_ma = st.slider("장기 이동평균 기간", 20, 200, 50)

# 데이터 불러오기
data = yf.download(ticker, start=start_date, end=end_date)
data['Short_MA'] = data['Close'].rolling(short_ma).mean()
data['Long_MA'] = data['Close'].rolling(long_ma).mean()

# 매수/매도 신호
data['Signal'] = 0
data['Signal'][short_ma:] = \
    (data['Short_MA'][short_ma:] > data['Long_MA'][short_ma:]).astype(int)
data['Position'] = data['Signal'].diff()

st.subheader("📊 주가 및 이동평균선")
st.line_chart(data[['Close', 'Short_MA', 'Long_MA']])

# 매수/매도 시점 표시
st.subheader("🔔 매수/매도 시점")
buy_signals = data[data['Position'] == 1]
sell_signals = data[data['Position'] == -1]
st.write("매수 시점", buy_signals.index.date.tolist())
st.write("매도 시점", sell_signals.index.date.tolist())

# 전략 수익률 계산
data['Market_Return'] = data['Close'].pct_change()
data['Strategy_Return'] = data['Market_Return'] * data['Signal'].shift(1)
cumulative_market = (1 + data['Market_Return']).cumprod()
cumulative_strategy = (1 + data['Strategy_Return']).cumprod()

st.subheader("📈 전략 vs 시장 수익률")
st.line_chart(pd.DataFrame({
    '시장 수익률': cumulative_market,
    '전략 수익률': cumulative_strategy
}))

# 요약 결과
st.subheader("🧾 결과 요약")
st.write(f"기간: {start_date} ~ {end_date}")
st.write(f"최종 전략 누적 수익률: {cumulative_strategy[-1]:.2f}배")
st.write(f"최종 시장 누적 수익률: {cumulative_market[-1]:.2f}배")


# 🎉 마무리
st.markdown("<br><center>Made with ❤️ by Streamlit</center>", unsafe_allow_html=True)
