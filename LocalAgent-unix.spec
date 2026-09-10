# -*- mode: python ; coding: utf-8 -*-
# Unix (macOS / Linux) PyInstaller spec for Mingbird.
from PyInstaller.utils.hooks import collect_data_files

datas += collect_data_files('tkinterdnd2')
datas = [('skills', 'skills'), ('AGENTS.md', '.'), ('README.md', '.'),
         ('LICENSE', '.'), ('VERSION', '.'), ('CHANGELOG.md', '.'),
         ('stt', 'stt'), ('app.png', '.'),
         ('app_lang_en.txt', '.'), ('app_lang_zh.txt', '.'),
         ('mcp_utils_server.py', '.')]
datas += collect_data_files('ttkbootstrap')

a = Analysis(
    ['agent_gui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['PIL._tkinter_finder', 'ttkbootstrap', 'sounddevice',
                   'soundfile', 'sherpa_onnx', 'numpy', 'requests', 'bs4'],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='LocalAgent',
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               name='LocalAgent')
