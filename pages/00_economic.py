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
# 📂 파일 업로드
# -----------------------------
st.sidebar.header("📁 데이터 업로드")
elder_file = st.sidebar.file_uploader("독거노인 인구 파일 (CSV 또는 XLSX)", type=["csv", "xlsx"])
facility_file = st.sidebar.file_uploader("의료기관 데이터 파일 (CSV 또는 XLSX)", type=["csv", "xlsx"])

# -----------------------------
# 🔍 파일 읽기 함수
# -----------------------------
def read_any(file):
    """CSV 또는 XLSX 파일을 읽어 DataFrame으로 반환합니다."""
    if file is None:
        return None
    try:
        if file.name.endswith(".csv"):
            raw = file.read()
            # UTF-8로 시도 후, 실패 시 CP949로 재시도
            try:
                return pd.read_csv(io.BytesIO(raw), encoding="utf-8")
            except UnicodeDecodeError:
                return pd.read_csv(io.BytesIO(raw), encoding="cp949")
        elif file.name.endswith(".xlsx"):
            return pd.read_excel(file)
    except Exception as e:
        # 오류 발생 시 사용자에게 알리고 None 반환
        st.error(f"파일 읽기 오류: {e}")
        return None

# -----------------------------
# 📊 파일 로드
# -----------------------------
df_elder = read_any(elder_file)
df_facility = read_any(facility_file)

# -----------------------------
# 💡 메인 로직 시작
# -----------------------------
if df_elder is not None and df_facility is not None:
    st.success("✅ 두 파일 모두 업로드 완료!")

    st.subheader("👵 독거노인 인구 데이터 미리보기")
    st.dataframe(df_elder.head())

    st.subheader("🏥 의료기관 데이터 미리보기")
    st.dataframe(df_facility.head())

    # -----------------------------
    # 🔠 지역 컬럼 자동 인식 및 선택
    # -----------------------------
    elder_region_col = [c for c in df_elder.columns if "시도" in c or "지역" in c or "행정구역" in c]
    facility_region_col = [c for c in df_facility.columns if "시도" in c or "주소" in c or "지역" in c]

    # 인식된 컬럼이 없으면 사용자에게 선택권을 줍니다.
    elder_region = elder_region_col[0] if elder_region_col else st.selectbox("독거노인 지역 컬럼 선택 (시/도, 시/군/구 포함)", df_elder.columns)
    facility_region = facility_region_col[0] if facility_region_col else st.selectbox("의료기관 지역 컬럼 선택 (주소 포함)", df_facility.columns)

    # -----------------------------
    # 🧹 데이터 전처리 (시/도 레벨로 통일)
    # -----------------------------
    # 시도 레벨로 통일하기 위해 앞 2글자만 사용 (예: '서울특별시' -> '서울')
    df_elder["지역"] = df_elder[elder_region].astype(str).str[:2]
    df_facility["지역"] = df_facility[facility_region].astype(str).str[:2]

    # -----------------------------
    # 1. 독거노인 인구 컬럼 선택
    # -----------------------------
    target_col = None
    for c in df_elder.columns:
        # '독거'를 포함하고 '비율'이나 '인구'를 포함하는 컬럼 자동 탐색
        if "독거" in c and ("비율" in c or "인구" in c):
            target_col = c
            break
    
    # 자동 탐색 실패 시 사용자에게 선택하도록 함
    if target_col is None:
        st.warning("독거노인 인구수(비율) 컬럼을 자동으로 찾지 못했습니다. 올바른 숫자 컬럼을 선택해주세요.")
        target_col = st.selectbox("독거노인 인구 컬럼 선택", df_elder.columns)

    # 숫자 변환 안전 처리: 사용자가 선택한 컬럼을 숫자로 변환하고 NaN은 0으로 처리
    df_elder[target_col] = pd.to_numeric(df_elder[target_col], errors='coerce').fillna(0)

    # -----------------------------
    # 2. 독거노인 인구 데이터 집계 (CRITICAL FIX)
    # -----------------------------
    # 시/도('지역')별로 독거노인 인구수 총합을 계산합니다.
    df_elder_grouped = df_elder.groupby("지역")[target_col].sum().reset_index(name="독거노인_총인구")

    # -----------------------------
    # 3. 의료기관 데이터 집계
    # -----------------------------
    # 시/도('지역')별로 의료기관 수를 계산합니다.
    df_facility_grouped = df_facility.groupby("지역").size().reset_index(name="의료기관_수")

    # -----------------------------
    # 4. 데이터 병합 및 비율 계산
    # -----------------------------
    # 집계된 두 데이터프레임을 병합
    df = pd.merge(df_elder_grouped, df_facility_grouped, on="지역", how="inner")
    
    # 안전한 인구수 컬럼을 가져옵니다.
    safe_population = df["독거노인_총인구"]
    
    # 0으로 나누는 오류 방지: 독거노인 인구 1명당 의료기관 수를 계산합니다.
    df["의료기관_비율"] = df["의료기관_수"] / (safe_population + 1e-9)
    
    # 최종 결과 데이터프레임
    df_result = df.rename(columns={"독거노인_총인구": f"독거노인_총인구({target_col})"})

    st.subheader("📈 병합 결과 데이터")
    st.dataframe(df_result[["지역", f"독거노인_총인구({target_col})", "의료기관_수", "의료기관_비율"]])

    # -----------------------------
    # 🗺️ 지도 시각화
    # -----------------------------
    # 시도 경계 지오제이슨 파일 로드
    geojson_url = "https://raw.githubusercontent.com/southkorea/southkorea-maps/master/kostat/2013/json/skorea_provinces_geo_simple.json"
    geojson = requests.get(geojson_url).json()

    # Plotly Choropleth 지도 생성
    fig = px.choropleth(
        df_result,
        geojson=geojson,
        locations="지역",
        featureidkey="properties.name", # 지도 데이터의 지역 이름 컬럼
        color="의료기관_비율",
        color_continuous_scale="YlOrRd", # 노란색-주황색-빨간색 스케일
        title="시도별 독거노인 인구 대비 의료기관 분포",
        hover_name="지역",
        hover_data={f"독거노인_총인구({target_col})": True, "의료기관_수": True, "지역": False, "의료기관_비율": ':.2f'} # 툴팁에 표시할 데이터
    )
    
    # 지도 영역을 대한민국 시도 경계에 맞게 조정
    fig.update_geos(
        fitbounds="locations", 
        visible=False,
        scope='asia',
        center={"lat": 36, "lon": 127.8} 
    )
    # 레이아웃 업데이트 (제목 중앙 정렬)
    fig.update_layout(
        margin={"r":0,"t":50,"l":0,"b":0},
        title_x=0.5
    )
    
    st.plotly_chart(fig, use_container_width=True)

else:
    st.info("👆 사이드바에서 두 개의 파일을 모두 업로드해주세요.")
