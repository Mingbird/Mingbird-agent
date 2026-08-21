#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""蜂鸟/Hummingbird 安装器:把内嵌 app 复制到 %LOCALAPPDATA%\LocalAgent,写语言标记,建桌面快捷方式。
打包: pyinstaller --onefile --add-data "dist/LocalAgent;app" installer.py --name Hummingbird-Setup
语言: 安装包名含 EN/英文 → 强制英文;含 中文 → 强制中文;否则自动。
"""
import os, sys, shutil, subprocess

def main():
    payload = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "app")
    dest = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "LocalAgent")
    # 根据安装包名判断语言
    self_name = os.path.basename(sys.argv[0] if sys.argv else "setup.exe").upper()
    if "EN" in self_name or "HUMBINGBIRD" in self_name or "ENGLISH" in self_name:
        lang = "en"; label = "Hummingbird"; lnk = "Hummingbird.lnk"
    elif "ZH" in self_name or "CN" in self_name or "中文" in self_name or "蜂鸟" in self_name:
        lang = "zh"; label = "蜂鸟"; lnk = "蜂鸟.lnk"
    else:
        lang = ""; label = "蜂鸟"; lnk = "蜂鸟.lnk"

    print(f"Installing to: {dest}  |  Language: {lang or 'auto'}")
    # 先结束正在运行的 LocalAgent,避免其占用文件导致拷贝中断成残缺安装
    subprocess.run(["taskkill", "/F", "/IM", "LocalAgent.exe"],
                   capture_output=True, shell=False)
    import time
    for _ in range(20):
        if not any(p.lower() == "localagent.exe"
                   for p in subprocess.run(["tasklist"], capture_output=True,
                                           text=True).stdout.lower().splitlines()):
            break
        time.sleep(0.3)
    if os.path.exists(dest):
        shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)
    shutil.copytree(payload, dest, dirs_exist_ok=True)
    # 语言标记:强制 GUI 界面语言
    if lang:
        with open(os.path.join(dest, "app_lang.txt"), "w", encoding="utf-8") as f:
            f.write(lang)
    exe = os.path.join(dest, "LocalAgent.exe")
    ps = ("$ws=New-Object -ComObject WScript.Shell; "
          f"$s=$ws.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\\{lnk}'); "
          f"$s.TargetPath='{exe}'; $s.WorkingDirectory='{dest}'; $s.IconLocation='{exe},0'; $s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True)
    print(f"Done! Desktop shortcut \"{label}\" created.")
    print("Prerequisite: Ollama installed & running, with local models pulled.")
    docs = os.path.join(dest, "_internal", "AGENTS.md")
    print("Docs:", docs if os.path.exists(docs) else os.path.join(dest, "AGENTS.md"))
    input("Press Enter to exit...")

if __name__ == "__main__":
    main()
