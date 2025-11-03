import streamlit as st
import pandas as pd
import plotly.express as px
import io
import requests

st.set_page_config(page_title="독거노인 대비 의료기관 분포 분석", layout="wide")
st.title("🏥 지역별 독거노인 인구 대비 의료기관 분포 분석")

st.markdown("""
이 앱은 **지역별 독거노인 인구수**와 **의료기관 수**를 비교하여  
얼마나 고르게 분포되어 있는지를 지도 위에서 시각화합니다.
""")

# -----------------------------
# 📂 데이터 업로드
# -----------------------------
st.sidebar.header("📂 데이터 업로드")
elder_file = st.sidebar.file_uploader("독거노인 인구 파일 (CSV 또는 XLSX)", type=["csv", "xlsx"])
facility_file = st.sidebar.file_uploader("의료기관 데이터 파일 (CSV 또는 XLSX)", type=["csv", "xlsx"])

# -----------------------------
# 🔍 파일 읽기 함수
# -----------------------------
def read_any(file):
    if file is None:
        return None
    try:
        if file.name.endswith(".csv"):
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

# -----------------------------
# 📊 파일 로드
# -----------------------------
df_elder = read_any(elder_file)
df_facility = read_any(facility_file)

if df_elder is not None and df_facility is not None:
    st.success("✅ 두 파일 모두 업로드 완료!")

    st.subheader("👵 독거노인 인구 데이터 미리보기")
    st.dataframe(df_elder.head())

    st.subheader("🏥 의료기관 데이터 미리보기")
    st.dataframe(df_facility.head())

    # -----------------------------
    # 🔠 지역 컬럼 자동 인식
    # -----------------------------
    elder_region_col = [c for c in df_elder.columns if "시도" in c or "지역" in c or "행정구역" in c]
    facility_region_col = [c for c in df_facility.columns if "시도" in c or "주소" in c or "지역" in c]

    elder_region = elder_region_col[0] if elder_region_col else st.selectbox("독거노인 지역 컬럼 선택", df_elder.columns)
    facility_region = facility_region_col[0] if facility_region_col else st.selectbox("의료기관 지역 컬럼 선택", df_facility.columns)

    # -----------------------------
    # 🧹 데이터 전처리
    # -----------------------------
    df_elder["지역"] = df_elder[elder_region].astype(str).str[:2]
    df_facility["지역"] = df_facility[facility_region].astype(str).str[:2]

    # 의료기관 수 계산
    df_facility_grouped = df_facility.groupby("지역").size().reset_index(name="의료기관_수")

    # 독거노인 인구 컬럼 탐색
    target_col = None
    for c in df_elder.columns:
        if "독거" in c and ("비율" in c or "인구" in c):
            target_col = c
            break
    if target_col is None:
        target_col = st.selectbox("독거노인 인구 컬럼 선택", df_elder.columns)

    # -----------------------------
    # 🛡 안전한 숫자 변환
    # -----------------------------
    df_elder[target_col] = pd.to_numeric(
        df_elder[target_col].astype(str).str.replace(",", "").str.strip(),
        errors="coerce"  # 변환 불가 값은 NaN
    ).fillna(0)  # NaN → 0

    # -----------------------------
    # 🔗 데이터 병합
    # -----------------------------
    df = pd.merge(df_elder, df_facility_grouped, on="지역", how="inner")
    df["의료기관_비율"] = df["의료기관_수"] / (df[target_col] + 1e-9)

    st.subheader("📈 병합 결과 데이터")
    st.dataframe(df[["지역", target_col, "의료기관_수", "의료기관_비율"]])

    # -----------------------------
    # 🗺 지도 시각화
    # -----------------------------
    geojson_url = "https://raw.githubusercontent.com/southkorea/southkorea-maps/master/kostat/2013/json/skorea_provinces_geo_simple.json"
    geojson = requests.get(geojson_url).json()

    # 필요시 지역 이름 매핑
    # ex: '서울' -> '서울특별시', '부산' -> '부산광역시', 등
    region_mapping = {
        "서울": "서울", "부산": "부산", "대구": "대구", "인천": "인천",
        "광주": "광주", "대전": "대전", "울산": "울산", "세종": "세종",
        "경기": "경기", "강원": "강원", "충북": "충북", "충남": "충남",
        "전북": "전북", "전남": "전남", "경북": "경북", "경남": "경남", "제주": "제주"
    }
    df["지역"] = df["지역"].map(region_mapping)

    fig = px.choropleth(
        df,
        geojson=geojson,
        locations="지역",
        featureidkey="properties.name",
        color="의료기관_비율",
        color_continuous_scale="YlOrRd",
        title="시도별 독거노인 인구 대비 의료기관 분포"
    )
    fig.update_geos(fitbounds="locations", visible=False)
    st.plotly_chart(fig, use_container_width=True)

else:
    st.info("👆 사이드바에서 두 개의 파일을 모두 업로드해주세요.")
