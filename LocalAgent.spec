# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas += collect_data_files('tkinterdnd2')
datas = [('skills', 'skills'), ('AGENTS.md', '.'), ('README.md', '.'), ('README_EN.md', '.'), ('RELEASE_NOTES.md', '.'), ('LICENSE', '.'), ('VERSION', '.'), ('CHANGELOG.md', '.'),
         ('stt', 'stt'), ('app.ico', '.')]
datas += collect_data_files('ttkbootstrap')


a = Analysis(
    ['agent_gui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['ttkbootstrap', 'tkinterdnd2', 'sounddevice', 'soundfile', 'sherpa_onnx', 'numpy', 'requests', 'bs4'],
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
    name='LocalAgent',
    icon='app.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name='LocalAgent',
)
