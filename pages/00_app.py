import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import requests
import io

st.set_page_config(page_title="독거노인 대비 의료기관 분포 분석", layout="wide")
st.title("🏥 지역별 독거노인 인구 대비 의료기관 분포 분석")

st.markdown("""
이 앱은 **지역별 독거노인 인구수**와 **의료기관 수**를 비교하여  
얼마나 고르게 분포되어 있는지를 지도 위에서 시각화합니다.

- 🟥 **빨간색**: 독거노인 인구 대비 의료기관이 **부족한 지역**  
- 🟩 **초록색**: 독거노인 인구 대비 의료기관이 **많은 지역**
""")

# -----------------------------
# 📂 파일 업로드
# -----------------------------
st.sidebar.header("📁 데이터 업로드")
elder_file = st.sidebar.file_uploader("독거노인 인구 파일 (xlsx)", type=["xlsx"])
facility_file = st.sidebar.file_uploader("의료기관 데이터 파일 (csv)", type=["csv"])

# -----------------------------
# 📊 데이터 불러오기
# -----------------------------
if elder_file and facility_file:
    try:
        # 독거노인 데이터 (첫 행이 실제 헤더)
        df_elder_raw = pd.read_excel(elder_file, header=None)
        df_elder_raw.columns = df_elder_raw.iloc[0]
        df_elder = df_elder_raw.iloc[1:].copy()

        df_elder = df_elder.rename(columns={
            "행정구역별": "지역",
            "2024.1": "독거노인_수"
        })
        df_elder["독거노인_수"] = pd.to_numeric(df_elder["독거노인_수"], errors="coerce").fillna(0)

        # 의료기관 데이터
        raw = facility_file.read()
        try:
            df_facility = pd.read_csv(io.BytesIO(raw), encoding="utf-8")
        except:
            df_facility = pd.read_csv(io.BytesIO(raw), encoding="cp949")

        # -----------------------------
        # 🧹 의료기관 주소에서 지역 추출
        # -----------------------------
        def extract_region(addr):
            if pd.isna(addr):
                return np.nan
            for name in ["서울특별시","부산광역시","대구광역시","인천광역시","광주광역시","대전광역시","울산광역시","세종특별자치시",
                         "경기도","강원도","충청북도","충청남도","전라북도","전라남도","경상북도","경상남도","제주특별자치도"]:
                if name[:2] in str(addr):
                    return name
            return np.nan

        if "소재지전체주소" in df_facility.columns:
            df_facility["지역"] = df_facility["소재지전체주소"].apply(extract_region)
        else:
            df_facility["지역"] = np.nan

        # -----------------------------
        # 🏥 의료기관 수 집계
        # -----------------------------
        df_facility_grouped = df_facility.groupby("지역").size().reset_index(name="의료기관_수")

        # -----------------------------
        # 📈 데이터 병합 및 비율 계산
        # -----------------------------
        df = pd.merge(df_elder, df_facility_grouped, on="지역", how="inner")
        df["독거노인_수"] = df["독거노인_수"].replace(0, np.nan)
        df["의료기관_비율"] = df["의료기관_수"] / df["독거노인_수"]

        st.success("✅ 데이터 병합 완료!")

        st.subheader("📋 병합 결과 미리보기")
        st.dataframe(df[["지역", "독거노인_수", "의료기관_수", "의료기관_비율"]])

        # -----------------------------
        # 🗺️ 지도 시각화
        # -----------------------------
        geojson_url = "https://raw.githubusercontent.com/southkorea/southkorea-maps/master/kostat/2013/json/skorea_provinces_geo_simple.json"
        geojson = requests.get(geojson_url).json()

        fig = px.choropleth(
            df,
            geojson=geojson,
            locations="지역",
            featureidkey="properties.name",
            color="의료기관_비율",
            color_continuous_scale="RdYlGn",
            range_color=(df["의료기관_비율"].min(), df["의료기관_비율"].max()),
            title="시도별 독거노인 인구 대비 의료기관 분포"
        )

        fig.update_geos(fitbounds="locations", visible=False)
        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"❌ 오류 발생: {e}")
else:
    st.info("👆 사이드바에서 두 개의 파일을 모두 업로드해주세요.")
