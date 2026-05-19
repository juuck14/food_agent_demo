# food-photo-recipe

Gemini API를 이용해 음식 사진을 분석하고, 한국어로 음식명/재료/레시피를 생성하는 최소 기능(MVP) 웹앱입니다.

## 기능

- jpg, jpeg, png, webp 이미지 업로드
- 업로드 이미지 미리보기
- Gemini(`gemini-2.5-flash`)로 사진 분석
- 아래 정보를 한국어로 출력
  - 음식명 후보
  - 신뢰도
  - 분석 요약
  - 보이는 재료
  - 추정 재료
  - 필요한 재료
  - 조리 시간
  - 난이도
  - 조리 단계
  - 주의사항
- JSON 파싱 실패 시 원문 응답 표시

## 설치 방법 (Conda)

```bash
cd food-photo-recipe
conda create -n food-photo-recipe python=3.11 -y
conda activate food-photo-recipe
pip install -r requirements.txt
```

## Gemini API key 설정 방법

1. `.env.example` 파일을 `.env`로 복사합니다.
2. `.env`의 값을 실제 키로 바꿉니다.

```bash
cp .env.example .env
```

`.env` 예시:

```env
GEMINI_API_KEY=your_real_key
```

## 실행 방법

```bash
conda activate food-photo-recipe
streamlit run app.py
```

브라우저에서 표시되는 로컬 주소(예: `http://localhost:8501`)로 접속해 테스트합니다.

## 주의사항

- 이 앱은 **사진 기반 추정** 결과를 제공합니다.
- 실제 사용된 재료, 양념, 소스, 알레르기 성분과 다를 수 있습니다.
- 알레르기/건강 관련 판단은 반드시 신뢰 가능한 별도 정보로 재확인하세요.
