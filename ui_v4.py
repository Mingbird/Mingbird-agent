# -*- coding: utf-8 -*-
"""Mingbird v4 UI primitives (Tk).

Small, dependency-light widgets used by the redesigned desktop shell:
- Pill        rounded flat button (Pillow-drawn background, hover state)
- Icon        flat icon/text button with hover tint
- CtxBar      thin context-usage bar
- ellipsize   width-aware text truncation

Colours always come from ui_theme tokens; no hardcoded palette here.
"""
import tkinter as tk
from tkinter import font as tkfont

try:
    from PIL import Image, ImageDraw, ImageTk
    HAVE_PIL = True
except Exception:          # pragma: no cover - Pillow is a hard dep, but stay safe
    HAVE_PIL = False

# 字体族按平台解析(init_fonts 在 root 就绪后从已安装字体里挑第一个可用的)。
# 直接写死 "Microsoft YaHei UI" 会让 macOS/Linux 落到默认字体,CJK 变方框或发虚。
UI_FAMILY = "Microsoft YaHei UI"
DISPLAY_FAMILY = "Segoe UI"
EMOJI_FAMILY = "Segoe UI Emoji"
MONO_FAMILY = "Consolas"

_UI_CANDIDATES = ("Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC",
                  "Source Han Sans SC", "WenQuanYi Micro Hei", "Arial Unicode MS")
_DISPLAY_CANDIDATES = ("Segoe UI", "Helvetica Neue", "SF Pro Text",
                       "Noto Sans", "DejaVu Sans")
_EMOJI_CANDIDATES = ("Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji",
                     "Segoe UI Symbol")
_MONO_CANDIDATES = ("Consolas", "Menlo", "SF Mono", "DejaVu Sans Mono",
                    "Liberation Mono", "Courier New")

# v4.1 字号整体上调一档:8/9/10 在 2K 屏上偏小,正文改为 12pt。
FONT = (UI_FAMILY, 12)
FONT_SM = (UI_FAMILY, 11)
FONT_XS = (UI_FAMILY, 10)
FONT_BOLD = (UI_FAMILY, 12, "bold")
FONT_TITLE = (UI_FAMILY, 16, "bold")
FONT_BRAND = (UI_FAMILY, 14, "bold")
MONO = (MONO_FAMILY, 11)
MONO_SM = (MONO_FAMILY, 10)


def init_fonts(root):
    """Pick installed font families per platform and refresh the font tuples.

    Must run once after the Tk root exists and before widgets are built.
    """
    global UI_FAMILY, DISPLAY_FAMILY, EMOJI_FAMILY, MONO_FAMILY
    global FONT, FONT_SM, FONT_XS, FONT_BOLD, FONT_TITLE, FONT_BRAND
    global MONO, MONO_SM
    try:
        installed = set(tkfont.families(root))
    except Exception:
        installed = set()

    def pick(cands):
        for c in cands:
            if c in installed:
                return c
        return cands[0]

    UI_FAMILY = pick(_UI_CANDIDATES)
    DISPLAY_FAMILY = pick(_DISPLAY_CANDIDATES)
    EMOJI_FAMILY = pick(_EMOJI_CANDIDATES)
    MONO_FAMILY = pick(_MONO_CANDIDATES)
    FONT = (UI_FAMILY, 12)
    FONT_SM = (UI_FAMILY, 11)
    FONT_XS = (UI_FAMILY, 10)
    FONT_BOLD = (UI_FAMILY, 12, "bold")
    FONT_TITLE = (UI_FAMILY, 16, "bold")
    FONT_BRAND = (UI_FAMILY, 14, "bold")
    MONO = (MONO_FAMILY, 11)
    MONO_SM = (MONO_FAMILY, 10)

# DPI 标尺:窗口与布局单位是物理像素,字体按点缩放;200% 缩放下固定像素
# 尺寸只剩一半视觉宽度。set_scale() 在启动时按实际 DPI 设置一次。
_S = 1.0


def set_scale(s):
    global _S
    try:
        _S = max(1.0, float(s))
    except Exception:
        _S = 1.0


def px(n):
    return int(round(n * _S))

_IMG_CACHE = {}


def _rr_img(w, h, r, fill, bg):
    """Antialiased rounded rectangle as a Tk image (cached)."""
    w, h, r = max(1, int(w)), max(1, int(h)), max(0, int(r))
    key = (w, h, r, fill, bg)
    img = _IMG_CACHE.get(key)
    if img is not None:
        return img
    if not HAVE_PIL:
        return None
    s = 4
    im = Image.new("RGB", (w * s, h * s), bg)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w * s - 1, h * s - 1], radius=r * s, fill=fill)
    img = ImageTk.PhotoImage(im.resize((w, h), Image.LANCZOS))
    if len(_IMG_CACHE) > 500:
        _IMG_CACHE.clear()
    _IMG_CACHE[key] = img
    return img


def _circle_img(d, fill, bg):
    return _rr_img(d, d, d // 2, fill, bg)


def card_img(w, h, r, fill, outline, bg):
    """Rounded card with a 1px outline (composer/plan surfaces)."""
    w, h, r = max(2, int(w)), max(2, int(h)), max(0, int(r))
    key = (w, h, r, fill, outline, bg)
    img = _IMG_CACHE.get(key)
    if img is not None:
        return img
    if not HAVE_PIL:
        return None
    s = 4
    im = Image.new("RGB", (w * s, h * s), bg)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w * s - 1, h * s - 1], radius=r * s,
                        fill=fill, outline=outline, width=s)
    img = ImageTk.PhotoImage(im.resize((w, h), Image.LANCZOS))
    if len(_IMG_CACHE) > 500:
        _IMG_CACHE.clear()
    _IMG_CACHE[key] = img
    return img


def check_img(size, fill, outline, bg, on):
    """Rounded checkbox: filled primary + white tick when on, hairline when off."""
    size = max(10, int(size))
    key = (size, fill, outline, bg, bool(on))
    img = _IMG_CACHE.get(key)
    if img is not None:
        return img
    if not HAVE_PIL:
        return None
    s = 4
    px = size * s
    im = Image.new("RGB", (px, px), bg)
    d = ImageDraw.Draw(im)
    r = int(px * 0.28)
    if on:
        d.rounded_rectangle([0, 0, px - 1, px - 1], radius=r, fill=fill)
        d.line([(px * 0.24, px * 0.52), (px * 0.43, px * 0.72),
                (px * 0.77, px * 0.30)], fill="#FFFFFF",
               width=max(2, int(px * 0.10)), joint="curve")
    else:
        d.rounded_rectangle([0, 0, px - 1, px - 1], radius=r, fill=bg,
                            outline=outline, width=max(1, int(px * 0.06)))
    out = ImageTk.PhotoImage(im.resize((size, size), Image.LANCZOS))
    if len(_IMG_CACHE) > 500:
        _IMG_CACHE.clear()
    _IMG_CACHE[key] = out
    return out


def ellipsize(text, max_px, font):
    """Truncate text with an ellipsis so it fits max_px at the given font."""
    text = str(text or "")
    if max_px <= 0:
        return ""
    f = tkfont.Font(font=font)
    if f.measure(text) <= max_px:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if f.measure(text[:mid] + "…") <= max_px:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + "…"


class Pill(tk.Label):
    """Rounded flat button.

    kind: primary | surface | soft | ghost | danger
    """

    def __init__(self, master, text, command, t, kind="ghost", h=32,
                 padx=14, font=None, radius=9, width=None):
        font = font or FONT_SM
        self.t = t
        self.command = command
        self.kind = kind
        h, padx, radius = px(h), px(padx), px(radius)
        if width:
            width = px(width)
        self._h = h
        self._padx = padx
        self._font = font
        self._radius = radius
        self._fixed_w = width
        self._enabled = True
        self._text = str(text)
        self._normal_img = None
        self._hover_img = None
        self._hover = False
        super().__init__(master, text=self._text, bd=0,
                         bg=master.cget("bg"), fg=t["text"],
                         font=font, cursor="hand2", compound="center",
                         padx=0, pady=0, takefocus=0)
        self._render()
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda e: self._paint(True))
        self.bind("<Leave>", lambda e: self._paint(False))

    # -- palette ---------------------------------------------------------
    def _colors(self, hover=False):
        t = self.t
        if not self._enabled:
            return t["track"], t["faint"]
        if self.kind == "primary":
            return (t["primary_hover"] if hover else t["primary"]), t["primary_text"]
        if self.kind == "soft":
            return t["soft"], t["primary"]
        if self.kind == "surface":
            return (t["soft"] if hover else t["surface"]), t["text"]
        if self.kind == "danger":
            return t["danger_fill"], "#FFFFFF"
        # ghost
        return (t["soft"] if hover else self.master.cget("bg")), \
               (t["primary"] if hover else t["muted"])

    def _width(self):
        if self._fixed_w:
            return self._fixed_w
        f = tkfont.Font(font=self._font)
        return f.measure(self._text) + self._padx * 2

    def _build(self, fill, bg):
        return _rr_img(self._width(), self._h, self._radius, fill, bg)

    def _render(self):
        bg = self.master.cget("bg")
        fill, fg = self._colors(False)
        self._normal_img = self._build(fill, bg)
        self._hover_img = self._build(self._colors(True)[0], bg)
        self.configure(image=self._normal_img, bg=bg, fg=fg,
                       text=self._text,
                       cursor="hand2" if self._enabled else "arrow")

    def _paint(self, hover):
        if not self._enabled:
            return
        self._hover = hover
        bg = self.master.cget("bg")
        fill, fg = self._colors(hover)
        # hover image must match the current text/theme; rebuild cheaply (cached)
        img = self._build(fill, bg)
        if hover:
            self._hover_img = img
        else:
            self._normal_img = img
        self.configure(image=img, fg=fg)

    def _click(self, _e=None):
        if self._enabled and self.command:
            self.command()

    # -- public API ------------------------------------------------------
    def set_text(self, text):
        text = str(text)
        if text != self._text:
            self._text = text
            self._render()

    def set_kind(self, kind):
        if kind != self.kind:
            self.kind = kind
            self._render()

    def set_enabled(self, on):
        on = bool(on)
        if on != self._enabled:
            self._enabled = on
            self._render()

    def apply_theme(self, t):
        self.t = t
        self._render()


class Icon(tk.Label):
    """Flat icon/text button with hover tint."""

    def __init__(self, master, glyph, command, t, fg_key="muted",
                 font=None, padx=6, pady=3):
        font = font or FONT_SM
        self.t = t
        self.command = command
        self._fg_key = fg_key
        self._padx = px(padx)
        self._pady = px(pady)
        super().__init__(master, text=glyph, bd=0, bg=master.cget("bg"),
                         fg=t[fg_key], font=font, cursor="hand2",
                         padx=self._padx, pady=self._pady, takefocus=0)
        self.bind("<Button-1>", lambda e: self.command and self.command())
        self.bind("<Enter>", lambda e: self.configure(bg=t["soft"], fg=t["primary"]))
        self.bind("<Leave>", lambda e: self.configure(bg=master.cget("bg"),
                                                      fg=self.t[self._fg_key]))

    def apply_theme(self, t):
        self.t = t
        self.configure(bg=self.master.cget("bg"), fg=t[self._fg_key])


class Check(tk.Frame):
    """Minimal checkbox: rounded box + label, no native bevel.

    Keeps the tk.BooleanVar contract (`get()`/`set()`), so call sites and
    prefs round-trips are unchanged.
    """

    def __init__(self, master, text, variable, t, font=None, box=16,
                 command=None):
        font = font or FONT_SM
        self.t = t
        self.variable = variable
        self._box = px(box)
        self._font = font
        self._command = command
        self._img = None
        super().__init__(master, bg=master.cget("bg"), bd=0,
                         highlightthickness=0, cursor="hand2")
        self._mark = tk.Label(self, bg=master.cget("bg"), bd=0,
                              cursor="hand2", padx=0, pady=0)
        self._mark.pack(side="left")
        self._txt = tk.Label(self, text=str(text), bg=master.cget("bg"),
                             fg=t["muted"], font=font, cursor="hand2",
                             bd=0, padx=0, pady=0)
        self._txt.pack(side="left", padx=(px(7), 0))
        self._render()
        for w in (self, self._mark, self._txt):
            w.bind("<Button-1>", self._toggle)
        self._txt.bind("<Enter>", lambda e: self._txt.configure(fg=t["text"]))
        self._txt.bind("<Leave>", lambda e: self._txt.configure(fg=t["muted"]))
        try:
            self.variable.trace_add("write", lambda *a: self._render())
        except Exception:
            pass

    def _render(self):
        bg = self.master.cget("bg")
        self.configure(bg=bg)
        self._mark.configure(bg=bg)
        self._txt.configure(bg=bg)
        self._img = check_img(self._box, self.t["primary"], self.t["border"],
                              bg, bool(self.variable.get()))
        if self._img is not None:
            self._mark.configure(image=self._img)

    def _toggle(self, _e=None):
        self.variable.set(not bool(self.variable.get()))
        if self._command:
            self._command()

    def set_text(self, text):
        self._txt.configure(text=str(text))

    def apply_theme(self, t):
        self.t = t
        self._txt.configure(fg=t["muted"])
        self._render()


class CtxBar(tk.Frame):
    """Thin progress bar for context usage."""

    def __init__(self, master, t):
        super().__init__(master, bg=t["bg"], height=px(3))
        self._fill = tk.Frame(self, bg=t["primary"], height=px(3))
        self._fill.place(x=0, y=0, relwidth=0, relheight=1)

    def set(self, pct):
        try:
            v = max(0.0, min(float(pct), 100.0)) / 100.0
        except Exception:
            v = 0.0
        try:
            self._fill.place_configure(relwidth=v)
        except Exception:
            pass

    def apply_theme(self, t):
        self.configure(bg=t["bg"])
        self._fill.configure(bg=t["primary"])
