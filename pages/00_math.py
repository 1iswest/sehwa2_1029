# 파일명: facility_access_folium.py

import streamlit as st
import pandas as pd
import numpy as np
from scipy.spatial import Voronoi
import folium
from streamlit_folium import folium_static

st.set_page_config(page_title="시설 접근성 분석", layout="wide")
st.title("🏥 병원/약국 접근성 분석 웹앱")
st.write("시설 위치를 기반으로 Voronoi 다이어그램을 Folium 지도에 시각화합니다.")

# ----------------------
# 1. 시설 위치 입력
# ----------------------
st.sidebar.header("시설 위치 입력")
upload_file = st.sidebar.file_uploader("시설 좌표 CSV 업로드", type=['csv'])
st.sidebar.write("CSV 파일은 'name', 'latitude', 'longitude' 컬럼 필요")

if upload_file is not None:
    df = pd.read_csv(upload_file)
    st.write("업로드한 시설 데이터:")
    st.dataframe(df)
else:
    st.info("CSV를 업로드하지 않았습니다. 기본 예시 데이터를 사용합니다.")
    df = pd.DataFrame({
        'name': ['병원A', '약국B', '병원C', '약국D'],
        'latitude': [37.5665, 37.5651, 37.5700, 37.5680],
        'longitude': [126.9780, 126.9820, 126.9750, 126.9900]
    })
    st.dataframe(df)

# ----------------------
# 2. Voronoi 다이어그램 계산
# ----------------------
coords = df[['longitude', 'latitude']].values
vor = Voronoi(coords)

# ----------------------
# 3. 지도 기반 시각화 (Folium)
# ----------------------
st.subheader("지도 기반 Voronoi 영역 시각화")
m = folium.Map(location=[np.mean(coords[:,1]), np.mean(coords[:,0])], zoom_start=14)

# 시설 표시
for i, row in df.iterrows():
    folium.Marker(
        location=[row['latitude'], row['longitude']],
        popup=row['name'],
        icon=folium.Icon(color='red', icon='info-sign')
    ).add_to(m)

# Voronoi 영역 폴리곤 표시 (단순화)
for region in vor.regions:
    if not -1 in region and len(region) > 0:
        polygon = [vor.vertices[i] for i in region]
        # Folium 좌표 형식: [lat, lon]
        folium.Polygon(
            locations=[(y, x) for x, y in polygon],
            color='blue',
            fill=True,
            fill_opacity=0.2
        ).add_to(m)

folium_static(m)

# ----------------------
# 4. 간단한 접근성 분석
# ----------------------
st.subheader("시설별 접근성 요약")
center_lat, center_lon = np.mean(coords[:,1]), np.mean(coords[:,0])
df['distance_to_center'] = np.sqrt((df['latitude']-center_lat)**2 + (df['longitude']-center_lon)**2)
st.dataframe(df[['name','distance_to_center']])
st.write("※ 거리 단위는 위도/경도 기준이며, 실제 도로망 기반 분석과는 차이가 있습니다.")
