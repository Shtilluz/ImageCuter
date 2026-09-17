# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from PyInstaller.utils.hooks import collect_all

dnd_datas, dnd_binaries, dnd_hiddenimports = collect_all('tkinterdnd2')

icon_file = os.path.join('resource', 'Icon.ico') if sys.platform == 'win32' else None

a = Analysis(
    ['gui_cutter.py'],
    pathex=[],
    binaries=dnd_binaries,
    datas=dnd_datas,
    hiddenimports=dnd_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='gui_cutter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)
