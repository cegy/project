import io
import os
import re
import pdfplumber
import pandas as pd
import streamlit as st
import numpy as np

import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="서울시민 결혼·가족 변화 분석 (Plotly 버전)", layout="wide")

# ---------------------------
# 고정 파일 경로 (main.py와 동일 폴더)
# ---------------------------
PDF_FILENAME = "서울시민의+결혼과+가족+형태의+변화+분석.pdf"
PDF_PATH = os.path.join(os.path.dirname(__file__), PDF_FILENAME)

METRICS_CSV_NAME = "seoul_family_metrics.csv"
METRICS_CSV_PATH = os.path.join(os.path.dirname(__file__), METRICS_CSV_NAME)

# ---------------------------
# 캐시 유틸
# ---------------------------
@st.cache_data(show_spinner=False)
def read_pdf_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

@st.cache_data(show_spinner=False)
def extract_text_from_pdf(file_bytes: bytes) -> str:
    text_chunks = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text(x_tolerance=1.5, y_tolerance=1.5) or ""
            t = re.sub(r"[ \t]+", " ", t)
            text_chunks.append(t.strip())
    return "\n\n".join(text_chunks)

def split_sentences_rough_korean(text: str):
    # 마침표/물음표/느낌표/개행 기준 간단 분리
    sents = re.split(r'(?<=[.!?])\s+|\n+', text)
    return [s.strip() for s in sents if len(s.strip()) > 1]

def keyword_hits(sentences, kw):
    kw_norm = kw.lower()
    rows = []
    for i, s in enumerate(sentences):
        if kw_norm in s.lower():
            rows.append({"keyword": kw, "sentence_idx": i, "sentence": s})
    return rows

def make_snippet(hit, window=160):
    s = hit["sentence"]
    if len(s) <= window:
        return s
    return s[: window//2] + " … " + s[-window//2 :]

@st.cache_data(show_spinner=False)
def load_metrics_csv(path: str):
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    if "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
        df = df.sort_values("year")
    return df

def make_metrics_template_df():
    cols = [
        "year",
        "marriage_rate",            # 혼인율
        "first_marriage_age_m",     # 남자 평균 초혼연령
        "first_marriage_age_f",     # 여자 평균 초혼연령
        "divorce_rate",             # 이혼율
        "tfr",                      # 합계출산율
        "one_person_share"          # 1인 가구 비중(%)
    ]
    years = [2015, 2018, 2020, 2022, 2024]
    df = pd.DataFrame({c: [None]*len(years) for c in cols})
    df["year"] = years
    return df[cols]

def melt_for_line(df, year_col, metric_cols):
    d = df[[year_col] + metric_cols].copy()
    # 숫자형으로 변환
    for c in metric_cols:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    long = d.melt(id_vars=year_col, value_vars=metric_cols,
                  var_name="metric", value_name="value")
    return long

def corr_dataframe(df, cols):
    d = df[cols].apply(pd.to_numeric, errors="coerce")
    return d.corr()

# ---------------------------
# 사이드바 - 공통 분석 설정
# ---------------------------
st.sidebar.header("🔎 텍스트 분석 설정")
default_keywords = [
    "혼인율", "초혼", "재혼", "이혼", "출산", "합계출산율",
    "1인 가구", "비혼", "만혼", "동거", "가족형태", "출생", "고령화"
]
keywords = st.sidebar.text_area(
    "관심 키워드(줄바꿈으로 구분)",
    value="\n".join(default_keywords),
    height=180
).splitlines()
keywords = [k.strip() for k in keywords if k.strip()]
context_window = st.sidebar.slider("문맥 스니펫 길이(문자수)", 60, 400, 160, 20)

st.sidebar.header("📈 지표 대시보드 설정")
metric_defaults = ["marriage_rate", "tfr", "one_person_share"]
selected_metrics = st.sidebar.text_input(
    "표시할 지표(쉼표로 구분)",
    value=", ".join(metric_defaults)
)
selected_metrics = [m.strip() for m in selected_metrics.split(",") if m.strip()]

# ---------------------------
# 상단 정보
# ---------------------------
st.title("📊 서울시민의 결혼·가족 형태 변화 — Plotly 대시보드")
st.caption("같은 폴더의 PDF와 CSV를 직접 읽어 분석합니다.")
st.write(f"PDF 파일: **{PDF_FILENAME}**")
st.caption(f"경로: `{PDF_PATH}`")

# ---------------------------
# 탭 구성
# ---------------------------
tab1, tab2 = st.tabs(["📰 텍스트 분석 (PDF)", "📊 지표 대시보드 (CSV)"])

# ===========================
# 탭 1: 텍스트 분석
# ===========================
with tab1:
    if not os.path.exists(PDF_PATH):
        st.error("지정된 PDF 파일을 찾을 수 없습니다. `main.py`와 같은 폴더에 "
                 f"`{PDF_FILENAME}` 파일이 있는지 확인하세요.")
        st.stop()

    with st.spinner("PDF에서 텍스트 추출 중…"):
        raw_bytes = read_pdf_bytes(PDF_PATH)
        raw_text = extract_text_from_pdf(raw_bytes)

    sentences = split_sentences_rough_korean(raw_text)
    st.success(f"텍스트 추출 완료: 약 {len(sentences)}개 문장")

    # 키워드 검색/시각화
    hits_all = []
    for kw in keywords:
        hits_all.extend(keyword_hits(sentences, kw))

    if hits_all:
        df_hits = pd.DataFrame(hits_all)
        counts = (
            df_hits["keyword"]
            .value_counts()
            .rename_axis("keyword")
            .reset_index(name="count")
            .sort_values("count", ascending=False)
        )

        st.subheader("📈 키워드 출현 빈도 (Plotly)")
        fig_bar = px.bar(
            counts,
            x="keyword",
            y="count",
            text="count",
            title="Keyword Frequency",
        )
        fig_bar.update_traces(textposition="outside")
        fig_bar.update_layout(xaxis_title="키워드", yaxis_title="빈도", margin=dict(t=60))
        st.plotly_chart(fig_bar, use_container_width=True)

        st.subheader("🧩 문맥 스니펫")
        df_hits["snippet"] = df_hits.apply(lambda r: make_snippet(r, context_window), axis=1)
        show_cols = ["keyword", "sentence_idx", "snippet"]
        st.dataframe(df_hits[show_cols], use_container_width=True, height=360)

        csv = df_hits[show_cols + ["sentence"]].to_csv(index=False).encode("utf-8-sig")
        st.download_button("CSV로 내보내기", data=csv, file_name="keyword_snippets.csv", mime="text/csv")
    else:
        st.info("설정한 키워드가 본문에서 발견되지 않았습니다. 사이드바에서 키워드를 조정해 보세요.")

    # 간단 요약
    st.subheader("📝 간단 요약(룰 기반)")
    years = sorted(set(re.findall(r"\b(19\d{2}|20\d{2})\b", raw_text)))
    bullets = []
    if years:
        bullets.append(f"- 보고서에 등장하는 연도 범위: **{years[0]}–{years[-1]}**")
    for term in ["혼인율", "초혼", "이혼", "출산", "합계출산율", "1인 가구", "비혼", "동거", "만혼"]:
        if re.search(term, raw_text):
            bullets.append(f"- **{term}** 관련 서술이 포함되어 있음")
    if not bullets:
        bullets.append("- 주요 용어를 찾지 못했습니다. 키워드/스니펫 결과를 참고하세요.")
    for b in bullets:
        st.markdown(b)

    with st.expander("📄 본문 미리보기"):
        st.text_area("텍스트(일부)", value=raw_text[:8000], height=260)

# ===========================
# 탭 2: 지표 대시보드
# ===========================
with tab2:
    st.write(f"CSV 파일(선택): **{METRICS_CSV_NAME}**")
    st.caption(f"경로: `{METRICS_CSV_PATH}`")

    dfm = load_metrics_csv(METRICS_CSV_PATH)

    if dfm is None:
        st.warning("지표 CSV가 없습니다. 아래 템플릿을 내려받아 수치를 채운 뒤 "
                   f"`{METRICS_CSV_NAME}` 이름으로 같은 폴더에 저장하세요.")
        template_df = make_metrics_template_df()
        st.dataframe(template_df, use_container_width=True, height=240)

        csv_bytes = template_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "지표 템플릿 CSV 다운로드",
            data=csv_bytes,
            file_name=METRICS_CSV_NAME,
            mime="text/csv"
        )
    else:
        st.success("지표 CSV 로드 완료")
        st.dataframe(dfm, use_container_width=True, height=300)

        # 선택 지표 유효성 필터
        numeric_cols = [c for c in dfm.columns if c != "year"]
        active_cols = [c for c in selected_metrics if c in dfm.columns and c != "year"]
        if not active_cols:
            active_cols = [c for c in metric_defaults if c in dfm.columns]

        # ----- 시계열 라인차트 (Plotly) -----
        st.subheader("📈 시계열 라인차트 (Plotly)")
        try:
            long = melt_for_line(dfm, "year", active_cols)
            fig_line = px.line(
                long,
                x="year",
                y="value",
                color="metric",
                markers=True,
                title="Selected Metrics Over Time"
            )
            fig_line.update_layout(
                xaxis_title="year",
                yaxis_title="value",
                hovermode="x unified",
                margin=dict(t=60)
            )
            st.plotly_chart(fig_line, use_container_width=True)
        except Exception as e:
            st.error(f"라인차트에서 오류가 발생했습니다: {e}")

        # ----- 전년 대비 증감률 -----
        st.subheader("↕️ 전년 대비 증감률(%)")
        pct_df = dfm[["year"] + active_cols].copy()
        for col in active_cols:
            pct_df[col] = pd.to_numeric(pct_df[col], errors="coerce")
            pct_df[col] = pct_df[col].pct_change() * 100.0
        st.dataframe(pct_df, use_container_width=True, height=220)

        # 증감률 라인(옵션)
        try:
            long_pct = melt_for_line(pct_df, "year", active_cols)
            fig_pct = px.line(
                long_pct,
                x="year",
                y="value",
                color="metric",
                markers=True,
                title="YoY Change (%)"
            )
            fig_pct.update_layout(xaxis_title="year", yaxis_title="pct_change(%)", hovermode="x unified")
            st.plotly_chart(fig_pct, use_container_width=True)
        except Exception:
            pass

        # ----- 상관행렬 (Plotly Heatmap) -----
        st.subheader("🔗 지표 상관행렬")
        try:
            corr_cols = [c for c in active_cols if c in dfm.columns]
            if len(corr_cols) >= 2:
                corr = corr_dataframe(dfm, corr_cols)
                # 히트맵 + 값 표시
                heat = go.Heatmap(
                    z=corr.values,
                    x=corr_cols,
                    y=corr_cols,
                    zmin=-1, zmax=1,
                    colorbar=dict(title="corr")
                )
                fig_corr = go.Figure(data=[heat])
                # 값 annotation
                annotations = []
                for i, row in enumerate(corr.values):
                    for j, val in enumerate(row):
                        annotations.append(
                            dict(
                                x=corr_cols[j],
                                y=corr_cols[i],
                                text=f"{val:.2f}",
                                xref="x1", yref="y1",
                                showarrow=False
                            )
                        )
                fig_corr.update_layout(
                    title="Correlation Matrix",
                    annotations=annotations,
                    margin=dict(t=60)
                )
                st.plotly_chart(fig_corr, use_container_width=True)
            else:
                st.info("상관행렬을 보려면 2개 이상의 지표가 필요합니다.")
        except Exception as e:
            st.error(f"상관행렬에서 오류가 발생했습니다: {e}")
