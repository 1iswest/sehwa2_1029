import streamlit as st
import pandas as pd
import numpy as np
from scipy.spatial import Voronoi
import folium
from streamlit_folium import folium_static

st.set_page_config(page_title="독거노인 접근성 분석", layout="wide")
st.title("🏠 독거노인 시설 접근성 분석 웹앱")
st.write("독거노인 위치와 시설 위치를 기반으로 Voronoi 다이어그램을 지도에 시각화합니다.")

# ----------------------
# 1. 기본 데이터
# ----------------------
facility_df = pd.DataFrame({
    'name': ['병원A', '약국B', '병원C'],
    'latitude': [37.5665, 37.5651, 37.5700],
    'longitude': [126.9780, 126.9820, 126.9750]
})

elderly_df = pd.DataFrame({
    'name': ['노인1', '노인2', '노인3', '노인4'],
    'latitude': [37.5670, 37.5640, 37.5690, 37.5660],
    'longitude': [126.9800, 126.9790, 126.9760, 126.9770]
})

st.subheader("시설 위치")
st.dataframe(facility_df)

st.subheader("독거노인 위치")
st.dataframe(elderly_df)

# ----------------------
# 2. Voronoi 계산
# ----------------------
coords = facility_df[['longitude', 'latitude']].values
vor = Voronoi(coords)

# ----------------------
# 3. Folium 지도 시각화
# ----------------------
st.subheader("지도 기반 Voronoi 영역 시각화")
m = folium.Map(location=[np.mean(coords[:,1]), np.mean(coords[:,0])], zoom_start=15)

# 시설 마커
for i, row in facility_df.iterrows():
    folium.Marker(
        location=[row['latitude'], row['longitude']],
        popup=row['name'],
        icon=folium.Icon(color='red', icon='plus')
    ).add_to(m)

# 독거노인 마커
for i, row in elderly_df.iterrows():
    folium.Marker(
        location=[row['latitude'], row['longitude']],
        popup=row['name'],
        icon=folium.Icon(color='blue', icon='user')
    ).add_to(m)

# Voronoi 영역 단순 표시
for region in vor.regions:
    if not -1 in region and len(region) > 0:
        polygon = [vor.vertices[i] for i in region]
        folium.Polygon(
            locations=[(y, x) for x, y in polygon],
            color='orange',
            fill=True,
            fill_opacity=0.2
        ).add_to(m)

folium_static(m)

# ----------------------
# 4. 독거노인별 접근성 계산
# ----------------------
st.subheader("독거노인별 가장 가까운 시설")
nearest_list = []
for idx, elderly in elderly_df.iterrows():
    distances = np.sqrt((facility_df['latitude'] - elderly['latitude'])**2 +
                        (facility_df['longitude'] - elderly['longitude'])**2)
    nearest_idx = distances.idxmin()
    nearest_list.append({
        'elderly': elderly['name'],
        'nearest_facility': facility_df.loc[nearest_idx, 'name'],
        'distance': distances.min()
    })

nearest_df = pd.DataFrame(nearest_list)
st.dataframe(nearest_df)
st.write("※ 거리 단위는 위도/경도 기준이며, 실제 도로망 기반 분석과는 차이가 있습니다.")
