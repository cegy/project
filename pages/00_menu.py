import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="가족생활 가치관 대시보드", page_icon="🏠", layout="wide")

st.title("🏠 서울시 가족생활 가치관 대시보드 (Plotly)")
st.markdown("""
이 대시보드는 **성별, 연령별, 학력별, 소득별, 혼인상태, 지역별**에 따른  
가족생활 가치관(예: 자녀교육, 부부역할, 부모재산 인식 등)을 시각적으로 탐색합니다.
""")

# ---- 파일 업로드 ----
uploaded=pd.read_csv("https://raw.githubusercontent.com/cegy/project/main/family.csv", encoding="cp949")

if uploaded:
    if uploaded.name.endswith(".csv"):
        df = pd.read_csv(uploaded)
    else:
        df = pd.read_excel(uploaded)
else:
    st.info("GitHub에서 올릴 파일 구조 예시를 사용 중입니다.")
    data = {
        "구분별(1)": ["서울시"] * 6,
        "구분별(2)": ["성별", "성별", "연령별", "학력별", "소득별", "혼인상태"],
        "구분별(3)": ["남자", "여자", "30대", "대졸 이상", "300-400만원", "기혼"],
        "정기적으로자녀위주": [6.1, 5.9, 6.2, 6.0, 6.3, 6.1],
        "자녀교육배우자": [6.0, 6.1, 5.8, 6.0, 6.2, 6.0],
        "부부의공동육아": [6.2, 6.3, 6.1, 6.2, 6.4, 6.3],
        "부모재산인식": [5.5, 5.4, 5.3, 5.6, 5.5, 5.3]
    }
    df = pd.DataFrame(data)

# ---- 전처리 ----
df.columns = df.columns.str.strip()
category_cols = ["구분별(1)", "구분별(2)", "구분별(3)"]

st.sidebar.header("🎛️ 분석 필터")
selected_level2 = st.sidebar.selectbox(
    "분석 기준 선택", df["구분별(2)"].unique()
)
filtered_df = df[df["구분별(2)"] == selected_level2]

# ---- 수치형 컬럼 자동 탐색 ----
value_cols = [c for c in df.columns if c not in category_cols]

# ---- 막대그래프 ----
st.subheader(f"📊 {selected_level2}별 가치관 점수 비교")
bar_df = filtered_df.melt(id_vars=category_cols, var_name="항목", value_name="점수")

fig_bar = px.bar(
    bar_df,
    x="구분별(3)",
    y="점수",
    color="항목",
    barmode="group",
    text_auto=True,
    title=f"{selected_level2}별 가치관 점수 비교",
)
fig_bar.update_layout(xaxis_title=selected_level2, yaxis_title="평균점수(0~10)")
st.plotly_chart(fig_bar, use_container_width=True)

# ---- 레이더차트 (Radar / Spider Plot) ----
st.subheader(f"🕸️ {selected_level2}별 가치관 프로파일 (레이더차트)")
fig_radar = go.Figure()

for _, row in filtered_df.iterrows():
    fig_radar.add_trace(go.Scatterpolar(
        r=row[value_cols].values,
        theta=value_cols,
        fill='toself',
        name=row["구분별(3)"]
    ))

fig_radar.update_layout(
    polar=dict(radialaxis=dict(visible=True, range=[0, 10])),
    showlegend=True,
)
st.plotly_chart(fig_radar, use_container_width=True)

# ---- 요약 통계 ----
st.subheader("📈 요약 통계")
summary = filtered_df[value_cols].describe().T
st.dataframe(summary)

# ---- 데이터 다운로드 ----
st.download_button(
    "📥 필터링된 데이터 다운로드 (CSV)",
    data=filtered_df.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"{selected_level2}_가족생활가치관.csv",
    mime="text/csv"
)

st.caption("© 2025 가족생활 가치관 분석 | Plotly + Streamlit by 멋짐")
