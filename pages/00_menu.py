import streamlit as st
import pandas as pd

st.title("🏠 가족생활 가치관 데이터 미리보기")

url = "https://raw.githubusercontent.com/cegy/project/main/family.csv"

try:
    # utf-8-sig → cp949 순서로 시도
    df = pd.read_csv(url, encoding="utf-8-sig")
except UnicodeDecodeError:
    df = pd.read_csv(url, encoding="cp949")
except Exception as e:
    st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
    st.stop()

st.write("✅ 데이터 불러오기 성공")
st.dataframe(df.head())
