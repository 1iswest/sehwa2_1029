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
- 자동 감지: 업로드하지 않으면 서버 기본 파일을 사용합니다.
""")

st.sidebar.header("데이터 업로드 (선택)")
elder_file = st.sidebar.file_uploader("독거노인 인구 파일 (CSV/XLSX)", type=["csv", "xlsx"])
facility_file = st.sidebar.file_uploader("의료기관 파일 (CSV/XLSX)", type=["csv", "xlsx"])

# --- 안전한 파일 읽기 ---
def read_any(file_or_path):
    if file_or_path is None:
        return None
    # Uploaded file object
    if hasattr(file_or_path, "read"):
        name = getattr(file_or_path, "name", "").lower()
        try:
            if name.endswith((".xls", ".xlsx")):
                return pd.read_excel(file_or_path)
            elif name.endswith(".csv"):
                try:
                    return pd.read_csv(file_or_path)  # 기본 utf-8
                except UnicodeDecodeError:
                    file_or_path.seek(0)
                    return pd.read_csv(file_or_path, encoding="cp949", errors="replace")
            else:
                raise ValueError(f"지원되지 않는 파일 형식: {name}")
        except Exception as e:
            raise e
    # Path string
    else:
        path = str(file_or_path)
        if not os.path.exists(path):
            return None
        if path.endswith((".xls", ".xlsx")):
            return pd.read_excel(path)
        elif path.endswith(".csv"):
            try:
                return pd.read_csv(path)
            except UnicodeDecodeError:
                return pd.read_csv(path, encoding="cp949", errors="replace")
        else:
            raise ValueError(f"지원되지 않는 파일 형식: {path}")

# --- 서버 기본 파일 처리 ---
if elder_file is None:
    elder_path_guess = "/mnt/data/독거노인가구비율_시도_시_군_구__20251029204458.xlsx"
    if os.path.exists(elder_path_guess):
        df_elder = read_any(elder_path_guess)
        st.sidebar.write("독거노인 파일: 서버 기본 파일 사용")
    else:
        df_elder = None
else:
    df_elder = read_any(elder_file)

if facility_file is None:
    facility_path_guess = "/mnt/data/전국의료기관 표준데이터.csv"
    if os.path.exists(facility_path_guess):
        df_facility = read_any(facility_path_guess)
        st.sidebar.write("의료기관 파일: 서버 기본 파일 사용")
    else:
        df_facility = None
else:
    df_facility = read_any(facility_file)

# --- 컬럼 자동 감지 ---
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

def detect_aggregated_cols(df):
    mapping = {}
    for c in df.columns:
        lc = c.lower()
        if any(k in lc for k in ["병원","의원","hospital","clinic"]) and any(x in lc for x in ["수","cnt","count","num"]):
            mapping["병원_수"] = c
        if "약국" in lc and any(x in lc for x in ["수","cnt","count","num"]):
            mapping["약국_수"] = c
        if any(k in lc for k in ["복지","복지관","social"]) and any(x in lc for x in ["수","cnt","count","num"]):
            mapping["복지시설_수"] = c
    return mapping

def count_facility_rows(df, region_col):
    kind_col = None
    for c in df.columns:
        lc = c.lower()
        if any(k in lc for k in FAC_KIND_KEYWORDS) or any(k in lc for k in ["의원","병원","약국","업종","종별","classification","category","type","kind","name"]):
            kind_col = c
            break
    if region_col not in df.columns:
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
            df = df.assign(_region_auto=df.iloc[:,0].astype(str))
            region_col = "_region_auto"
    else:
        df[region_col] = df[region_col].astype(str)

    if kind_col is None:
        grouped = df.groupby(region_col).size().reset_index(name="시설_총수")
        grouped = grouped.rename(columns={region_col: "지역"})
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

# --- 데이터 유효성 ---
if df_elder is None or df_facility is None:
    st.warning("독거노인 파일 또는 의료기관 파일이 업로드되지 않았거나 서버에 존재하지 않습니다.")
    st.stop()

# (이후 기존 코드 그대로 유지, df_elder_proc, df_fac, df_merge 처리...)
