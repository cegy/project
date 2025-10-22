import io
import os
import re
from typing import List, Tuple, Optional, Dict

import pdfplumber
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="PDF 표 → 시각화(자동 필터링)", layout="wide")

# --------- 설정 ---------
PDF_FILENAME = "서울시민의+결혼과+가족+형태의+변화+분석.pdf"
PDF_PATH = os.path.join(os.path.dirname(__file__), PDF_FILENAME)

NUM_RE = re.compile(r"^-?\s*[\d,]+(?:\.\d+)?\s*%?$")

# --------- 숫자/연도 유틸 ---------
def to_number(x):
    if pd.isna(x):
        return pd.NA
    s = str(x).strip()
    if not NUM_RE.match(s):
        return pd.NA
    is_pct = s.endswith("%")
    s = s.replace("%", "").replace(",", "")
    try:
        val = float(s)
        return val / 100.0 if is_pct else val
    except Exception:
        return pd.NA

def is_year_like(s) -> bool:
    try:
        v = int(str(s).strip())
        return 1900 <= v <= 2100
    except Exception:
        return False

# --------- 전처리 ---------
def clean_table(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()
    df = df.applymap(lambda x: "" if pd.isna(x) else str(x).strip())
    # 첫 행이 헤더로 보이면 헤더로 승격
    header_row = df.iloc[0]
    if (header_row != "").mean() >= 0.5:
        df.columns = header_row
        df = df.iloc[1:].reset_index(drop=True)
    # 빈 컬럼명 보정
    df.columns = [c if str(c).strip() != "" else f"col_{i}" for i, c in enumerate(df.columns)]
    # 완전 빈 행 제거
    df = df[~(df.apply(lambda r: (r == "").all(), axis=1))].reset_index(drop=True)
    return df

def coerce_numeric_cols(df: pd.DataFrame, exclude: Optional[List[str]] = None) -> pd.DataFrame:
    exclude = exclude or []
    out = df.copy()
    for c in out.columns:
        if c in exclude:
            continue
        out[c] = out[c].apply(to_number)
    return out

# --------- 세로/가로 구조 감지 & long 변환 ---------
def to_long_vertical(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    # 연도 컬럼 후보
    cols = list(df.columns)
    # 1) 이름으로 추정
    name_hits = [c for c in cols if re.search(r"(연도|년도|year|Year|시점|기간)", str(c))]
    year_col = name_hits[0] if name_hits else None
    # 2) 값으로 추정
    if year_col is None:
        for c in cols:
            try:
                vals = pd.to_numeric(df[c], errors="coerce")
                ok = vals.dropna()
                if len(ok) >= max(3, len(df)//3) and (ok.between(1900,2100)).mean() > 0.6:
                    year_col = c
                    break
            except Exception:
                pass
    if year_col is None:
        return None

    value_cols = [c for c in cols if c != year_col]
    if not value_cols:
        return None

    df2 = df.copy()
    # 숫자 변환
    df2 = coerce_numeric_cols(df2, exclude=[year_col])
    # 연도 숫자화
    df2[year_col] = pd.to_numeric(df2[year_col], errors="coerce")

    # value_cols 중 시각화 가능한 것만 남김(유효값≥2 & 분산>0)
    keep = []
    for c in value_cols:
        s = pd.to_numeric(df2[c], errors="coerce")
        s_valid = s.dropna()
        if len(s_valid) >= 2 and (s_valid.max() != s_valid.min()):
            keep.append(c)
    if not keep:
        return None

    long = df2[[year_col] + keep].melt(id_vars=year_col, value_vars=keep,
                                       var_name="metric", value_name="value")
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    long = long.dropna(subset=["value", year_col])
    if long.empty or long[year_col].nunique() < 2:
        return None
    long = long.sort_values([year_col, "metric"]).reset_index(drop=True)
    long.attrs["year_col"] = year_col
    return long

def to_long_horizontal(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    # 열 머리글에 연도가 2개 이상이면 가로형으로 판단
    year_cols = [c for c in df.columns if is_year_like(c)]
    if len(year_cols) < 2:
        return None

    # 지표/항목 열(첫 번째 비연도 열) 추정
    non_year = [c for c in df.columns if c not in year_cols]
    if not non_year:
        # 모든 열이 연도면, 행 머리 첫 컬럼을 metric으로 가정
        metric_col = "metric"
        df2 = df.copy()
        df2.insert(0, metric_col, [f"row_{i}" for i in range(len(df2))])
    else:
        metric_col = non_year[0]
        df2 = df.copy()

    # 값 숫자화
    numeric_years = [int(c) for c in year_cols]
    for c in year_cols:
        df2[c] = df2[c].apply(to_number)

    # 지표 이름 공백 제거
    df2[metric_col] = df2[metric_col].astype(str).str.strip()

    long = df2.melt(id_vars=metric_col, value_vars=year_cols,
                    var_name="year", value_name="value")
    long["year"] = pd.to_numeric(long["year"], errors="coerce")
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    long = long.dropna(subset=["value", "year"])

    # 각 metric마다 유효값 ≥2 & 분산>0 필터
    ok_metrics = []
    for m, g in long.groupby(metric_col):
        vals = g["value"].dropna()
        if len(vals) >= 2 and (vals.max() != vals.min()):
            ok_metrics.append(m)
    long = long[long[metric_col].isin(ok_metrics)]
    if long.empty or long["year"].nunique() < 2:
        return None

    # 표준 컬럼명으로 통일
    long = long.rename(columns={metric_col: "metric", "year": "year"})
    long.attrs["year_col"] = "year"
    return long

def pick_first_visualizable_long(tables: List[Tuple[int, pd.DataFrame]]) -> Tuple[int, pd.DataFrame, pd.DataFrame]:
    """
    tables에서 시각화 가능한 long 데이터가 나올 때까지 검사.
    반환: (page_no, df_clean, df_long)
    """
    for pno, raw in tables:
        dfc = clean_table(raw)
        # 1) 세로형 시도
        long_v = to_long_vertical(dfc)
        if long_v is not None:
            return pno, dfc, long_v
        # 2) 가로형 시도
        long_h = to_long_horizontal(dfc)
        if long_h is not None:
            return pno, dfc, long_h
    # 없으면 첫 표 반환 + 빈 long
    if tables:
        pno, raw = tables[0]
        return pno, clean_table(raw), pd.DataFrame(columns=["year", "metric", "value"])
    return -1, pd.DataFrame(), pd.DataFrame(columns=["year", "metric", "value"])

# --------- PDF 테이블 추출 ---------
@st.cache_data(show_spinner=False)
def extract_tables_from_pdf(path: str) -> List[Tuple[int, pd.DataFrame]]:
    results: List[Tuple[int, pd.DataFrame]] = []
    with pdfplumber.open(path) as pdf:
        for p_idx, page in enumerate(pdf.pages):
            try:
                tables = page.extract_tables(
                    {
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "lines",
                        "intersection_tolerance": 5,
                    }
                )
            except Exception:
                tables = page.extract_tables()
            for t in tables or []:
                if not t:
                    continue
                df = pd.DataFrame(t)
                if df.replace("", pd.NA).dropna(how="all").empty:
                    continue
                results.append((p_idx + 1, df))
    return results

# --------- UI ---------
st.title("📄 PDF 표에서 ‘시각화 가능한 데이터’만 자동 선택 → 📊 Plotly")
st.caption("세로/가로 표 구조를 자동 인지하고, 숫자 칼럼만 남겨 시각화합니다.")

st.write(f"PDF 파일: **{PDF_FILENAME}**")
st.caption(f"경로: `{PDF_PATH}`")

if not os.path.exists(PDF_PATH):
    st.error("PDF 파일을 찾을 수 없습니다. 같은 폴더에 파일이 있는지 확인하세요.")
    st.stop()

with st.spinner("PDF에서 표 추출 중…"):
    tables = extract_tables_from_pdf(PDF_PATH)

if not tables:
    st.error("표를 찾지 못했습니다. 스캔(이미지) PDF일 수 있습니다. 벡터/텍스트 기반 PDF를 사용하거나 CSV로 변환해 주세요.")
    st.stop()

# 표 선택 목록
table_labels = [f"p.{p} - table#{i+1} (shape={df.shape[0]}x{df.shape[1]})"
                for i, (p, df) in enumerate(tables)]
default_pno, default_clean, default_long = pick_first_visualizable_long(tables)
default_idx = 0
if default_pno != -1:
    for i, (p, _) in enumerate(tables):
        if p == default_pno:
            default_idx = i
            break

idx = st.selectbox("표 선택 (자동으로 시각화 가능한 표가 기본 선택됩니다)",
                   options=list(range(len(tables))),
                   index=default_idx,
                   format_func=lambda i: table_labels[i])

page_no, df_raw = tables[idx]
df_clean = clean_table(df_raw)

# 현재 선택 표에서 long 데이터 만들기(세로/가로 둘 다 시도)
df_long_v = to_long_vertical(df_clean)
df_long_h = to_long_horizontal(df_clean)
df_long = df_long_v if df_long_v is not None else df_long_h

st.info(f"선택: p.{page_no} 표 | 원본 shape: {df_raw.shape} → 전처리 shape: {df_clean.shape}")
st.subheader("🧹 전처리된 표 미리보기")
st.dataframe(df_clean, use_container_width=True, height=260)

if df_long is None or df_long.empty:
    st.warning("이 표에서는 시각화 가능한 숫자 시리즈를 찾지 못했습니다. 다른 표를 선택해 보세요.")
    st.stop()

year_col = df_long.attrs.get("year_col", "year")
st.caption(f"인식된 연도 컬럼: **{year_col}**")

# 시각화 가능한 metric만 남음 → 사용자가 선택 가능
metrics_all = sorted(df_long["metric"].dropna().unique().tolist())
# 데이터 포인트(연도) 수 기준으로 상위 metrics 추려 기본 선택
metric_scores: Dict[str, int] = {m: df_long[df_long["metric"] == m][year_col].nunique() for m in metrics_all}
metrics_sorted = sorted(metrics_all, key=lambda m: (-metric_scores[m], m))
default_metrics = metrics_sorted[: min(5, len(metrics_sorted))]

selected_metrics = st.multiselect(
    "시각화할 지표 선택(최소 1개)",
    options=metrics_all,
    default=default_metrics
)
if not selected_metrics:
    st.info("한 개 이상 지표를 선택하세요.")
    st.stop()

df_plot = df_long[df_long["metric"].isin(selected_metrics)].copy()

# 연도 범위 안내
years_nonnull = df_plot[year_col].dropna()
if not years_nonnull.empty:
    st.caption(f"연도 범위: **{int(years_nonnull.min())}–{int(years_nonnull.max())}**")

# --------- Plotly 시각화 ---------
st.subheader("📈 시계열 라인 차트")
fig_line = px.line(
    df_plot, x=year_col, y="value", color="metric",
    markers=True, title="Selected Metrics Over Time"
)
fig_line.update_layout(xaxis_title=str(year_col), yaxis_title="value", hovermode="x unified", margin=dict(t=60))
st.plotly_chart(fig_line, use_container_width=True)

st.subheader("📊 연도별 막대 차트")
bar_mode = st.radio("막대 모드", options=["group", "stack"], horizontal=True, index=0)
fig_bar = px.bar(
    df_plot, x=year_col, y="value", color="metric", barmode=bar_mode, title="Yearly Values"
)
fig_bar.update_layout(xaxis_title=str(year_col), yaxis_title="value", hovermode="x unified", margin=dict(t=60))
st.plotly_chart(fig_bar, use_container_width=True)

# --------- 다운로드 ---------
st.subheader("⬇️ 데이터 다운로드")
st.download_button(
    "전처리 표 CSV 내려받기",
    data=df_clean.to_csv(index=False).encode("utf-8-sig"),
    file_name="table_cleaned.csv",
    mime="text/csv"
)
st.download_button(
    "long 포맷 CSV 내려받기 (시각화용)",
    data=df_plot.to_csv(index=False).encode("utf-8-sig"),
    file_name="table_long_visualizable.csv",
    mime="text/csv"
)

with st.expander("ℹ️ 동작 원리 / 한계"):
    st.markdown("""
- 표 구조 자동 인식
  - **세로형**: (연도 컬럼 1개 + 수치 컬럼 N개) → long 변환  
  - **가로형**: (열 머리글이 연도 다수) → 첫 비연도 열을 **지표명**으로 보고 long 변환  
- 숫자 인식: 콤마/퍼센트(%) 처리. 퍼센트는 **0~1 스케일**로 환산합니다.  
- 시각화 가능 기준: **유효값 ≥ 2**이고 **분산>0**인 시리즈만 사용합니다.  
- 스캔(이미지) PDF는 표 추출이 어려울 수 있습니다.
""")
