# -*- mode: python ; coding: utf-8 -*-
# WikiExport.spec — PyInstaller 빌드 설정
# 빌드 명령: pyinstaller WikiExport.spec

block_cipher = None

a = Analysis(
    ['gui_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('styles', 'styles'),      # CSS 파일들 번들에 포함
        ('mirror_wiki.py', '.'),   # WikiParser 모듈 포함
    ],
    hiddenimports=[
        'mirror_wiki',
        'bs4',
        'requests',
        'urllib3',
        'charset_normalizer',
        'certifi',
        'idna',
        'soupsieve',
        'html.parser',
        'collections',
        'collections.abc',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='WikiExport',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # 콘솔 창 없음 (GUI 전용)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
