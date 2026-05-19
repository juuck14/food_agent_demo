import json
import mimetypes
import os
import time

import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

st.set_page_config(page_title="음식 사진 레시피 생성기", page_icon="🍽️", layout="centered")
st.title("🍽️ 음식 사진 레시피 생성기 (Gemini)")
st.write("음식 사진을 업로드하고 **레시피 생성하기** 버튼을 눌러보세요.")

uploaded_file = st.file_uploader(
    "음식 사진 업로드",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=False,
)

if uploaded_file is not None:
    st.image(uploaded_file, caption="업로드한 이미지", use_container_width=True)

prompt = """
너는 음식 사진을 분석하는 요리 보조 AI다.
아래 지침을 반드시 지켜라.

1) 반드시 한국어로 응답한다.
2) 음식 사진만 근거로 분석한다.
3) 사진이 음식이 아니면 is_food를 false로 설정하고 non_food_reason에 이유를 설명한다.
4) 사진이 음식이면 is_food를 true로 설정하고 레시피를 작성한다.
5) 사진에서 확실히 보이는 재료는 visible_ingredients에 넣는다.
6) 확실하지 않고 추정한 재료는 guessed_ingredients에 넣는다.
7) 사진에서 보이지 않는 양념, 소스, 알레르기 성분은 확정적으로 단정하지 않는다.
8) 확신이 낮으면 confidence를 low로 설정하고 warnings에 불확실성을 명시한다.
9) 레시피는 1인분 기준으로 작성한다.
10) 반드시 아래 JSON 스키마 형태의 **순수 JSON 문자열만** 반환한다.
11) markdown 코드블록(```) 또는 설명 문장은 절대 포함하지 않는다.

JSON 스키마:
{
  "is_food": true,
  "non_food_reason": "음식이 아닐 때만 이유를 작성, 음식일 때는 빈 문자열",
  "dish_guess": "음식명 후보",
  "confidence": "high | medium | low",
  "summary": "사진 기반 분석 요약",
  "visible_ingredients": ["사진에서 보이는 재료"],
  "guessed_ingredients": ["사진만으로 추정한 재료"],
  "recipe": {
    "servings": 1,
    "cooking_time": "예: 20분",
    "difficulty": "easy | medium | hard",
    "ingredients": ["레시피에 필요한 재료"],
    "steps": ["조리 단계"]
  },
  "warnings": ["주의사항"]
}
""".strip()


def generate_with_retry(client, image_bytes, mime_type, retries=3, base_delay=3):
    for attempt in range(1, retries + 1):
        try:
            return client.models.generate_content(
                model="gemini-2.5-flash",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    prompt,
                ],
            )
        except Exception as e:
            err_text = str(e).lower()
            is_rate_limited = (
                "429" in err_text
                or "quota" in err_text
                or "resource_exhausted" in err_text
                or "rate limit" in err_text
                or "too many requests" in err_text
            )

            if not is_rate_limited or attempt == retries:
                raise

            wait_seconds = base_delay * (2 ** (attempt - 1))
            st.warning(
                f"요청이 많아 잠시 대기 후 재시도합니다. ({attempt}/{retries}, {wait_seconds}초 대기)"
            )
            time.sleep(wait_seconds)


if st.button("레시피 생성하기", type="primary"):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        st.error(
            "GEMINI_API_KEY가 설정되지 않았습니다. .env 파일에 키를 추가한 뒤 다시 실행해주세요."
        )
        st.stop()

    if uploaded_file is None:
        st.warning("먼저 음식 사진을 업로드해주세요.")
        st.stop()

    try:
        image_bytes = uploaded_file.getvalue()
        mime_type = uploaded_file.type or mimetypes.guess_type(uploaded_file.name)[0] or "image/jpeg"

        client = genai.Client(api_key=api_key)

        with st.spinner("Gemini가 사진을 분석하고 레시피를 생성하는 중입니다..."):
            response = generate_with_retry(client, image_bytes, mime_type)

        raw_text = (response.text or "").strip()

        try:
            result = json.loads(raw_text)
        except json.JSONDecodeError:
            st.error("JSON 파싱에 실패했습니다. 모델 원문 응답을 확인해주세요.")
            st.code(raw_text or "(빈 응답)", language="text")
            st.stop()

        if not result.get("is_food", False):
            st.warning("업로드한 이미지는 음식 사진이 아닌 것으로 판단되었습니다.")
            st.write(f"**판별 사유:** {result.get('non_food_reason', '사유 없음')}")
            st.stop()

        st.success("레시피 생성이 완료되었습니다!")

        st.subheader("음식 분석 결과")
        st.write(f"**음식명 후보:** {result.get('dish_guess', '-')}")
        st.write(f"**신뢰도:** {result.get('confidence', '-')}")
        st.write(f"**요약:** {result.get('summary', '-')}")

        st.markdown("**보이는 재료**")
        for item in result.get("visible_ingredients", []):
            st.write(f"- {item}")

        st.markdown("**추정 재료**")
        for item in result.get("guessed_ingredients", []):
            st.write(f"- {item}")

        recipe = result.get("recipe", {})
        st.subheader("레시피")
        st.write(f"**조리 시간:** {recipe.get('cooking_time', '-')}")
        st.write(f"**난이도:** {recipe.get('difficulty', '-')}")

        st.markdown("**필요한 재료**")
        for item in recipe.get("ingredients", []):
            st.write(f"- {item}")

        st.markdown("**조리 단계**")
        for idx, step in enumerate(recipe.get("steps", []), start=1):
            st.write(f"{idx}. {step}")

        st.markdown("**주의사항**")
        for item in result.get("warnings", []):
            st.write(f"- {item}")

    except Exception as e:
        err_text = str(e).lower()
        if (
            "429" in err_text
            or "quota" in err_text
            or "resource_exhausted" in err_text
            or "rate limit" in err_text
            or "too many requests" in err_text
        ):
            st.error(
                "현재 Gemini 무료 API 요청 한도를 초과했습니다. 잠시 후 다시 시도하거나, 요청 간격을 늘려주세요."
            )
        else:
            st.error("요청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
            st.exception(e)
