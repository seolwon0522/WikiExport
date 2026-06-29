#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import sys
import logging
import threading
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext


# ---------------------------------------------------------------------------
# 경로 헬퍼 (PyInstaller --onefile 호환)
# ---------------------------------------------------------------------------

def get_exe_dir():
    """실행 파일 위치 반환 (exe: 실행 파일 폴더, 개발: 스크립트 폴더)"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_resource_path(relative_path):
    """PyInstaller 번들 내 리소스 절대 경로 반환"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)


CONFIG_FILE = os.path.join(get_exe_dir(), 'config.json')


# ---------------------------------------------------------------------------
# 로깅 → Tkinter Text 위젯 핸들러
# ---------------------------------------------------------------------------

class _TextLogHandler(logging.Handler):
    """로그 레코드를 Tkinter ScrolledText 위젯에 thread-safe하게 출력"""

    def __init__(self, widget):
        super().__init__()
        self._widget = widget

    def emit(self, record):
        msg = self.format(record) + '\n'

        def _append():
            self._widget.configure(state='normal')
            self._widget.insert(tk.END, msg)
            self._widget.see(tk.END)
            self._widget.configure(state='disabled')

        # Tkinter는 메인 스레드에서만 UI 조작 가능 → after() 사용
        self._widget.after(0, _append)


# ---------------------------------------------------------------------------
# 마우스 오버 툴팁
# ---------------------------------------------------------------------------

class _Tooltip:
    """위젯에 마우스를 올리면 말풍선 설명 표시"""

    def __init__(self, widget, text):
        self._widget = widget
        self._text   = text
        self._tw     = None
        widget.bind('<Enter>', self._show)
        widget.bind('<Leave>', self._hide)

    def _show(self, _event=None):
        if self._tw:
            return
        x = self._widget.winfo_rootx() + 24
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 6
        self._tw = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.wm_attributes('-topmost', True)
        tk.Label(
            tw, text=self._text, justify='left',
            background='#fffde7', relief='solid', borderwidth=1,
            font=('Malgun Gothic', 9), wraplength=380, padx=10, pady=8,
        ).pack()

    def _hide(self, _event=None):
        if self._tw:
            self._tw.destroy()
            self._tw = None


# ---------------------------------------------------------------------------
# 메인 애플리케이션 클래스
# ---------------------------------------------------------------------------

class WikiExportApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Redmine Wiki Export")
        self.geometry("780x780")
        self.minsize(660, 620)
        self._running = False
        self._thread = None
        self._current_parser = None  # 중단 시 abort 플래그 전달용
        self._build_ui()
        self._load_config()

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------

    def _build_ui(self):
        self._v_url      = tk.StringVar()
        self._v_apikey   = tk.StringVar()
        self._v_folder   = tk.StringVar()
        self._v_filename = tk.StringVar()
        self._v_show_api = tk.BooleanVar(value=False)

        # 프로젝트 다중 선택 상태
        self._project_checks  = {}   # identifier -> {'var': BooleanVar, 'name': str}
        self._saved_selection = []   # config.json 에서 복원된 선택 식별자 목록
        self._loading_projects = False
        self._proj_status = tk.StringVar(value='Base URL · API Key 입력 후 “불러오기”')

        # ── 입력 폼 ──────────────────────────────────────────────────
        form = ttk.LabelFrame(self, text="Redmine 연결 설정", padding=(12, 8))
        form.pack(fill='x', padx=16, pady=(14, 4))
        form.columnconfigure(1, weight=1)

        def _add_row(grid_row, label_text, var, hint_text, tooltip_text, extra=None):
            """라벨 + ⓘ + 입력 + 힌트 한 행 추가"""
            # 라벨 + ⓘ 아이콘
            lf = ttk.Frame(form)
            lf.grid(row=grid_row * 2, column=0, sticky='ne', padx=(0, 8), pady=(10, 0))
            ttk.Label(lf, text=f"{label_text}:").pack(side='left')
            tip_icon = ttk.Label(lf, text=' ⓘ', foreground='#0077cc', cursor='question_arrow')
            tip_icon.pack(side='left')
            _Tooltip(tip_icon, tooltip_text)

            # 입력 위젯
            if extra == 'api':
                ef = ttk.Frame(form)
                ef.grid(row=grid_row * 2, column=1, sticky='we', pady=(10, 0))
                ef.columnconfigure(0, weight=1)
                self._api_entry = ttk.Entry(ef, textvariable=var, show='*')
                self._api_entry.grid(row=0, column=0, sticky='we')
                ttk.Checkbutton(
                    ef, text="표시", variable=self._v_show_api,
                    command=self._toggle_api,
                ).grid(row=0, column=1, padx=(8, 0))
            elif extra == 'browse':
                ef = ttk.Frame(form)
                ef.grid(row=grid_row * 2, column=1, sticky='we', pady=(10, 0))
                ef.columnconfigure(0, weight=1)
                ttk.Entry(ef, textvariable=var).grid(row=0, column=0, sticky='we')
                ttk.Button(
                    ef, text="📁 찾아보기", command=self._browse_folder,
                ).grid(row=0, column=1, padx=(8, 0))
            else:
                ttk.Entry(form, textvariable=var).grid(
                    row=grid_row * 2, column=1, sticky='we', pady=(10, 0))

            # 힌트 라벨
            ttk.Label(
                form, text=hint_text,
                foreground='#888888', font=('Malgun Gothic', 8),
            ).grid(row=grid_row * 2 + 1, column=1, sticky='w', padx=(2, 0), pady=(1, 4))

        _add_row(
            0, 'Base URL', self._v_url,
            hint_text   = '예) http://192.168.0.10:6080   또는   https://redmine.mycompany.com',
            tooltip_text = (
                'Redmine 서버 주소입니다.\n'
                '브라우저에서 Redmine에 접속할 때 사용하는 URL을 입력하세요.\n'
                '끝에 슬래시(/)는 붙이지 않아도 됩니다.\n\n'
                '예)  http://106.255.231.26:6080\n'
                '     https://redmine.example.com'
            ),
        )
        self._build_project_selector(form, 1)
        _add_row(
            2, 'API Key', self._v_apikey,
            hint_text   = 'Redmine 로그인 → 우측 상단 내 계정 → API 액세스 키 (40자리)',
            tooltip_text = (
                'Redmine REST API 인증 키입니다. (40자리 영문+숫자)\n\n'
                '발급 방법:\n'
                '  1. Redmine 로그인 후 우측 상단 계정 아이콘 클릭\n'
                '  2. "내 계정" 페이지 이동\n'
                '  3. 우측 하단 "API 액세스 키" 항목에서 키 확인 또는 생성\n\n'
                '키가 보이지 않으면 관리자에게 API 활성화를 요청하세요.'
            ),
            extra='api',
        )
        _add_row(
            3, '저장 폴더', self._v_folder,
            hint_text   = '내보낸 HTML · 이미지 · styles 폴더가 이곳에 저장됩니다',
            tooltip_text = (
                '내보내기 결과물이 저장될 폴더입니다.\n\n'
                '생성되는 파일:\n'
                '  · wikiexport.html  — 모든 위키를 합친 단일 HTML\n'
                '  · images/          — 위키에 첨부된 이미지\n'
                '  · styles/          — CSS 스타일 파일\n\n'
                '"📁 찾아보기" 버튼으로 원하는 폴더를 선택하세요.'
            ),
            extra='browse',
        )
        _add_row(
            4, '파일명', self._v_filename,
            hint_text   = '저장될 HTML 파일 이름  (기본값: wikiexport.html)',
            tooltip_text = (
                '생성될 HTML 파일의 이름입니다.\n'
                '.html 확장자로 끝나야 합니다.\n\n'
                '기본값: wikiexport.html'
            ),
        )

        # ── 버튼 바 ──────────────────────────────────────────────────
        btn_bar = ttk.Frame(self)
        btn_bar.pack(fill='x', padx=16, pady=(6, 8))

        self._btn_start = ttk.Button(
            btn_bar, text="▶  내보내기 시작", command=self._start_export)
        self._btn_start.pack(side='left')

        self._btn_stop = ttk.Button(
            btn_bar, text="■  중단", command=self._stop_export, state='disabled')
        self._btn_stop.pack(side='left', padx=(8, 0))

        ttk.Button(btn_bar, text="로그 지우기", command=self._clear_log).pack(side='right')

        # ── 로그 출력 ─────────────────────────────────────────────────
        log_frame = ttk.LabelFrame(self, text="실행 로그", padding=6)
        log_frame.pack(fill='both', expand=True, padx=16, pady=(0, 14))

        self._log_box = scrolledtext.ScrolledText(
            log_frame, state='disabled', wrap='word',
            height=18, font=('Consolas', 9))
        self._log_box.pack(fill='both', expand=True)

    # ------------------------------------------------------------------
    # UI 이벤트
    # ------------------------------------------------------------------

    def _toggle_api(self):
        self._api_entry.config(show='' if self._v_show_api.get() else '*')

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="저장 폴더 선택")
        if folder:
            self._v_folder.set(folder)

    # ------------------------------------------------------------------
    # 프로젝트 선택 (서버에서 목록 불러오기 → 체크박스 다중 선택)
    # ------------------------------------------------------------------

    def _build_project_selector(self, form, grid_row):
        """Project Key 수기 입력 대신, 서버에서 위키 프로젝트를 불러와 체크박스로 선택"""
        # 라벨 + ⓘ
        lf = ttk.Frame(form)
        lf.grid(row=grid_row * 2, column=0, sticky='ne', padx=(0, 8), pady=(10, 0))
        ttk.Label(lf, text="프로젝트:").pack(side='left')
        tip = ttk.Label(lf, text=' ⓘ', foreground='#0077cc', cursor='question_arrow')
        tip.pack(side='left')
        _Tooltip(tip, (
            'Base URL 과 API Key 를 입력한 뒤 “프로젝트 불러오기”를 누르면\n'
            '해당 키로 접근 가능한 위키 프로젝트 목록을 가져옵니다.\n\n'
            '내보낼 프로젝트를 하나 이상 체크하세요.\n'
            '여러 개를 선택하면 각각 별도 폴더/HTML 로 생성됩니다.'
        ))

        box = ttk.Frame(form)
        box.grid(row=grid_row * 2, column=1, sticky='we', pady=(10, 0))
        box.columnconfigure(0, weight=1)

        bar = ttk.Frame(box)
        bar.grid(row=0, column=0, sticky='we')
        self._btn_load = ttk.Button(bar, text="🔄 프로젝트 불러오기", command=self._load_projects)
        self._btn_load.pack(side='left')
        ttk.Label(bar, textvariable=self._proj_status,
                  foreground='#888888', font=('Malgun Gothic', 8)).pack(side='left', padx=(8, 0))

        # 스크롤 가능한 체크박스 영역
        list_wrap = ttk.Frame(box, relief='solid', borderwidth=1)
        list_wrap.grid(row=1, column=0, sticky='we', pady=(6, 0))
        self._proj_canvas = tk.Canvas(list_wrap, height=92, highlightthickness=0)
        sb = ttk.Scrollbar(list_wrap, orient='vertical', command=self._proj_canvas.yview)
        self._proj_inner = ttk.Frame(self._proj_canvas)
        self._proj_inner.bind(
            '<Configure>',
            lambda e: self._proj_canvas.configure(scrollregion=self._proj_canvas.bbox('all')))
        self._proj_canvas.create_window((0, 0), window=self._proj_inner, anchor='nw')
        self._proj_canvas.configure(yscrollcommand=sb.set)
        self._proj_canvas.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')

        sel_bar = ttk.Frame(box)
        sel_bar.grid(row=2, column=0, sticky='we', pady=(2, 0))
        ttk.Button(sel_bar, text="전체 선택", width=10,
                   command=lambda: self._set_all_projects(True)).pack(side='left')
        ttk.Button(sel_bar, text="전체 해제", width=10,
                   command=lambda: self._set_all_projects(False)).pack(side='left', padx=(6, 0))

        ttk.Label(form, text='불러오기 후 내보낼 프로젝트를 체크하세요 (여러 개 가능)',
                  foreground='#888888', font=('Malgun Gothic', 8)
                  ).grid(row=grid_row * 2 + 1, column=1, sticky='w', padx=(2, 0), pady=(1, 4))

    def _set_all_projects(self, value):
        for info in self._project_checks.values():
            info['var'].set(value)

    def _selected_projects(self):
        """체크된 (identifier, name) 목록"""
        return [(ident, info['name'])
                for ident, info in self._project_checks.items() if info['var'].get()]

    def _load_projects(self):
        if self._loading_projects:
            return
        url    = self._v_url.get().strip().rstrip('/')
        apikey = self._v_apikey.get().strip()
        if not url.startswith(('http://', 'https://')):
            messagebox.showerror("입력 오류", "먼저 올바른 Base URL을 입력하세요 (http:// 또는 https://).")
            return
        if not apikey:
            messagebox.showerror("입력 오류", "먼저 API Key를 입력하세요.")
            return
        self._loading_projects = True
        self._btn_load.config(state='disabled')
        self._proj_status.set("불러오는 중...")
        threading.Thread(target=self._load_projects_worker,
                         args=(url, apikey), daemon=True).start()

    def _load_projects_worker(self, base_url, apikey):
        """백그라운드: /projects.json 페이징 수집 → 위키 모듈 프로젝트만 필터"""
        try:
            import requests as _req
            projects = []
            offset, limit = 0, 100
            while True:
                resp = _req.get(
                    f"{base_url}/projects.json",
                    headers={'X-Redmine-API-Key': apikey},
                    params={'limit': limit, 'offset': offset, 'include': 'enabled_modules'},
                    timeout=15,
                )
                if resp.status_code == 401:
                    self.after(0, lambda: self._proj_load_failed("인증 실패 (401) — API Key를 확인하세요."))
                    return
                if resp.status_code == 403:
                    self.after(0, lambda: self._proj_load_failed("접근 거부 (403) — 권한을 확인하세요."))
                    return
                resp.raise_for_status()
                data  = resp.json()
                batch = data.get('projects', [])
                projects.extend(batch)
                total  = data.get('total_count', len(projects))
                offset += limit
                if offset >= total or not batch:
                    break

            # 위키 모듈이 있는 프로젝트만 (모듈 정보 없으면 일단 포함)
            wiki_projects = []
            for p in projects:
                mods = p.get('enabled_modules')
                if mods is None or any(m.get('name') == 'wiki' for m in mods):
                    wiki_projects.append({'identifier': p['identifier'],
                                          'name': p.get('name', p['identifier'])})
            self.after(0, lambda: self._render_projects(wiki_projects))
        except Exception as e:
            self.after(0, lambda: self._proj_load_failed(f"불러오기 실패: {e}"))

    def _proj_load_failed(self, msg):
        self._loading_projects = False
        self._btn_load.config(state='normal')
        self._proj_status.set("❌ " + msg)

    def _render_projects(self, projects):
        self._loading_projects = False
        self._btn_load.config(state='normal')
        for child in self._proj_inner.winfo_children():
            child.destroy()
        self._project_checks.clear()

        if not projects:
            self._proj_status.set("위키가 활성화된 프로젝트가 없습니다.")
            return

        for p in projects:
            ident = p['identifier']
            var = tk.BooleanVar(value=(ident in self._saved_selection))
            ttk.Checkbutton(
                self._proj_inner,
                text=f"{p['name']}  ({ident})",
                variable=var,
            ).pack(anchor='w', padx=6, pady=1)
            self._project_checks[ident] = {'var': var, 'name': p['name']}

        self._proj_status.set(f"✓ {len(projects)}개 — 내보낼 항목을 체크하세요.")
        self._proj_canvas.yview_moveto(0)

    def _clear_log(self):
        self._log_box.configure(state='normal')
        self._log_box.delete('1.0', tk.END)
        self._log_box.configure(state='disabled')

    def _log(self, msg):
        """메인 스레드 또는 워커 스레드에서 안전하게 로그 추가"""
        def _append():
            self._log_box.configure(state='normal')
            self._log_box.insert(tk.END, msg + '\n')
            self._log_box.see(tk.END)
            self._log_box.configure(state='disabled')
        self.after(0, _append)

    # ------------------------------------------------------------------
    # 설정 로드 / 저장
    # ------------------------------------------------------------------

    def _load_config(self):
        if not os.path.exists(CONFIG_FILE):
            self._v_folder.set(get_exe_dir())
            self._v_filename.set('wikiexport.html')
            return
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            r = cfg.get('redmine', {})
            o = cfg.get('output', {})
            self._v_url.set(r.get('base_url', ''))
            self._v_apikey.set(r.get('api_key', ''))
            # 이전 선택 복원: project_keys(리스트) 우선, 없으면 project_key(단일, 구버전 호환)
            sel = r.get('project_keys')
            if not sel:
                single = r.get('project_key')
                sel = [single] if single else []
            self._saved_selection = list(sel)
            self._v_folder.set(o.get('location', get_exe_dir()))
            self._v_filename.set(o.get('filename', 'wikiexport.html'))
        except Exception:
            self._v_folder.set(get_exe_dir())
            self._v_filename.set('wikiexport.html')

    def _save_config(self):
        selected = [ident for ident, _ in self._selected_projects()]
        cfg = {
            "redmine": {
                "base_url":     self._v_url.get().strip(),
                "project_keys": selected,
                # 첫 선택은 project_key 로도 저장 → CLI(mirror_wiki.py) 하위호환
                "project_key":  selected[0] if selected else "",
                "api_key":      self._v_apikey.get().strip(),
            },
            "output": {
                "filename": self._v_filename.get().strip(),
                "location": self._v_folder.get().strip(),
            },
            "options": {
                "timeout":        30,
                "retry_attempts": 3,
            },
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._log(f"⚠️  config.json 저장 실패: {e}")

    # ------------------------------------------------------------------
    # 입력 검증
    # ------------------------------------------------------------------

    def _validate(self):
        url    = self._v_url.get().strip()
        apikey = self._v_apikey.get().strip()
        folder = self._v_folder.get().strip()
        fname  = self._v_filename.get().strip()

        if not url:
            messagebox.showerror("입력 오류", "Base URL을 입력하세요.")
            return False
        if not url.startswith(('http://', 'https://')):
            messagebox.showerror("입력 오류", "Base URL은 http:// 또는 https://로 시작해야 합니다.")
            return False
        if not apikey:
            messagebox.showerror("입력 오류", "API Key를 입력하세요.")
            return False
        if not self._selected_projects():
            messagebox.showerror("입력 오류",
                "내보낼 프로젝트를 1개 이상 선택하세요.\n(“🔄 프로젝트 불러오기” 후 체크)")
            return False
        if not folder:
            messagebox.showerror("입력 오류", "저장 폴더를 선택하세요.")
            return False
        if not fname:
            messagebox.showerror("입력 오류", "파일명을 입력하세요.")
            return False
        return True

    # ------------------------------------------------------------------
    # 내보내기 실행
    # ------------------------------------------------------------------

    def _start_export(self):
        if self._running:
            return
        if not self._validate():
            return
        self._save_config()
        self._clear_log()
        self._running = True
        self._btn_start.config(state='disabled')
        self._btn_stop.config(state='normal')
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _stop_export(self):
        self._running = False
        if self._current_parser is not None:
            self._current_parser._abort = True
        self._log("⚠️  중단 요청됨 (현재 페이지 완료 후 종료됩니다...)")

    def _worker(self):
        """백그라운드 스레드 — export 로직 실행"""
        # GUI 로그 핸들러 추가
        gui_handler = _TextLogHandler(self._log_box)
        gui_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)  # basicConfig가 no-op일 때 대비해 명시적 설정
        root_logger.addHandler(gui_handler)

        try:
            import requests as _req
            from mirror_wiki import WikiParser  # 지연 import (exe 내부 모듈)

            base_url = self._v_url.get().strip().rstrip('/')
            apikey   = self._v_apikey.get().strip()
            folder   = self._v_folder.get().strip()
            filename = self._v_filename.get().strip()
            if not filename.lower().endswith('.html'):
                filename += '.html'
            projects = self._selected_projects()   # [(identifier, name), ...]

            # ── 사전 연결 진단 (1회) ──────────────────────────────────────
            self._log("🔌 서버 연결 테스트 중...")
            try:
                test_resp = _req.get(
                    base_url,
                    headers={'X-Redmine-API-Key': apikey},
                    timeout=10,
                    allow_redirects=True,
                )
                sc = test_resp.status_code
                if sc == 401:
                    self._log(f"❌ 인증 실패 (401) — API Key가 잘못되었습니다.")
                    self._log("   → Redmine '내 계정' > 'API 액세스 키'를 확인하세요.")
                    return
                elif sc == 403:
                    self._log(f"❌ 접근 거부 (403) — 이 서버에 접근 권한이 없습니다.")
                    self._log("   → API Key 또는 프로젝트 멤버 권한을 확인하세요.")
                    return
                elif sc >= 500:
                    self._log(f"❌ 서버 오류 ({sc}) — Redmine 서버에 문제가 있습니다.")
                    return
                self._log(f"✓ 서버 연결 성공 (HTTP {sc})")
            except _req.exceptions.ConnectionError:
                self._log(f"❌ 연결 실패 — '{base_url}'에 접속할 수 없습니다.")
                self._log("   → Base URL(IP/포트)이 올바른지, 서버가 실행 중인지 확인하세요.")
                return
            except _req.exceptions.Timeout:
                self._log("❌ 연결 타임아웃 — 서버 응답 없음 (10초 초과).")
                self._log("   → 네트워크 또는 방화벽 설정을 확인하세요.")
                return
            except Exception as e:
                self._log(f"⚠️  연결 테스트 중 예외 발생: {e} (계속 진행)")
            # ─────────────────────────────────────────────────────────────

            self._log(f"\n📦 총 {len(projects)}개 프로젝트를 내보냅니다.")
            src_styles = get_resource_path('styles')
            results = []  # (name, ok, pages, images, path)

            for idx, (ident, name) in enumerate(projects, 1):
                if not self._running:
                    self._log("⚠️  내보내기 중단됨.")
                    break

                self._log(f"\n{'='*52}")
                self._log(f"[{idx}/{len(projects)}] {name}  ({ident})")
                self._log(f"{'='*52}")

                # 프로젝트마다 자기 하위 폴더로 독립 생성 (이미지/앵커 충돌 방지)
                proj_out = os.path.join(folder, ident)
                images_folder = os.path.join(proj_out, 'images')
                parser = WikiParser(
                    base_url=base_url, api_key=apikey,
                    images_folder=images_folder, timeout=30, max_retries=3,
                )
                self._current_parser = parser

                # Step 1 — TOC
                self._log("📝 Step 1: TOC 페이지 가져오는 중...")
                toc_html = parser.fetch_toc_page(ident)
                if not toc_html:
                    self._log(f"❌ TOC 실패 — '{ident}' 건너뜀.")
                    results.append((name, False, 0, 0, ''))
                    continue

                # Step 2 — 링크 파싱
                self._log("🔍 Step 2: 위키 링크 추출 중...")
                links = parser.parse_toc_links(toc_html)
                if not links:
                    self._log("❌ 위키 페이지를 찾지 못함 — 건너뜀.")
                    results.append((name, False, 0, 0, ''))
                    continue
                self._log(f"✓ {len(links)}개 페이지 발견")

                if not self._running:
                    self._log("⚠️  내보내기 중단됨.")
                    break

                # Step 3 — 페이지 다운로드
                self._log(f"⬇️  Step 3: {len(links)}개 페이지 다운로드 중...")
                parser.fetch_all_pages(links)
                if not parser.pages:
                    self._log("❌ 페이지 수신 실패 — 건너뜀.")
                    results.append((name, False, 0, 0, ''))
                    continue

                if not self._running:
                    self._log("⚠️  내보내기 중단됨.")
                    break

                # Step 4 — HTML 생성
                self._log("🔗 Step 4: HTML 생성 중...")
                merged_html = parser.generate_merged_html(ident)

                # Step 5 — 저장
                self._log("💾 Step 5: 파일 저장 중...")
                os.makedirs(proj_out, exist_ok=True)
                output_path = os.path.join(proj_out, filename)
                parser.save_to_file(merged_html, output_path)

                # styles 폴더 복사 (프로젝트 폴더마다)
                dst_styles = os.path.join(proj_out, 'styles')
                if os.path.isdir(src_styles):
                    if not os.path.isdir(dst_styles):
                        shutil.copytree(src_styles, dst_styles)
                else:
                    self._log("⚠️  styles 폴더를 번들에서 찾을 수 없습니다.")

                abs_path = os.path.abspath(output_path)
                self._log(f"✅ 완료: {abs_path}")
                self._log(f"   페이지 {len(parser.pages)}개 / 이미지 {len(parser.downloaded_images)}개"
                          f" / {len(merged_html) / (1024*1024):.2f} MB")
                results.append((name, True, len(parser.pages),
                                len(parser.downloaded_images), abs_path))
                self._current_parser = None

            # ── 전체 요약 ────────────────────────────────────────────────
            ok = [r for r in results if r[1]]
            self._log(f"\n{'='*52}")
            self._log(f"🏁 전체 완료 — 성공 {len(ok)} / 시도 {len(results)}")
            for name, success, pg, im, _ in results:
                if success:
                    self._log(f"  ✅ {name}  (페이지 {pg}, 이미지 {im})")
                else:
                    self._log(f"  ❌ {name}  실패")
            self._log(f"{'='*52}\n")

            if ok:
                self.after(0, lambda: self._on_complete(folder))

        except Exception as e:
            import traceback
            self._log(f"❌ 예기치 않은 오류 발생: {e}")
            self._log(traceback.format_exc())
        finally:
            root_logger.removeHandler(gui_handler)
            self._running = False
            self._current_parser = None
            self.after(0, self._reset_buttons)

    def _on_complete(self, folder):
        if messagebox.askyesno("완료", "내보내기가 완료되었습니다.\n저장 폴더를 열겠습니까?"):
            os.startfile(folder)

    def _reset_buttons(self):
        self._btn_start.config(state='normal')
        self._btn_stop.config(state='disabled')


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    app = WikiExportApp()
    app.mainloop()
