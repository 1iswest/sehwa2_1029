# app.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import requests
import io

st.set_page_config(page_title="지역별 복지시설 지도 분석 (강화판)", layout="wide")
st.title("지역별 독거노인 대비 복지시설·병원 지도 분석 (강화판)")

st.markdown("""
- 다양한 컬럼명과 파일형식(csv/xlsx)을 자동 인식하여 병합합니다.
- 시설 파일이 **이미 집계(병원_수 등)** 되어 있거나 **개별 시설 행(한 행=한 시설)** 인 경우 모두 처리합니다.
- `지역` 컬럼명이 다른 경우(예: 시도, 시군구, 시도명 등)에도 자동 매칭합니다.
""")

st.sidebar.header("CSV / XLSX 파일 업로드")
elder_file = st.sidebar.file_uploader("독거노인 인구 파일 업로드 (csv 또는 xlsx)", type=["csv", "xlsx"])
facility_file = st.sidebar.file_uploader("의료기관/복지시설 파일 업로드 (csv 또는 xlsx)", type=["csv", "xlsx"])

# 유틸: 파일 읽기 (csv/xlsx 자동)
def read_file(file):
    if file is None:
        return None
    if hasattr(file, "name") and file.name.lower().endswith(".xlsx"):
        return pd.read_excel(file)
    else:
        # csv: 인코딩 문제 대비
        try:
            return pd.read_csv(file)
        except Exception:
            file.seek(0)
            return pd.read_csv(file, encoding='cp949', errors='replace')

# 유틸: 가능한 지역 컬럼명 후보들(소문자 비교)
REGION_KEYWORDS = [
    "지역", "시도", "시군구", "시도명", "시군구명", "행정구역", "addr", "주소", "address",
    "sido", "gungu", "sigungu", "emd", "구", "군", "읍", "면"
]

# 유틸: 가능성 있는 독거노인/인구 컬럼
ELDER_KEYWORDS = ["독거", "노인", "노령", "인구", "가구", "수", "population"]

# 유틸: 시설 종류 키워드
HOSPITAL_KEYWORDS = ["병원", "의원", "요양병원", "의원급"]
PHARMACY_KEYWORDS = ["약국"]
WELFARE_KEYWORDS = ["복지", "복지관", "사회복지", "복지시설"]

def guess_region_col(df):
    cols = df.columns.tolist()
    lower_cols = [c.lower() for c in cols]
    # 1) exact match
    for kw in ["지역","시도","시군구","시도명","시군구명","행정구역"]:
        if kw in cols:
            return kw
        if kw in lower_cols:
            return cols[lower_cols.index(kw)]
    # 2) contains keyword
    for i, c in enumerate(lower_cols):
        for kw in REGION_KEYWORDS:
            if kw in c:
                return cols[i]
    # 3) fallback: first column
    return cols[0] if len(cols)>0 else None

def guess_elder_count_col(df):
    cols = df.columns.tolist()
    lower_cols = [c.lower() for c in cols]
    for i,c in enumerate(lower_cols):
        for kw in ELDER_KEYWORDS:
            if kw in c and ("수" in c or "명" in c or "인구" in c or "count" in c or "population" in c):
                return cols[i]
    # fallback: numeric column with largest sum
    numeric = df.select_dtypes(include=[np.number])
    if not numeric.empty:
        sums = numeric.sum(axis=0).sort_values(ascending=False)
        return sums.index[0]
    return None

def detect_aggregated_facility_cols(df):
    # 집계형이면 병원_수, 약국_수, 복지시설_수 같은 컬럼이 있어야 함
    cols = df.columns.tolist()
    lower = [c.lower() for c in cols]
    found = {}
    for kw, name in [(HOSPITAL_KEYWORDS, "병원_수"), (PHARMACY_KEYWORDS, "약국_수"), (WELFARE_KEYWORDS, "복지시설_수")]:
        for i,c in enumerate(lower):
            for k in kw:
                if k in c and ("수" in c or "cnt" in c or "count" in c or "num" in c):
                    found[name] = cols[i]
    # numeric columns named explicitly
    if "병원_수" in cols or "병원" in cols:
        # map known names to standardized
        pass
    return found

def count_facility_types_from_rows(df, region_col):
    # 시설 파일이 개별행(한 행=한 시설) 형태일 때 업종/종류 컬럼에서 병원/약국/복지 카운트
    cols_lower = [c.lower() for c in df.columns]
    # 업종 컬럼 찾기
    kind_col = None
    for i,c in enumerate(cols_lower):
        for kw in ["종별","업종","업태","구분","종류","명칭","개설명", "의료기관명"]:
            if kw in c:
                kind_col = df.columns[i]
                break
        if kind_col:
            break
    # 주소 지역 컬럼 (만약 지역 컬럼이 상세주소라면 시도/시군구 추출)
    addr_col = None
    for i,c in enumerate(cols_lower):
        if "주소" in c or "도로명" in c or "소재지" in c:
            addr_col = df.columns[i]
            break

    # normalize region strings for grouping
    tmp = df.copy()
    # if addr_col provided, try to extract 시도 or 시군구 using splitting by space
    if addr_col is not None and region_col not in tmp.columns:
        tmp[region_col] = tmp[addr_col].astype(str).str.split().str[0]  # 간단 추출 (시/도)
    else:
        tmp[region_col] = tmp[region_col].astype(str)

    # classify
    def classify_kind(x):
        s = str(x).lower()
        # 한글 키워드를 소문자로 검사
        for k in HOSPITAL_KEYWORDS:
            if k in s:
                return "병원"
        for k in PHARMACY_KEYWORDS:
            if k in s:
                return "약국"
        for k in WELFARE_KEYWORDS:
            if k in s:
                return "복지시설"
        # if contains '의원' but not '약국'
        if "의원" in s:
            return "병원"
        return "기타"

    if kind_col is None:
        # 업종 컬럼 없으면 전체를 '병원/약국/복지'로 구분 못 함 -> 전체 시설 수로만 집계
        grouped = tmp.groupby(region_col).size().reset_index(name="시설_총수")
        return grouped.rename(columns={region_col:"지역"})
    else:
        tmp["_kind_cls"] = tmp[kind_col].apply(classify_kind)
        grouped = tmp.groupby([region_col, "_kind_cls"]).size().unstack(fill_value=0).reset_index()
        grouped = grouped.rename(columns={region_col:"지역"})
        # 보장: 컬럼 이름 통일
        if "병원" not in grouped.columns: grouped["병원"] = 0
        if "약국" not in grouped.columns: grouped["약국"] = 0
        if "복지시설" not in grouped.columns: grouped["복지시설"] = 0
        # 몇몇 파일은 '의원'만 있어서 병원 수 계산이 '병원' 칼럼에 없을 수 있음 handled above
        return grouped[["지역","병원","약국","복지시설"]]

# 파일 읽기
df_elder = read_file(elder_file)
df_facility = read_file(facility_file)

if df_elder is None or df_facility is None:
    st.info("두 개의 파일을 모두 업로드해야 분석을 시작할 수 있습니다.")
else:
    try:
        st.subheader("업로드된 파일 정보 (자동 감지)")
        st.write("독거노인 파일 (상위 5행)")
        st.dataframe(df_elder.head())
        st.write("시설 파일 (상위 5행)")
        st.dataframe(df_facility.head())

        # 컬럼 자동 추정
        elder_region_col = guess_region_col(df_elder)
        elder_count_col = guess_elder_count_col(df_elder)

        facility_region_col = guess_region_col(df_facility)
        # 시설 파일이 이미 집계형인지 확인
        agg_cols_map = detect_aggregated_facility_cols(df_facility)

        st.write("자동 감지 결과:")
        st.write({
            "elder_region_col": elder_region_col,
            "elder_count_col": elder_count_col,
            "facility_region_col": facility_region_col,
            "aggregated_columns_found": agg_cols_map
        })

        # 표준 형태로 전처리: elder df -> 지역, 독거노인_인구수
        df_elder_proc = df_elder.copy()
        df_elder_proc = df_elder_proc.rename(columns={elder_region_col: "지역"})
        if elder_count_col is not None:
            df_elder_proc = df_elder_proc.rename(columns={elder_count_col: "독거노인_인구수"})
        else:
            # 숫자형 칼럼이 없으면 에러
            raise ValueError("독거 노인 인구를 나타내는 컬럼을 자동으로 찾을 수 없습니다. '독거' 또는 '인구'가 포함된 컬럼이 있어야 합니다.")

        # 시설 데이터 처리: 집계형이면 바로 사용, 아니면 행단위 집계로 변환
        if len(agg_cols_map) >= 1:
            # 가능한 매핑을 사용하여 standardized columns 생성
            df_fac_proc = df_facility.copy()
            # region col 보정
            if facility_region_col in df_fac_proc.columns:
                df_fac_proc = df_fac_proc.rename(columns={facility_region_col: "지역"})
            else:
                df_fac_proc["지역"] = df_fac_proc.iloc[:,0].astype(str)

            # 병원/약국/복지 컬럼이 어떤 이름인지 매핑해서 표준화
            # agg_cols_map 예: {"병원_수": "병원수컬럼명", ...}
            # 기본값 0
            df_fac_proc["병원_수"] = 0
            df_fac_proc["약국_수"] = 0
            df_fac_proc["복지시설_수"] = 0
            for std_col, orig in agg_cols_map.items():
                if orig in df_fac_proc.columns:
                    df_fac_proc[std_col] = pd.to_numeric(df_fac_proc[orig], errors='coerce').fillna(0).astype(int)
            # 만약 집계가 시도별이 아닐 수 있으니 시군구/시도 둘 다 대응
            df_fac_proc = df_fac_proc[["지역","병원_수","약국_수","복지시설_수"]]
            # 일부 파일은 여러 행(예: 시군구마다 속한 여러 행)으로 되어 있을 수 있으므로 groupby
            df_fac_proc = df_fac_proc.groupby("지역", as_index=False).sum()
        else:
            # 행단위(시설 목록) -> 카운트 집계
            # facility_region_col이 존재하지 않으면 시/도 추출을 시도
            region_col_name = facility_region_col if facility_region_col in df_facility.columns else None
            if region_col_name is None:
                # 시군구/주소 컬럼 찾아서 region 컬럼으로 사용
                # 우선 첫 번째 컬럼을 사용하되 경고
                region_col_name = df_facility.columns[0]
            df_fac_proc = count_facility_types_from_rows(df_facility, region_col=region_col_name)
            # rename to standard counts
            rename_map = {}
            if "병원" in df_fac_proc.columns:
                rename_map["병원"] = "병원_수"
            if "약국" in df_fac_proc.columns:
                rename_map["약국"] = "약국_수"
            if "복지시설" in df_fac_proc.columns:
                rename_map["복지시설"] = "복지시설_수"
            if "시설_총수" in df_fac_proc.columns:
                # 총수만 있을 경우 복지, 약국 등은 0
                df_fac_proc["병원_수"] = df_fac_proc["시설_총수"]
            df_fac_proc = df_fac_proc.rename(columns=rename_map)
            # 결측 컬럼 채우기
            for c in ["병원_수","약국_수","복지시설_수"]:
                if c not in df_fac_proc.columns:
                    df_fac_proc[c] = 0
            # 컬럼 순서 통일
            df_fac_proc = df_fac_proc[["지역","병원_수","약국_수","복지시설_수"]]

        st.subheader("전처리된 데이터 (병합 전)")
        st.write("독거노인 데이터")
        st.dataframe(df_elder_proc.head())
        st.write("시설 집계 데이터")
        st.dataframe(df_fac_proc.head())

        # 지역명 간단 정리(양쪽 공백 제거)
        df_elder_proc["지역"] = df_elder_proc["지역"].astype(str).str.strip()
        df_fac_proc["지역"] = df_fac_proc["지역"].astype(str).str.strip()

        # 간단한 지역명 치환(서울->서울특별시 등) : 시도 단위 매칭 보조
        simple_to_official = {
            "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시",
            "인천": "인천광역시", "광주": "광주광역시", "대전": "대전광역시",
            "울산": "울산광역시", "세종": "세종특별자치시", "경기": "경기도",
            "강원": "강원도", "충북": "충청북도", "충남": "충청남도",
            "전북": "전라북도", "전남": "전라남도", "경북": "경상북도",
            "경남": "경상남도", "제주": "제주특별자치도"
        }
        df_elder_proc["지역_매칭용"] = df_elder_proc["지역"].replace(simple_to_official).fillna(df_elder_proc["지역"])
        df_fac_proc["지역_매칭용"] = df_fac_proc["지역"].replace(simple_to_official).fillna(df_fac_proc["지역"])

        # 병합 (지역_매칭용 기준)
        df = pd.merge(df_elder_proc, df_fac_proc, left_on="지역_매칭용", right_on="지역_매칭용", how="left", suffixes=("_elder","_fac"))
        # 만약 병합에 실패하면 지역 문자열 비교를 도와주기 위한 샘플 출력
        if df.shape[0] == 0:
            raise ValueError("병합 결과가 비어 있습니다. '지역' 컬럼명 또는 값이 서로 다릅니다. 업로드된 파일의 지역명 예시:\n"
                             f"독거노인 파일 지역 예시: {df_elder_proc['지역'].head(10).tolist()}\n"
                             f"시설 파일 지역 예시: {df_fac_proc['지역'].head(10).tolist()}")

        # 결측값 처리
        for c in ["병원_수","약국_수","복지시설_수"]:
            if c not in df.columns:
                df[c] = 0
        df["독거노인_인구수"] = pd.to_numeric(df["독거노인_인구수"], errors='coerce').fillna(0)

        # 비율 계산 (분모 0 방지)
        df["병원_비율"] = df["병원_수"] / df["독거노인_인구수"].replace({0: np.nan})
        df["약국_비율"] = df["약국_수"] / df["독거노인_인구수"].replace({0: np.nan})
        df["복지시설_비율"] = df["복지시설_수"] / df["독거노인_인구수"].replace({0: np.nan})
        df[["병원_비율","약국_비율","복지시설_비율"]] = df[["병원_비율","약국_비율","복지시설_비율"]].fillna(0)

        st.subheader("병합 결과 (일부 컬럼)")
        st.dataframe(df[["지역_매칭용","지역_elder","지역_fac","독거노인_인구수","병원_수","약국_수","복지시설_수","병원_비율"]].head())

        # 지도용 지역명 후보(시도 단위 geojson 우선, 실패 시 시군구)
        # 먼저 시도(프로빈스) geojson 로드
        province_geo = "https://raw.githubusercontent.com/southkorea/southkorea-maps/master/kostat/2013/json/skorea_provinces_geo_simple.json"
        municipal_geo = "https://raw.githubusercontent.com/southkorea/southkorea-maps/master/kostat/2013/json/skorea_municipalities_geo_simple.json"

        # 시도 geo 로드
        geo_prov = requests.get(province_geo).json()
        prov_names = [f["properties"]["name"] for f in geo_prov["features"]]

        # 시군구 geo 로드
        geo_muni = requests.get(municipal_geo).json()
        muni_names = [f["properties"]["name"] for f in geo_muni["features"]]

        # 어느 레벨과 매칭되는지 판단 (지역_매칭용이 시도명 리스트에 포함되는지 확인)
        sample_regions = df["지역_매칭용"].unique().tolist()
        # 간단 매칭 판정
        prov_match_count = sum(1 for r in sample_regions if r in prov_names)
        muni_match_count = sum(1 for r in sample_regions if r in muni_names)

        if prov_match_count >= max(1, muni_match_count):
            geojson = geo_prov
            featureidkey = "properties.name"
            st.write(f"지도 레벨: 시도(province). prov_match_count={prov_match_count}, muni_match_count={muni_match_count}")
            df_plot = df.copy()
            df_plot["지역_매칭용"] = df_plot["지역_매칭용"].replace(simple_to_official).fillna(df_plot["지역_매칭용"])
            locations_col = "지역_매칭용"
        else:
            geojson = geo_muni
            featureidkey = "properties.name"
            st.write(f"지도 레벨: 시군구(municipality). prov_match_count={prov_match_count}, muni_match_count={muni_match_count}")
            # 만약 현재 df의 지역이 '시도'명만 들어있다면 시군구와 매칭 못함 -> 사용자에게 안내
            locations_col = "지역_매칭용"

        # 선택 박스
        facility_option = st.selectbox("시각화할 값 선택", ["병원_비율", "약국_비율", "복지시설_비율", "병원_수", "약국_수", "복지시설_수"])

        # Plotly Choropleth
        fig = px.choropleth(
            df,
            geojson=geojson,
            locations=locations_col,
            featureidkey=featureidkey,
            color=facility_option,
            color_continuous_scale="YlOrRd",
            labels={facility_option: facility_option},
            title=f"지역별 {facility_option} 분포"
        )
        fig.update_geos(fitbounds="locations", visible=False, showcountries=False, showframe=False, projection_type="mercator")
        fig.update_layout(margin={"r":0,"t":40,"l":0,"b":0})
        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"처리 중 오류 발생: {e}")
        # 디버그용 추가 정보 출력 (개발 중일 때만 표시)
        import traceback
        st.text(traceback.format_exc())
