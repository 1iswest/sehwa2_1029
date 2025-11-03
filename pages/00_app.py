# ... (이전 코드 생략)

# -----------------------------
# 의료기관 수 계산 및 병합
# -----------------------------
df_facility_grouped = df_facility.groupby("지역").size().reset_index(name="의료기관_수")

# 독거노인 인구 컬럼 수치형으로 변환
df_elder[target_col] = pd.to_numeric(df_elder[target_col], errors='coerce').fillna(0)

# 병합
df = pd.merge(df_elder, df_facility_grouped, on="지역", how="inner")

# *********************************
# 비율 계산 수정 (핵심 수정: 독거노인 1000명당 의료기관 수)
# *********************************
# 독거노인 1000명당 의료기관 수 = (의료기관 수 / 독거노인 수) * 1000
df["의료기관_비율"] = (df["의료기관_수"] / (df[target_col].replace(0, 1) + 1e-9)) * 1000
df = df.rename(columns={"의료기관_비율": "독거노인_1000명당_의료기관_수"})

# -----------------------------
# 병합 결과 데이터 미리보기 및 지도 시각화 제목/색상 범위 수정
# -----------------------------
st.subheader(" 병합 결과 데이터")
st.dataframe(df[["지역", target_col, "의료기관_수", "독거노인_1000명당_의료기관_수"]])

# ... (중간 코드 생략)

fig = px.choropleth(
    df,
    geojson=geojson,
    locations="지역",
    featureidkey="properties.name",
    color="독거노인_1000명당_의료기관_수", # 수정된 컬럼명 사용
    color_continuous_scale="RdYlGn",
    title="시도별 독거노인 **1000명당** 의료기관 분포", # 제목 수정
    # 비율의 최대/최소값을 사용하여 색상 범위 설정
    range_color=(df["독거노인_1000명당_의료기관_수"].min(), df["독거노인_1000명당_의료기관_수"].max()),
    hover_data={
        "지역": True, 
        target_col: True, 
        "의료기관_수": True,
        "독거노인_1000명당_의료기관_수": ':.2f' # 소수점 둘째 자리까지 표시
    }
)

# ... (나머지 코드 생략)
