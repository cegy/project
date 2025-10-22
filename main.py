import io
import re
import nltk
import pdfplumber
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

# 최초 1회만 필요
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

st.set_page_config(page_title="서울시민 결혼·가족 변화 분석 뷰어", layout="wide")

# ---------------------------
# 사이드바 - 키워드 설정
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

st.title("📊 서울시민의 결혼·가족 형태 변화 — PDF 분석 뷰어")
st.caption("PDF에서 텍스트를 추출해 키워드 카운트, 문맥 스니펫, 간단 요약을 제공합니다.")

uploaded = st.file_uploader("분석할 PDF를 업로드하세요", type=["pdf"])

def extract_text_from_pdf(file_bytes: bytes) -> str:
    text_chunks = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text(x_tolerance=1.5, y_tolerance=1.5) or ""
            # 페이지 번호 마커 등 불필요한 공백 정리
            t = re.sub(r"[ \t]+", " ", t)
            text_chunks.append(t.strip())
    return "\n\n".join(text_chunks)

def split_sentences_rough_korean(text: str):
    # 한글 문장 분리(간단 버전): 마침표/물음표/느낌표 기준 + NLTK 보조
    # 보고서 문체 특성상 개행을 문장 경계로도 활용
    text = re.sub(r"([.!?])", r"\1 ", text)
    # NLTK sentence tokenize (언어 혼용 문서에도 무난)
    sents = nltk.sent_tokenize(text)
    # 개행 기준 보강
    more = []
    for s in sents:
        more.extend([ss.strip() for ss in re.split(r"\n+", s) if ss.strip()])
    return [s for s in more if len(s) > 1]

def keyword_hits(sentences, kw):
    # 대소문자/띄어쓰기 변형에 강건하게(한글은 그대로, 영문은 소문자)
    kw_norm = kw.lower()
    rows = []
    for i, s in enumerate(sentences):
        s_norm = s.lower()
        if kw_norm in s_norm:
            rows.append({"keyword": kw, "sentence_idx": i, "sentence": s})
    return rows

def make_snippet(text, hit, window=160):
    s = hit["sentence"]
    # 원문 텍스트에서 문장 위치 못 잡을 수 있으니 문장 자체로 스니펫 구성
    if len(s) <= window:
        return s
    mid = len(s) // 2
    return s[: window//2] + " … " + s[-window//2 :]

if uploaded:
    with st.spinner("PDF에서 텍스트 추출 중…"):
        raw_text = extract_text_from_pdf(uploaded.read())

    # 문장 분리
    sentences = split_sentences_rough_korean(raw_text)
    total_sentences = len(sentences)

    st.success(f"텍스트 추출 완료: 약 {total_sentences}개 문장")

    # ---------------------------
    # 키워드 매칭
    # ---------------------------
    hits_all = []
    for kw in keywords:
        hits = keyword_hits(sentences, kw)
        hits_all.extend(hits)

    if hits_all:
        df_hits = pd.DataFrame(hits_all)
        # 키워드별 카운트
        counts = df_hits["keyword"].value_counts().rename_axis("keyword").reset_index(name="count")

        # 시각화
        st.subheader("📈 키워드 출현 빈도")
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(counts["keyword"], counts["count"])
        ax.set_ylabel("빈도")
        ax.set_xlabel("키워드")
        ax.set_xticklabels(counts["keyword"], rotation=20, ha="right")
        st.pyplot(fig, use_container_width=True)

        # 스니펫 테이블
        st.subheader("🧩 문맥 스니펫")
        df_hits["snippet"] = df_hits.apply(lambda r: make_snippet(raw_text, r, context_window), axis=1)
        show_cols = ["keyword", "sentence_idx", "snippet"]
        st.dataframe(df_hits[show_cols], use_container_width=True, height=360)

        # 다운로드
        csv = df_hits[show_cols + ["sentence"]].to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "CSV로 내보내기",
            data=csv,
            file_name="keyword_snippets.csv",
            mime="text/csv"
        )
    else:
        st.info("설정한 키워드가 본문에서 발견되지 않았습니다. 사이드바에서 키워드를 바꿔보세요.")

    # ---------------------------
    # 간단 요약(룰 기반)
    # ---------------------------
    st.subheader("📝 간단 요약(룰 기반)")
    # 연도/지표 추출 데모: '2010', '2024' 같은 4자리 연도
    years = sorted(set(re.findall(r"\b(19\d{2}|20\d{2})\b", raw_text)))
    bullets = []

    if years:
        bullets.append(f"- 보고서 내 텍스트에서 식별된 연도 범위: **{years[0]}–{years[-1]}**")

    # 주요 용어 존재 여부
    for term in ["혼인율", "초혼", "이혼", "출산", "합계출산율", "1인 가구", "비혼", "동거", "만혼"]:
        if re.search(term, raw_text):
            bullets.append(f"- **{term}** 관련 서술이 포함되어 있음")

    if not bullets:
        bullets.append("- 규칙 기반 요약 후보를 찾지 못했습니다. 키워드/스니펫에서 직접 확인하세요.")

    for b in bullets:
        st.markdown(b)

    # ---------------------------
    # 본문 미리보기
    # ---------------------------
    with st.expander("📄 본문 원문 일부 보기"):
        st.text_area("텍스트(일부)", value=raw_text[:8000], height=260)
else:
    st.info("왼쪽 상단에서 PDF를 업로드하면 분석이 시작됩니다.")
    st.markdown("""
- 기본 키워드를 그대로 사용하거나, **사이드바에서 관심 키워드**를 바꿔보세요.  
- 업로드 후 **키워드 빈도 막대그래프**, **문맥 스니펫 테이블**, **간단 요약**이 자동 생성됩니다.
""")
