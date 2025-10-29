import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="퀀트 투자 시뮬레이터 📈", page_icon="💹", layout="wide")

st.title("💰 퀀트 투자 시뮬레이터 (Streamlit 전용)")
st.write("실제 주가 데이터를 대신해 랜덤 시뮬레이션으로 퀀트 전략을 체험합니다.")

# 🧮 사용자 입력
st.sidebar.header("⚙️ 시뮬레이션 설정")
days = st.sidebar.slider("시뮬레이션 기간 (일)", 30, 365, 180)
initial_price = st.sidebar.number_input("초기 가격", min_value=1000, value=10000)
short_ma = st.sidebar.slider("단기 이동평균 기간", 5, 20, 5)
long_ma = st.sidebar.slider("장기 이동평균 기간", 10, 50, 20)
seed = st.sidebar.number_input("랜덤 시드", value=42)

np.random.seed(seed)

# 📈 랜덤 주가 생성 (간단한 브라운 모션)
returns = np.random.normal(0, 0.01, days)
price = [initial_price]
for r in returns:
    price.append(price[-1] * (1 + r))
price = price[1:]

data = pd.DataFrame({"Price": price})
data['Short_MA'] = data['Price'].rolling(short_ma).mean()
data['Long_MA'] = data['Price'].rolling(long_ma).mean()

# 매수/매도 신호
data['Signal'] = 0
data['Signal'][long_ma:] = (data['Short_MA'][long_ma:] > data['Long_MA'][long_ma:]).astype(int)
data['Position'] = data['Signal'].diff()

# 📊 그래프
st.subheader("📊 가격 및 이동평균선")
st.line_chart(data[['Price', 'Short_MA', 'Long_MA']])

st.subheader("🔔 매수/매도 시점")
buy_signals = data[data['Position'] == 1]
sell_signals = data[data['Position'] == -1]
st.write("매수 시점:", buy_signals.index.tolist())
st.write("매도 시점:", sell_signals.index.tolist())

# 전략 수익률 계산
data['Market_Return'] = data['Price'].pct_change()
data['Strategy_Return'] = data['Market_Return'] * data['Signal'].shift(1)
cumulative_market = (1 + data['Market_Return']).cumprod()
cumulative_strategy = (1 + data['Strategy_Return']).cumprod()

st.subheader("📈 전략 vs 시장 수익률")
st.line_chart(pd.DataFrame({
    '시장 수익률': cumulative_market,
    '전략 수익률': cumulative_strategy
}))

st.subheader("🧾 결과 요약")
st.write(f"최종 전략 누적 수익률: {cumulative_strategy.iloc[-1]:.2f}배")
st.write(f"최종 시장 누적 수익률: {cumulative_market.iloc[-1]:.2f}배")
