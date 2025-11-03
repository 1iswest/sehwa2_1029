# app.py
import streamlit as st
import pandas as pd
import numpy as np
import json
import re
from io import StringIO, BytesIO
import requests
import plotly.express as px

st.set_page_config(layout="wide", page_title="독거노인 의료접근성 분석", initial_sidebar_state="expanded")

st.title("행정구역별 독거노인 의료접근성 분석 · 시각화")
st.markdown("업로드한 데이터로 행정구역별 의료기관 수와 독거노인 지표를 병합하여 Choropleth, 산점도, TOP10 등을 제공합니다.")

#
# --- 사이드바: 입력
#
st.sidebar.header("1) 데이터 업로드")
file_elder = st.sidebar.file_uploader("독거노인 가구 파일 (.xlsx) — (예: 독거노인가구비율_시도_시군구.xlsx)", type=["xlsx", "csv"])
file_med = st.sidebar.file_uploader("의료기관 표준데이터 (.csv)", type=["csv"])

st.sidebar.markdown("---")
st.sidebar.header("2) 설정 · 필터")
admin_level = st.sidebar.radio("행정단위 수준", options=["시도(광역)", "시군구(기초)"], index=1)
w1 = st.sidebar.slider("가중치 w1 (독거노인비율 표준화)", 0.0, 5.0, 1.0, 0.1)
w2 = st.sidebar.slider("가중치 w2 (1천명당 기관수 표준화)", 0.0, 5.0, 1.0, 0.1)
show_mismatch = st.sidebar.checkbox("주소 파싱 실패(미매칭) 표시", value=True)
st.sidebar.markdown("---")
st.sidebar.header("3) GeoJSON (자동 다운로드)")
st.sidebar.info("코드가 공용 저장소에서 시군구 GeoJSON을 자동으로 다운로드 시도합니다. 실패 시 직접 업로드하세요.")
geojson_file = st.sidebar.file_uploader("(폴백) GeoJSON 파일 업로드", type=["geojson", "json"])

#
# --- Helper: GeoJSON 자동 다운로드 (대한민국 시군구)
#
GEOJSON_URLS = [
    # 우선순위로 시도 — public repo (availability not guaranteed)
    "https://raw.githubusercontent.com/southkorea/sido-maps/master/korea-sigungu.geojson",
    "https://raw.githubusercontent.com/southkorea/sigungu-maps/master/korea-sigungu.geojson",
]

def download_geojson():
    for url in GEOJSON_URLS:
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                gj = r.json()
                st.sidebar.success(f"GeoJSON 자동 다운로드 성공 ({url})")
                return gj
        except Exception:
            continue
    return None

geojson = None
if geojson_file is not None:
    geojson = json.load(geojson_file)
else:
    geojson = download_geojson()
    if geojson is None:
        st.sidebar.error("자동 다운로드 실패 — GeoJSON 파일을 직접 업로드해 주세요.")
        st.stop()

#
# --- Helper: 주소 정규화 함수
#
def normalize_admin_name(name):
    """간단한 정규화: 공백 제거, 괄호 제거, 특례/광역 등 처리, '시','군','구' 유지 또는 제거 등.
       반환값으로 기본 표준명(예: '고양시 덕양구' 혹은 '고양시') 형태를 시도합니다."""
    if pd.isna(name):
        return ""
    s = str(name).strip()
    # 소괄호 내용 제거
    s = re.sub(r"\(.*?\)", "", s).strip()
    # 흔한 잘못 표기 치환(특례시 -> 시 표준화 예)
    s = s.replace("특례시", "시")
    s = s.replace("광역시", "시")
    s = s.replace("특별자치시", "시")
    s = s.replace("특별자치도", "도")
    # 여러 구분자 -> 공백 하나로
    s = re.sub(r"[\-,/]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s

def extract_sigungu(name, want_level="시군구"):
    """문자열에서 시/군/구 수준 토큰을 추출.
       want_level: '시도' 또는 '시군구' """
    s = normalize_admin_name(name)
    # 우선 '시 군 구' 등 토큰 탐색
    # 패턴 예: "경기도 고양시 덕양구", "고양특례시 덕양구", "서울특별시 강남구"
    tokens = s.split()
    if len(tokens) == 0:
        return ""
    # 시군구 찾기 (마지막 토큰에 '구','군','시' 포함되는 경우)
    last = tokens[-1]
    if re.search(r"(구|군)$", last):
        sigungu = " ".join(tokens[-2:]) if len(tokens) >= 2 else last
    elif re.search(r"(시)$", last):
        # 시면 시도 레벨 혹은 시 자체
        # 만약 전체 주소에 구가 있으면 '시 구' 구성
        if len(tokens) >= 2 and re.search(r"(구|군)$", tokens[-1]):
            sigungu = " ".join(tokens[-2:])
        else:
            # 시만 반환 (시도 레벨)
            sigungu = last
    else:
        # fallback: 마지막 두 토큰 합치기
        sigungu = " ".join(tokens[-2:]) if len(tokens) >= 2 else tokens[0]
    sigungu = sigungu.strip()
    return sigungu

#
# --- 데이터 로딩 & 전처리
#
st.header("데이터 미리보기 및 전처리")
if (file_elder is None) or (file_med is None):
    st.warning("먼저 사이드바에서 두 개의 파일(독거노인 가구 파일, 의료기관 데이터)을 업로드하세요.")
    st.stop()

# load elder data (xlsx or csv)
try:
    if file_elder.type in ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel"]:
        elder_df = pd.read_excel(file_elder)
    else:
        elder_df = pd.read_csv(file_elder)
except Exception as e:
    st.error(f"독거노인 데이터 로드 실패: {e}")
    st.stop()

# load medical institutions
try:
    med_df = pd.read_csv(file_med, low_memory=False)
except Exception as e:
    st.error(f"의료기관 데이터 로드 실패: {e}")
    st.stop()

st.subheader("독거노인 데이터 (샘플)")
st.dataframe(elder_df.head())

st.subheader("의료기관 데이터 (샘플)")
st.dataframe(med_df.head())

#
# --- 사용자에게 어떤 컬럼이 있는지 확인하도록 도움 (자동 매핑 시도)
#
st.markdown("**자동 컬럼 매핑(추정)**: 아래에서 실제 컬럼을 선택하세요. (파일별 컬럼명이 다를 수 있음)")

# guesses for elder df
elder_cols = elder_df.columns.tolist()
elder_area_col = st.selectbox("독거노인 파일: 행정구역 컬럼(예: 시군구명)", options=elder_cols, index=0)
elder_house_col = st.selectbox("독거노인 파일: 독거노인 가구 수 컬럼(수치)", options=elder_cols, index=1 if len(elder_cols)>1 else 0)
elder_ratio_col = st.selectbox("독거노인 파일: 독거노인 비율 컬럼(백분율 또는 소수)", options=elder_cols, index=2 if len(elder_cols)>2 else 0)

# guesses for med df
med_cols = med_df.columns.tolist()
med_addr_col = st.selectbox("의료기관 파일: 주소 컬럼 (의료기관 주소 문자열)", options=med_cols, index=med_cols.index("주소") if "주소" in med_cols else 0)
med_name_col = st.selectbox("의료기관 파일: 기관명 컬럼", options=med_cols, index=0)

#
# --- 주소 파싱 & 집계
#
st.markdown("### 주소 파싱 및 행정구역 집계")
# create parsed admin column
med_df["parsed_area_raw"] = med_df[med_addr_col].astype(str).apply(normalize_admin_name)
med_df["parsed_sigungu"] = med_df[med_addr_col].astype(str).apply(lambda x: extract_sigungu(x, want_level="시군구"))

# count institutions by parsed_sigungu
inst_counts = med_df.groupby("parsed_sigungu").size().reset_index(name="institutions_count")
st.write(f"의료기관 총 레코드: {len(med_df)}  — 파싱된 고유 행정구역 수: {inst_counts['parsed_sigungu'].nunique()}")

st.dataframe(inst_counts.head(30))

#
# --- elder df: normalize area names
#
elder_df["area_norm"] = elder_df[elder_area_col].astype(str).apply(normalize_admin_name)
# try to map to either 시/군/구 combination or 시도
# create key candidates
elder_df["area_sigungu_candidate"] = elder_df["area_norm"].apply(lambda x: extract_sigungu(x, want_level="시군구"))

# merge on the sigungu candidate
merged = pd.merge(elder_df, inst_counts, left_on="area_sigungu_candidate", right_on="parsed_sigungu", how="left")

# fill missing institution counts by 0
merged["institutions_count"] = merged["institutions_count"].fillna(0).astype(int)

# create derived metrics
# expected columns: elder_house_col (가구수) 혹은 elder_ratio_col (비율) — 사용자 파일 구조에 따라 다름.
# We'll compute institutions per 1000 독거노인 가구 if 가구 수 exists, else per 1000명(비율 기반용 설명) — 사용자에게 알림
has_house = elder_house_col in elder_df.columns and pd.api.types.is_numeric_dtype(elder_df[elder_house_col])
if has_house:
    merged["elder_households"] = pd.to_numeric(merged[elder_house_col], errors="coerce").fillna(0)
    merged["inst_per_1000_households"] = merged["institutions_count"] / (merged["elder_households"] / 1000).replace({0: np.nan})
else:
    # fallback: try using ratio * population if available — but we don't have population — so compute inst per 1000 by using institution count / (ratio proxy)
    merged["elder_ratio"] = pd.to_numeric(merged[elder_ratio_col], errors="coerce").fillna(0)
    merged["inst_per_1000_households"] = merged["institutions_count"]  # fallback raw count (will be standardized later)
    st.warning("독거노인 가구 수 컬럼을 찾지 못했습니다. inst_per_1000_households는 기관수 원값을 사용하여 표준화합니다. (정확한 지표를 위해 가구수 컬럼 권장)")

# 독거노인 비율 표준화 (z-score)
merged["elder_ratio_numeric"] = pd.to_numeric(merged[elder_ratio_col], errors="coerce").fillna(0)
merged["elder_ratio_z"] = (merged["elder_ratio_numeric"] - merged["elder_ratio_numeric"].mean()) / (merged["elder_ratio_numeric"].std() + 1e-9)
merged["inst_per_1000_z"] = (merged["inst_per_1000_households"] - merged["inst_per_1000_households"].mean()) / (merged["inst_per_1000_households"].std() + 1e-9)

# Score
merged["score_raw"] = w1 * merged["elder_ratio_z"] - w2 * merged["inst_per_1000_z"]
# scale score to 0-100 for interpretability
min_s, max_s = merged["score_raw"].min(), merged["score_raw"].max()
merged["score_0_100"] = ((merged["score_raw"] - min_s) / (max_s - min_s + 1e-9)) * 100

st.subheader("병합 결과 (예시)")
st.dataframe(merged[[elder_area_col, "area_norm", "area_sigungu_candidate", "institutions_count", "elder_ratio_numeric", "elder_households" if has_house else elder_ratio_col, "inst_per_1000_households", "score_0_100"]].head(50))

#
# --- Choropleth: GeoJSON과 병합 (매칭 로직)
#
st.header("시각화")

# try to find a property key that contains 행정명칭 in the GeoJSON
properties_sample = geojson["features"][0].get("properties", {})
prop_keys = list(properties_sample.keys())

st.write("GeoJSON 속성 예시 키:", prop_keys)

# candidate property keys that commonly appear: 'name','SIG_KOR_NM','EMD_KOR_NM','ADM_NM' 등
candidates = ["SIG_KOR_NM", "SIG_NM", "name", "NAME", "ADM_NM", "CTP_KOR_NM", "CTP_ENG_NM", "gungu", "SIG_CD"]
found_key = None
for k in candidates:
    if k in prop_keys:
        found_key = k
        break
# fallback: take first string-valued property
if found_key is None:
    for k in prop_keys:
        v = properties_sample.get(k)
        if isinstance(v, str):
            found_key = k
            break

if found_key is None:
    st.error("GeoJSON에서 적절한 행정구역 이름 속성을 찾지 못했습니다. (GeoJSON 속성 확인 필요)")
    st.stop()

st.write(f"GeoJSON에서 사용될 매칭 속성: `{found_key}`")

# build mapping from geojson names -> feature id
geo_names = []
for feat in geojson["features"]:
    prop = feat.get("properties", {})
    name = prop.get(found_key, "")
    name_norm = normalize_admin_name(name)
    # for matching, also consider extract_sigungu
    name_sigungu = extract_sigungu(name_norm)
    geo_names.append((name_norm, name_sigungu, prop))

# create a df for matching
geo_df = pd.DataFrame(geo_names, columns=["geo_name_norm", "geo_sigungu", "geo_prop"])
# Try exact match on 'area_sigungu_candidate' <-> 'geo_sigungu'
match_df = pd.merge(merged, geo_df, left_on="area_sigungu_candidate", right_on="geo_sigungu", how="left")

# Count unmatched
unmatched = match_df[match_df["geo_name_norm"].isna() | (match_df["geo_name_norm"]=="")]
st.write(f"매칭 실패 수: {len(unmatched)} (show_mismatch 설정에 따라 표시)")

# For unmatched, try fuzzy: match by whether area_sigungu_candidate is substring of geo_name_norm
def fuzzy_match_row(row, geo_df):
    target = row["area_sigungu_candidate"]
    if not target:
        return None
    for i, r in geo_df.iterrows():
        if target in r["geo_name_norm"] or r["geo_name_norm"] in target:
            return r["geo_name_norm"]
    return None

match_df["geo_name_norm"] = match_df.apply(lambda r: r["geo_name_norm"] if pd.notna(r.get("geo_name_norm")) and r.get("geo_name_norm")!="" else fuzzy_match_row(r, geo_df), axis=1)

# final matched subset
matched_final = match_df[match_df["geo_name_norm"].notna()]

# prepare choropleth data: need a mapping id -> value; set feature id as geo_name_norm
# We'll add a property 'JOIN_NAME' to geojson features matching geo_name_norm
for feat in geojson["features"]:
    prop = feat.get("properties", {})
    name = prop.get(found_key, "")
    name_norm = normalize_admin_name(name)
    feat["properties"]["JOIN_NAME"] = name_norm

# create dict: JOIN_NAME -> score
score_map = dict(zip(matched_final["geo_name_norm"], matched_final["score_0_100"]))

# Map values to GeoJSON features (for visualization)
for feat in geojson["features"]:
    join = feat["properties"].get("JOIN_NAME", "")
    feat["properties"]["score_0_100"] = float(np.nan if join not in score_map else score_map[join])

# Choropleth with plotly
st.subheader("색상지도 (Choropleth)")
fig = px.choropleth(
    matched_final,
    geojson=geojson,
    locations="geo_name_norm",
    featureidkey=f"properties.JOIN_NAME",
    color="score_0_100",
    hover_name=elder_area_col,
    hover_data={"institutions_count": True, "inst_per_1000_households": True, "score_0_100": True},
    color_continuous_scale="RdYlBu_r",
    labels={"score_0_100": "취약도(0-100)"},
)
fig.update_geos(fitbounds="locations", visible=False)
fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=600)
st.plotly_chart(fig, use_container_width=True)

#
# --- 산점도
#
st.subheader("산점도: 독거노인 비율 vs 1천명당 기관 수")
scatter_df = merged.copy()
fig2 = px.scatter(
    scatter_df,
    x="elder_ratio_numeric",
    y="inst_per_1000_households",
    hover_name=elder_area_col,
    size="institutions_count",
    trendline="ols",
    labels={"elder_ratio_numeric":"독거노인 비율", "inst_per_1000_households":"(기관수) 또는 (1천명당 기관수)"},
)
st.plotly_chart(fig2, use_container_width=True)

#
# --- TOP / RANKING
#
st.subheader("랭킹 · TOP / BOTTOM")
top_n = st.number_input("Top N (상/하위)", min_value=1, max_value=50, value=10)
ranked = merged.sort_values("score_0_100", ascending=False).reset_index(drop=True)
st.markdown("**상위 지역 (취약도 높음)**")
st.table(ranked.head(top_n)[[elder_area_col, "institutions_count", "inst_per_1000_households", "elder_ratio_numeric", "score_0_100"]])

st.markdown("**하위 지역 (취약도 낮음)**")
st.table(ranked.tail(top_n)[[elder_area_col, "institutions_count", "inst_per_1000_households", "elder_ratio_numeric", "score_0_100"]])

#
# --- 데이터 다운로드
#
st.subheader("결과 다운로드")
out_csv = merged.copy()
to_download = out_csv[[elder_area_col, "area_sigungu_candidate", "institutions_count", "elder_ratio_numeric", "inst_per_1000_households", "score_0_100"]]
csv_bytes = to_download.to_csv(index=False).encode('utf-8')
st.download_button("CSV로 다운로드", csv_bytes, file_name="region_scores.csv", mime="text/csv")

#
# --- 이상치 / 미매칭 표시
#
if show_mismatch:
    mism = merged[merged["area_sigungu_candidate"].isin(unmatched["area_sigungu_candidate"] if not unmatched.empty else [])]
    st.subheader("미매칭 / 파싱 불확실 레코드 (예시)")
    if mism.empty:
        st.write("미매칭 레코드 없음 (혹은 모두 매칭됨).")
    else:
        st.dataframe(mism[[elder_area_col, elder_house_col if has_house else elder_ratio_col, "area_sigungu_candidate"]].head(100))

st.markdown("----")
st.caption("참고: 이 앱은 업로드된 파일의 컬럼명/구조에 따라 결과가 달라집니다. 정확한 '독거노인 가구 수' 컬럼이 있으면 기관수 대비 접근성 지표가 의미있게 계산됩니다.")
