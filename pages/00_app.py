 # app.py
import streamlit as st
import pandas as pd
import numpy as np
import json
import re
import requests
import plotly.express as px

st.set_page_config(page_title="독거노인 의료접근성 분석", layout="wide")

st.title("🏥 독거노인 의료접근성 분석 웹앱")
st.markdown("파일을 업로드하면 자동으로 행정구역별 의료기관 접근성을 계산하고 시각화합니다.")

# --- Sidebar ---
st.sidebar.header("📂 데이터 업로드")
elder_file = st.sidebar.file_uploader("독거노인가구 데이터 (.xlsx 또는 .csv)", type=["xlsx", "csv"])
med_file = st.sidebar.file_uploader("의료기관 데이터 (.csv)", type=["csv"])

st.sidebar.header("⚙️ 설정")
w1 = st.sidebar.slider("가중치 w₁ (독거노인 비율)", 0.0, 5.0, 1.0, 0.1)
w2 = st.sidebar.slider("가중치 w₂ (의료기관 수)", 0.0, 5.0, 1.0, 0.1)

st.sidebar.markdown("---")
st.sidebar.info("GeoJSON 파일은 자동으로 다운로드됩니다. 실패 시 직접 업로드하세요.")
geojson_file = st.sidebar.file_uploader("(선택) GeoJSON 파일 업로드", type=["geojson", "json"])

# --- Helper functions ---
def normalize_name(name):
    if pd.isna(name):
        return ""
    s = str(name)
    s = re.sub(r"\(.*?\)", "", s)  # 괄호 내용 제거
    s = s.replace("특례시", "시").replace("광역시", "시")
    s = s.replace("특별자치시", "시").replace("특별자치도", "도")
    return re.sub(r"\s+", " ", s.strip())

def extract_sigungu(name):
    s = normalize_name(name)
    tokens = s.split()
    if len(tokens) >= 2:
        return tokens[-2] + " " + tokens[-1] if tokens[-1].endswith(("구", "군")) else tokens[-1]
    return s

def download_geojson():
    urls = [
        "https://raw.githubusercontent.com/southkorea/sigungu-maps/master/korea-sigungu.geojson",
        "https://raw.githubusercontent.com/southkorea/sido-maps/master/korea-sigungu.geojson",
    ]
    for url in urls:
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                st.sidebar.success("GeoJSON 자동 다운로드 성공 ✅")
                return r.json()
        except:
            pass
    return None

# --- Data load ---
if (elder_file is None) or (med_file is None):
    st.warning("📢 두 개의 파일(독거노인, 의료기관)을 업로드해주세요.")
    st.stop()

try:
    elder_df = pd.read_excel(elder_file) if elder_file.name.endswith("xlsx") else pd.read_csv(elder_file)
    med_df = pd.read_csv(med_file, low_memory=False)
except Exception as e:
    st.error(f"파일 로드 중 오류: {e}")
    st.stop()

st.subheader("📊 데이터 미리보기")
st.write("**독거노인 데이터:**")
st.dataframe(elder_df.head())
st.write("**의료기관 데이터:**")
st.dataframe(med_df.head())

# --- Column selection ---
st.markdown("### 🔍 컬럼 선택")
elder_area_col = st.selectbox("독거노인 데이터 - 행정구역 컬럼", elder_df.columns)
elder_ratio_col = st.selectbox("독거노인 데이터 - 독거노인 비율(%) 컬럼", elder_df.columns)
elder_count_col = st.selectbox("독거노인 데이터 - 독거노인 가구 수(명) 컬럼", elder_df.columns)
addr_col = st.selectbox("의료기관 데이터 - 주소 컬럼", med_df.columns)

# --- Preprocessing ---
med_df["행정구역"] = med_df[addr_col].astype(str).apply(extract_sigungu)
inst_count = med_df.groupby("행정구역").size().reset_index(name="의료기관수")

elder_df["행정구역"] = elder_df[elder_area_col].astype(str).apply(extract_sigungu)
merged = pd.merge(elder_df, inst_count, on="행정구역", how="left").fillna({"의료기관수": 0})

merged["독거노인가구수"] = pd.to_numeric(merged[elder_count_col], errors="coerce").fillna(0)
merged["독거노인비율"] = pd.to_numeric(merged[elder_ratio_col], errors="coerce").fillna(0)

# 의료기관 밀도(1천명당)
merged["기관밀도"] = merged["의료기관수"] / (merged["독거노인가구수"] / 1000).replace(0, np.nan)

# 표준화 (z-score)
merged["비율z"] = (merged["독거노인비율"] - merged["독거노인비율"].mean()) / (merged["독거노인비율"].std() + 1e-9)
merged["기관z"] = (merged["기관밀도"] - merged["기관밀도"].mean()) / (merged["기관밀도"].std() + 1e-9)

# 취약도 점수
merged["취약도점수"] = w1 * merged["비율z"] - w2 * merged["기관z"]
merged["취약도(0-100)"] = ((merged["취약도점수"] - merged["취약도점수"].min()) / 
                     (merged["취약도점수"].max() - merged["취약도점수"].min() + 1e-9)) * 100

st.success("데이터 병합 및 지표 계산 완료 ✅")

# --- GeoJSON load ---
if geojson_file is not None:
    geojson = json.load(geojson_file)
else:
    geojson = download_geojson()
    if geojson is None:
        st.error("GeoJSON을 불러오지 못했습니다. 직접 업로드해주세요.")
        st.stop()

# --- Choropleth map ---
st.header("🗺️ 지역별 취약도 지도")
for feat in geojson["features"]:
    name = normalize_name(feat["properties"].get("SIG_KOR_NM", ""))
    feat["properties"]["JOIN"] = extract_sigungu(name)

fig = px.choropleth(
    merged,
    geojson=geojson,
    locations="행정구역",
    featureidkey="properties.JOIN",
    color="취약도(0-100)",
    hover_name="행정구역",
    hover_data=["의료기관수", "기관밀도", "독거노인비율"],
    color_continuous_scale="RdYlBu_r",
    labels={"취약도(0-100)": "취약도 지수"},
)
fig.update_geos(fitbounds="locations", visible=False)
st.plotly_chart(fig, use_container_width=True)

# --- Scatter plot ---
st.header("📈 독거노인 비율 vs 의료기관 밀도")
fig2 = px.scatter(
    merged,
    x="독거노인비율",
    y="기관밀도",
    size="의료기관수",
    hover_name="행정구역",
    trendline="ols",
    color="취약도(0-100)",
)
st.plotly_chart(fig2, use_container_width=True)

# --- Ranking table ---
st.header("🏅 지역별 순위")
top_n = st.slider("표시할 상/하위 개수", 3, 20, 10)
top = merged.nlargest(top_n, "취약도(0-100)")[["행정구역", "의료기관수", "독거노인비율", "기관밀도", "취약도(0-100)"]]
bottom = merged.nsmallest(top_n, "취약도(0-100)")[["행정구역", "의료기관수", "독거노인비율", "기관밀도", "취약도(0-100)"]]

st.subheader("상위 지역 (취약도 ↑)")
st.dataframe(top)
st.subheader("하위 지역 (취약도 ↓)")
st.dataframe(bottom)

# --- Download ---
st.header("💾 결과 다운로드")
csv = merged.to_csv(index=False).encode("utf-8")
st.download_button("CSV로 저장", csv, file_name="접근성_분석결과.csv", mime="text/csv")
