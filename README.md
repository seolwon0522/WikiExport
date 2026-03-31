# 📚 Redmine Wiki Export Tool (사용 설명서)

Redmine의 Wiki 문서를 한 개의 HTML 파일로 만드는 도구입니다. 다른 사람과 공유하기 쉽고, 어디서나 열어볼 수 있습니다.

---

## 🚀 빠른 시작 (처음 사용자)

### 1단계: 설정 파일 준비

**`config.json`** 파일을 열어서 다음 정보를 입력하세요:

```json
{
  "redmine": {
    "base_url": "http://your-redmine-server",
    "project_key": "your-project-key",
    "api_key": "your-api-key"
  },
  "output": {
    "filename": "wikiexport.html",
    "location": "./"
  },
  "options": {
    "timeout": 30,
    "retry_attempts": 3
  }
}
```

**각 항목 설명:**
- **base_url**: Redmine 서버 주소
- **project_key**: 프로젝트 식별자
- **api_key**: Redmine에서 발급받은 API 키
- **filename**: 생성될 HTML 파일 이름
- **timeout**: 요청 타임아웃(초), 느린 서버의 경우 늘려주세요 (기본값: 30)
- **retry_attempts**: 실패 시 재시도 횟수 (기본값: 3)

### 2단계: 배치 파일 실행

**`Run_WikiExport.bat`** 파일을 **더블클릭**하세요.

```
✅ 자동으로 실행됩니다
```

처음 실행할 때:
- Python이 필요합니다
- 인터넷 연결 필요
- 크기에 따라 1~5분 소요

### 3단계: 결과 확인

실행 완료 후:
- ✅ `wikiexport.html` 파일 생성
- ✅ `images/` 폴더에 이미지 저장

### 4단계: HTML 열기

**`wikiexport.html`** 파일을 **더블클릭**하면 웹 브라우저에서 열립니다.

---

## 📋 설정 상세 가이드

### API 키 받기

1. Redmine에 로그인
2. 우측 상단의 사용자 이름 클릭 → **계정**
3. **API 액세스 토큰** 섹션에서 **토큰 생성** 클릭
4. 생성된 키를 `config.json`의 `api_key`에 붙여넣기

---

## ⚙️ 트러블슈팅

### 문제 1: Python이 없거나 에러 발생

**해결:**
1. Python 3.8 이상 설치 필요
2. https://www.python.org 에서 다운로드
3. 설치할 때 "Add Python to PATH" 체크 필수

### 문제 2: "❌ Error: config.json not found!"

**해결:**
- `config.json` 파일이 `Run_WikiExport.bat`과 같은 폴더에 있는지 확인

### 문제 3: API 키가 작동 안 함

**해결:**
1. API 키가 정확한지 확인 (공백 없어야 함)
2. Redmine에서 "API 토큰 활성화" 되었는지 확인
3. 해당 프로젝트에 접근 권한이 있는지 확인


---

## 📁 파일 구조

```
wikiexport/
├── Run_WikiExport.bat          ← 이 파일을 실행
├── config.json                 ← 설정 파일
├── mirror_wiki.py              ← 실행되는 Python 프로그램 (수정 X)
├── styles/                     ← CSS 파일 (수정 X)
├── wikiexport.html             ← ✨ 생성된 결과 파일 (이걸 열어보기)
└── images/                     ← 모든 이미지 저장됨
    ├── page-1-로그인/
    ├── page-1-마감정산/
    └── ...
```

---

## 🛠️ 고급 사용법

### 같은 경로에서 다시 실행

기존 파일을 덮어씁니다:
1. `Run_WikiExport.bat` 더블클릭
2. 완료 대기
3. `wikiexport.html` 새로고침 (F5)

### 다른 파일명으로 저장

`config.json`의 `filename` 변경:

```json
"filename": "우리팀_매뉴얼.html"
```

---

## ✅ 체크리스트

실행 전 확인사항:

- [ ] Windows PC 또는 Mac/Linux
- [ ] Python 3.8 이상 설치됨
- [ ] `config.json` 파일 있음
- [ ] `base_url`, `api_key`, `project_key` 입력됨
- [ ] 인터넷 연결됨

---

## 📞 추가 정보

**생성되는 HTML 파일의 특징:**

- 📱 **반응형**: 핸드폰에서도 잘 보임
- 🔍 **검색 가능**: Ctrl+F로 찾기 가능
- 📖 **목차 자동 생성**: 좌측에 목차 표시 및 검색 기능 제공
- 🖼️ **이미지 포함**: 모든 이미지가 로컬에 저장되어 표시됨
- 💾 **오프라인 사용**: 인터넷 없이도 열람 가능

---

## 📝 주의사항

1. 배치 파일 실행 중에 터미널 창을 닫지 마세요
2. 큰 프로젝트는 시간이 오래 걸릴 수 있습니다
3. 실행 중에 Redmine 서버가 느리면 에러가 발생할 수 있습니다

---

**😊 처음 사용자도 쉽게 따라할 수 있습니다!**

질문이 있으면 이 파일을 읽어보고, 해결 안 되면 문의하세요.
