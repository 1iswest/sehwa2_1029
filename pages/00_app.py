import streamlit as st
import pandas as pd
import plotly.express as px
import io
import requests

st.set_page_config(page_title="독거노인 대비 의료기관 분포 분석", layout="wide")
st.title(" 지역별 독거노인 인구 대비 의료기관 분포 분석")

st.markdown("""
이 앱은 **지역별 독거노인 인구수**와 **의료기관 수**를 비교하여
얼마나 고르게 분포되어 있는지를 지도 위에서 시각화합니다.

- **빨간색**: 독거노인 인구 대비 의료기관이 **부족한 지역**
- **초록색**: 독거노인 인구 대비 의료기관이 **많은 지역**
""")

# -----------------------------
# 파일 업로드
# -----------------------------
st.sidebar.header(" 데이터 업로드")
# 파일 업로드는 Streamlit 실행 환경에서 진행되므로, 여기서는 그대로 유지합니다.
elder_file = st.sidebar.file_uploader("독거노인 인구 파일 (CSV 또는 XLSX)", type=["csv", "xlsx"])
facility_file = st.sidebar.file_uploader("의료기관 데이터 파일 (CSV 또는 XLSX)", type=["csv", "xlsx"])

# -----------------------------
# 파일 읽기 함수
# -----------------------------
def read_any(file):
    if file is None:
        return None
    try:
        if file.name.endswith(".csv"):
            raw = file.read()
            try:
                # 1. 원본 코드: UTF-8 시도
                return pd.read_csv(io.BytesIO(raw), encoding="utf-8")
            except UnicodeDecodeError:
                # 2. 원본 코드: cp949 재시도
                return pd.read_csv(io.BytesIO(raw), encoding="cp949")
        elif file.name.endswith(".xlsx"):
            # 3. XLSX 파일 처리 (첫 번째 시트 사용)
            return pd.read_excel(file)
    except Exception as e:
        st.error(f"파일 읽기 오류: {e}")
        return None

# -----------------------------
# 파일 로드
# -----------------------------
df_elder = read_any(elder_file)
df_facility = read_any(facility_file)

if df_elder is not None and df_facility is not None:
    st.success(" 두 파일 모두 업로드 완료!")

    # -----------------------------
    # 데이터 전처리: 독거노인 데이터 (df_elder)
    # 헤더 문제 해결 (두 줄짜리 헤더 처리)
    # -----------------------------
    # '행정구역별'이 포함된 첫 번째 행이 인덱스가 아니거나, 실제 데이터 위에 두 줄 헤더가 있는 경우
    if df_elder.columns[0] == '행정구역별' and '2024' in df_elder.columns:
        # 두 줄 헤더를 한 줄로 결합하거나, 실제 컬럼명이 있는 행을 헤더로 지정
        # (업로드된 파일 미리보기 기준)
        new_columns = []
        for col in df_elder.columns:
            if col == '행정구역별':
                new_columns.append('지역')
            else:
                # 두 번째 행의 값(실제 측정 지표)을 컬럼명으로 사용
                new_col_name = df_elder.loc[0, col] if 0 in df_elder.index else col
                new_columns.append(new_col_name)

        # 실제 컬럼명이 있는 행을 헤더로 다시 읽거나, 첫 번째 데이터 행부터 시작하도록 처리
        df_elder.columns = df_elder.iloc[0] # 첫 번째 데이터 행을 새 컬럼으로 지정
        df_elder = df_elder[1:].reset_index(drop=True) # 그 행을 제외하고 데이터 시작

        # 컬럼 이름 재설정 (전처리가 필요할 수 있음. 임시로 컬럼 번호 사용)
        # 업로드된 파일의 구조에 맞춰 '행정구역별'을 '지역'으로 변경
        if '행정구역별' in df_elder.columns:
            df_elder = df_elder.rename(columns={'행정구역별': '지역'})
        
        # '65세이상 1인가구(A) (가구)' 컬럼을 직접 찾아 사용
        target_col_candidates = [c for c in df_elder.columns if '1인가구' in c and '65세이상' in c]
        if target_col_candidates:
            target_col = target_col_candidates[0]
        else:
            # 자동 탐색 실패 시 수동 선택
            st.error("독거노인 인구 컬럼을 자동으로 찾을 수 없습니다. 수동 선택을 진행합니다.")
            target_col = st.selectbox("독거노인 인구 컬럼 선택", df_elder.columns)

    else:
        # 기존 코드의 컬럼 자동 탐색 로직 사용
        target_col = None
        for c in df_elder.columns:
            if "독거" in c and ("비율" not in c) and ("인구" in c or "가구" in c):
                target_col = c
                break
        if target_col is None:
            st.error("독거노인 인구 컬럼을 자동으로 찾을 수 없습니다. 수동 선택을 진행합니다.")
            target_col = st.selectbox("독거노인 인구 컬럼 선택", df_elder.columns)
            
        # 기존 코드의 지역 컬럼 자동 탐색 로직 사용
        elder_region_col = [c for c in df_elder.columns if "시도" in c or "지역" in c or "행정구역" in c]
        elder_region = elder_region_col[0] if elder_region_col else st.selectbox("독거노인 지역 컬럼 선택", df_elder.columns)
        df_elder = df_elder.rename(columns={elder_region: '지역'})

    # -----------------------------
    # 데이터 전처리: 의료기관 데이터 (df_facility)
    # -----------------------------
    facility_region_col = [c for c in df_facility.columns if "시도" in c or "주소" in c or "지역" in c or "소재지전체주소" in c]
    facility_region = facility_region_col[0] if facility_region_col else st.selectbox("의료기관 지역 컬럼 선택", df_facility.columns)


    st.subheader(" 독거노인 인구 데이터 미리보기 (전처리 후)")
    st.dataframe(df_elder.head())

    st.subheader(" 의료기관 데이터 미리보기")
    st.dataframe(df_facility.head())

    # -----------------------------
    # 데이터 전처리 및 지역명 자동 변환
    # -----------------------------
    # 독거노인 데이터 (지역 컬럼 이름 통일: 이미 위에서 '지역'으로 변경되었거나, 셀렉트박스로 선택됨)
    if '지역' not in df_elder.columns:
        st.error("독거노인 데이터에 '지역' 컬럼이 존재하지 않습니다. 수동 선택을 다시 확인해주세요.")
    
    # 의료기관 데이터 (주소 컬럼에서 시/도 추출)
    df_facility["지역"] = df_facility[facility_region].astype(str).str[:2]
    
    # 지역명 자동 변환 (GeoJSON 매칭 보정)
    def normalize_region(name):
        name = str(name).strip()
        mapping = {
            "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
            "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
            "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
            "전북": "전북특별자치도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도",
            "제주": "제주특별자치도"
        }
        # 약칭 매칭
        for key, val in mapping.items():
            if name.startswith(key):
                return val
        return name

    # 독거노인 데이터의 '전국' 행 제거 및 지역 정규화
    df_elder = df_elder[df_elder['지역'] != '전국']
    df_elder["지역"] = df_elder["지역"].apply(normalize_region)
    df_facility["지역"] = df_facility["지역"].apply(normalize_region)
    
    # -----------------------------
    # 의료기관 수 계산
    # -----------------------------
    df_facility_grouped = df_facility.groupby("지역").size().reset_index(name="의료기관_수")

    # 독거노인 인구 컬럼 수치형으로 변환
    df_elder[target_col] = pd.to_numeric(df_elder[target_col], errors='coerce').fillna(0)

    # 병합
    df = pd.merge(df_elder, df_facility_grouped, on="지역", how="inner")

    # *********************************
    # 비율 계산 수정 (핵심 수정)
    # 의료기관 비율 = 의료기관 수 / 독거노인 수 (1e-9는 0으로 나누는 오류 방지)
    # *********************************
    df["의료기관_비율"] = df["의료기관_수"] / (df[target_col].replace(0, 1) + 1e-9)

    st.subheader(" 병합 결과 데이터")
    st.dataframe(df[["지역", target_col, "의료기관_수", "의료기관_비율"]])

    # -----------------------------
    # 지도 시각화
    # -----------------------------
    geojson_url = "https://raw.githubusercontent.com/southkorea/southkorea-maps/master/kostat/2013/json/skorea_provinces_geo_simple.json"
    geojson = requests.get(geojson_url).json()

    # GeoJSON에 '강원도'와 '전라북도'가 구 명칭으로 되어있을 수 있으므로 임시 보정
    for feature in geojson['features']:
        if feature['properties']['name'] == '강원도':
            feature['properties']['name'] = '강원특별자치도'
        if feature['properties']['name'] == '전라북도':
            feature['properties']['name'] = '전북특별자치도'

    fig = px.choropleth(
        df,
        geojson=geojson,
        locations="지역",
        featureidkey="properties.name",
        color="의료기관_비율",
        color_continuous_scale="RdYlGn", # 빨강(부족) → 노랑(보통) → 초록(많음)
        title="시도별 독거노인 인구 대비 의료기관 분포",
        # 비율의 최대/최소값을 사용하여 색상 범위 설정
        range_color=(df["의료기관_비율"].min(), df["의료기관_비율"].max()),
        hover_data={
            "지역": True, 
            target_col: True, 
            "의료기관_수": True,
            "의료기관_비율": ':.4f' # 소수점 넷째 자리까지 표시
        }
    )

    fig.update_geos(
        fitbounds="locations",
        visible=False,
        bgcolor="#f5f5f5"
    )

    st.plotly_chart(fig, use_container_width=True)

else:
    st.info(" 사이드바에서 두 개의 파일을 모두 업로드해주세요.")
