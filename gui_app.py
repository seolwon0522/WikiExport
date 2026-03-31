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
        self._v_project  = tk.StringVar()
        self._v_apikey   = tk.StringVar()
        self._v_folder   = tk.StringVar()
        self._v_filename = tk.StringVar()
        self._v_show_api = tk.BooleanVar(value=False)

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
        _add_row(
            1, 'Project Key', self._v_project,
            hint_text   = '예) my-project   ← URL의 /projects/ 뒤에 오는 영문 식별자',
            tooltip_text = (
                'Redmine 프로젝트 식별자(슬러그)입니다.\n\n'
                '확인 방법:\n'
                '브라우저에서 위키 페이지를 열었을 때 주소창을 보면\n'
                'http://서버/projects/【여기】/wiki  ← 이 부분입니다.\n\n'
                '예) URL이 http://서버/projects/bp-cloudpos-docs/wiki 이면\n'
                '    Project Key = bp-cloudpos-docs'
            ),
        )
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
            self._v_project.set(r.get('project_key', ''))
            self._v_apikey.set(r.get('api_key', ''))
            self._v_folder.set(o.get('location', get_exe_dir()))
            self._v_filename.set(o.get('filename', 'wikiexport.html'))
        except Exception:
            self._v_folder.set(get_exe_dir())
            self._v_filename.set('wikiexport.html')

    def _save_config(self):
        cfg = {
            "redmine": {
                "base_url":    self._v_url.get().strip(),
                "project_key": self._v_project.get().strip(),
                "api_key":     self._v_apikey.get().strip(),
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
        proj   = self._v_project.get().strip()
        apikey = self._v_apikey.get().strip()
        folder = self._v_folder.get().strip()
        fname  = self._v_filename.get().strip()

        if not url:
            messagebox.showerror("입력 오류", "Base URL을 입력하세요.")
            return False
        if not url.startswith(('http://', 'https://')):
            messagebox.showerror("입력 오류", "Base URL은 http:// 또는 https://로 시작해야 합니다.")
            return False
        if not proj:
            messagebox.showerror("입력 오류", "Project Key를 입력하세요.")
            return False
        if not apikey:
            messagebox.showerror("입력 오류", "API Key를 입력하세요.")
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
            project  = self._v_project.get().strip()
            apikey   = self._v_apikey.get().strip()
            folder   = self._v_folder.get().strip()
            filename = self._v_filename.get().strip()
            if not filename.lower().endswith('.html'):
                filename += '.html'

            # ── 사전 연결 진단 ───────────────────────────────────────────
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

            images_folder = os.path.join(folder, 'images')
            parser = WikiParser(
                base_url=base_url,
                api_key=apikey,
                images_folder=images_folder,
                timeout=30,
                max_retries=3,
            )
            self._current_parser = parser

            # Step 1 — TOC
            self._log("\n📝 Step 1: TOC 페이지 가져오는 중...")
            toc_html = parser.fetch_toc_page(project)
            if not toc_html:
                self._log("❌ TOC 페이지를 가져오지 못했습니다.")
                self._log(f"   → Project Key '{project}'가 올바른지 확인하세요.")
                self._log(f"   → 주소: {base_url}/projects/{project}/wiki")
                return

            # Step 2 — 링크 파싱
            self._log("\n🔍 Step 2: 위키 링크 추출 중...")
            links = parser.parse_toc_links(toc_html)
            if not links:
                self._log("❌ TOC에서 위키 페이지를 찾지 못했습니다.")
                return
            self._log(f"✓ {len(links)}개 페이지 발견")

            if not self._running:
                self._log("⚠️  내보내기 중단됨.")
                return

            # Step 3 — 페이지 다운로드
            self._log(f"\n⬇️  Step 3: {len(links)}개 페이지 다운로드 중...")
            parser.fetch_all_pages(links)
            if not parser.pages:
                self._log("❌ 페이지를 가져오지 못했습니다.")
                return

            if not self._running:
                self._log("⚠️  내보내기 중단됨.")
                return

            # Step 4 — HTML 생성
            self._log("\n🔗 Step 4: HTML 생성 중...")
            merged_html = parser.generate_merged_html(project)

            # Step 5 — 저장
            self._log("\n💾 Step 5: 파일 저장 중...")
            os.makedirs(folder, exist_ok=True)
            output_path = os.path.join(folder, filename)
            parser.save_to_file(merged_html, output_path)

            # styles 폴더 복사 (HTML의 상대 경로 참조 유지)
            src_styles = get_resource_path('styles')
            dst_styles = os.path.join(folder, 'styles')
            if os.path.isdir(src_styles):
                if not os.path.isdir(dst_styles):
                    shutil.copytree(src_styles, dst_styles)
                    self._log(f"✓ styles 폴더 복사: {dst_styles}")
                else:
                    self._log("✓ styles 폴더 이미 존재 — 복사 생략")
            else:
                self._log("⚠️  styles 폴더를 번들에서 찾을 수 없습니다.")

            abs_path = os.path.abspath(output_path)
            self._log(f"\n{'='*52}")
            self._log(f"✅ 내보내기 완료!")
            self._log(f"📂 파일: {abs_path}")
            self._log(f"📊 총 {len(parser.pages)}개 페이지 / {len(parser.downloaded_images)}개 이미지")
            self._log(f"📈 파일 크기: {len(merged_html) / (1024*1024):.2f} MB")
            self._log(f"{'='*52}\n")

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
