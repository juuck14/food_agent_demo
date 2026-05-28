import json
import mimetypes
import os
import time

import streamlit as st
from dotenv import load_dotenv
import google.genai as genai
from google.genai import types

load_dotenv()

st.set_page_config(page_title="음식 사진 레시피 생성기", page_icon="🍽️", layout="centered")
st.title("🍽️ 음식 사진 레시피 생성기 (Gemini)")
st.write("음식 사진을 업로드하고 **레시피 생성하기** 버튼을 눌러보세요.")

SOURCE_MD_PATH = "source.md"


def load_source_md(path: str = SOURCE_MD_PATH) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


uploaded_file = st.file_uploader(
    "음식 사진 업로드",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=False,
)

if uploaded_file is not None:
    st.image(uploaded_file, caption="업로드한 이미지", use_container_width=True)

st.subheader("사용자 설정")
servings = st.number_input("몇 인분으로 만들까요?", min_value=1, max_value=20, value=1, step=1)
user_preference_text = st.text_area(
    "추가 선호사항 (선택)",
    placeholder="예: 빨간 소스는 달지 않은 케첩 베이스, 사진에 없는 재료는 최대한 제외, 10분 내 조리 희망",
    help="첨부 파일 외에 매번 텍스트 선호사항을 함께 전달할 수 있습니다.",
)

source_md_content = load_source_md()
if source_md_content:
    st.caption(f"source.md 설정 로드 완료 ({len(source_md_content)}자)")
else:
    st.caption("source.md가 비어있거나 없어 기본 설정만 사용합니다.")

prompt = f"""
너는 음식 사진을 분석하는 요리 보조 AI다.
아래 지침을 반드시 지켜라.

[기본 설정]
- 목표 인분: {servings}인분
- source.md 내용: {source_md_content if source_md_content else '(비어 있음)'}
- 추가 사용자 선호사항: {user_preference_text if user_preference_text.strip() else '(없음)'}

1) 반드시 한국어로 응답한다.
2) 음식 사진만 근거로 분석한다.
3) 사진이 음식이 아니면 is_food를 false로 설정하고 non_food_reason에 이유를 설명한다.
4) 사진이 음식이면 is_food를 true로 설정하고 레시피를 작성한다.
5) 사진에서 확실히 보이는 재료는 visible_ingredients에 넣는다.
6) 확실하지 않고 추정한 재료는 guessed_ingredients에 넣는다.
7) 사진에서 보이지 않는 양념, 소스, 알레르기 성분은 확정적으로 단정하지 않는다.
8) 확신이 낮으면 confidence를 low로 설정하고 warnings에 불확실성을 명시한다.
9) 레시피는 반드시 목표 인분 기준으로 작성한다.
10) 재료뿐 아니라 필요한 조리도구(cooking_tools), 조리기기(cooking_equipment)를 반드시 포함한다.
11) 부족한 재료 추출(ingredient_extraction)과 md 파일 관리(md_export) 단계에서 재사용할 수 있게 스키마를 준수한다.
12) 반드시 아래 JSON 스키마 형태의 **순수 JSON 문자열만** 반환한다.
13) markdown 코드블록(```) 또는 설명 문장은 절대 포함하지 않는다.

JSON 스키마:
{{
  "is_food": true,
  "non_food_reason": "음식이 아닐 때만 이유를 작성, 음식일 때는 빈 문자열",
  "dish_guess": "음식명 후보",
  "confidence": "high | medium | low",
  "summary": "사진 기반 분석 요약",
  "visible_ingredients": ["사진에서 보이는 재료"],
  "guessed_ingredients": ["사진만으로 추정한 재료"],
  "user_preferences_applied": ["적용한 사용자 선호사항 요약"],
  "recipe": {{
    "servings": {servings},
    "cooking_time": "예: 20분",
    "difficulty": "easy | medium | hard",
    "ingredients": ["레시피에 필요한 재료"],
    "cooking_tools": ["예: 칼, 도마, 볼"],
    "cooking_equipment": ["예: 가스레인지, 오븐, 에어프라이어"],
    "steps": ["조리 단계"]
  }},
  "ingredient_extraction": {{
    "required_ingredients": ["필요 재료 전체 목록"],
    "missing_ingredients": ["사진에서 확인되지 않아 추가 준비가 필요한 재료"],
    "optional_ingredients": ["대체 가능하거나 선택 재료"]
  }},
  "md_export": {{
    "title": "마크다운 문서 제목",
    "sections": [
      {{"heading": "요약", "content": "요약 텍스트"}},
      {{"heading": "재료", "content": "재료 목록 텍스트"}},
      {{"heading": "도구/기기", "content": "도구 및 기기 목록 텍스트"}},
      {{"heading": "조리 순서", "content": "단계 텍스트"}}
    ]
  }},
  "warnings": ["주의사항"]
}}
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

        st.markdown("**적용된 사용자 선호사항**")
        for item in result.get("user_preferences_applied", []):
            st.write(f"- {item}")

        recipe = result.get("recipe", {})
        st.subheader("레시피")
        st.write(f"**인분:** {recipe.get('servings', servings)}")
        st.write(f"**조리 시간:** {recipe.get('cooking_time', '-')}")
        st.write(f"**난이도:** {recipe.get('difficulty', '-')}")

        st.markdown("**필요한 재료**")
        for item in recipe.get("ingredients", []):
            st.write(f"- {item}")

        st.markdown("**필요한 조리도구**")
        for item in recipe.get("cooking_tools", []):
            st.write(f"- {item}")

        st.markdown("**필요한 조리기기**")
        for item in recipe.get("cooking_equipment", []):
            st.write(f"- {item}")

        st.markdown("**조리 단계**")
        for idx, step in enumerate(recipe.get("steps", []), start=1):
            st.write(f"{idx}. {step}")

        extraction = result.get("ingredient_extraction", {})
        st.subheader("부족한 재료 추출")
        st.markdown("**추가 준비 필요 재료**")
        for item in extraction.get("missing_ingredients", []):
            st.write(f"- {item}")

        st.markdown("**선택 재료**")
        for item in extraction.get("optional_ingredients", []):
            st.write(f"- {item}")

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
