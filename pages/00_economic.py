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

if df_elder is not None and df_facility is not None:
    st.success("✅ 두 파일 모두 업로드 완료!")

    st.subheader("👵 독거노인 인구 데이터 미리보기")
    st.dataframe(df_elder.head())

    st.subheader("🏥 의료기관 데이터 미리보기")
    st.dataframe(df_facility.head())

    # -----------------------------
    # 🔠 지역 컬럼 자동 인식 및 선택
    # -----------------------------
    # 독거노인 데이터의 지역 컬럼을 자동 인식
    elder_region_col = [c for c in df_elder.columns if "시도" in c or "지역" in c or "행정구역" in c]
    # 의료기관 데이터의 지역 컬럼을 자동 인식 (주소 포함)
    facility_region_col = [c for c in df_facility.columns if "시도" in c or "주소" in c or "지역" in c]

    # 인식된 컬럼이 없으면 사용자에게 선택권을 줍니다.
    elder_region = elder_region_col[0] if elder_region_col else st.selectbox("독거노인 지역 컬럼 선택", df_elder.columns)
    facility_region = facility_region_col[0] if facility_region_col else st.selectbox("의료기관 지역 컬럼 선택", df_facility.columns)

    # -----------------------------
    # 🧹 데이터 전처리
    # -----------------------------
    # 시도 레벨로 통일하기 위해 앞 2글자만 사용
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
    
    # 자동 탐색 실패 시 사용자에게 선택하도록 함
    if target_col is None:
        st.warning("독거노인 인구 컬럼을 자동으로 찾지 못했습니다. 올바른 인구수 컬럼을 선택해주세요.")
        # 사용자가 선택할 때까지 대기
        target_col = st.selectbox("독거노인 인구 컬럼 선택", df_elder.columns)

    # 숫자 변환 안전 처리 (독거노인 인구 컬럼)
    # 숫자로 변환할 수 없는 값은 NaN으로 만들고, 0으로 채웁니다.
    df_elder[target_col] = pd.to_numeric(df_elder[target_col], errors='coerce').fillna(0)

    # 병합
    df = pd.merge(df_elder, df_facility_grouped, on="지역", how="inner")
    
    # FIX: 0으로 나누는 오류 방지 및 타입 안정성 확보
    # target_col이 숫자가 아닌 문자열("행정구역별")로 잘못 선택되어도 안전하게 처리되도록
    # pd.to_numeric을 사용해 최종적으로 숫자 타입임을 보장합니다.
    safe_population = pd.to_numeric(df[target_col], errors='coerce').fillna(0)
    
    # 0으로 나누는 오류를 방지하기 위해 분모에 아주 작은 값(1e-9)을 더합니다.
    df["의료기관_비율"] = df["의료기관_수"] / (safe_population + 1e-9)

    st.subheader("📈 병합 결과 데이터")
    # 결과 데이터프레임을 시각화합니다.
    st.dataframe(df[["지역", target_col, "의료기관_수", "의료기관_비율"]])

    # -----------------------------
    # 🗺️ 지도 시각화
    # -----------------------------
    # 시도 경계 지오제이슨 파일 로드
    geojson_url = "https://raw.githubusercontent.com/southkorea/southkorea-maps/master/kostat/2013/json/skorea_provinces_geo_simple.json"
    geojson = requests.get(geojson_url).json()

    # Plotly Choropleth 지도 생성
    fig = px.choropleth(
        df,
        geojson=geojson,
        locations="지역",
        featureidkey="properties.name", # 지도 데이터의 지역 이름 컬럼
        color="의료기관_비율",
        color_continuous_scale="YlOrRd", # 노란색-주황색-빨간색 스케일
        title="시도별 독거노인 인구 대비 의료기관 분포",
        hover_name="지역",
        hover_data={target_col: True, "의료기관_수": True, "지역": False, "의료기관_비율": ':.2f'} # 툴팁에 표시할 데이터
    )
    
    # 지도 영역을 대한민국 시도 경계에 맞게 조정
    fig.update_geos(
        fitbounds="locations", 
        visible=False,
        scope='asia',
        # 대한민국 중심으로 설정
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
