# 📚 Redmine Wiki Export Tool

Redmine 프로젝트의 위키 전체를 **단일 HTML 파일**로 내보내는 도구입니다.
좌측 고정 목차(TOC) + 실시간 검색이 포함된 오프라인 열람용 문서를 생성하며,
한 번에 **여러 프로젝트**를 선택해 각각 내보낼 수 있습니다.

---

## 🖥️ 실행

### GUI (권장)

`dist/WikiExport.exe` 를 더블클릭하거나, Python 환경에서:

```
pip install -r requirements.txt
python gui_app.py
```

**사용 순서**

1. **Base URL** 과 **API Key** 입력
2. **🔄 프로젝트 불러오기** — 위키가 활성화된 프로젝트 목록을 가져옵니다
3. 내보낼 프로젝트를 **체크** (여러 개 선택 가능 · 전체 선택/해제 지원)
4. **저장 폴더** · **파일명** 지정 후 **▶ 내보내기 시작**

입력값과 선택은 로컬 `config.json` 에 저장되어 다음 실행 때 자동 복원됩니다.

### CLI

`config.json` 을 채운 뒤 실행합니다. (CLI는 `project_key` 하나만 처리 — 다중 선택은 GUI를 사용하세요.)

```
python mirror_wiki.py
```

---

## 📂 출력 구조

선택한 프로젝트마다 **식별자 이름의 하위 폴더**로 독립 생성됩니다:

```
저장 폴더/
├── bp-cloudpos/
│   ├── wikiexport.html
│   ├── images/
│   └── styles/
└── bp-cloudpos-docs/
    ├── wikiexport.html
    ├── images/
    └── styles/
```

각 폴더는 완전히 독립적이라, 폴더째 옮기거나 공유해도 이미지·스타일이 깨지지 않습니다.

**HTML 기능** — 좌측 고정 목차(트리) · 목차 실시간 검색 · "목차로 돌아가기" · 페이지 간 링크 유지 · 이미지 로컬 저장 · 반응형 레이아웃

---

## ⚙️ config.json

`config.example.json` 을 복사해 `config.json` 을 만든 뒤 값을 채웁니다.

```json
{
  "redmine": {
    "base_url": "http://your-redmine-server",
    "api_key": "your-api-key",
    "project_key": "project-a",
    "project_keys": ["project-a", "project-b"]
  },
  "output": {
    "filename": "wikiexport.html",
    "location": "./"
  },
  "options": { "timeout": 30, "retry_attempts": 3 }
}
```

| 항목 | 설명 |
|------|------|
| `base_url` | Redmine 서버 주소 (끝 `/` 불필요) |
| `api_key` | REST API 인증 키 (40자리) |
| `project_keys` | GUI 다중 내보내기 대상 식별자 목록 (GUI가 자동 관리) |
| `project_key` | CLI(`mirror_wiki.py`)용 단일 식별자 |
| `filename` / `location` | 결과 HTML 이름 / 저장 폴더 |
| `timeout` / `retry_attempts` | 요청 타임아웃(초) / 재시도 횟수 |

> `config.json` 은 `.gitignore` 처리되어 저장소에 올라가지 않습니다.
> exe로 공유할 땐 **exe 파일만** 전달하세요 (API 키 유출 방지).

---

## 🔑 API 키 발급

Redmine 로그인 → 우측 상단 **내 계정** → 우측 하단 **API 액세스 키** 확인/생성 → `api_key` 에 입력.

---

## 🛠️ 트러블슈팅

| 증상 | 해결 |
|------|------|
| `ModuleNotFoundError` | `pip install -r requirements.txt` |
| 인증 실패 (401) | API Key 확인 (앞뒤 공백 없이) · 관리자 REST API 활성화 |
| 접근 거부 / 없음 (403 / 404) | 프로젝트 멤버 권한 · 식별자 확인 |
| 프로젝트 목록이 안 뜸 | Base URL · API Key 입력 후 "🔄 프로젝트 불러오기" 클릭 |

---

## 🔨 EXE 빌드 (개발자용)

```
pip install pyinstaller
pyinstaller WikiExport.spec
```

결과물: `dist/WikiExport.exe` (단일 파일, `styles/` 와 `mirror_wiki.py` 번들 포함)

---

## 📁 파일 구조

```
WikiExport/
├── gui_app.py           GUI — 프로젝트 불러오기 · 다중 선택
├── mirror_wiki.py       WikiParser — 다운로드 · 파싱 · HTML 병합
├── styles/              Redmine CSS (빌드 시 번들)
├── config.example.json  설정 예시
├── WikiExport.spec      PyInstaller 빌드 설정
├── Run_WikiExport.bat   CLI 실행 배치
└── requirements.txt     의존성 (requests, beautifulsoup4)
```
