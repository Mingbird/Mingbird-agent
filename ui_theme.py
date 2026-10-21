#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mingbird UI design tokens & dual-theme engine (Tk/ttkbootstrap).

双主题对等:light/dark 两套完整令牌;ui_mode = auto(跟随系统) | light | dark。
Tokens 命名:bg/sidebar surface/elevated/text/muted/faint/primary/accent/border/sel。
v4 UI(侧边栏 + 对话 + 计划抽屉)在旧令牌之上补 side/faint/soft/track/danger/ok;
旧键全部保留,旧对话框与 ttk 主题不受影响。
"""
import os
import subprocess
import sys

try:
    import winreg
except ImportError:
    winreg = None

PRIMARY_LIGHT = "#0F8A7E"   # 鸣翠
PRIMARY_DARK = "#3FBFAF"
ACCENT = "#E8A33D"          # 冠金

THEMES = {
    "light": {
        "ttk_theme": "flatly",
        "bg": "#F7F6F2", "side": "#F1F0EA", "surface": "#FFFFFF",
        "card": "#FFFFFF", "elevated": "#EFEDE8",
        "text": "#1E2226", "muted": "#6F767D", "faint": "#9AA0A6",
        "primary": PRIMARY_LIGHT, "primary_hover": "#0C786D",
        "primary_text": "#FFFFFF",
        "accent": ACCENT, "border": "#E4E2DA", "sel": "#DDEEEB",
        "soft": "#E1F0EC", "track": "#E4E2DA",
        "user_bubble": "#E6F1EE", "user": "#E6F1EE",
        "code_bg": "#F2F1EC",
        "danger": "#C4554D", "danger_fill": "#C4554D", "ok": "#2E9E6B",
        "warn": "#B7791F",
    },
    "dark": {
        "ttk_theme": "darkly",
        "bg": "#141619", "side": "#0E1012", "surface": "#1B1E22",
        "card": "#1F2327", "elevated": "#22262B",
        "text": "#E8EBEE", "muted": "#98A0A8", "faint": "#6F777F",
        "primary": PRIMARY_DARK, "primary_hover": "#55D0C0",
        "primary_text": "#0E1512",
        "accent": "#E8B15C", "border": "#2A2F35", "sel": "#204441",
        "soft": "#1B3A36", "track": "#2A2F35",
        "user_bubble": "#1D3A35", "user": "#1D3A35",
        "code_bg": "#24282D",
        "danger": "#E07A72", "danger_fill": "#B3403A", "ok": "#4CC38A",
        "warn": "#E8B15C",
    },
}


def system_prefers_dark():
    """跟随系统:Windows 读注册表;macOS 问 defaults;Linux 问 gsettings。
    读不到时保守回到深色(旧行为),不影响显式 light/dark 选择。"""
    if sys.platform == "darwin":
        try:
            r = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                               capture_output=True, timeout=2)
            return r.returncode == 0 and b"Dark" in r.stdout
        except Exception:
            return True
    if sys.platform.startswith("linux"):
        try:
            r = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                capture_output=True, timeout=2)
            out = (r.stdout or b"").lower()
            if b"dark" in out:
                return True
            if b"default" in out or b"light" in out:
                return False
        except Exception:
            pass
        return True
    if winreg is None:
        return True
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        v, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
        return v == 0
    except Exception:
        return True


def resolve_theme_mode(ui_mode):
    """ui_mode: auto | light | dark -> 'light' | 'dark'"""
    if ui_mode == "auto":
        return "dark" if system_prefers_dark() else "light"
    return "dark" if ui_mode == "dark" else "light"


def tokens(mode):
    return THEMES.get(mode, THEMES["dark"])


def apply_tokens(style, root, tk_mod, mode, widgets=None):
    """把令牌刷到 ttkbootstrap Style 与关键裸控件上。widgets: [(widget, kind), ...]"""
    t = tokens(mode)
    try:
        style.theme_use(t["ttk_theme"])
    except Exception:
        pass
    root.configure(bg=t["bg"])
    try:
        style.configure(".", background=t["surface"], foreground=t["text"])
        style.configure("TFrame", background=t["surface"])
        style.configure("TLabel", background=t["surface"], foreground=t["text"])
        style.configure("card.TFrame", background=t["bg"])
        style.configure("rail.TFrame", background=t["side"])
        style.configure("rail.TLabel", background=t["side"], foreground=t["text"])
        style.configure("secondary.TLabel", background=t["surface"], foreground=t["muted"])
        style.configure("status.TFrame", background=t["side"])
    except Exception:
        pass
    # 裸 Tk 控件逐个上色
    for w, kind in (widgets or []):
        try:
            if not w.winfo_exists():
                continue
        except Exception:
            continue
        try:
            if kind == "text":
                w.configure(bg=t["bg"], fg=t["text"],
                            insertbackground=t["text"])
            elif kind == "code":
                w.configure(bg=t["code_bg"], fg=t["text"],
                            insertbackground=t["text"])
            elif kind == "list":
                w.configure(bg=t["surface"], fg=t["text"],
                            selectbackground=t["sel"],
                            selectforeground=t["text"])
            elif kind == "card":
                w.configure(bg=t["bg"])
            elif kind == "entry":
                w.configure(bg=t["surface"], fg=t["text"],
                            insertbackground=t["text"])
        except Exception:
            pass
    return t
