# -*- coding: utf-8 -*-
"""发版后生成 winget 安装清单:从 dist/ 取两个安装包的真实 SHA-256 填进模板。
用法: python scripts/make_winget_manifest.py
产物: packaging/winget/manifests/Mingbird.Mingbird.installer-v<版本>.yaml
提交 winget-pkgs(人工):fork microsoft/winget-pkgs →
  manifest/m/Mingbird/Mingbird/<版本>/ 放拆分后的 installer/locale/version
  清单 → PR 等审核。winget install 路径不走浏览器 MOTW,SmartScreen 无感。"""
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMPL = os.path.join(ROOT, "packaging", "winget", "Mingbird.yaml.template")
OUT_DIR = os.path.join(ROOT, "packaging", "winget", "manifests")


def sha256_upper(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def main():
    ver = open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip().lstrip("v")
    cn = os.path.join(ROOT, "dist", f"Mingbird-v{ver}-CN-Setup.exe")
    en = os.path.join(ROOT, "dist", f"Mingbird-v{ver}-EN-Setup.exe")
    for p in (cn, en):
        if not os.path.exists(p):
            sys.exit(f"缺安装包: {p}(先跑 PyInstaller + ISCC 打包)")
    tpl = open(TMPL, encoding="utf-8").read()
    out = (tpl.replace("{{VERSION}}", ver)
              .replace("{{CN_SHA256}}", sha256_upper(cn))
              .replace("{{EN_SHA256}}", sha256_upper(en)))
    os.makedirs(OUT_DIR, exist_ok=True)
    dst = os.path.join(OUT_DIR, f"Mingbird.Mingbird.installer-v{ver}.yaml")
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    print("已生成", dst)


if __name__ == "__main__":
    main()
