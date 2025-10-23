import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="가족생활 가치관 시각화", page_icon="🏠", layout="wide")
st.title("🏠 가족생활 가치관 데이터 대시보드")

# -----------------------------
# 데이터 불러오기
# -----------------------------
st.sidebar.header("📂 데이터 불러오기")
use_github = st.sidebar.checkbox("GitHub에서 family.csv 불러오기", value=True)

data_url = "https://raw.githubusercontent.com/cegy/project/main/family.csv"
df = None

try:
    if use_github:
        df = pd.read_csv(data_url, encoding="utf-8-sig", header=[0, 1])
        st.sidebar.success("✅ GitHub 데이터 불러오기 성공")
    else:
        uploaded = st.file_uploader("CSV 또는 XLSX 파일 업로드", type=["csv", "xlsx"])
        if uploaded is not None:
            if uploaded.name.endswith(".csv"):
                df = pd.read_csv(uploaded, encoding="utf-8-sig", header=[0, 1])
            else:
                df = pd.read_excel(uploaded, header=[0, 1])
except Exception as e:
    st.error(f"데이터 불러오기 실패: {e}")
    st.stop()

if df is None:
    st.warning("❗ 데이터를 불러오지 못했습니다.")
    st.stop()

# -----------------------------
# MultiIndex 컬럼 처리
# -----------------------------
# 위 행은 연도(2016), 아래 행은 항목명
df.columns = [f"{a}_{b}".strip("_") for a, b in df.columns]
df.columns = [c.replace("2016_", "").strip() for c in df.columns]  # '2016_' 제거

# -----------------------------
# 데이터 정리
# -----------------------------
category_cols = ["구분별(1)", "구분별(2)", "구분별(3)"]
if not all(c in df.columns for c in category_cols):
    st.error("⚠️ '구분별(1)', '구분별(2)', '구분별(3)' 열이 필요합니다.")
    st.stop()

value_cols = [c for c in df.columns if c not in category_cols]
long_df = df.melt(
    id_vars=category_cols,
    value_vars=value_cols,
    var_name="항목",
    value_name="점수"
)
long_df["점수"] = pd.to_numeric(long_df["점수"], errors="coerce")

# -----------------------------
# 분석 구분 선택
# -----------------------------
st.sidebar.header("🔍 분석 구분 선택")
categories = ["성별", "연령별", "학력별", "소득별", "혼인상태", "지역별"]
selected = st.sidebar.radio("분석할 구분을 선택하세요", categories, index=0)

filtered = long_df[long_df["구분별(2)"] == selected]
if filtered.empty:
    st.warning(f"'{selected}' 데이터가 없습니다.")
    st.stop()

# -----------------------------
# 시각화 1. 막대그래프
# -----------------------------
st.subheader(f"📊 {selected}별 가족가치관 항목별 평균 점수")

fig_bar = px.bar(
    filtered,
    x="구분별(3)",
    y="점수",
    color="항목",
    barmode="group",
    text_auto=True,
    title=f"{selected}별 항목별 평균 점수"
)
fig_bar.update_layout(
    xaxis_title=selected,
    yaxis_title="점수(0~10)",
    legend_title="항목명",
    legend=dict(orientation="h", y=-0.2)
)
st.plotly_chart(fig_bar, use_container_width=True)

# -----------------------------
# 시각화 2. 레이더차트
# -----------------------------
st.subheader(f"🕸️ {selected}별 가족가치관 프로파일 (레이더차트)")

fig_radar = go.Figure()
for name, sub in filtered.groupby("구분별(3)"):
    pivot = sub.groupby("항목")["점수"].mean()
    fig_radar.add_trace(go.Scatterpolar(
        r=pivot.values,
        theta=pivot.index,
        fill='toself',
        name=name
    ))

fig_radar.update_layout(
    polar=dict(radialaxis=dict(visible=True, range=[0, 10])),
    showlegend=True
)
st.plotly_chart(fig_radar, use_container_width=True)

# -----------------------------
# 시각화 3. 히트맵
# -----------------------------
st.subheader(f"🌡️ {selected}별 × 항목 히트맵")

pivot = filtered.pivot_table(
    index="구분별(3)",
    columns="항목",
    values="점수",
    aggfunc="mean"
)

fig_heat = px.imshow(
    pivot,
    aspect="auto",
    color_continuous_scale="RdYlGn_r",
    labels=dict(x="항목", y=selected, color="점수"),
    title=f"{selected}별 × 항목 히트맵"
)
st.plotly_chart(fig_heat, use_container_width=True)

# -----------------------------
# 다운로드
# -----------------------------
st.download_button(
    "📥 현재 보기 데이터 다운로드 (CSV)",
    data=filtered.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"{selected}_가족가치관.csv",
    mime="text/csv"
)
