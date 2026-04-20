# 📚 Redmine Wiki Export Tool (사용 설명서)

Redmine의 Wiki 문서 전체를 **단일 HTML 파일**로 내보내는 도구입니다.  
좌측 고정 목차(TOC) + 검색 기능이 포함된 오프라인 열람용 문서를 생성합니다.

---

## 🖥️ 실행 방법

### 방법 A — GUI 프로그램 (권장)

**`WikiExport.exe`** 를 더블클릭하거나, Python이 설치되어 있다면:

```
python gui_app.py
```

GUI 창에서 아래 정보를 입력하고 **▶ 내보내기 시작** 버튼을 누릅니다:

| 항목 | 설명 |
|------|------|
| **Base URL** | Redmine 서버 주소 (예: `http://192.168.0.10:6080`) |
| **Project Key** | 프로젝트 URL의 `/projects/` 뒤 식별자 (예: `bp-cloudpos-docs`) |
| **API Key** | Redmine 내 계정 → API 액세스 키 (40자리) |
| **저장 폴더** | 결과물을 저장할 폴더 |
| **파일명** | 생성될 HTML 파일 이름 (기본값: `wikiexport.html`) |

입력값은 로컬 `config.json`에 저장되어 다음 실행 때 불러옵니다.
GitHub 저장소에는 민감정보가 포함되지 않도록 `config.json` 대신 `config.example.json`만 추적합니다.

---

### 방법 B — 명령줄 (CLI)

**`Run_WikiExport.bat`** 을 더블클릭하거나 터미널에서 실행합니다.  
로컬 `config.json`에 먼저 설정을 입력해야 합니다.

```
python mirror_wiki.py
```

---

## ⚙️ config 설정

처음에는 `config.example.json`을 복사해서 `config.json`으로 만든 뒤 값을 채워 사용하세요.

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

파일 구분:
- `config.example.json`: 저장소에 포함되는 예시 파일
- `config.json`: 로컬 실행용 실제 설정 파일, GitHub에는 올리지 않음

**항목 설명:**
- **base_url**: Redmine 서버 주소 (끝에 `/` 불필요)
- **project_key**: 프로젝트 식별자 — 브라우저 URL의 `/projects/` 바로 뒤 값
- **api_key**: Redmine REST API 인증 키 (40자리 영문+숫자)
- **filename**: 생성될 HTML 파일 이름
- **location**: HTML 파일이 저장될 폴더 경로
- **timeout**: 요청 타임아웃(초), 느린 서버의 경우 늘려주세요 (기본값: 30)
- **retry_attempts**: 실패 시 재시도 횟수 (기본값: 3)

---

## 📋 API 키 발급 방법

1. Redmine에 로그인
2. 우측 상단 계정 아이콘 클릭 → **내 계정**
3. 우측 하단 **API 액세스 키** 항목에서 키 확인 또는 생성
4. 생성된 키(40자리)를 `config.json`의 `api_key`에 붙여넣기

---

## 📤 내보내기 처리 단계

내보내기 실행 시 다음 5단계가 순서대로 진행됩니다:

1. **서버 연결 테스트** — API Key 및 네트워크 사전 확인
2. **TOC 페이지 수신** — 위키 목차 인덱스 페이지 가져오기
3. **링크 추출** — 위키 페이지 목록 파싱
4. **페이지 다운로드** — 각 페이지 HTML + 이미지 로컬 저장
5. **HTML 병합 및 저장** — 단일 HTML 파일 생성, `styles/` 폴더 복사

---

## 📄 출력 HTML 기능

- **고정 좌측 목차** — 계층 구조(트리) 형태의 TOC
- **목차 실시간 검색** — 검색어 입력 시 즉시 필터링
- **반응형 레이아웃** — 모바일/좁은 화면에서 목차 상단 배치
- **내부 위키 링크 유지** — 페이지 간 링크가 앵커(#)로 재작성되어 동작
- **이미지 로컬 저장** — 페이지별 하위 폴더(`images/page-xxx/`)에 저장

---

## ⚙️ 트러블슈팅

### Python이 없거나 에러 발생

1. Python 3.8 이상 설치 필요
2. https://www.python.org 에서 다운로드
3. 설치할 때 **"Add Python to PATH"** 체크 필수
4. 의존 패키지 설치: `pip install requests beautifulsoup4`

### "❌ Error: config.json not found!"

`config.json` 파일이 `Run_WikiExport.bat`, `mirror_wiki.py`와 **같은 폴더**에 있는지 확인하세요.

### 인증 실패 (401)

- API Key가 정확한지 확인 (앞뒤 공백 없어야 함)
- Redmine 관리자 설정에서 REST API가 활성화되어 있는지 확인

### 접근 거부 (403) / 페이지 없음 (404)

- 해당 프로젝트에 멤버 권한이 있는지 확인
- Project Key가 올바른지 확인 (대소문자 구분)

---

## 🔨 EXE 빌드 (개발자용)

PyInstaller로 단일 실행 파일 생성:

```
pip install pyinstaller
pyinstaller WikiExport.spec
```

빌드 결과물: `dist/WikiExport.exe`

---

## 📁 파일 구조

```
wikiexport/
├── gui_app.py              ← GUI 메인 (python gui_app.py)
├── mirror_wiki.py          ← CLI 핵심 로직 (python mirror_wiki.py)
├── config.json             ← 연결 설정 파일
├── Run_WikiExport.bat      ← CLI 모드 실행 배치 파일
├── WikiExport.spec         ← PyInstaller EXE 빌드 설정
├── styles/                 ← Redmine CSS (빌드 시 번들 포함)
├── wikiexport.html         ← ✨ 내보내기 결과 HTML
└── images/                 ← 페이지별 이미지 저장 폴더
    ├── page-1-로그인/
    ├── page-1-마감정산/
    └── ...
```

---

## ✅ 실행 전 체크리스트

- [ ] Python 3.8 이상 설치 (`python --version`)
- [ ] 패키지 설치: `pip install requests beautifulsoup4`
- [ ] `config.json` 에 `base_url`, `project_key`, `api_key` 입력
- [ ] Redmine 서버 접근 가능 (네트워크 확인)

---

## 📝 주의사항

1. 배치 파일 실행 중에 터미널 창을 닫지 마세요
2. 큰 프로젝트는 시간이 오래 걸릴 수 있습니다
3. 실행 중에 Redmine 서버가 느리면 에러가 발생할 수 있습니다

---

**😊 처음 사용자도 쉽게 따라할 수 있습니다!**

질문이 있으면 이 파일을 읽어보고, 해결 안 되면 문의하세요.
