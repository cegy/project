import io
import os
import re
from typing import List, Tuple, Optional, Dict, Set

import pdfplumber
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="PDF 표 → Plotly 시각화(설명/단위 표시 강화)", layout="wide")

# --------- 설정 ---------
PDF_FILENAME = "서울시민의+결혼과+가족+형태의+변화+분석.pdf"
PDF_PATH = os.path.join(os.path.dirname(__file__), PDF_FILENAME)

NUM_RE = re.compile(r"^-?\s*[\d,]+(?:\.\d+)?\s*%?$")

# =========================
# 숫자/연도 유틸
# =========================
def to_number_and_is_percent(x):
    """값을 숫자로 변환하고, 원본이 %였는지 플래그 반환."""
    if pd.isna(x):
        return pd.NA, False
    s = str(x).strip()
    if not NUM_RE.match(s):
        return pd.NA, False
    is_pct = s.endswith("%")
    s = s.replace("%", "").replace(",", "")
    try:
        val = float(s)
        return (val / 100.0 if is_pct else val), is_pct
    except Exception:
        return pd.NA, False

def is_year_like(s) -> bool:
    try:
        v = int(str(s).strip())
        return 1900 <= v <= 2100
    except Exception:
        return False

# =========================
# 전처리
# =========================
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

def coerce_numeric_cols_with_percent_map(
    df: pd.DataFrame, exclude: Optional[List[str]] = None
) -> Tuple[pd.DataFrame, Set[str]]:
    """
    exclude 제외 모든 열을 숫자로 변환.
    퍼센트(%)가 한번이라도 등장한 열은 percent_cols에 기록.
    """
    exclude = exclude or []
    out = df.copy()
    percent_cols: Set[str] = set()
    for c in out.columns:
        if c in exclude:
            continue
        col_vals = []
        saw_pct = False
        for v in out[c].tolist():
            num, is_pct = to_number_and_is_percent(v)
            col_vals.append(num)
            saw_pct = saw_pct or is_pct
        out[c] = col_vals
        if saw_pct:
            percent_cols.add(c)
    # exclude(예: 연도)는 숫자 변환 시도
    for c in exclude:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out, percent_cols

# =========================
# 세로/가로 구조 감지 & long 변환
# =========================
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

    df2, percent_cols = coerce_numeric_cols_with_percent_map(df, exclude=[year_col])

    # 시각화 가능한 값 컬럼 필터(유효값 ≥2 & 분산>0)
    keep = []
    for c in value_cols:
        s = pd.to_numeric(df2[c], errors="coerce")
        s_valid = s.dropna()
        if len(s_valid) >= 2 and (s_valid.max() != s_valid.min()):
            keep.append(c)
    if not keep:
        return None

    long = df2[[year_col] + keep].melt(
        id_vars=year_col, value_vars=keep, var_name="metric", value_name="value"
    )
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    long = long.dropna(subset=["value", year_col]).sort_values([year_col, "metric"]).reset_index(drop=True)

    if long.empty or long[year_col].nunique() < 2:
        return None

    # 메타 정보
    long.attrs["year_col"] = year_col
    # 퍼센트 여부는 컬럼명 기준으로 기록
    percent_metrics = {m for m in keep if m in percent_cols}
    long.attrs["percent_metrics"] = percent_metrics
    long.attrs["structure"] = "vertical"
    return long

def to_long_horizontal(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    # 열 머리글의 연도 탐색
    year_cols = [c for c in df.columns if is_year_like(c)]
    if len(year_cols) < 2:
        return None

    non_year = [c for c in df.columns if c not in year_cols]
    # 지표명 컬럼(없으면 임시)
    if not non_year:
        metric_col = "metric"
        df2 = df.copy()
        df2.insert(0, metric_col, [f"row_{i}" for i in range(len(df2))])
    else:
        metric_col = non_year[0]
        df2 = df.copy()

    # 퍼센트 맵: metric별로 % 포함 여부 판단
    percent_metrics: Set[str] = set()
    # melt 전에 % 탐지
    for idx, row in df2.iterrows():
        # metric 이름
        mname = str(row[metric_col]).strip()
        # 해당 행의 연도 값들 중 %가 하나라도 있으면 해당 metric은 percent로 간주
        saw_pct = False
        for yc in year_cols:
            cell = row[yc]
            if isinstance(cell, str) and "%" in cell:
                saw_pct = True
                break
        if saw_pct:
            percent_metrics.add(mname)

    # 숫자 변환
    for c in year_cols:
        df2[c] = df2[c].apply(lambda v: to_number_and_is_percent(v)[0])

    df2[metric_col] = df2[metric_col].astype(str).str.strip()

    long = df2.melt(id_vars=metric_col, value_vars=year_cols, var_name="year", value_name="value")
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

    long = long.rename(columns={metric_col: "metric"})
    long.attrs["year_col"] = "year"
    long.attrs["percent_metrics"] = percent_metrics.intersection(set(ok_metrics))
    long.attrs["structure"] = "horizontal"
    return long

def pick_first_visualizable_long(tables: List[Tuple[int, pd.DataFrame]]) -> Tuple[int, pd.DataFrame, pd.DataFrame]:
    for pno, raw in tables:
        dfc = clean_table(raw)
        long_v = to_long_vertical(dfc)
        if long_v is not None:
            return pno, dfc, long_v
        long_h = to_long_horizontal(dfc)
        if long_h is not None:
            return pno, dfc, long_h
    if tables:
        pno, raw = tables[0]
        return pno, clean_table(raw), pd.DataFrame(columns=["year", "metric", "value"])
    return -1, pd.DataFrame(), pd.DataFrame(columns=["year", "metric", "value"])

# =========================
# PDF 테이블 추출
# =========================
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

# =========================
# UI
# =========================
st.title("📄 PDF 표 → 📊 Plotly 시각화")
st.caption("무엇을 시각화했는지 **설명/단위**를 함께 표기합니다.")

st.write(f"PDF 파일: **{PDF_FILENAME}**")
st.caption(f"경로: `{PDF_PATH}`")

if not os.path.exists(PDF_PATH):
    st.error("PDF 파일을 찾을 수 없습니다. 같은 폴더에 파일이 있는지 확인하세요.")
    st.stop()

with st.spinner("PDF에서 표 추출 중…"):
    tables = extract_tables_from_pdf(PDF_PATH)

if not tables:
    st.error("표를 찾지 못했습니다. 스캔(이미지) PDF일 수 있습니다.")
    st.stop()

table_labels = [f"p.{p} - table#{i+1} (shape={df.shape[0]}x{df.shape[1]})"
                for i, (p, df) in enumerate(tables)]
default_pno, default_clean, default_long = pick_first_visualizable_long(tables)
default_idx = 0
if default_pno != -1:
    for i, (p, _) in enumerate(tables):
        if p == default_pno:
            default_idx = i
            break

idx = st.selectbox(
    "표 선택 (자동으로 시각화 가능한 표가 기본 선택됩니다)",
    options=list(range(len(tables))),
    index=default_idx,
    format_func=lambda i: table_labels[i]
)

page_no, df_raw = tables[idx]
df_clean = clean_table(df_raw)

# 현재 표를 long 변환(세로→가로 순으로 시도)
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
percent_metrics: Set[str] = df_long.attrs.get("percent_metrics", set())
structure = df_long.attrs.get("structure", "unknown")

metrics_all = sorted(df_long["metric"].dropna().unique().tolist())
# 기본 선택: 데이터 포인트 많은 것 위주
metric_scores: Dict[str, int] = {m: df_long[df_long["metric"] == m][year_col].nunique() for m in metrics_all}
metrics_sorted = sorted(metrics_all, key=lambda m: (-metric_scores[m], m))
default_metrics = metrics_sorted[: min(5, len(metrics_sorted))]

selected_metrics = st.multiselect("시각화할 지표 선택(최소 1개)", options=metrics_all, default=default_metrics)
if not selected_metrics:
    st.info("한 개 이상 지표를 선택하세요.")
    st.stop()

# 단위 토글: 인식된 퍼센트 지표만 %로 보기
show_percent = st.checkbox("퍼센트 지표를 %로 보기(그 외 지표는 원값 유지)", value=True)

df_plot = df_long[df_long["metric"].isin(selected_metrics)].copy()

# % 표시 지표만 배율 100 적용
if show_percent and percent_metrics:
    df_plot["display_value"] = df_plot.apply(
        lambda r: (r["value"] * 100.0) if r["metric"] in percent_metrics else r["value"], axis=1
    )
    y_label = "value / % (혼합)"
else:
    df_plot["display_value"] = df_plot["value"]
    y_label = "value"

# 연도 범위/요약
yr_nonnull = df_plot[year_col].dropna()
year_min = int(yr_nonnull.min()) if not yr_nonnull.empty else None
year_max = int(yr_nonnull.max()) if not yr_nonnull.empty else None

# =========================
# 📝 무엇을 시각화했나요? (오류 수정된 설명 블록)
# =========================
selected_str = ", ".join(selected_metrics)
percent_str = ", ".join(sorted(percent_metrics)) if percent_metrics else "없음"
markdown_text = (
    "- **원본**: `" + PDF_FILENAME + "`, **페이지**: p." + str(page_no) + ", **표 구조**: " + str(structure) + "\n"
    + "- **연도 컬럼**: `" + str(year_col) + "` | **연도 범위**: **" + str(year_min) + "–" + str(year_max) + "**\n"
    + "- **선택 지표(" + str(len(selected_metrics)) + "개)**: " + selected_str + "\n"
    + "- **퍼센트 인식 지표**: " + percent_str + "\n"
    + "  - 퍼센트 인식 지표는 내부 저장 시 `0–1` 스케일로 변환됩니다.\n"
    + "  - ✅ 옵션 ‘퍼센트 지표를 %로 보기’를 켜면, 해당 지표만 **×100** 하여 **% 단위**로 표시합니다."
)
st.subheader("📝 무엇을 시각화했나요?")
st.markdown(markdown_text)

desc_rows = []
for m in selected_metrics:
    cnt = df_plot[df_plot["metric"] == m][year_col].nunique()
    unit = "%" if (m in percent_metrics and show_percent) else ("(비율 0–1)" if m in percent_metrics else "(값)")
    desc_rows.append({"metric": m, "points": cnt, "unit_shown": unit})
st.dataframe(pd.DataFrame(desc_rows), use_container_width=True, height=180)

# =========================
# Plotly 시각화 (설명 포함 타이틀/호버)
# =========================
title_suffix = f"(p.{page_no} · {year_min}–{year_max} · {len(selected_metrics)} metrics)"

st.subheader("📈 시계열 라인 차트")
fig_line = px.line(
    df_plot,
    x=year_col, y="display_value", color="metric", markers=True,
    title=f"Selected Metrics Over Time {title_suffix}"
)
# hover 단위 표시용 customdata 준비
df_plot_sorted = df_plot.sort_values([year_col, "metric"]).copy()
df_plot_sorted["unit_str"] = df_plot_sorted["metric"].apply(
    lambda m: "%" if (m in percent_metrics and show_percent) else ""
)
fig_line.update_traces(
    customdata=df_plot_sorted["unit_str"],
    hovertemplate="<b>%{fullData.name}</b><br>"
                  + f"{year_col}=%{{x}}<br>"
                  + "value=%{y:.3f} %{customdata}<extra></extra>"
)
fig_line.update_layout(xaxis_title=str(year_col), yaxis_title=y_label, hovermode="x unified", margin=dict(t=60))
st.plotly_chart(fig_line, use_container_width=True)

st.subheader("📊 연도별 막대 차트")
bar_mode = st.radio("막대 모드", options=["group", "stack"], horizontal=True, index=0)
fig_bar = px.bar(
    df_plot, x=year_col, y="display_value", color="metric", barmode=bar_mode,
    title=f"Yearly Values {title_suffix}"
)
fig_bar.update_traces(
    customdata=df_plot_sorted["unit_str"],
    hovertemplate="<b>%{fullData.name}</b><br>"
                  + f"{year_col}=%{{x}}<br>"
                  + "value=%{y:.3f} %{customdata}<extra></extra>"
)
fig_bar.update_layout(xaxis_title=str(year_col), yaxis_title=y_label, hovermode="x unified", margin=dict(t=60))
st.plotly_chart(fig_bar, use_container_width=True)

# =========================
# 다운로드
# =========================
st.subheader("⬇️ 데이터 다운로드")
st.download_button(
    "전처리 표 CSV 내려받기",
    data=df_clean.to_csv(index=False).encode("utf-8-sig"),
    file_name="table_cleaned.csv",
    mime="text/csv"
)
# 시각화에 실제 사용한 subset + 표시값 포함
export_cols = [year_col, "metric", "value", "display_value"]
st.download_button(
    "시각화용 long CSV 내려받기 (표시값 포함)",
    data=df_plot[export_cols].to_csv(index=False).encode("utf-8-sig"),
    file_name="table_long_visualized.csv",
    mime="text/csv"
)

with st.expander("ℹ️ 동작 원리 / 한계"):
    st.markdown("""
- **무엇을 시각화했는가**가 항상 보이도록: 표 페이지/구조/연도범위/지표/단위를 상단에 요약합니다.  
- 퍼센트(%)는 내부적으로 0–1 스케일로 변환되며, 토글을 통해 %로 표시할 수 있습니다(퍼센트 지표에만 적용).  
- 시각화 가능한 지표 기준: **유효값 ≥ 2** & **분산 > 0**.  
- 스캔(이미지) PDF는 표 추출이 어려울 수 있습니다.
""")
