import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="퀀트 투자 시뮬레이터 📈", page_icon="💹", layout="wide")

st.title("💰 퀀트 투자 시뮬레이터 (포트폴리오용)")
st.write("실제 주가 없이 랜덤 시뮬레이션으로 퀀트 전략을 체험하고, 목표 달성 기간까지 계산합니다.")

# 🧮 사용자 입력
st.sidebar.header("⚙️ 시뮬레이션 설정")
days = st.sidebar.slider("시뮬레이션 기간 (일)", 30, 365, 180)
initial_price = st.sidebar.number_input("초기 가격", min_value=1000, value=10000)
short_ma = st.sidebar.slider("단기 이동평균 기간", 5, 20, 5)
long_ma = st.sidebar.slider("장기 이동평균 기간", 10, 50, 20)
goal_price = st.sidebar.number_input("🎯 목표 가격 (선택)", min_value=0, value=0)
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

# 📊 가격 및 이동평균선
st.subheader("📊 가격 및 이동평균선")
st.line_chart(data[['Price', 'Short_MA', 'Long_MA']])

# 🔔 매수/매도 시점
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

# 📈 전략 vs 시장 수익률
st.subheader("📈 전략 vs 시장 수익률")
st.line_chart(pd.DataFrame({
    '시장 수익률': cumulative_market,
    '전략 수익률': cumulative_strategy
}))

# 🧾 결과 요약
st.subheader("🧾 결과 요약")
st.write(f"최종 전략 누적 수익률: {cumulative_strategy.iloc[-1]:.2f}배")
st.write(f"최종 시장 누적 수익률: {cumulative_market.iloc[-1]:.2f}배")

# 🎯 목표 달성 기간 계산
if goal_price > 0:
    year_needed = 0
    max_days = 1000  # 무한 루프 방지
    while True:
        year_needed += 1
        sim_returns = np.random.normal(0, 0.01, year_needed)
        sim_price = initial_price
        for r in sim_returns:
            sim_price *= (1 + r)
        if sim_price >= goal_price or year_needed > max_days:
            break
    if year_needed <= max_days:
        st.success(f"목표 가격 {goal_price:,} 원에 도달하려면 약 {year_needed} 일 필요! 🎯")
    else:
        st.warning("목표 가격에 도달하기 어려움 😢")

# 🔹 여러 시나리오 비교
st.subheader("💹 여러 수익률 시나리오 비교")
scenario_rates = [-0.01, 0.0, 0.01]  # -1%, 0%, +1% 변동성
scenario_df = pd.DataFrame({"Day": range(1, days+1)})
for r in scenario_rates:
    sim_price_list = [initial_price]
    for _ in range(days):
        sim_price_list.append(sim_price_list[-1] * (1 + r + np.random.normal(0,0.01)))
    scenario_df[f"{r*100:.1f}% 시나리오"] = sim_price_list[1:]

st.line_chart(scenario_df.set_index("Day"))

st.markdown("---")
st.write("💡 **설명:** 단순 이동평균 전략 + 랜덤 시뮬레이션으로 퀀트 전략 이해. 여러 시나리오 비교로 위험과 수익률 감각 학습 가능.")
