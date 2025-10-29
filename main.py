import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

# 🌟 페이지 설정
st.set_page_config(page_title="경제 공부용 투자 시뮬레이터 💰", page_icon="📈", layout="centered")

# 🎨 스타일
st.markdown("""
    <style>
    body {
        background: linear-gradient(135deg, #fceabb, #f8b500);
        font-family: 'Segoe UI', sans-serif;
    }
    .title {
        text-align: center;
        color: #333;
        font-size: 2.5em;
        font-weight: bold;
        text-shadow: 1px 1px 3px #ffffff;
    }
    .desc {
        text-align: center;
        color: #555;
        margin-bottom: 25px;
    }
    </style>
""", unsafe_allow_html=True)

# 🏦 제목
st.markdown('<div class="title">💸 경제 공부용 투자 시뮬레이터 📈</div>', unsafe_allow_html=True)
st.markdown('<div class="desc">초보자도 쉽게 이해할 수 있는 간단한 투자 체험 도구입니다 😊</div>', unsafe_allow_html=True)

# 🧮 사용자 입력
st.sidebar.header("⚙️ 시뮬레이션 설정")
investment = st.sidebar.number_input("💰 투자 금액 (원)", min_value=10000, step=10000, value=1000000)
annual_return = st.sidebar.slider("📊 예상 연평균 수익률 (%)", 0.0, 20.0, 7.0, step=0.5)
years = st.sidebar.slider("🕓 투자 기간 (년)", 1, 30, 10)
compound = st.sidebar.radio("🔁 복리 계산 방식", ["연복리", "단리"])

# 📈 수익 계산
if compound == "연복리":
    df = pd.DataFrame({
        "Year": list(range(1, years + 1)),
        "Value": [investment * ((1 + annual_return / 100) ** i) for i in range(1, years + 1)]
    })
else:
    df = pd.DataFrame({
        "Year": list(range(1, years + 1)),
        "Value": [investment * (1 + (annual_return / 100) * i) for i in range(1, years + 1)]
    })

# 💵 최종 수익 요약
final_value = df["Value"].iloc[-1]
profit = final_value - investment

st.markdown(f"""
### 🧾 결과 요약
- **초기 투자 금액:** {investment:,.0f} 원  
- **예상 수익률:** {annual_return:.1f}% / 년  
- **투자 기간:** {years}년  
- **최종 예상 금액:** 💎 **{final_value:,.0f} 원**  
- **총 수익:** 🎉 **{profit:,.0f} 원**
""")

# 📊 그래프
fig, ax = plt.subplots()
ax.plot(df["Year"], df["Value"], marker="o", linewidth=2)
ax.set_title("💹 투자 성장 그래프", fontsize=14)
ax.set_xlabel("투자 경과 년수")
ax.set_ylabel("투자금 가치 (원)")
st.pyplot(fig)

# 📘 경제 개념 설명
st.markdown("---")
st.subheader("📚 경제 개념 간단 정리")
st.markdown("""
- **단리(Simple Interest)**: 매년 이자만 계산 (예: 7%면 매년 원금의 7%만 증가)  
- **복리(Compound Interest)**: 이자에 이자가 붙는 방식으로, 시간이 지날수록 빠르게 증가  
- **투자 수익률(Return)**: 1년 동안 자산이 얼마나 성장했는지를 나타내는 비율  
- **리스크(Risk)**: 높은 수익률을 기대할수록 손실 가능성도 커짐 ⚠️  

> 📖 *"복리는 세계 8번째 불가사의다."* — 아인슈타인
""")

# 🎉 마무리
st.markdown("<br><center>Made with ❤️ by Streamlit</center>", unsafe_allow_html=True)
