import streamlit as st
import pandas as pd
import plotly.express as px
import json

st.set_page_config(page_title="지역별 복지시설 지도 분석", layout="wide")
st.title("지역별 독거노인 대비 시설 지도 분석")
st.markdown("""
업로드한 CSV 데이터를 기반으로, 각 지역별 독거노인 인구 대비 병원/약국/복지시설 분포를 지도 위 색상으로 확인할 수 있습니다.
""")

# 파일 업로드
st.sidebar.header("CSV 파일 업로드")
uploaded_file = st.sidebar.file_uploader("지역별 데이터 CSV 파일 선택", type=["csv"])

if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file)
        st.success("파일 업로드 성공!")
        st.subheader("데이터 미리보기")
        st.dataframe(df.head())

        expected_columns = ["지역", "독거노인_인구수", "병원_수", "약국_수", "복지시설_수"]
        if not all(col in df.columns for col in expected_columns):
            st.error(f"CSV 파일에는 다음 컬럼이 필요합니다: {expected_columns}")
        else:
            # 비율 계산
            df["병원_비율"] = df["병원_수"] / df["독거노인_인구수"]
            df["약국_비율"] = df["약국_수"] / df["독거노인_인구수"]
            df["복지시설_비율"] = df["복지시설_수"] / df["독거노인_인구수"]

            st.subheader("지역별 시설 대비 독거노인 비율")
            st.dataframe(df[["지역", "병원_비율", "약국_비율", "복지시설_비율"]])

            # Choropleth 지도 시각화
            st.subheader("지도 기반 시각화")

            # 사용자 선택
            facility_option = st.selectbox("시각화할 시설 선택", ["병원_비율", "약국_비율", "복지시설_비율"], index=0)

            # 한국 시군구 GeoJSON 불러오기 (예시 URL)
            geojson_url = "https://raw.githubusercontent.com/southkorea/southkorea-maps/master/kostat/2013/json/skorea_municipalities_geo_simple.json"
            geojson = json.load(open("skorea_municipalities_geo_simple.json", "r", encoding="utf-8"))

            # 지도 그리기
            fig = px.choropleth(
                df,
                geojson=geojson,
                locations="지역",
                featureidkey="properties.name",  # GeoJSON에서 지역 이름 key
                color=facility_option,
                color_continuous_scale="YlOrRd",
                labels={facility_option: "시설 대비 독거노인 비율"},
                title=f"지역별 {facility_option} 분포"
            )
            fig.update_geos(fitbounds="locations", visible=False)
            st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"파일 처리 중 오류 발생: {e}")
else:
    st.info("CSV 파일을 업로드하면 분석을 시작할 수 있습니다.")
