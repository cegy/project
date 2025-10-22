import io
import os
import re
import pdfplumber
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

st.set_page_config(page_title="서울시민 결혼·가족 변화 분석 (로컬 PDF)", layout="wide")

# ---------------------------
# 고정 파일 경로 (main.py와 동일 폴더)
# ---------------------------
PDF_FILENAME = "서울시민의+결혼과+가족+형태의+변화+분석.pdf"
PDF_PATH = os.path.join(os.path.dirname(__file__), PDF_FILENAME)

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
    # 마침표/물음표/느낌표/개행 기준 간단 분리 (NLTK 미사용)
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

# ---------------------------
# 사이드바 - 분석 설정
# ---------------------------
st.sidebar.header("🔎 분석 설정")
default_keywords = [
    "혼인율", "초혼", "재혼", "이혼", "출산", "합계출산율",
    "1인 가구", "비혼", "만혼", "동거", "가족형태", "출생", "고령화"
]
keywords = st.sidebar.text_area(
    "관심 키워드(줄바꿈으로 구분)",
    value="\n".join(default_keywords),
    height=200
).splitlines()
keywords = [k.strip() for k in keywords if k.strip()]
context_window = st.sidebar.slider("문맥 스니펫 길이(문자수)", 60, 400, 160, 20)

# ---------------------------
# 상단 정보
# ---------------------------
st.title("📊 서울시민의 결혼·가족 형태 변화 — 로컬 PDF 분석 뷰어")
st.caption("같은 폴더의 PDF를 직접 읽어 키워드 빈도, 문맥 스니펫, 간단 요약을 제공합니다.")
st.write(f"대상 파일: **{PDF_FILENAME}**")
st.caption(f"경로: `{PDF_PATH}`")

# ---------------------------
# 파일 유효성 체크
# ---------------------------
if not os.path.exists(PDF_PATH):
    st.error("지정된 PDF 파일을 찾을 수 없습니다. `main.py`와 같은 폴더에 "
             f"`{PDF_FILENAME}` 파일이 있는지 확인하세요.")
    st.stop()

# ---------------------------
# 본문 처리
# ---------------------------
with st.spinner("PDF에서 텍스트 추출 중…"):
    raw_bytes = read_pdf_bytes(PDF_PATH)
    raw_text = extract_text_from_pdf(raw_bytes)

sentences = split_sentences_rough_korean(raw_text)
st.success(f"텍스트 추출 완료: 약 {len(sentences)}개 문장")

# ---------------------------
# 키워드 검색/시각화
# ---------------------------
hits_all = []
for kw in keywords:
    hits_all.extend(keyword_hits(sentences, kw))

if hits_all:
    df_hits = pd.DataFrame(hits_all)
    counts = df_hits["keyword"].value_counts().rename_axis("keyword").reset_index(name="count")

    st.subheader("📈 키워드 출현 빈도")
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(counts["keyword"], counts["count"])
    ax.set_ylabel("빈도")
    ax.set_xlabel("키워드")
    ax.set_xticklabels(counts["keyword"], rotation=20, ha="right")
    st.pyplot(fig, use_container_width=True)

    st.subheader("🧩 문맥 스니펫")
    df_hits["snippet"] = df_hits.apply(lambda r: make_snippet(r, context_window), axis=1)
    show_cols = ["keyword", "sentence_idx", "snippet"]
    st.dataframe(df_hits[show_cols], use_container_width=True, height=360)

    csv = df_hits[show_cols + ["sentence"]].to_csv(index=False).encode("utf-8-sig")
    st.download_button("CSV로 내보내기", data=csv, file_name="keyword_snippets.csv", mime="text/csv")
else:
    st.info("설정한 키워드가 본문에서 발견되지 않았습니다. 사이드바에서 키워드를 조정해 보세요.")

# ---------------------------
# 간단 요약(룰 기반)
# ---------------------------
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

# ---------------------------
# 원문 일부 미리보기
# ---------------------------
with st.expander("📄 본문 미리보기"):
    st.text_area("텍스트(일부)", value=raw_text[:8000], height=260)
