#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mingbird UI design tokens & dual-theme engine (Tk/ttkbootstrap).

双主题对等:light/dark 两套完整令牌;ui_mode = auto(跟随系统) | light | dark。
Tokens 命名:bg/surface/elevated/text/muted/primary/accent/border/sel。
"""
import os

try:
    import winreg
except ImportError:
    winreg = None

PRIMARY_LIGHT = "#0F8A7E"   # 鸣翠
PRIMARY_DARK = "#1FA396"
ACCENT = "#F2A93B"          # 冠金

THEMES = {
    "light": {
        "ttk_theme": "flatly", "bg": "#F6F5F2", "surface": "#FFFFFF",
        "elevated": "#EFEDE8", "text": "#23282C", "muted": "#7A838B",
        "primary": PRIMARY_LIGHT, "primary_text": "#FFFFFF",
        "accent": ACCENT, "border": "#DCD8D0", "sel": "#DDEEEB",
        "user_bubble": "#E4F1EF", "code_bg": "#F0EFEB",
    },
    "dark": {
        "ttk_theme": "darkly", "bg": "#1E2226", "surface": "#262B31",
        "elevated": "#2E343B", "text": "#E8EAED", "muted": "#98A2AB",
        "primary": PRIMARY_DARK, "primary_text": "#0E1512",
        "accent": ACCENT, "border": "#3A4148", "sel": "#204441",
        "user_bubble": "#24403C", "code_bg": "#191D21",
    },
}


def system_prefers_dark():
    """跟随系统:读 Windows AppsUseLightTheme;非 Windows/读不到默认 dark。"""
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
        style.configure("rail.TFrame", background=t["elevated"])
        style.configure("rail.TLabel", background=t["elevated"], foreground=t["text"])
        style.configure("secondary.TLabel", background=t["surface"], foreground=t["muted"])
        style.configure("status.TFrame", background=t["elevated"])
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
