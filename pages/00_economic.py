import streamlit as st
import pandas as pd
import plotly.express as px
import io
import requests

st.set_page_config(page_title="독거노인 대비 의료기관 분포 분석", layout="wide")
st.title("🏥 지역별 독거노인 인구 대비 의료기관 분포 분석")

st.markdown("""
이 앱은 **지역별 독거노인 인구수**와 **의료기관 수**를 비교하여  
**독거노인 1000명당 의료기관 수**를 계산하고 지도 위에서 시각화합니다.
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
    # 🔠 지역 컬럼 자동 인식 및 선택 (유연성 확보)
    # -----------------------------
    elder_cols = df_elder.columns.tolist()
    facility_cols = df_facility.columns.tolist()
    
    # 지역 컬럼 자동 인식 로직
    elder_region_col = next((c for c in elder_cols if "시도" in c or "행정구역" in c), elder_cols[0])
    facility_region_col = next((c for c in facility_cols if "시도" in c or "주소" in c), facility_cols[0])

    # 사용자에게 지역 컬럼 선택 UI를 명시적으로 제공
    st.subheader("🎯 데이터프레임 컬럼 선택")
    
    col1, col2 = st.columns(2)
    with col1:
        elder_region = st.selectbox(
            "독거노인 인구 데이터의 지역 컬럼 선택 (예: 행정구역별, 시도명)", 
            elder_cols, 
            index=elder_cols.index(elder_region_col) if elder_region_col in elder_cols else 0
        )
    with col2:
        facility_region = st.selectbox(
            "의료기관 데이터의 지역 컬럼 선택 (예: 주소, 시도명)", 
            facility_cols, 
            index=facility_cols.index(facility_region_col) if facility_region_col in facility_cols else 0
        )
    
    # -----------------------------
    # 1. 독거노인 인구 (숫자) 컬럼 선택 (오류 발생 핵심 해결)
    # -----------------------------
    # 인구 컬럼은 사용자가 반드시 수동으로 선택하도록 유도하여 '행정구역별'과 같은 문자열 컬럼 선택 오류를 방지합니다.
    target_col = st.selectbox(
        "**[필수]** 독거노인 인구수 또는 비율 컬럼 선택 (반드시 **숫자** 데이터여야 합니다)", 
        [c for c in elder_cols if c != elder_region], # 지역 컬럼 제외
        index=0
    )

    # -----------------------------
    # 🧹 데이터 전처리 (시/도 레벨로 통일)
    # -----------------------------
    try:
        # 시도 레벨로 통일하기 위해 앞 2글자만 사용 (예: '서울특별시' -> '서울')
        df_elder["지역"] = df_elder[elder_region].astype(str).str[:2]
        df_facility["지역"] = df_facility[facility_region].astype(str).str[:2]
    except Exception as e:
        st.error(f"지역 컬럼 전처리 오류: 선택하신 컬럼 ({elder_region}, {facility_region})의 데이터 형식이 올바른 지역 이름이 아닐 수 있습니다. 오류: {e}")
        st.stop()
        
    # -----------------------------
    # 2. 독거노인 인구 데이터 타입 안전성 확보 및 집계
    # -----------------------------
    try:
        # 선택된 인구 컬럼의 데이터를 강제로 숫자(float)로 변환합니다. 변환 불가능한 값은 0으로 처리합니다.
        df_elder[target_col + '_NUMERIC'] = pd.to_numeric(df_elder[target_col], errors='coerce').fillna(0)
        
        # 시/도('지역')별로 독거노인 인구수 총합을 계산합니다.
        df_elder_grouped = df_elder.groupby("지역")[target_col + '_NUMERIC'].sum().reset_index(name="독거노인_총인구")
        
    except Exception as e:
        st.error(f"독거노인 인구 컬럼 변환 및 집계 오류: 선택하신 컬럼 ({target_col})이 숫자로 변환되지 않습니다. 인구수/비율이 맞는 숫자로 된 컬럼을 선택해주세요.")
        st.stop()


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
    
    if df.empty:
        st.error("데이터 병합 결과가 비어있습니다. '지역' 컬럼에서 추출된 시/도 값이 일치하지 않는 것 같습니다. '주소' 또는 '행정구역' 컬럼이 올바른지 확인해주세요.")
        st.stop()
        
    # 안전한 인구수 컬럼을 가져옵니다.
    safe_population = df["독거노인_총인구"]
    
    # 최종 비율 계산: 독거노인 1000명당 의료기관 수
    # 0으로 나누는 오류 방지 및 비율을 1000명 기준으로 조정 (시각화 명확성)
    df["의료기관_비율"] = (df["의료기관_수"] / (safe_population + 1e-9)) * 1000
    
    # 최종 결과 데이터프레임
    df_result = df.rename(columns={"독거노인_총인구": f"독거노인_총인구(선택: {target_col})"})

    st.subheader("📈 병합 결과 데이터 (독거노인 1000명당 의료기관 수)")
    st.dataframe(df_result[["지역", f"독거노인_총인구(선택: {target_col})", "의료기관_수", "의료기관_비율"]])

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
        title="시도별 독거노인 인구 1000명당 의료기관 분포",
        hover_name="지역",
        hover_data={
            f"독거노인_총인구(선택: {target_col})": ':,.0f', 
            "의료기관_수": True, 
            "의료기관_비율": ':.2f',
            "지역": False # 지역 이름은 hover_name으로 충분
        } 
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
