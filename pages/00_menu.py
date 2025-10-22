import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="가족생활 가치관 시각화", page_icon="🏠", layout="wide")
st.title("🏠 가족생활 가치관 데이터 대시보드")

# -----------------------------
# 데이터 불러오기
# -----------------------------
#uploaded = st.file_uploader("📂 가족생활 가치관 CSV 또는 엑셀 파일 업로드", type=["csv", "xlsx"])
uploaded=pd.read_csv("https://raw.githubusercontent.com/cegy/project/main/family.csv", encoding="cp949")
if uploaded:
    if uploaded.name.endswith(".csv"):
        df = pd.read_csv(uploaded, encoding="utf-8-sig")
    else:
        df = pd.read_excel(uploaded, header=[0,1]) if st.checkbox("2행 머리글 사용") else pd.read_excel(uploaded)
else:
    st.stop()

# MultiIndex 헤더 병합 (2016|자녀위주 등)
if isinstance(df.columns, pd.MultiIndex):
    df.columns = ['|'.join([str(c) for c in col if str(c) != 'nan']).strip() for col in df.columns]

# 컬럼 정리
df.columns = [str(c).strip() for c in df.columns]
if "구분별(2)" not in df.columns or "구분별(3)" not in df.columns:
    st.error("⚠️ '구분별(2)', '구분별(3)' 열이 포함되어야 합니다.")
    st.stop()

# Melt하여 긴형으로 변환
category_cols = ["구분별(1)", "구분별(2)", "구분별(3)"]
value_cols = [c for c in df.columns if c not in category_cols]
long_df = df.melt(id_vars=category_cols, value_vars=value_cols, var_name="항목", value_name="점수")
long_df["점수"] = pd.to_numeric(long_df["점수"], errors="coerce")

# -----------------------------
# 버튼 UI
# -----------------------------
st.sidebar.header("🔍 분석 구분 선택")

categories = ["성별", "연령별", "학력별", "소득별", "혼인상태", "지역별"]
selected = None

cols = st.columns(3)
for i, cat in enumerate(categories):
    if cols[i % 3].button(cat):
        selected = cat

if not selected:
    st.info("왼쪽 또는 위의 버튼을 눌러 시각화할 구분을 선택하세요.")
    st.stop()

# -----------------------------
# 선택된 구분별 데이터 필터링
# -----------------------------
filtered = long_df[long_df["구분별(2)"] == selected]
if filtered.empty:
    st.warning(f"'{selected}' 데이터가 없습니다.")
    st.stop()

# -----------------------------
# Plotly 시각화
# -----------------------------
st.subheader(f"📊 {selected}별 가족가치관 점수 비교")

fig_bar = px.bar(
    filtered,
    x="구분별(3)",
    y="점수",
    color="항목",
    barmode="group",
    text_auto=True,
    title=f"{selected}별 항목별 평균 점수",
)
fig_bar.update_layout(xaxis_title=selected, yaxis_title="점수(0~10)")
st.plotly_chart(fig_bar, use_container_width=True)

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
fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0,10])), showlegend=True)
st.plotly_chart(fig_radar, use_container_width=True)

st.subheader(f"🌡️ {selected}별 × 항목 히트맵")
pivot = filtered.pivot_table(index="구분별(3)", columns="항목", values="점수", aggfunc="mean")
fig_heat = px.imshow(
    pivot,
    aspect="auto",
    labels=dict(x="항목", y=selected, color="점수"),
    title=f"{selected}별 × 항목 히트맵",
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
