# -*- mode: python ; coding: utf-8 -*-
# Onedir build used for packaging the Linux AppImage.

import os
from PyInstaller.utils.hooks import collect_all

dnd_datas, dnd_binaries, dnd_hiddenimports = collect_all('tkinterdnd2')

a = Analysis(
    ['gui_cutter.py'],
    pathex=[],
    binaries=dnd_binaries,
    datas=dnd_datas + [(os.path.join('resource', name), 'resource') for name in ('Icon.png', 'Icon.ico')],
    hiddenimports=dnd_hiddenimports + ['PIL._tkinter_finder'],
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
    [],
    exclude_binaries=True,
    name='gui_cutter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='gui_cutter',
)
