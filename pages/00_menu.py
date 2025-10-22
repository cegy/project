import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="가족형태 및 시간 사용 대시보드", page_icon="👨‍👩‍👧‍👦", layout="wide")

st.title("👨‍👩‍👧‍👦 가족형태 및 시간 사용 분석 대시보드 (Plotly)")

st.markdown("""
이 대시보드는 가족형태별, 요일별, 연령대별 **시간 사용 패턴**을 분석합니다.  
CSV 파일을 업로드하거나, 기본 샘플 데이터를 사용해보세요.
""")

# ---- CSV 업로드 ----
uploaded = st.file_uploader("📂 CSV 파일 업로드 (예: 가족형태, 연령대, 요일, 사용시간 컬럼 포함)", type=["csv"])

if uploaded:
    df = pd.read_csv(uploaded)
else:
    st.info("샘플 데이터를 불러왔습니다. (가족형태, 연령대, 요일, 사용시간 예시)")
    data = {
        "가족형태": ["핵가족", "1인가구", "확대가족", "핵가족", "1인가구", "핵가족", "확대가족", "1인가구"] * 3,
        "연령대": ["10대", "20대", "30대", "40대", "50대", "60대", "70대", "20대"] * 3,
        "요일": ["월", "화", "수", "목", "금", "토", "일", "일"] * 3,
        "사용시간(시간)": [4, 3, 5, 6, 7, 8, 5, 2] * 3,
    }
    df = pd.DataFrame(data)

# ---- 데이터 요약 ----
st.subheader("📊 데이터 미리보기")
st.dataframe(df.head())

# ---- 필터 설정 ----
st.sidebar.header("🔍 필터 설정")
selected_family = st.sidebar.multiselect("가족형태 선택", options=df["가족형태"].unique(), default=df["가족형태"].unique())
selected_day = st.sidebar.multiselect("요일 선택", options=df["요일"].unique(), default=df["요일"].unique())

filtered_df = df[df["가족형태"].isin(selected_family) & df["요일"].isin(selected_day)]

# ---- 1. 가족형태별 평균 시간 ----
st.subheader("👪 가족형태별 평균 사용시간")
avg_time = filtered_df.groupby("가족형태")["사용시간(시간)"].mean().reset_index()
fig1 = px.bar(
    avg_time,
    x="가족형태",
    y="사용시간(시간)",
    color="가족형태",
    text_auto=True,
    title="가족형태별 평균 사용시간",
)
st.plotly_chart(fig1, use_container_width=True)

# ---- 2. 요일별 시간 사용 변화 ----
st.subheader("📅 요일별 평균 시간 사용 추이")
day_time = filtered_df.groupby(["요일", "가족형태"])["사용시간(시간)"].mean().reset_index()
fig2 = px.line(
    day_time,
    x="요일",
    y="사용시간(시간)",
    color="가족형태",
    markers=True,
    title="요일별 시간 사용 변화",
)
st.plotly_chart(fig2, use_container_width=True)

# ---- 3. 연령대별 사용시간 비교 ----
st.subheader("👶 연령대별 시간 사용 분포")
fig3 = px.box(
    filtered_df,
    x="연령대",
    y="사용시간(시간)",
    color="가족형태",
    points="all",
    title="연령대별 사용시간 분포",
)
st.plotly_chart(fig3, use_container_width=True)

# ---- 데이터 다운로드 ----
st.download_button(
    label="📥 필터링된 데이터 다운로드 (CSV)",
    data=filtered_df.to_csv(index=False).encode("utf-8-sig"),
    file_name="가족형태_시간사용_분석결과.csv",
    mime="text/csv",
)

st.caption("© 2025 교육용 대시보드 | Plotly + Streamlit Demo")
