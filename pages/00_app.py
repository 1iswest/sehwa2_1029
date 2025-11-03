# app.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import requests
import io
import os

st.set_page_config(page_title="의료기관 분포 균등성 분석 (독거노인 대비)", layout="wide")
st.title("의료기관 분포 균등성 분석 — 독거노인 인구 대비")

st.markdown("""
이 앱은 **지역별 독거노인 인구**와 **의료기관(병원·의원·약국 등)** 데이터를 사용해,
의료기관이 노인 분포에 비해 얼마나 고르게 분포되어 있는지를 여러 지표와 지도·그래프로 시각화합니다.
- 업로드 형식: CSV 또는 XLSX
- 자동 감지: 업로드하지 않으면 `/mnt/data/전국의료기관 표준데이터.csv` 와 `/mnt/data/독거노인가구비율_시도_시_군_구__20251029204458.xlsx` 를 시도합니다.
""")

st.sidebar.header("데이터 업로드 (선택)")
elder_file = st.sidebar.file_uploader("독거노인 인구 파일 (CSV/XLSX)", type=["csv", "xlsx"])
facility_file = st.sidebar.file_uploader("의료기관 파일 (CSV/XLSX)", type=["csv", "xlsx"])

# --- Helpers for reading files robustly ---
def read_any(file_or_path):
    if file_or_path is None:
        return None
    # If it's an uploaded file object
    if hasattr(file_or_path, "read"):
        name = getattr(file_or_path, "name", "")
        try:
            if name.lower().endswith(".xlsx") or name.lower().endswith(".xls"):
                return pd.read_excel(file_or_path)
            else:
                try:
                    return pd.read_csv(file_or_path)
                except Exception:
                    file_or_path.seek(0)
                    return pd.read_csv(file_or_path, encoding="cp949", errors="replace")
        except Exception as e:
            raise e
    # If it's a path string
    else:
        path = file_or_path
        if not os.path.exists(path):
            return None
        if path.lower().endswith((".xls", ".xlsx")):
            return pd.read_excel(path)
        else:
            try:
                return pd.read_csv(path)
            except Exception:
                return pd.read_csv(path, encoding="cp949", errors="replace")

# try to load default uploaded-by-user files on server if not provided
if elder_file is None:
    elder_path_guess = "/mnt/data/독거노인가구비율_시도_시_군_구__20251029204458.xlsx"
    if os.path.exists(elder_path_guess):
        try:
            df_elder = read_any(elder_path_guess)
            st.sidebar.write("독거노인 파일: 서버 업로드 파일을 사용합니다.")
        except Exception:
            df_elder = None
    else:
        df_elder = None
else:
    df_elder = read_any(elder_file)

if facility_file is None:
    facility_path_guess = "/mnt/data/전국의료기관 표준데이터.csv"
    if os.path.exists(facility_path_guess):
        try:
            df_facility = read_any(facility_path_guess)
            st.sidebar.write("의료기관 파일: 서버 업로드 파일을 사용합니다.")
        except Exception:
            df_facility = None
    else:
        df_facility = None
else:
    df_facility = read_any(facility_file)

# Quick utility: guess region column
REGION_KEYWORDS = ["지역","시도","시군구","시도명","시군구명","행정구역","주소","소재지","sido","gungu","sigungu"]
ELDER_KEYWORDS = ["독거","노인","고령","인구","가구","elder","population","count"]
FAC_KIND_KEYWORDS = ["업종","종별","의료기관명","종류","구분","업태","classification","category","name"]

def guess_col(df, keywords):
    if df is None:
        return None
    cols = df.columns.tolist()
    lower = [c.lower() for c in cols]
    # exact matches first
    for kw in keywords:
        if kw in cols:
            return kw
        if kw.lower() in lower:
            return cols[lower.index(kw.lower())]
    # contains
    for i,c in enumerate(lower):
        for kw in keywords:
            if kw.lower() in c:
                return cols[i]
    return None

def guess_elder_count(df):
    if df is None:
        return None
    cols = df.columns.tolist()
    lower = [c.lower() for c in cols]
    for i,c in enumerate(lower):
        for kw in ELDER_KEYWORDS:
            if kw in c and any(x in c for x in ["수","명","count","pop","인구"]):
                return cols[i]
    # fallback: numeric column with largest sum
    numeric = df.select_dtypes(include=[np.number])
    if not numeric.empty:
        s = numeric.sum().sort_values(ascending=False)
        return s.index[0]
    return None

# functions to aggregate facility file whether aggregated or raw
def detect_aggregated_cols(df):
    # find columns that look like counts for hospital/pharmacy/welfare
    mapping = {}
    lower = [c.lower() for c in df.columns]
    for c in df.columns:
        lc = c.lower()
        if any(k in lc for k in ["병원","의원","hospital","clinic"]) and any(x in lc for x in ["수","cnt","count","num"]):
            mapping["병원_수"] = c
        if "약국" in lc and any(x in lc for x in ["수","cnt","count","num"]):
            mapping["약국_수"] = c
        if any(k in lc for k in ["복지","복지관","social"] ) and any(x in lc for x in ["수","cnt","count","num"]):
            mapping["복지시설_수"] = c
    return mapping

def count_facility_rows(df, region_col):
    # attempt to detect a kind/type column to separate 병원/약국/복지
    kind_col = None
    for c in df.columns:
        lc = c.lower()
        if any(k in lc for k in FAC_KIND_KEYWORDS) or any(k in lc for k in ["의원","병원","약국","업종","종별","classification","category","type","kind","name"]):
            kind_col = c
            break
    # address fallback if region_col not present
    if region_col not in df.columns:
        # try to find address and take first token as 시도
        addr_col = None
        for c in df.columns:
            if "주소" in c or "소재지" in c or "도로명" in c or "address" in c:
                addr_col = c
                break
        if addr_col:
            tmp_region = df[addr_col].astype(str).str.split().str[0]
            df = df.assign(_region_auto=tmp_region)
            region_col = "_region_auto"
        else:
            # fallback: use first column
            df = df.assign(_region_auto=df.iloc[:,0].astype(str))
            region_col = "_region_auto"
    else:
        df[region_col] = df[region_col].astype(str)

    if kind_col is None:
        # can't classify kinds - return total facility counts per region
        grouped = df.groupby(region_col).size().reset_index(name="시설_총수")
        grouped = grouped.rename(columns={region_col: "지역"})
        # map to 병원_수 as total so mapping later works
        grouped["병원_수"] = grouped["시설_총수"]
        grouped["약국_수"] = 0
        grouped["복지시설_수"] = 0
        return grouped[["지역","병원_수","약국_수","복지시설_수"]]
    else:
        def cls_kind(x):
            s = str(x).lower()
            if "약국" in s or "pharm" in s:
                return "약국"
            if "복지" in s or "welfare" in s:
                return "복지시설"
            # treat 의원/병원/clinic as 병원
            if "병원" in s or "의원" in s or "clinic" in s or "hospital" in s:
                return "병원"
            return "기타"

        tmp = df.copy()
        tmp["_kind_cls"] = tmp[kind_col].apply(cls_kind)
        grouped = tmp.groupby([region_col, "_kind_cls"]).size().unstack(fill_value=0).reset_index()
        grouped = grouped.rename(columns={region_col:"지역"})
        for col in ["병원","약국","복지시설"]:
            if col not in grouped.columns:
                grouped[col] = 0
        grouped = grouped.rename(columns={"병원":"병원_수","약국":"약국_수","복지시설":"복지시설_수"})
        return grouped[["지역","병원_수","약국_수","복지시설_수"]]

# --- load / validate ---
if df_elder is None or df_facility is None:
    st.warning("독거노인 파일 또는 의료기관 파일이 업로드되지 않았거나 서버에 존재하지 않습니다. 사이드바에서 파일을 업로드하거나 서버의 기본 파일을 올려주세요.")
    st.stop()

st.subheader("원본 데이터 미리보기")
st.write("독거노인 파일 (상위 5행)")
st.dataframe(df_elder.head())
st.write("의료기관 파일 (상위 5행)")
st.dataframe(df_facility.head())

# detect columns
elder_region_col = guess_col(df_elder, REGION_KEYWORDS) or df_elder.columns[0]
elder_count_col = guess_elder_count(df_elder)
facility_region_col = guess_col(df_facility, REGION_KEYWORDS) or df_facility.columns[0]
agg_map = detect_aggregated_cols(df_facility)

st.write("자동 감지 결과:")
st.write({
    "elder_region_col": elder_region_col,
    "elder_count_col": elder_count_col,
    "facility_region_col": facility_region_col,
    "aggregated_columns_found": agg_map
})

# standardize elder df
df_elder_proc = df_elder.copy()
df_elder_proc = df_elder_proc.rename(columns={elder_region_col: "지역"})
if elder_count_col is None:
    st.error("독거노인 인구 컬럼(예: '독거노인', '인구', '수' 포함)을 자동으로 찾을 수 없습니다. 컬럼명을 확인해주세요.")
    st.stop()
df_elder_proc = df_elder_proc.rename(columns={elder_count_col: "독거노인_인구수"})
# ensure numeric
df_elder_proc["독거노인_인구수"] = pd.to_numeric(df_elder_proc["독거노인_인구수"], errors="coerce").fillna(0).astype(int)
df_elder_proc["지역"] = df_elder_proc["지역"].astype(str).str.strip()

# process facility file
if len(agg_map) >= 1:
    df_fac = df_facility.copy()
    # rename region if exists
    if facility_region_col in df_fac.columns:
        df_fac = df_fac.rename(columns={facility_region_col: "지역"})
    else:
        df_fac["지역"] = df_fac.iloc[:,0].astype(str)
    # create standard cols
    df_fac["병원_수"] = 0
    df_fac["약국_수"] = 0
    df_fac["복지시설_수"] = 0
    for std, orig in agg_map.items():
        if orig in df_fac.columns:
            df_fac[std] = pd.to_numeric(df_fac[orig], errors="coerce").fillna(0).astype(int)
    df_fac = df_fac[["지역","병원_수","약국_수","복지시설_수"]]
    df_fac = df_fac.groupby("지역", as_index=False).sum()
else:
    # raw rows -> aggregate by region
    df_fac = count_facility_rows(df_facility, region_col=facility_region_col)
    df_fac["지역"] = df_fac["지역"].astype(str).str.strip()

# small normalization mapping for common short/official names
simple_to_official = {
    "서울":"서울특별시","부산":"부산광역시","대구":"대구광역시","인천":"인천광역시",
    "광주":"광주광역시","대전":"대전광역시","울산":"울산광역시","세종":"세종특별자치시",
    "경기":"경기도","강원":"강원도","충북":"충청북도","충남":"충청남도",
    "전북":"전라북도","전남":"전라남도","경북":"경상북도","경남":"경상남도","제주":"제주특별자치도"
}

df_elder_proc["지역_매칭용"] = df_elder_proc["지역"].replace(simple_to_official).fillna(df_elder_proc["지역"])
df_fac["지역_매칭용"] = df_fac["지역"].replace(simple_to_official).fillna(df_fac["지역"])

# merge using 매칭용
df_merge = pd.merge(df_elder_proc, df_fac, left_on="지역_매칭용", right_on="지역_매칭용", how="left", suffixes=("_elder","_fac"))
# fill NaN counts with 0
for c in ["병원_수","약국_수","복지시설_수"]:
    if c not in df_merge.columns:
        df_merge[c] = 0
    else:
        df_merge[c] = pd.to_numeric(df_merge[c], errors="coerce").fillna(0).astype(int)

# compute totals and rates
df_merge["의료기관_총수"] = df_merge["병원_수"] + df_merge["약국_수"] + df_merge["복지시설_수"]
# 시설 per 1000 elderly (avoid zero division)
df_merge["시설_per_1k_elder"] = df_merge.apply(lambda r: (r["의료기관_총수"] / r["독거노인_인구수"] * 1000) if r["독거노인_인구수"]>0 else 0, axis=1)

# metrics for evenness
def gini(array, weights=None):
    # array: values (non-negative)
    a = np.array(array, dtype=float)
    if weights is None:
        # standard Gini
        if a.size == 0:
            return np.nan
        if np.all(a==0):
            return 0.0
        # sort
        sorted_a = np.sort(a)
        n = a.size
        index = np.arange(1, n+1)
        return (2.0 * np.sum(index * sorted_a) / (n * np.sum(sorted_a))) - (n+1)/n
    else:
        # weighted Gini
        w = np.array(weights, dtype=float)
        if np.sum(w) == 0 or np.sum(a)==0:
            return 0.0
        # sort by a/w? we'll compute weighted Gini using standard formula
        sorted_idx = np.argsort(a)
        sorted_a = a[sorted_idx]
        sorted_w = w[sorted_idx]
        cumw = np.cumsum(sorted_w)
        cumx = np.cumsum(sorted_a * sorted_w)
        sum_w = cumw[-1]
        sum_xw = cumx[-1]
        B = np.sum(cumx / sum_xw * sorted_w / sum_w)
        return 1 - 2*B

# Gini of facilities per region (unweighted)
gini_fac = gini(df_merge["의료기관_총수"].values)
# Gini of facilities per elderly (i.e., compute facilities per elderly and gini)
fac_per_elder = df_merge.apply(lambda r: (r["의료기관_총수"]/r["독거노인_인구수"]) if r["독거노인_인구수"]>0 else 0, axis=1).values
gini_fac_per_elder = gini(fac_per_elder)

# Alternatively compute weighted Gini of facility distribution relative to elderly population:
# idea: if facilities were perfectly matched to elderly, cumulative facility share vs cumulative elderly share would be identical.
# compute Gini-like dissimilarity: Gini of facilities with weights equal to elderly counts
try:
    gini_weighted = gini(df_merge["의료기관_총수"].values, weights=df_merge["독거노인_인구수"].values)
except Exception:
    gini_weighted = np.nan

# coefficient of variation of 시설_per_1k_elder
cv = (df_merge["시설_per_1k_elder"].std() / df_merge["시설_per_1k_elder"].mean()) if df_merge["시설_per_1k_elder"].mean()!=0 else np.nan

st.subheader("요약 지표")
col1, col2, col3, col4 = st.columns(4)
col1.metric("지역 수", int(df_merge.shape[0]))
col2.metric("총 의료기관 수", int(df_merge["의료기관_총수"].sum()))
col3.metric("Gini (시설 수)", f"{gini_fac:.3f}")
col4.metric("Gini (시설/노인)", f"{gini_fac_per_elder:.3f}")

st.write(f"가중 Gini(시설 분포, 노인 인구 가중): {gini_weighted:.3f}")
st.write(f"CoV (시설 per 1k elderly): {cv:.3f}")

# Lorenz curve: facilities vs elderly
def lorenz_curve(values, weights=None):
    # returns cumulative share arrays (x=cum population share, y=cum value share)
    if weights is None:
        sorted_vals = np.sort(values)
        cumvals = np.cumsum(sorted_vals)
        total = cumvals[-1] if len(cumvals)>0 else 0
        if total==0:
            return np.array([0,1]), np.array([0,1])
        cumvals = np.insert(cumvals, 0, 0)
        x = np.linspace(0,1,len(cumvals))
        y = cumvals / total
        return x, y
    else:
        a = np.array(values, dtype=float)
        w = np.array(weights, dtype=float)
        # sort by weights? For Lorenz we usually sort by per-capita value; here we will sort by value/weight ratio
        ratio = np.zeros_like(a)
        mask = w>0
        ratio[mask] = a[mask]/w[mask]
        idx = np.argsort(ratio)
        a_s = a[idx]
        w_s = w[idx]
        cumw = np.cumsum(w_s)
        cumv = np.cumsum(a_s)
        total_w = cumw[-1] if len(cumw)>0 else 0
        total_v = cumv[-1] if len(cumv)>0 else 0
        if total_w==0 or total_v==0:
            return np.array([0,1]), np.array([0,1])
        x = np.insert(cumw/total_w, 0, 0)
        y = np.insert(cumv/total_v, 0, 0)
        return x, y

x_fac, y_fac = lorenz_curve(df_merge["의료기관_총수"].values)
x_pop, y_pop = lorenz_curve(df_merge["의료기관_총수"].values, weights=df_merge["독거노인_인구수"].values)

st.subheader("Lorenz 곡선 (시설 분포)")
fig_l = go.Figure()
fig_l.add_trace(go.Scatter(x=x_fac, y=y_fac, mode="lines+markers", name="시설 분포(지역순)"))
fig_l.add_trace(go.Scatter(x=[0,1], y=[0,1], mode="lines", name="완전 균등선", line=dict(dash="dash")))
fig_l.update_layout(xaxis_title="누적 지역(비율)", yaxis_title="누적 시설(비율)", height=400)
st.plotly_chart(fig_l, use_container_width=True)

st.subheader("Lorenz 곡선 — 시설 vs 노인(노인 가중)")
fig_lw = go.Figure()
fig_lw.add_trace(go.Scatter(x=x_pop, y=y_pop, mode="lines+markers", name="시설 대 노인(노인 가중)"))
fig_lw.add_trace(go.Scatter(x=[0,1], y=[0,1], mode="lines", name="완전 일치선", line=dict(dash="dash")))
fig_lw.update_layout(xaxis_title="누적 노인 인구(비율)", yaxis_title="누적 시설(비율)", height=400)
st.plotly_chart(fig_lw, use_container_width=True)

# Choropleth map of 시설_per_1k_elder
st.subheader("지도: 지역별 의료기관 수 (독거노인 1,000명 당)")

# load province geojson and municipal geojson (fallback to province)
province_geo = "https://raw.githubusercontent.com/southkorea/southkorea-maps/master/kostat/2013/json/skorea_provinces_geo_simple.json"
municipal_geo = "https://raw.githubusercontent.com/southkorea/southkorea-maps/master/kostat/2013/json/skorea_municipalities_geo_simple.json"

geo_prov = requests.get(province_geo).json()
prov_names = [f["properties"]["name"] for f in geo_prov["features"]]

geo_muni = requests.get(municipal_geo).json()
muni_names = [f["properties"]["name"] for f in geo_muni["features"]]

sample_regions = df_merge["지역_매칭용"].unique().tolist()
prov_match = sum(1 for r in sample_regions if r in prov_names)
muni_match = sum(1 for r in sample_regions if r in muni_names)

if prov_match >= max(1, muni_match):
    geojson_use = geo_prov
    featureidkey = "properties.name"
    locations = "지역_매칭용"
    st.write("지도 레벨: 시도")
else:
    geojson_use = geo_muni
    featureidkey = "properties.name"
    locations = "지역_매칭용"
    st.write("지도 레벨: 시군구 (가능하면 시군구명으로 매칭하세요)")

fig_map = px.choropleth(
    df_merge,
    geojson=geojson_use,
    locations=locations,
    featureidkey=featureidkey,
    color="시설_per_1k_elder",
    color_continuous_scale="YlOrRd",
    labels={"시설_per_1k_elder": "시설 per 1k elderly"},
    title="지역별 의료기관 / 1,000 독거노인"
)
fig_map.update_geos(fitbounds="locations", visible=False, showcountries=False, showframe=False, projection_type="mercator")
fig_map.update_layout(margin={"r":0,"t":40,"l":0,"b":0})
st.plotly_chart(fig_map, use_container_width=True)

# Top/bottom regions
st.subheader("상위/하위 지역 (의료기관 per 1k 독거노인)")
top_n = st.slider("표시할 지역 수", 3, 20, 5)
df_rank = df_merge[["지역","지역_매칭용","독거노인_인구수","의료기관_총수","시설_per_1k_elder"]].copy()
df_rank = df_rank.sort_values("시설_per_1k_elder", ascending=False)
st.write("Top 지역")
st.dataframe(df_rank.head(top_n).reset_index(drop=True))
st.write("Bottom 지역")
st.dataframe(df_rank.tail(top_n).sort_values("시설_per_1k_elder").reset_index(drop=True))

# Additional plot: histogram of 시설_per_1k_elder
st.subheader("분포: 의료기관 per 1k 독거노인 (히스토그램)")
fig_hist = px.histogram(df_merge, x="시설_per_1k_elder", nbins=30, title="시설 per 1k elderly 분포")
st.plotly_chart(fig_hist, use_container_width=True)

# Export processed data
st.subheader("전처리된 병합 데이터 다운로드")
to_download = df_merge[["지역","지역_매칭용","독거노인_인구수","병원_수","약국_수","복지시설_수","의료기관_총수","시설_per_1k_elder"]]
csv = to_download.to_csv(index=False).encode('utf-8')
st.download_button("CSV로 다운로드", data=csv, file_name="merged_facility_elder_analysis.csv", mime="text/csv")

st.markdown("---")
st.markdown("**해석 가이드 (간단)**\n- Gini 값이 0에 가까울수록 균등 분포, 1에 가까우면 집중됨.\n- `시설_per_1k_elder`의 CoV가 낮으면(0에 가까움) 지역 간 편차가 작아 **상대적으로 균등**함.\n- Lorenz 곡선이 대각선에서 멀수록 불균등. 노인 가중 Lorenz는 노인 분포와 시설 분포의 불일치를 보여줌.")

st.success("분석 완료 — 결과를 확인하시고 추가로 비교/필터(예: 시도만, 특정 구만) 기능을 원하시면 알려주세요!")
