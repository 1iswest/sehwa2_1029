import streamlit as st
import pandas as pd
import plotly.express as px
import io
import requests

st.set_page_config(page_title="의료기관 분포 불균형 분석", layout="wide")
st.title("🏥 독거노인 인구 대비 의료기관 분포 불균형 분석")

st.markdown("""
두 개의 파일을 업로드하면 **독거노인 인구수 대비 의료기관 분포의 불균형**을 시각적으로 확인할 수 있습니다.
""")

st.sidebar.header("📂 데이터 업로드")
elder_file = st.sidebar.file_uploader("독거노인 인구 파일 (xlsx, csv)", type=["xlsx", "csv"])
facility_file = st.sidebar.file_uploader("의료기관 파일 (csv, xlsx)", type=["csv", "xlsx"])

# --------- 파일 읽기 함수 ----------
def read_any(file):
    if file is None:
        return None
    try:
        if file.name.endswith(".csv"):
            # BytesIO로부터 문자열 디코딩 후 처리
            raw = file.read()
            try:
                return pd.read_csv(io.BytesIO(raw), encoding="utf-8")
            except UnicodeDecodeError:
                return pd.read_csv(io.BytesIO(raw), encoding="cp949")
        elif file.name.endswith(".xlsx"):
            return pd.read_excel(file)
    except Exception as e:
        st.error(f"파일 읽기 오류: {e}")
        return None

# 파일 읽기
df_elder = read_any(elder_file)
df_facility = read_any(facility_file)

if df_elder is not None and df_facility is not None:
    st.success("✅ 두 파일 모두 업로드 성공!")

    st.subheader("📊 데이터 미리보기")
    st.write("**독거노인 인구 데이터 (상위 5행)**")
    st.dataframe(df_elder.head())
    st.write("**의료기관 데이터 (상위 5행)**")
    st.dataframe(df_facility.head())

    # ---- 지역 컬럼 자동 탐색 ----
    elder_region_col = [c for c in df_elder.columns if "시도" in c or "지역" in c or "행정구역" in c]
    facility_region_col = [c for c in df_facility.columns if "시도" in c or "주소" in c or "지역" in c]
    elder_region = elder_region_col[0] if elder_region_col else st.selectbox("독거노인 지역 컬럼 선택", df_elder.columns)
    facility_region = facility_region_col[0] if facility_region_col else st.selectbox("의료기관 지역 컬럼 선택", df_facility.columns)

    # ---- 데이터 전처리 ----
    df_elder["지역"] = df_elder[elder_region].astype(str).str[:2]  # 시도 단위로 통일
    df_facility["지역"] = df_facility[facility_region].astype(str).str[:2]

    # 의료기관 수 계산
    df_facility_grouped = df_facility.groupby("지역").size().reset_index(name="의료기관_수")

    # 병합
    df = pd.merge(df_elder, df_facility_grouped, on="지역", how="inner")

    # 독거노인가구비율 또는 인구수 자동 탐색
    target_col = None
    for c in df_elder.columns:
        if "독거" in c and ("비율" in c or "인구" in c):
            target_col = c
            break
    if target_col is None:
        target_col = st.selectbox("독거노인 인구 컬럼 선택", df_elder.columns)

    df["의료기관_비율"] = df["의료기관_수"] / (df[target_col] + 1e-9)

    st.subheader("📈 지역별 요약")
    st.dataframe(df[["지역", target_col, "의료기관_수", "의료기관_비율"]])

    # ---- GeoJSON 로드 ----
    geojson_url = "https://raw.githubusercontent.com/southkorea/southkorea-maps/master/kostat/2013/json/skorea_provinces_geo_simple.json"
    geojson = requests.get(geojson_url).json()

    # ---- 지도 시각화 ----
    fig = px.choropleth(
        df,
        geojson=geojson,
        locations="지역",
        featureidkey="properties.name",
        color="의료기관_비율",
        color_continuous_scale="YlOrRd",
        title="시도별 독거노인 인구 대비 의료기관 분포 비율"
    )
    fig.update_geos(fitbounds="locations", visible=False)
    st.plotly_chart(fig, use_container_width=True)

else:
    st.info("👆 두 개의 데이터를 모두 업로드해주세요.")
