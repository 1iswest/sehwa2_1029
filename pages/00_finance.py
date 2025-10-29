import streamlit as st

import yfinance as yf

import pandas as pd

import plotly.graph_objs as go

from datetime import datetime, timedelta

st.title("글로벌 시가총액 TOP10 기업의 최근 1년간 주가 변화")

top10 = {

    'AAPL': 'Apple',

    'MSFT': 'Microsoft',

    'GOOGL': 'Alphabet (Google)',

    'AMZN': 'Amazon',

    'NVDA': 'Nvidia',

    'META': 'Meta Platforms',

    'BRK-B': 'Berkshire Hathaway',

    'TSLA': 'Tesla',

    'LLY': 'Eli Lilly',

    'TSM': 'TSMC'

}

st.write("조회 기업:")

st.write(", ".join([f"{v}({k})" for k, v in top10.items()]))

end = datetime.today()

start = end - timedelta(days=365)

with st.spinner("데이터를 가져오고 있습니다..."):

    data = yf.download(list(top10.keys()), start=start, end=end, group_by='ticker', auto_adjust=True)

# 데이터 구조 자동 감지

if isinstance(data.columns, pd.MultiIndex):

    # 야후파이낸스 종목 여러 개 → MultiIndex

    # 구조 확인: 보통 ('AAPL', 'Adj Close'), ...

    # level 0: 티커, level 1: 속성

    if "Adj Close" in data.columns.get_level_values(1):

        # 각 티커별 "Adj Close"만 추출

        adj_close = pd.DataFrame({ticker: data[ticker]['Adj Close'] for ticker in top10 if ticker in data.columns.get_level_values(0)})

    elif "Close" in data.columns.get_level_values(1):

        adj_close = pd.DataFrame({ticker: data[ticker]['Close'] for ticker in top10 if ticker in data.columns.get_level_values(0)})

    else:

        st.error("데이터에서 'Adj Close' 또는 'Close' 값을 찾을 수 없습니다.")

        st.write(data.head())

        st.stop()

else:

    # 단일 컬럼 (종목 1개 등) 혹은 Wide-Format

    if "Adj Close" in data.columns:

        adj_close = data["Adj Close"].to_frame()

    elif "Close" in data.columns:

        adj_close = data["Close"].to_frame()

    else:

        st.error("데이터에서 'Adj Close' 또는 'Close' 값을 찾을 수 없습니다.")

        st.write(data.head())

        st.stop()

adj_close = adj_close.fillna(method="ffill")

fig = go.Figure()

for ticker, name in top10.items():

    if ticker in adj_close.columns:

        fig.add_trace(go.Scatter(

            x=adj_close.index, y=adj_close[ticker], mode='lines', name=name

        ))

fig.update_layout(

    title='글로벌 시가총액 TOP10 기업 주가 변화 (최근 1년)',

    xaxis_title='날짜',

    yaxis_title='종가(USD)',

    legend_title='기업명',

    height=600

)

st.plotly_chart(fig, use_container_width=True)
