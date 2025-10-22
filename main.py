import io
import os
import re
from typing import List, Tuple, Optional

import pdfplumber
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="PDF 표 추출 → Plotly 시각화", layout="wide")

# ---------------------------
# 고정 파일 경로 (main.py와 동일 폴더)
# ---------------------------
PDF_FILENAME = "서울시민의+결혼과+가족+형태의+변화+분석.pdf"
PDF_PATH = os.path.join(os.path.dirname(__file__), PDF_FILENAME)

# ---------------------------
# 유틸: 숫자 정규화/컬럼 자동감지
# ---------------------------
NUM_RE = re.compile(r"^-?\s*[\d,]+(?:\.\d+)?\s*%?$")

def to_number(x):
    """문자 → 숫자(float). 쉼표/퍼센트 처리. 변환 실패 시 NaN."""
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

def guess_year_col(cols: List[str], df: pd.DataFrame) -> Optional[str]:
    """
    연도 컬럼(예: 연도, 년도, year, 2015.. 등)을 추정.
    1) 이름 기반 2) 값 분포 기반
    """
    name_hits = [c for c in cols if re.search(r"(연도|년도|year|Year|기간|시점)", str(c))]
    if name_hits:
        return name_hits[0]
    # 값이 1900~2100 사이 정수로 많이 들어 있으면 연도 취급
    for c in cols:
        try:
            vals = pd.to_numeric(df[c], errors="coerce").dropna()
            if len(vals) >= max(3, len(df) // 3):
                if (vals.between(1900, 2100)).mean() > 0.6:
                    return c
        except Exception:
            pass
    return None

def clean_table(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    - 헤더 행 추정(첫 행에 문자열 비율이 높으면 헤더로 사용)
    - 공백/줄바꿈 제거
    - 전열 문자열 strip
    """
    df = df_raw.copy()
    # 모든 값 문자열화
    df = df.applymap(lambda x: str(x).strip() if pd.notna(x) else "")
    # 첫 행을 헤더로 쓸지 판단
    header_row = df.iloc[0]
    str_ratio = (header_row != "").mean()
    if str_ratio >= 0.5:
        df.columns = header_row
        df = df.iloc[1:].reset_index(drop=True)
    # 빈 컬럼명 처리
    df.columns = [c if c != "" else f"col_{i}" for i, c in enumerate(df.columns)]
    # 완전 빈 행 제거
    df = df[~(df.apply(lambda r: (r == "").all(), axis=1))].reset_index(drop=True)
    return df

def coerce_numeric_cols(df: pd.DataFrame, year_col: Optional[str]) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if c == year_col:
            continue
        out[c] = out[c].apply(to_number)
    # year_col도 숫자로 가능하면
    if year_col and year_col in out.columns:
        out[year_col] = pd.to_numeric(out[year_col], errors="coerce")
    return out

def longify(df: pd.DataFrame, year_col: str, value_cols: List[str]) -> pd.DataFrame:
    long = df[[year_col] + value_cols].melt(
        id_vars=year_col, value_vars=value_cols, var_name="metric", value_name="value"
    )
    # 숫자로 강제
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    # 연도 정렬
    long = long.sort_values([year_col, "metric"]).reset_index(drop=True)
    return long

# ---------------------------
# PDF → 표 추출
# ---------------------------
@st.cache_data(show_spinner=False)
def extract_tables_from_pdf(path: str) -> List[Tuple[int, pd.DataFrame]]:
    """
    각 페이지에서 table.extract()로 얻은 테이블을 DataFrame 리스트로 반환.
    [(page_index, df), ...]
    """
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
                # 완전 공백 테이블 제외
                if df.replace("", pd.NA).dropna(how="all").empty:
                    continue
                results.append((p_idx + 1, df))
    return results

# ---------------------------
# 상단 UI
# ---------------------------
st.title("📄 PDF 표 추출 → 📊 Plotly 시각화")
st.caption("PDF 안의 **표**를 추출해서 그대로 시각화합니다. (텍스트 키워드 분석 없음)")

st.write(f"대상 PDF: **{PDF_FILENAME}**")
st.caption(f"경로: `{PDF_PATH}`")

if not os.path.exists(PDF_PATH):
    st.error("지정된 PDF 파일을 찾을 수 없습니다. `main.py`와 같은 폴더에 "
             f"`{PDF_FILENAME}` 파일이 있는지 확인하세요.")
    st.stop()

with st.spinner("PDF에서 표 감지/추출 중…"):
    tables = extract_tables_from_pdf(PDF_PATH)

if not tables:
    st.error("표를 찾지 못했습니다. 스캔(이미지) PDF일 가능성이 큽니다.\n"
             "- 원본이 벡터 PDF인지 확인하거나\n"
             "- 표를 CSV로 정리하여 불러오는 방식을 고려하세요.")
    st.stop()

# 표 선택
table_labels = [f"p.{p} - table#{i+1} (shape={df.shape[0]}x{df.shape[1]})"
                for i, (p, df) in enumerate(tables)]
sel = st.selectbox("시각화할 표 선택", options=list(range(len(tables))),
                   format_func=lambda i: table_labels[i])

page_no, df_raw = tables[sel]
st.info(f"선택: p.{page_no} 표 | 원본 shape: {df_raw.shape}")

# 표 전처리 프리뷰
df_clean = clean_table(df_raw)
st.subheader("🧹 전처리된 표 미리보기")
st.dataframe(df_clean, use_container_width=True, height=300)

# 연도 컬럼/값 컬럼 지정
st.subheader("⚙️ 컬럼 매핑")
cols = list(df_clean.columns)
default_year = guess_year_col(cols, df_clean)
year_col = st.selectbox("연도(가로축)로 사용할 컬럼", options=cols,
                        index=cols.index(default_year) if default_year in cols else 0)

# 수치형 후보 자동 선택(연도 제외)
numeric_candidates = [c for c in cols if c != year_col]
st.caption("※ 숫자로 변환 가능한 컬럼만 시각화에 사용됩니다(%, 콤마 자동 처리).")

# 숫자 변환
df_numeric = coerce_numeric_cols(df_clean, year_col)

# 실제 숫자값이 충분히 존재하는 컬럼만 필터
value_cols_valid = []
for c in numeric_candidates:
    series = pd.to_numeric(df_numeric[c], errors="coerce")
    if series.notna().sum() >= 2:  # 최소 2개 이상 값
        value_cols_valid.append(c)

if not value_cols_valid:
    st.warning("시각화 가능한 수치 컬럼을 찾지 못했습니다. 다른 표를 선택해 보세요.")
    st.stop()

selected_values = st.multiselect("시각화할 값 컬럼(복수 선택 가능)", options=value_cols_valid,
                                 default=value_cols_valid[: min(3, len(value_cols_valid))])

if not selected_values:
    st.info("값 컬럼을 하나 이상 선택하세요.")
    st.stop()

# 롱 포맷으로 변환
df_long = longify(df_numeric, year_col, selected_values)

# 결측/연도 범위 안내
years_nonnull = df_long[year_col].dropna().unique()
if len(years_nonnull) > 0:
    st.caption(f"인식된 연도 범위: **{int(pd.Series(years_nonnull).min())}–{int(pd.Series(years_nonnull).max())}**")

# ---------------------------
# Plotly 시각화
# ---------------------------
st.subheader("📈 시계열 라인 차트")
fig_line = px.line(
    df_long, x=year_col, y="value", color="metric",
    markers=True, title="Selected metrics over time"
)
fig_line.update_layout(xaxis_title=str(year_col), yaxis_title="value", hovermode="x unified")
st.plotly_chart(fig_line, use_container_width=True)

st.subheader("📊 연도별 막대 차트 (스택/그룹 전환)")
bar_mode = st.radio("막대 모드", options=["group", "stack"], horizontal=True, index=0)
fig_bar = px.bar(
    df_long, x=year_col, y="value", color="metric",
    barmode=bar_mode, title="Yearly values"
)
fig_bar.update_layout(xaxis_title=str(year_col), yaxis_title="value", hovermode="x unified")
st.plotly_chart(fig_bar, use_container_width=True)

# ---------------------------
# 다운로드
# ---------------------------
st.subheader("⬇️ 데이터 다운로드")
st.download_button(
    "전처리 표 CSV 내려받기",
    data=df_numeric.to_csv(index=False).encode("utf-8-sig"),
    file_name="table_cleaned.csv",
    mime="text/csv"
)
st.download_button(
    "롱 포맷 CSV 내려받기 (시각화용)",
    data=df_long.to_csv(index=False).encode("utf-8-sig"),
    file_name="table_long.csv",
    mime="text/csv"
)

with st.expander("ℹ️ 도움말"):
    st.markdown(
        """
- 이 앱은 **PDF 내부의 표**를 추출해 숫자 컬럼을 자동 인식(%, 콤마 제거) 후 시각화합니다.  
- **연도 컬럼**은 자동 추정되지만, 필요 시 상단 셀렉트박스에서 직접 바꿀 수 있습니다.  
- 스캔(이미지) PDF는 표 추출이 어렵습니다. 이런 경우:
  1) 원본(텍스트/벡터) PDF를 사용하거나  
  2) 표를 CSV로 직접 정리해 불러오세요.  
- 값이 퍼센트(%)인 경우 자동으로 0~1 스케일로 환산됩니다.
        """
    )
