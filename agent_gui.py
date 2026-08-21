#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蜂鸟 · 本地 AI 助手 — Windows 桌面 GUI v4(现代化)
基于 ttkbootstrap 的聊天工作区设计:
- 侧边栏:附件 / 会话 / 计划(todo)
- 主区:💬 对话(聊天气泡视图) + 🖥 日志(流式控制台)
- 📎 文件上传:复制到工作目录 _attachments/,agent 按需读取
- ⚙ 设置:上下文窗口 / 温度 / 输出上限 / 自定义系统提示(持久化)
- 🌓 主题切换(darkly / superhero / flatly / cosmo ...)
- 快捷键:Ctrl+N 新对话 · Ctrl+F 历史搜索 · Ctrl+Enter 发送 · Ctrl+L 清日志
"""
import tkinter as tk
from tkinter import ttk, filedialog
from tkinter import scrolledtext
import ttkbootstrap as tb
import subprocess, threading, os, queue, sys, re, glob, json, time, shutil
import voice_input
import appconfig   # 统一配置层:Ollama 地址/模型映射等由用户配置,不硬编码

# 冻结(exe)时用 exe 自身目录,避免 __file__ 相对 CWD 解析错导致文件找不到
if getattr(sys, "frozen", False):
    AGENT_DIR = os.path.dirname(sys.executable)
else:
    AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_PY  = os.path.join(AGENT_DIR, "ollama_agent.py")
# ============ 国际化:自动检测语言(OS 中文→中文,否则英文),可用 AGENT_LANG 强制 ============
_LANG = os.environ.get("AGENT_LANG", "")
if not _LANG:
    try:
        _LANG = "zh" if (os.environ.get("LANG", "") or "").startswith("zh") or \
                       "Chinese" in os.environ.get("LANGUAGE", "") else "en"
    except Exception:
        _LANG = "en"
# 安装器强制语言(app_lang.txt 在 exe 旁)
try:
    _al = os.path.join(AGENT_DIR, "app_lang.txt")
    if os.path.exists(_al):
        _LANG = open(_al, encoding="utf-8").read().strip()[:2]
except Exception:
    pass

_T = {
    "蜂鸟 · 本地 AI 助手": "Hummingbird · Local AI Assistant",
    "模型:": "Model:", "会话:无": "Session: none", "目录:": "Dir:",
    "关闭思考": "Thinking OFF", "⚙ 设置": "⚙ Settings", "🌓 主题": "🌓 Theme",
    "＋ 新对话": "＋ New Chat", "添加附件": "Attachments", "清空": "Clear",
    "会话": "Sessions", "计划": "Plan", "💬 对话": "💬 Chat", "🖥 日志": "🖥 Logs",
    "发送": "Send", "🎤 语音": "🎤 Voice", "🎤 无音频": "🎤 No Audio", "■ 停止录音": "■ Stop",
    "上下文窗口:": "Context:", "温度:": "Temp:", "输出上限:": "Max out:",
    "自定义系统提示": "Custom system prompt", "启用": "Enable",
    "本地 agent 可用技能(渐进式:用到才加载全文)": "Available skills (loaded on demand)",
    "关键词:": "Keyword:", "搜索": "Search", "附件:": "Attachments:",
    "本地 AI 助手": "Local AI Assistant",
    "ℹ 关于": "ℹ About", "版本": "Version", "许可": "License",
    "项目文档": "Docs", "打开安装目录": "Open install dir",
    "关闭": "Close", "欢迎使用": "Welcome",
    "未能自动启动 Ollama,请手动运行 ollama serve 后再试。": "Could not start Ollama automatically. Please run `ollama serve` manually and try again.",
    "全离线·小模型优先的本地 AI agent": "Local-first, small-model-first AI agent",
    "输入任务或对话,Ctrl+Enter 发送。可以直接说:": "Type a task or chat — Ctrl+Enter to send. Try:",
    "· 用中文回答我,别客气": "· Answer in plain language",
    "· 在某个目录里写个 Python 程序并跑测试": "· Write a Python program in a folder and run its tests",
    "· 帮我查资料、整理成报告": "· Research a topic and summarize it into a report",
    "· 管理本地文件,整理照片": "· Manage local files / organize photos",
    "模型可在上方切换;工具栏可开关思考过程、切主题。": "Switch model above; toggle thinking & theme in the toolbar.",
    "浏览": "Browse", "打开": "Open",
    "历史搜索": "Search", "技能列表": "Skills",
    "添加": "Add", "载入": "Load", "回放": "Replay",
    "停止": "Stop", "续跑": "Resume", "清空对话": "Clear chat",
    "清空输出": "Clear output", "保存": "Save",
    "查看对话": "View conversation", "恢复此会话": "Restore session",
    "输入任务或对话…(Ctrl+Enter 发送)": "Type a task or chat… (Ctrl+Enter to send)",
    " 上下文: - / - ( - % )": "  Ctx: - / - ( - % )",
    " 上下文: {pt} / {total} ({pct}%)": "  Ctx: {pt} / {total} ({pct}%)",
    "会话:": "Session: ",
    "(会话 {name} 无内容)": "(Session {name} is empty)",
    "继续之前的对话,完成或回答当前需求。": "Continue the previous conversation and finish the current request.",
    "会话历史搜索": "Session search",
    "(输入关键词再搜索)": "(type a keyword to search)",
    "会话回放: {name}": "Session replay: {name}",
    "会话 {name} — 完整对话记录(Ctrl+F 搜索)": "Session {name} — full transcript (Ctrl+F to search)",
    "(读取失败)": "(read failed)",
    "启用自定义系统提示(替代内置,可大幅改造行为)": "Enable custom system prompt (replaces the built-in one)",
    "转写中…": "Transcribing…",
    "未捕捉到声音,请重试": "No voice captured, please retry",
    "[忙:任务运行中,先停止再语音输入]": "[Busy: a task is running, stop it before voice input]",
    "[录音中… 说完话自动停止]": "[Recording… auto-stops when you finish speaking]",
    "[录音启动失败: {e}]": "[Recording failed to start: {e}]",
    "[录音超时,自动停止]": "[Recording timed out, stopped]",
    "转写失败: ": "Transcription failed: ",
    "[语音已转录({stt})并填入输入框]": "[Transcribed ({stt}) and filled into the input]",
    "[语音转录无结果:{stt} 转写能力有限,可换用更强音频模型]": "[No result from {stt}. Limited STT — try a stronger audio model]",
    "[已清除旧进度]": "[Old progress cleared]",
    "[已停止,重跑并勾选'续跑'可从中断处继续]": "[Stopped. Rerun with 'Resume' checked to continue from the breakpoint]",
    "[已停止 — 重跑勾选'续跑'可从中断处继续]": "[Stopped — rerun with 'Resume' to continue from the breakpoint]",
    "Ollama ✓(无模型)": "Ollama ✓ (no models)",
    "Ollama ✗ 未启动": "Ollama ✗ not running",
    "[Ollama 已启动]": "[Ollama started]",
    "(暂无技能)": "(no skills)",
    "(尚无计划 — agent 会先建 todo 再执行)": "(No plan yet — the agent will create a todo list first)",
    "蜂鸟 · 本地 AI 助手 错误": "Hummingbird · Local AI Assistant Error",
    "未能自动启动 ollama,请先手动运行 ollama serve。": "Could not start Ollama automatically. Run `ollama serve` manually first.",
    "开始: ": "Started: ",
    "🤔 思考中…": "🤔 thinking…",
    "🤔 思考过程 ({n} 字) — 点击展开/折叠": "🤔 thinking ({n} chars) — click to expand/collapse",
    "🤔 思考过程 ({n} 字) — 点击折叠": "🤔 thinking ({n} chars) — click to collapse",
    "🤔 思考过程 · {n} 字": "🤔 thinking · {n} chars",
    "查看": "View",
    "计划 (todo)": "Plan (todo)",
}
def _t(s):
    if _LANG == "zh":
        return s
    return _T.get(s, s)
DEFAULT_TASKS = os.path.join(os.path.expanduser("~"), "agent_tasks")
# 全局异常日志:任何未捕获异常写入文件,便于定位打包后报错
_ERR_LOG = os.path.join(os.path.expanduser("~/.ollama_agent"), "gui_error.log")
def _log_exc(exc_type, exc, tb):
    try:
        with open(_ERR_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[{time.strftime('%H:%M:%S')}] {exc_type.__name__}: {exc}\n")
            import traceback; f.write("".join(traceback.format_tb(tb)))
    except Exception:
        pass
    if exc_type is not SystemExit:
        try:
            import tkinter.messagebox as _mb
            _mb.showerror(_t("蜂鸟 · 本地 AI 助手 错误"), f"{exc_type.__name__}: {exc}\n(详情见 {_ERR_LOG})")
        except Exception:
            pass
sys.excepthook = _log_exc
if __name__ == "__main__":
    # 打包后进程内 Tk 回调异常也记录(避免只弹窗无日志)
    import tkinter as _tk
    _tk.Tk.report_callback_exception = staticmethod(_log_exc)

AGENT_HOME = os.path.expanduser("~/.ollama_agent")
SESSION_DIR = os.path.join(AGENT_HOME, "sessions")
SKILL_DIRS = [os.path.join(AGENT_DIR, "skills"),
              os.path.join(AGENT_HOME, "skills")]
PREFS_FILE = os.path.join(AGENT_HOME, "gui_prefs.json")
SYS_OVERRIDE_FILE = os.path.join(AGENT_HOME, "system_override.txt")
THEMES = ["minty-light", "pulse-dark", "tokyo-night-dark", "dracula-dark",
          "pulse-light", "sandstone-light", "solarized-light"]

def _c(style, key, fallback=None):
    try:
        v = getattr(style.colors, key, None)
        return v if v is not None else (fallback or "#222222")
    except Exception:
        return fallback or "#222222"

# ============ 现代极简主题(温暖单色,编辑式排版) ============
# 原则:暖米白底、炭灰文字、仅一处语义点缀色、细边框、无渐变/阴影
MINIMAL = {
    "name": "minimal_light",
    "bg": "#F7F6F3",          # 暖米白画布
    "fg": "#2F3437",          # 炭灰正文
    "muted": "#787774",       # 次级灰
    "border": "#E6E4DF",      # 超浅结构线
    "card": "#FFFFFF",        # 卡片面
    "primary": "#346538",     # 点缀:褪色绿(主操作)
    "info": "#1F6C9F",        # 点缀:褪色蓝(信息)
    "warn": "#956400",        # 点缀:褪色黄(警告)
    "danger": "#9F2F2D",      # 点缀:褪色红(危险)
    "font_title": ("Microsoft YaHei UI", 12, "bold"),
    "font_body": ("Microsoft YaHei UI", 10),
    "font_small": ("Microsoft YaHei UI", 9),
    "font_mono": ("Consolas", 9),
}

def build_minimal_theme(root):
    """把 ttkbootstrap 主题改造成温暖极简配色。"""
    st = root.style
    # ttkbootstrap 2.0 主题 minty-light(清爽浅色),在其上覆盖暖色
    try:
        st.theme_use("minty-light")
    except Exception:
        st.theme_use("flatly")
    c = st.colors
    for attr, val in [("bg", MINIMAL["bg"]), ("fg", MINIMAL["fg"]),
                      ("selectbg", MINIMAL["primary"]), ("selectfg", "#FFFFFF"),
                      ("border", MINIMAL["border"]), ("inputbg", "#FFFFFF"),
                      ("inputfg", MINIMAL["fg"]), ("primary", MINIMAL["primary"]),
                      ("info", MINIMAL["info"]), ("warning", MINIMAL["warn"]),
                      ("danger", MINIMAL["danger"]), ("success", MINIMAL["primary"])]:
        try: setattr(c, attr, val)
        except Exception: pass
    # 按钮:主按钮实心炭黑(极简 CTA),次级按钮白底细边
    st.configure("TButton", font=MINIMAL["font_body"], padding=(14, 7),
                 borderwidth=1, relief="flat")
    st.configure("Accent.TButton", background=MINIMAL["primary"],
                 foreground="#FFFFFF", bordercolor=MINIMAL["primary"])
    st.configure("Secondary.TButton", background=MINIMAL["card"],
                 foreground=MINIMAL["fg"], bordercolor=MINIMAL["border"])
    st.configure("TLabel", background=MINIMAL["bg"], foreground=MINIMAL["fg"],
                 font=MINIMAL["font_body"])
    st.configure("TFrame", background=MINIMAL["bg"])
    st.configure("TLabelframe", background=MINIMAL["bg"], bordercolor=MINIMAL["border"])
    st.configure("TLabelframe.Label", background=MINIMAL["bg"],
                 foreground=MINIMAL["muted"], font=MINIMAL["font_small"])
    st.configure("TNotebook", background=MINIMAL["bg"], bordercolor=MINIMAL["border"])
    st.configure("TNotebook.Tab", font=MINIMAL["font_body"], padding=(16, 7))
    st.configure("TCheckbutton", background=MINIMAL["bg"], foreground=MINIMAL["fg"],
                 font=MINIMAL["font_small"])
    st.configure("TEntry", fieldbackground="#FFFFFF", foreground=MINIMAL["fg"],
                 bordercolor=MINIMAL["border"], insertcolor=MINIMAL["fg"])
    st.configure("TCombobox", fieldbackground="#FFFFFF", foreground=MINIMAL["fg"])
    st.configure("TProgressbar", background=MINIMAL["primary"], troughcolor=MINIMAL["border"])
    st.configure("TSeparator", background=MINIMAL["border"])
    return st

class AgentGUI:
    def app_version(self):
        """读取 VERSION 文件显示真实版本号(源码/PyInstaller 打包均可)。"""
        for base in (AGENT_DIR, os.path.join(AGENT_DIR, "_internal"),
                     getattr(sys, "_MEIPASS", "")):
            p = os.path.join(base, "VERSION")
            if p and os.path.exists(p):
                try:
                    v = open(p, encoding="utf-8").read().strip()
                    if v: return v
                except Exception:
                    pass
        return "v0.6.0"

    def refresh_models(self):
        """从 ollama 动态读取已安装模型,构建 显示名→tag 映射。
        用户可在 config.json 的 models 字段给模型起友好名;未配置的模型直接用原始 tag。
        不硬编码任何模型名——每个用户按自己机器上的模型配置。"""
        m = {}
        cfg_display = appconfig.model_map()          # {显示名: tag}
        tag_to_display = {v: k for k, v in cfg_display.items()}
        tags = []
        try:
            import urllib.request as _ur
            r = json.loads(_ur.urlopen(f"{appconfig.ollama_host()}/api/tags", timeout=3).read())
            tags = [x.get("name") for x in r.get("models", [])]
        except Exception:
            tags = list(cfg_display.values())        # ollama 不可达时,退回用户配置的模型
        if not tags:
            tags = list(cfg_display.values())
        for t in tags:
            display = tag_to_display.get(t, t)
            m[_t(display)] = t
        self._model_map = m
        try:
            self.model_cb["values"] = list(m)
            if self.model_var.get() not in m and m:
                self.model_var.set(list(m)[0])
        except Exception:
            pass
        return m

    def __init__(self, root):
        self.root = root
        self.style = build_minimal_theme(root)   # 现代极简主题
        self.prefs = self.load_prefs()
        self.proc = None
        self.q = queue.Queue()
        self.session = None
        self.attachments = []      # 已复制的附件绝对路径
        self._rendered_session = None  # 当前 transcript 对应的会话名
        self._new_chat_guard = False
        self._asst_buf = ""            # 多行助手回答缓冲
        self._voice_busy = False
        self._voice_rec = None
        self._voice_stop_timer = None
        self._vad_timer = None
        # 流式思考状态
        self._think_text = ""        # 累计的思考内容
        self._think_live = False     # 思考正在流式显示
        self._think_open = False     # 思考已展开(还是折叠成标记行)
        self._streaming_asst = False # 当前助手内容是否已流式上屏(避免重复渲染)

        root.title(f"{_t('蜂鸟 · 本地 AI 助手')} — {self.app_version()}")
        # 窗口图标(原创蜂鸟,随包自带)
        try:
            _ic = os.path.join(AGENT_DIR, "app.ico")
            if os.path.exists(_ic):
                root.iconbitmap(_ic)
        except Exception:
            pass
        # 默认开足够大的窗口,保证所有功能露出(避免小窗口只显示左上角)
        try:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            w, h = min(1400, int(sw * 0.9)), min(900, int(sh * 0.9))
            root.geometry(f"{w}x{h}")
        except Exception:
            root.geometry("1200x860")
        root.minsize(980, 680)
        root.state("zoomed")   # Windows 下默认最大化

        self._build_toolbar()
        self.refresh_models()          # 动态读取 ollama 里的模型
        self._build_body()
        self._build_statusbar()

        # 快捷键
        root.bind("<Control-n>", lambda e: self.new_chat())
        root.bind("<Control-f>", lambda e: self.search_history())
        root.bind("<Control-l>", lambda e: self.clear_log())
        root.bind("<Control-i>", lambda e: self.send_chat())
        self.input.bind("<Control-Return>", lambda e: self.send_chat())
        root.bind("<F5>", lambda e: self.run_agent())

        self.apply_theme()
        self._welcome()               # 空状态欢迎语
        self.refresh_sessions()
        self.refresh_voice_state()
        self.root.after(100, self.poll)
        self.root.after(500, self.poll_todo)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ================= 偏好 =================
    def load_prefs(self):
        d = {"theme": "minty-light", "ctx": 65536, "temp": 0.0, "num_predict": 2048,
             "sys_enable": False, "sys_text": ""}
        try:
            j = json.load(open(PREFS_FILE, encoding="utf-8")); d.update(j)
        except Exception:
            pass
        return d
    def save_prefs(self):
        json.dump(self.prefs, open(PREFS_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)

    # ================= 构建界面 =================
    def _build_toolbar(self):
        bar = tb.Frame(self.root, padding=(8, 6)); bar.pack(fill="x")
        tb.Label(bar, text=_t("蜂鸟 · 本地 AI 助手"), font=MINIMAL["font_title"],
                 bootstyle="inverse-primary").pack(side="left", padx=(0, 10))
        tb.Label(bar, text=self.app_version(), bootstyle="secondary",
                 font=("Consolas", 9)).pack(side="left")
        tb.Label(bar, text=_t("模型:")).pack(side="left")
        _cfg_models = appconfig.model_map()
        self._model_map = {_t(k): v for k, v in _cfg_models.items()}   # 初始用用户配置的模型;refresh_models 会动态刷新
        _init_model = _t(next(iter(_cfg_models), ""))
        self.model_var = tk.StringVar(value=_init_model)
        self.model_cb = tb.Combobox(bar, textvariable=self.model_var,
                                    values=[_t(k) for k in _cfg_models],
                                    state="readonly", width=13, bootstyle="primary")
        self.model_cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_voice_state())
        self.model_cb.pack(side="left", padx=3)
        self.think_var = tk.BooleanVar(value=True)
        tb.Checkbutton(bar, text=_t("关闭思考"), variable=self.think_var,
                       bootstyle="round-toggle").pack(side="left", padx=6)
        tb.Button(bar, text=_t("⚙ 设置"), command=self.open_settings,
                  bootstyle="secondary-outline").pack(side="left", padx=2)
        tb.Button(bar, text=_t("🌓 主题"), command=self.cycle_theme,
                  bootstyle="secondary-outline").pack(side="left", padx=2)
        tb.Button(bar, text=_t("ℹ 关于"), command=self.show_about,
                  bootstyle="secondary-outline").pack(side="left", padx=2)
        self.sess_lbl = tb.Label(bar, text=_t("会话:无"), bootstyle="secondary")
        self.sess_lbl.pack(side="right")

        # 工作目录行
        bar2 = tb.Frame(self.root, padding=(8, 0, 8, 4)); bar2.pack(fill="x")
        tb.Label(bar2, text=_t("目录:")).pack(side="left")
        self.wd_var = tk.StringVar(value=os.path.join(DEFAULT_TASKS, "work"))
        self.wd_entry = tb.Entry(bar2, textvariable=self.wd_var)
        self.wd_entry.pack(side="left", fill="x", expand=True, padx=4)
        tb.Button(bar2, text=_t("浏览"), bootstyle="secondary",
                  command=self.choose_dir).pack(side="left")
        tb.Button(bar2, text=_t("打开"), bootstyle="secondary-outline",
                  command=self.open_dir).pack(side="left", padx=(4, 0))

    def _build_body(self):
        pw = tb.Panedwindow(self.root, orient="horizontal")
        pw.pack(fill="both", expand=True)

        # ---------- 侧边栏 ----------
        side = tb.Frame(pw, width=250); side.pack_propagate(False)
        pw.add(side, weight=0)
        side.columnconfigure(0, weight=1)

        tb.Button(side, text=_t("＋ 新对话"), bootstyle="primary",
                  command=self.new_chat).grid(row=0, column=0, sticky="ew", padx=6, pady=3)
        b2 = tb.Frame(side); b2.grid(row=1, column=0, sticky="ew", padx=6)
        tb.Button(b2, text=_t("历史搜索"), bootstyle="info-outline",
                  command=self.search_history).pack(side="left", fill="x", expand=True)
        tb.Button(b2, text=_t("技能列表"), bootstyle="info-outline",
                  command=self.show_skills).pack(side="left", padx=(4,0))

        # 附件
        att = tb.Labelframe(side, text=_t("添加附件"), padding=4)
        att.grid(row=2, column=0, sticky="ew", padx=6, pady=4)
        self.att_lb = tk.Listbox(att, height=3, font=("Consolas", 9), exportselection=False)
        self.att_lb.pack(fill="x")
        af = tb.Frame(att); af.pack(fill="x", pady=(3,0))
        tb.Button(af, text=_t("添加"), bootstyle="success-outline",
                  command=self.add_files).pack(side="left")
        tb.Button(af, text=_t("清空"), bootstyle="danger-outline",
                  command=self.clear_files).pack(side="left", padx=(4,0))

        # 会话
        se = tb.Labelframe(side, text=_t("会话"), padding=4)
        se.grid(row=3, column=0, sticky="nsew", padx=6, pady=4)
        side.rowconfigure(3, weight=1)
        self.se_lb = tk.Listbox(se, font=("Consolas", 8), exportselection=False)
        self.se_lb.pack(fill="both", expand=True)
        sf = tb.Frame(se); sf.pack(fill="x", pady=(3,0))
        tb.Button(sf, text=_t("载入"), bootstyle="primary-outline",
                  command=self.load_selected_session).pack(side="left")
        tb.Button(sf, text=_t("回放"), bootstyle="secondary-outline",
                  command=self.replay_selected_session).pack(side="left", padx=(4,0))
        self.se_lb.bind("<Double-1>", lambda e: self.load_selected_session())

        # 计划
        pl = tb.Labelframe(side, text=_t("计划 (todo)"), padding=4)
        pl.grid(row=4, column=0, sticky="ew", padx=6, pady=(0,4))
        self.plan_txt = tk.Text(pl, height=4, font=("Consolas", 8), state="disabled",
                                relief="flat", wrap="word")
        self.plan_txt.pack(fill="x")

        # ---------- 主区 ----------
        main = tb.Frame(pw); pw.add(main, weight=1)
        self.nb = tb.Notebook(main)
        self.nb.pack(fill="both", expand=True)

        # 对话页
        tab_chat = tb.Frame(self.nb, padding=6)
        self.nb.add(tab_chat, text=_t("💬 对话"))
        self.transcript = tk.Text(tab_chat, font=("Microsoft YaHei UI", 10),
                                  state="disabled", wrap="word", relief="flat",
                                  padx=10, pady=8)
        self.transcript.pack(fill="both", expand=True)
        self.input = tk.Text(tab_chat, height=3, font=("Microsoft YaHei UI", 10),
                             wrap="word", relief="solid", bd=1)
        self.input.pack(fill="x", pady=(6,4))
        self.input.insert("1.0", _t("输入任务或对话…(Ctrl+Enter 发送)"))
        crow = tb.Frame(tab_chat); crow.pack(fill="x")
        tb.Button(crow, text=_t("添加附件"), bootstyle="secondary-outline",
                  command=self.add_files).pack(side="left")
        self.send_btn = tb.Button(crow, text=_t("发送"), bootstyle="primary",
                                  command=self.send_chat); self.send_btn.pack(side="left", padx=6)
        self.mic_btn = tb.Button(crow, text=_t("🎤 语音"), bootstyle="info",
                                 command=self.voice_input, state="disabled")
        self.mic_btn.pack(side="left", padx=4)
        self.stop_btn = tb.Button(crow, text=_t("停止"), bootstyle="danger",
                                  command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        self.resume_var = tk.BooleanVar(value=True)
        tb.Checkbutton(crow, text=_t("续跑"), variable=self.resume_var).pack(side="left")
        tb.Button(crow, text=_t("清空对话"), bootstyle="secondary-outline",
                  command=self.clear_transcript).pack(side="right")

        # 日志页
        tab_log = tb.Frame(self.nb, padding=6)
        self.nb.add(tab_log, text=_t("🖥 日志"))
        self.console = tk.Text(tab_log, font=("Consolas", 9), state="disabled",
                               wrap="word", relief="flat")
        self.console.pack(fill="both", expand=True)
        lf = tb.Frame(tab_log); lf.pack(fill="x", pady=(4,0))
        tb.Button(lf, text=_t("清空输出"), bootstyle="secondary-outline",
                  command=self.clear_log).pack(side="right")

    def _build_statusbar(self):
        bar = tb.Frame(self.root, padding=(6, 3)); bar.pack(fill="x", side="bottom")
        self.ctx_bar = tb.Progressbar(bar, maximum=100, value=0, bootstyle="info-striped")
        self.ctx_bar.pack(side="left", fill="x", expand=True)
        self.status_var = tk.StringVar(value=_t(" 上下文: - / - ( - % )"))
        tb.Label(bar, textvariable=self.status_var, bootstyle="secondary",
                 width=30).pack(side="left", padx=(8, 0))
        self.ollama_lbl = tb.Label(bar, text="Ollama …", bootstyle="warning",
                                   font=("Microsoft YaHei UI", 9, "bold"),
                                   cursor="hand2")
        self.ollama_lbl.bind("<Button-1>", self._ollama_click)
        self.ollama_lbl.pack(side="right", padx=(0, 4))
        self.root.after(800, self._check_ollama)

    # ================= 目录 =================
    def choose_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.wd_var.set(d)
            self.att_lb.delete(0, "end"); self.attachments = []
    def open_dir(self):
        d = self.wd_var.get(); os.makedirs(d, exist_ok=True)
        subprocess.Popen(["explorer", os.path.normpath(d)])

    # ================= 主题 =================
    def cycle_theme(self):
        try: idx = THEMES.index(self.prefs["theme"])
        except ValueError: idx = 0
        self.prefs["theme"] = THEMES[(idx + 1) % len(THEMES)]
        self.root.style.theme_use(self.prefs["theme"])
        self.apply_theme(); self.save_prefs()
    def apply_theme(self):
        st = self.style
        M = MINIMAL
        self.root.configure(bg=M["bg"])
        for w in (self.transcript, self.console, self.plan_txt, self.att_lb, self.se_lb):
            try:
                w.configure(bg=M["bg"], fg=M["fg"], insertbackground=M["fg"],
                            selectbackground=M["primary"], selectforeground="#FFFFFF")
            except Exception:
                pass
        self.input.configure(bg=M["card"], fg=M["fg"], insertbackground=M["fg"])
        # 对话标签配色(极简:用户块 = 褪色绿;工具 = 灰;代码 = 暖灰底)
        self.transcript.tag_config("user", background="#EAF0E9", foreground="#23412B",
                                   font=M["font_body"], lmargin1=12, lmargin2=12, rmargin=12,
                                   spacing1=4, spacing3=4)
        self.transcript.tag_config("asst", foreground="#2F3437", background="#FFFFFF",
                                   font=M["font_body"], lmargin1=12, lmargin2=12, rmargin=12)
        self.transcript.tag_config("tool", foreground="#6B4E2E", background="#FBF3E0",
                                   font=M["font_mono"], lmargin1=12, lmargin2=12)
        self.transcript.tag_config("note", foreground=M["muted"],
                                   font=M["font_small"])
        self.transcript.tag_config("done", foreground="#2E5A38", background="#EAF3EA",
                                   font=("Microsoft YaHei UI", 10, "bold"),
                                   lmargin1=12, lmargin2=12)
        self.transcript.tag_config("code", foreground="#2F3437", background="#F1F0EC",
                                   font=M["font_mono"], lmargin1=20, lmargin2=20)
        self.transcript.tag_config("spacer", spacing1=6, spacing3=6)
        # 思考流:细体灰,与回答区分;折叠标记行可点击切换
        self.transcript.tag_config("think_region", foreground="#6E6E68", background="#EFEEE9",
                                   font=("Microsoft YaHei UI", 9, "italic"),
                                   lmargin1=16, lmargin2=16, rmargin=12)
        self.transcript.tag_config("think_marker", foreground="#6E6E68", background="#EFEEE9",
                                   font=("Microsoft YaHei UI", 9, "italic"),
                                   lmargin1=16, lmargin2=16, spacing1=3, spacing3=3)
        self.transcript.tag_bind("think_marker", "<Button-1>", self._toggle_think)

    def _c(self, key, fallback=None):
        return self.style.colors.get(key, fallback or "#222222")

    # ================= 附件 =================
    def add_files(self):
        paths = filedialog.askopenfilenames(title="选择要附加的文件")
        if not paths: return
        wd = self.wd_dir()
        attdir = os.path.join(wd, "_attachments")
        os.makedirs(attdir, exist_ok=True)
        for p in paths:
            base = os.path.basename(p); dest = os.path.join(attdir, base)
            n = 1
            while os.path.exists(dest):
                dest = os.path.join(attdir, f"{n}_{base}"); n += 1
            try:
                shutil.copy2(p, dest)
                self.attachments.append(dest)
                self.att_lb.insert("end", os.path.basename(dest))
            except Exception as e:
                self.log_note(f"[附件失败: {os.path.basename(p)} → {e}]")
    def clear_files(self):
        self.attachments = []; self.att_lb.delete(0, "end")
    def attach_note(self):
        if not self.attachments: return ""
        names = ", ".join(os.path.basename(a) for a in self.attachments)
        return (f"\n\n[📎 附件已放入工作目录 _attachments/ 下: {names}。"
                f"需要用它们时用 list_dir 查看 _attachments/,用 read_file 读取具体文件。]")

    def wd_dir(self):
        return self.wd_var.get() if hasattr(self, "wd_var") else os.path.join(DEFAULT_TASKS, "work")

    # ================= 会话 =================
    def refresh_sessions(self):
        self.se_lb.delete(0, "end")
        files = [f for f in sorted(glob.glob(os.path.join(SESSION_DIR, "*.json")))
                 if not f.endswith(".meta.json")]
        for s in files[-40:]:
            name = os.path.basename(s)[:-5]
            meta_p = os.path.join(SESSION_DIR, name + ".meta.json")
            tag = ""
            if os.path.exists(meta_p):
                try:
                    m = json.load(open(meta_p, encoding="utf-8"))
                    tag = f"[{m.get('status','?')}]"
                except Exception: pass
            self.se_lb.insert("end", f"{name} {tag}")
    def load_selected_session(self):
        sel = self.se_lb.curselection()
        if not sel: return
        name = self.se_lb.get(sel[0]).split(" [")[0]
        self.session = name
        self.sess_lbl.configure(text=_t("会话:") + name)
        p = os.path.join(SESSION_DIR, name + ".json")
        try: msgs = json.load(open(p, encoding="utf-8"))
        except Exception: msgs = None
        self.render_session(msgs, name)
        self.log_note(f"[已载入会话: {name}]")
    def replay_selected_session(self):
        sel = self.se_lb.curselection()
        if not sel: return
        name = self.se_lb.get(sel[0]).split(" [")[0]
        self.view_transcript(name)
    def _session_summary(self, name):
        meta_p = os.path.join(SESSION_DIR, name + ".meta.json")
        if os.path.exists(meta_p):
            try:
                m = json.load(open(meta_p, encoding="utf-8"))
                return f"{m.get('status','?')} | {m.get('task','')[:36]}"
            except Exception: pass
        return ""

    # ================= 对话渲染 =================
    def render_session(self, msgs, name):
        self.clear_transcript()
        self._rendered_session = name
        if not msgs:
            self.transcript.config(state="normal")
            self.transcript.insert("end", _t("(会话 {name} 无内容)").format(name=name) + "\n", "note")
            self.transcript.config(state="disabled"); return
        for m in msgs:
            role = m.get("role"); c = str(m.get("content","") or "")
            if role == "system": continue
            if role == "user" and (c.startswith("Continue: keep making") or c == _t("继续之前的对话,完成或回答当前需求。")):
                continue
            if role == "user":
                self.transcript.config(state="normal")
                self.transcript.insert("end", "\n", "spacer")
                self.transcript.insert("end", "  " + c + "\n", "user")
                self.transcript.config(state="disabled")
            elif role == "assistant":
                tcs = m.get("tool_calls")
                if tcs:
                    for tc in tcs:
                        fn = tc.get("function", {})
                        self.transcript.config(state="normal")
                        self.transcript.insert("end", f"  ⚙ {fn.get('name','')} "
                                              + json.dumps(fn.get('arguments',{}), ensure_ascii=False)[:70] + "\n", "tool")
                        self.transcript.config(state="disabled")
                if c:
                    self._insert_md(c)
            elif role == "tool":
                self.transcript.config(state="normal")
                self.transcript.insert("end", "      ↳ " + str(c)[:160] + "\n", "note")
                self.transcript.config(state="disabled")
        self._scroll_transcript()

    def _insert_md(self, text):
        """轻量 markdown:代码块 → 等宽深色;粗体 → bold。"""
        self.transcript.config(state="normal")
        in_code = False
        for line in text.split("\n"):
            if line.strip().startswith("```"):
                in_code = not in_code
                continue
            tag = "code" if in_code else "asst"
            self.transcript.insert("end", "\n" + line + "\n", tag)
        self.transcript.insert("end", "\n", "spacer")
        self.transcript.config(state="disabled")

    def add_user_bubble(self, text):
        self.transcript.config(state="normal")
        self.transcript.insert("end", "\n", "spacer")
        self.transcript.insert("end", "  " + text + "\n", "user")
        self.transcript.config(state="disabled")
        self._scroll_transcript()

    def _scroll_transcript(self):
        self.transcript.see("end")

    def clear_transcript(self):
        self._set_text(self.transcript)
        self._rendered_session = None
    def clear_log(self):
        self._set_text(self.console)
    def _set_text(self, w):
        w.config(state="normal"); w.delete("1.0", "end"); w.config(state="disabled")
    def log_note(self, txt):
        self.transcript.config(state="normal")
        self.transcript.insert("end", "  " + txt + "\n", "note")
        self.transcript.config(state="disabled")
        self._scroll_transcript()
    def log(self, txt):
        self.console.config(state="normal")
        self.console.insert("end", txt + "\n"); self.console.see("end")
        self.console.config(state="disabled")

    # ================= 关于 / 欢迎 =================
    def show_about(self):
        win = tb.Toplevel(self.root); win.title(_t("ℹ 关于")); win.geometry("460x340")
        win.transient(self.root); win.grab_set()
        M = MINIMAL
        win.configure(bg=M["bg"])
        tb.Label(win, text=_t("蜂鸟 · 本地 AI 助手"),
                 font=("Microsoft YaHei UI", 14, "bold"), bootstyle="inverse-primary",
                 padding=(16, 12)).pack(fill="x")
        body = tk.Frame(win, bg=M["bg"]); body.pack(fill="both", expand=True, padx=18, pady=10)
        info = (f"{_t('版本')}: {self.app_version()}\n"
                f"{_t('许可')}: Apache-2.0\n\n"
                f"{_t('全离线·小模型优先的本地 AI agent')}\n"
                f"Ollama + AMD iGPU / NVIDIA / CPU")
        tb.Label(body, text=info, font=M["font_body"], bootstyle="secondary",
                 justify="left", anchor="w").pack(fill="x")
        tb.Label(body, text="", background=M["bg"]).pack()
        # 打开内嵌文档
        df = tb.Frame(body); df.pack(fill="x", pady=(4, 0))
        docs = {"README": "README_EN.md", "RELEASE_NOTES.md": "RELEASE_NOTES.md",
                "AGENTS.md": "AGENTS.md", "LICENSE": "LICENSE"}
        for label, fn in docs.items():
            tb.Button(df, text=label, bootstyle="secondary-outline",
                      command=lambda n=fn: self._open_doc(n)).pack(side="left", padx=2)
        tb.Button(df, text=_t("打开安装目录"), bootstyle="secondary-outline",
                  command=lambda: subprocess.Popen(["explorer", AGENT_DIR])).pack(side="left", padx=2)
        tb.Button(win, text=_t("关闭"), bootstyle="primary",
                  command=win.destroy).pack(pady=(6, 10))

    def _open_doc(self, fn):
        """打开内嵌文档(exe 目录或 _internal 下)。"""
        for base in (AGENT_DIR, os.path.join(AGENT_DIR, "_internal"),
                     getattr(sys, "_MEIPASS", "")):
            p = os.path.join(base, fn)
            if os.path.exists(p):
                subprocess.Popen(["notepad", p])
                return
        self.log(f"[文档未找到: {fn}]")

    def _welcome(self):
        """空状态欢迎语:新对话时给出最快的上手提示。"""
        if self.transcript.get("1.0", "end-1c").strip():
            return
        M = MINIMAL
        self.transcript.config(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.insert("end", "\n", "spacer")
        self.transcript.insert("end", "  " + _t("欢迎使用") + " 🐦\n", "done")
        self.transcript.insert("end", "  " + _t("全离线·小模型优先的本地 AI agent") + "\n", "note")
        self.transcript.insert("end", "\n", "spacer")
        self.transcript.insert("end", "  " + _t("输入任务或对话,Ctrl+Enter 发送。可以直接说:") + "\n", "asst")
        for t in (_t("· 用中文回答我,别客气"),
                  _t("· 在某个目录里写个 Python 程序并跑测试"),
                  _t("· 帮我查资料、整理成报告"),
                  _t("· 管理本地文件,整理照片")):
            self.transcript.insert("end", "\n  " + t + "\n", "asst")
        self.transcript.insert("end", "\n", "spacer")
        self.transcript.insert("end", "  " + _t("模型可在上方切换;工具栏可开关思考过程、切主题。") + "\n", "note")
        self.transcript.insert("end", "\n", "spacer")
        self.transcript.config(state="disabled")

    # ================= 技能 / 搜索 =================
    def show_skills(self):
        win = tb.Toplevel(self.root); win.title(_t("技能列表")); win.geometry("600x440")
        tb.Label(win, text=_t("本地 agent 可用技能(渐进式:用到才加载全文)"), padding=6).pack(anchor="w")
        txt = scrolledtext.ScrolledText(win, font=("Consolas", 9), wrap="word")
        txt.pack(fill="both", expand=True, padx=6, pady=2)
        seen = {}
        for base in SKILL_DIRS:
            if os.path.isdir(base):
                for f in sorted(os.listdir(base)):
                    if f.endswith((".md", ".txt", ".py")):
                        name = f.rsplit(".", 1)[0]
                        if name not in seen: seen[name] = self._skill_desc(os.path.join(base, f))
        if not seen:
            txt.insert("end", _t("(暂无技能)") + "\n" + "\n".join(SKILL_DIRS))
        for n in sorted(seen):
            txt.insert("end", f"■ {n}\n   {seen[n]}\n\n" if seen[n] else f"■ {n}\n\n")
        txt.config(state="disabled")
    def _skill_desc(self, path):
        try: head = open(path, encoding="utf-8").read(600)
        except Exception:
            try: head = open(path, encoding="gbk").read(600)
            except Exception: return ""
        m = re.search(r"description:\s*(.+)", head)
        if m: return m.group(1).strip().strip('"').strip("'")[:110]
        for line in head.splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "-", "---")): return line[:110]
        return ""

    def search_history(self):
        win = tb.Toplevel(self.root); win.title(_t("会话历史搜索")); win.geometry("640x480")
        top = tb.Frame(win, padding=6); top.pack(fill="x")
        tb.Label(top, text=_t("关键词:")).pack(side="left")
        kw = tk.StringVar()
        ent = tb.Entry(top, textvariable=kw, width=28); ent.pack(side="left", padx=4)
        ent.bind("<Return>", lambda e: do_search())
        tb.Button(top, text=_t("搜索"), bootstyle="primary", command=lambda: do_search()).pack(side="left")
        fr = tb.Frame(win); fr.pack(fill="both", expand=True, padx=6, pady=2)
        lb = tk.Listbox(fr, font=("Consolas", 9)); lb.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(fr, orient="vertical", command=lb.yview); sb.pack(side="right", fill="y")
        lb.config(yscrollcommand=sb.set)
        results = []
        def do_search():
            q = kw.get().strip().lower(); lb.delete(0, "end"); results.clear()
            if not q: lb.insert("end", _t("(输入关键词再搜索)")); return
            files = [f for f in glob.glob(os.path.join(SESSION_DIR, "*.json"))
                     if not f.endswith(".meta.json")]
            for s in sorted(files):
                name = os.path.basename(s)[:-5]
                try: msgs = json.load(open(s, encoding="utf-8"))
                except Exception: continue
                text = " ".join(str(m.get("content","")) for m in msgs)
                idx = text.lower().find(q)
                if idx < 0: continue
                snip = text[max(0,idx-55):idx+120].replace("\n"," ")
                results.append(name)
                lb.insert("end", f"{name}  |  …{snip}…")
            if not results: lb.insert("end", f"(未找到含 '{q}' 的会话)")
        def view_sel():
            sel = lb.curselection()
            if sel: self.view_transcript(results[sel[0]])
        def load_sel():
            sel = lb.curselection()
            if not sel: return
            self.session = results[sel[0]]; self.sess_lbl.configure(text=_t("会话:") + self.session)
            p = os.path.join(SESSION_DIR, self.session + ".json")
            try: msgs = json.load(open(p, encoding="utf-8"))
            except Exception: msgs = None
            self.render_session(msgs, self.session)
            self.log_note(f"[从历史恢复会话: {self.session}]")
            win.destroy()
        bf = tb.Frame(win); bf.pack(pady=4)
        tb.Button(bf, text=_t("查看对话"), command=view_sel).pack(side="left", padx=4)
        tb.Button(bf, text=_t("恢复此会话"), bootstyle="primary", command=load_sel).pack(side="left", padx=4)
        ent.focus_set()

    def view_transcript(self, name):
        win = tb.Toplevel(self.root); win.title(_t("会话回放: {name}").format(name=name)); win.geometry("760x560")
        tb.Label(win, text=f_t("会话 {name} — 完整对话记录(Ctrl+F 搜索)").format(name=name), padding=6).pack(anchor="w")
        txt = scrolledtext.ScrolledText(win, font=("Consolas", 9), wrap="word")
        txt.pack(fill="both", expand=True, padx=6, pady=2)
        p = os.path.join(SESSION_DIR, name + ".json")
        try: msgs = json.load(open(p, encoding="utf-8"))
        except Exception:
            txt.insert("end", _t("(读取失败)")); txt.config(state="disabled"); return
        for m in msgs:
            role = m.get("role"); c = m.get("content","") or ""
            if role == "system": continue
            if role == "user" and (c.startswith("Continue: keep making") or c == _t("继续之前的对话,完成或回答当前需求。")):
                continue
            if role == "user":
                txt.insert("end", f"\n━━━ 👤 用户 ━━━\n{c}\n", "u")
            elif role == "assistant":
                for tc in m.get("tool_calls", []):
                    fn = tc.get("function", {})
                    txt.insert("end", f"\n⚙ {fn.get('name','')} {json.dumps(fn.get('arguments',{}), ensure_ascii=False)[:120]}\n", "t")
                if c: txt.insert("end", f"\n▸ {c}\n", "a")
            elif role == "tool":
                txt.insert("end", f"   ↳ {str(c)[:200]}\n", "r")
        txt.tag_config("u", foreground="#1a5fb4", font=("Microsoft YaHei UI", 10, "bold"))
        txt.tag_config("a", foreground="#000000")
        txt.tag_config("t", foreground="#a34e00")
        txt.tag_config("r", foreground="#7a7a7a")
        txt.config(state="disabled")

    # ================= 设置 =================
    def open_settings(self):
        win = tb.Toplevel(self.root); win.title(_t("设置")); win.geometry("520x520")
        prefs = dict(self.prefs)
        body = tb.Frame(win, padding=12); body.pack(fill="both", expand=True)
        r1 = tb.Frame(body); r1.pack(fill="x", pady=2)
        tb.Label(r1, text=_t("上下文窗口:")).pack(side="left")
        ctx = tb.Combobox(r1, values=[16384, 32768, 65536, 131072, 262144],
                          width=10, state="readonly")
        if prefs["ctx"] not in ctx["values"]:
            prefs["ctx"] = 32768   # 兼容旧保存值,归入梯度
        ctx.set(prefs["ctx"]); ctx.pack(side="left", padx=6)
        tb.Label(r1, text=_t("温度:")).pack(side="left")
        temp = ttk.Spinbox(r1, from_=0.0, to=2.0, increment=0.1, width=6)
        temp.set(prefs["temp"]); temp.pack(side="left", padx=6)
        tb.Label(r1, text=_t("输出上限:")).pack(side="left")
        np = tb.Combobox(r1, values=[512, 1024, 2048, 4096, 8192], width=8, state="readonly")
        np.set(prefs["num_predict"]); np.pack(side="left", padx=6)
        sys_en = tk.BooleanVar(value=prefs["sys_enable"])
        tb.Checkbutton(body, text=_t("启用自定义系统提示(替代内置,可大幅改造行为)"),
                       variable=sys_en, bootstyle="round-toggle").pack(anchor="w", pady=(8,2))
        sys_txt = scrolledtext.ScrolledText(body, height=10, font=("Consolas", 9), wrap="word")
        sys_txt.pack(fill="both", expand=True)
        sys_txt.insert("1.0", prefs["sys_text"])
        def save():
            prefs["ctx"] = int(ctx.get()); prefs["temp"] = float(temp.get())
            prefs["num_predict"] = int(np.get()); prefs["sys_enable"] = sys_en.get()
            prefs["sys_text"] = sys_txt.get("1.0", "end").strip()
            self.prefs.update(prefs)
            if prefs["sys_enable"] and prefs["sys_text"]:
                open(SYS_OVERRIDE_FILE, "w", encoding="utf-8").write(prefs["sys_text"])
            self.save_prefs()
            win.destroy()
        tb.Button(win, text=_t("保存"), bootstyle="success", command=save).pack(pady=8)

    # ================= 运行 =================
    def _input_text(self):
        t = self.input.get("1.0", "end").strip()
        return None if t in (_t("输入任务或对话…(Ctrl+Enter 发送)"), "") else t

    def run_agent(self):
        # 统一为一个发送入口:模型自己判断是聊天还是任务
        self.send_chat()

    def send_chat(self):
        if self.proc and self.proc.poll() is None:
            self.log_note("[忙:当前任务运行中,先停止再发送]"); return
        msg = self._input_text()
        if not msg: return
        self.input.delete("1.0", "end")
        self._flush_asst()
        self.add_user_bubble(msg)
        if not self.session:
            self.session = "chat_" + time.strftime("%m%d_%H%M%S")
            self.sess_lbl.configure(text=_t("会话:") + self.session)
        self.launch(msg, use_session=True, resume_ok=True)

    # ================= 语音输入 =================
    def refresh_voice_state(self):
        # STT 已独立(本地 sherpa-onnx),所有模型都可用语音;若本地 STT 不可用则回退到模型音频能力
        def _check():
            model = self._model_map.get(self.model_var.get())
            ok = voice_input.local_stt_available() or (model and voice_input.model_audio_capable(model))
            self.mic_btn.config(state="normal" if ok else "disabled")
            self.mic_btn.configure(text=_t("🎤 语音") if ok else "🎤 无音频")
            self.mic_btn.configure(bootstyle="info" if ok else "secondary")
        self.root.after(10, _check)

    def voice_input(self):
        """语音按钮:第一次点击开始录音,按钮变『■ 停止录音』;第二次点击结束并转写。
        开始后自动做 VAD(说完静音约 1.2s 自动结束),另有 60s 保险上限。"""
        if self._voice_rec:            # 正在录音 → 结束
            if self._voice_stop_timer:
                self.root.after_cancel(self._voice_stop_timer)   # 关键:取消挂起回调,防陈旧定时器提前掐断
                self._voice_stop_timer = None
            if self._vad_timer:
                self.root.after_cancel(self._vad_timer)
                self._vad_timer = None
            self.mic_btn.configure(text=_t("转写中…"), state="disabled")
            wav = os.path.join(AGENT_HOME, "voice_input.wav")
            ok = self._voice_rec.stop(wav)
            self._voice_rec = None
            if not ok:
                self._voice_done("", _t("未捕捉到声音,请重试"))
                return
            model = self._model_map.get(self.model_var.get())   # 主线程读,避免工作线程访问 Tk 变量
            threading.Thread(target=self._voice_worker, args=(wav, model), daemon=True).start()
        else:                          # 开始录音
            if self.proc and self.proc.poll() is None:
                self.log_note(_t("[忙:任务运行中,先停止再语音输入]")); return
            if self._voice_busy: return
            try:
                self._voice_rec = voice_input.Recorder()
                self._voice_rec.start()
                self.mic_btn.configure(text=_t("■ 停止录音"), bootstyle="danger")
                self.log_note(_t("[录音中… 说完话自动停止]"))
                self._voice_stop_timer = self.root.after(60000, self._auto_stop_voice)  # 60s 保险上限
                self._vad_timer = self.root.after(150, self._voice_vad_check)
            except Exception as e:
                self._voice_rec = None
                self.log_note(_t("[录音启动失败: {e}]").format(e=e))

    def _voice_vad_check(self):
        """轮询 VAD:检测到说完话(静音超时)就结束录音并转写。"""
        self._vad_timer = None
        rec = self._voice_rec
        if not rec or not rec._running:
            return
        if rec._auto_stop:
            self.voice_input()      # 走同一条结束路径
            return
        self._vad_timer = self.root.after(150, self._voice_vad_check)
    def _auto_stop_voice(self):
        self._voice_stop_timer = None
        if self._vad_timer:
            self.root.after_cancel(self._vad_timer); self._vad_timer = None
        if self._voice_rec:
            self.log_note(_t("[录音超时,自动停止]"))
            self.voice_input()   # 走同一条结束路径
    def _voice_worker(self, wav, model):
        try:
            stt = voice_input.pick_stt_model(model)
            text = voice_input.transcribe(stt, wav)
            self.root.after(0, lambda: self._voice_done(text, stt))
        except Exception as e:
            self.root.after(0, lambda: self._voice_done("", _t("转写失败: ") + str(e)))
    def _voice_done(self, text, stt):
        self._voice_busy = False
        self._voice_rec = None
        self.mic_btn.configure(text=_t("🎤 语音"), state="normal")
        if self.mic_btn.cget("text") != "🎤 无音频":
            self.mic_btn.configure(bootstyle="info")
        if text:
            self.input.delete("1.0", "end")
            self.input.insert("1.0", text.strip())
            self.log_note(_t("[语音已转录({stt})并填入输入框]").format(stt=stt))
        else:
            self.log_note(_t("[语音转录无结果:{stt} 转写能力有限,可换用更强音频模型]").format(stt=stt))

    def new_chat(self):
        self.session = None
        self.sess_lbl.configure(text=_t("会话:无"))
        self.clear_transcript()
        self._welcome()
        self.att_lb.delete(0, "end"); self.attachments = []
        self.status_var.set(_t(" 上下文: - / - ( - % )"))
        self.ctx_bar["value"] = 0
        self.input.delete("1.0", "end")

    def launch(self, task, use_session, resume_ok):
        model = self._model_map.get(self.model_var.get(), list(self._model_map.values())[0])
        workdir = self.wd_var.get() if hasattr(self, "wd_var") else os.path.join(DEFAULT_TASKS, "work")
        task = task + self.attach_note()
        os.makedirs(workdir, exist_ok=True)
        taskfile = os.path.join(workdir, "task_input.txt")
        with open(taskfile, "w", encoding="utf-8") as f: f.write(task)
        if not resume_ok:
            ck = os.path.join(workdir, ".agent_state.json")
            if os.path.exists(ck): os.remove(ck); self.log_note(_t("[已清除旧进度]"))
        env = dict(os.environ); env["PYTHONIOENCODING"]="utf-8"
        env["AGENT_STREAM"] = "1"   # 对话流式输出 + 思考流
        env["AGENT_THINK"] = "1" if self.think_var.get() else "0"
        env["AGENT_CTX"] = str(self.prefs["ctx"])
        env["AGENT_TEMP"] = str(self.prefs["temp"])
        env["AGENT_NUMPREDICT"] = str(self.prefs["num_predict"])
        if self.prefs.get("sys_enable"):
            if os.path.exists(SYS_OVERRIDE_FILE):
                env["AGENT_SYSTEM_FILE"] = SYS_OVERRIDE_FILE
        if getattr(sys, "frozen", False):
            # 打包后 sys.executable 是本 exe:用特殊参数让它以 agent CLI 模式跑(不开新窗口)
            args = [sys.executable, "ollama_agent.py", model, taskfile, workdir]
        else:
            args = [sys.executable, AGENT_PY, model, taskfile, workdir]
        if use_session or self.session: args += ["--session", self.session]
        if use_session: args += ["--append"]
        self.log(f"====== {_t('开始: ')}{model}" + (f" | {_t('会话:')}{self.session}" if self.session else "") + " ======")
        self.log(f"工作目录: {workdir}\n")
        self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", env=env, bufsize=1)
        threading.Thread(target=self.reader, daemon=True).start()
        self.send_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

    def reader(self):
        for line in iter(self.proc.stdout.readline, ""):
            self.q.put(line.rstrip("\n"))
        self.q.put(None)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill(); self.log("\n" + _t("[已停止,重跑并勾选'续跑'可从中断处继续]"))
            self.log_note(_t("[已停止 — 重跑勾选'续跑'可从中断处继续]"))

    # ================= 流解析 =================
    def poll(self):
        try:
            while True:
                line = self.q.get_nowait()
                if line is None:
                    self._collapse_think()
                    self._flush_asst()
                    self.log("\n===== 任务结束 =====")
                    self.send_btn.config(state="normal")
                    self.stop_btn.config(state="disabled"); self.proc = None
                    self.refresh_sessions()
                elif line:
                    self.log(line)
                    self.feed_transcript(line)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def _check_ollama(self):
        """Ollama 在线状态灯:绿=在线有模型,黄=在线无模型,红=离线。"""
        up = False; has_models = False
        try:
            import urllib.request as _ur
            r = json.loads(_ur.urlopen("http://127.0.0.1:11434/api/tags", timeout=2).read())
            up = True; has_models = bool(r.get("models"))
        except Exception:
            pass
        if up and has_models:
            self.ollama_lbl.configure(text="Ollama ✓", bootstyle="success")
        elif up:
            self.ollama_lbl.configure(text=_t("Ollama ✓(无模型)"), bootstyle="warning")
        else:
            self.ollama_lbl.configure(text=_t("Ollama ✗ 未启动"), bootstyle="danger")
        self.root.after(5000, self._check_ollama)

    def _try_start_ollama(self):
        """拉起 ollama serve(后台进程,不弹窗)。"""
        try:
            import ollama_agent
            ok = ollama_agent.ensure_ollama()
            if ok:
                self.log_note(_t("[Ollama 已启动]"))
            else:
                from tkinter import messagebox
                messagebox.showwarning(_t("Ollama"), _t("未能自动启动 Ollama,请手动运行 ollama serve 后再试。"))
        except Exception:
            pass

    def _ollama_click(self, evt=None):
        """点击 Ollama 灯:在线无动作;离线弹提示并尝试拉起。"""
        cur = self.ollama_lbl.cget("text")
        if "未启动" in cur or "✗" in cur:
            self.log_note("[尝试启动 Ollama…]")
            self._try_start_ollama()
        else:
            from tkinter import messagebox
            messagebox.showinfo(_t("Ollama"),
                                _t("Ollama 已在线。本 agent 全离线运行,数据不离开本机。")
                                if _LANG == "zh" else
                                "Ollama is online. This agent runs fully offline — data never leaves your machine.")
        self.root.after(1500, self._check_ollama)

    def _stream_tok(self, tok):
        """流式回答 token:实时追加到当前助手气泡(跳过 markdown 渲染,保持打字机效果)。"""
        try:
            if self._think_live or self._think_open:
                self._collapse_think()   # 回答开始前先收掉思考
            self.transcript.config(state="normal")
            if not self._asst_buf:
                self.transcript.insert("end", "\n", "spacer")
            self._asst_buf += tok
            self._streaming_asst = True
            self.transcript.insert("end", tok, "asst")
            self.transcript.config(state="disabled")
            self._scroll_transcript()
        except Exception:
            pass

    def _stream_think(self, tok):
        """流式思考 token:显示在灰色思考区(tag=think_region)。"""
        try:
            self.transcript.config(state="normal")
            if not self._think_live:
                self._collapse_think()
                self.transcript.insert("end", _t("🤔 思考中…") + "\n", "think_region")
                self._think_live = True
                self._think_text = ""
            self._think_text += tok
            self.transcript.insert("end", tok, "think_region")
            self.transcript.config(state="disabled")
            self._scroll_transcript()
        except Exception:
            pass

    def _collapse_think(self):
        """把思考区域(think_region)折叠成一行可点击标记;只动思考区,不碰正文。"""
        try:
            self.transcript.config(state="normal")
            r = self.transcript.tag_ranges("think_region")
            if r:
                start, end = r[0], r[1]
                m = self.transcript.tag_ranges("think_marker")
                if m:
                    # 展开态末尾的"点击折叠"标记一并移除
                    try:
                        if self.transcript.compare(m[0], ">=", start):
                            end = m[1]
                    except Exception:
                        pass
                self.transcript.delete(start, end)
                n = len(self._think_text)
                self.transcript.insert(start, _t("🤔 思考过程 ({n} 字) — 点击展开/折叠").format(n=n) + "\n", "think_marker")
            self.transcript.config(state="disabled")
        except Exception:
            pass
        self._think_live = False
        self._think_open = False

    def _toggle_think(self, event=None):
        """点击思考标记:展开显示全文 / 重新折叠(只动思考区,不碰正文)。"""
        if not self._think_text:
            return
        try:
            self.transcript.config(state="normal")
            r = self.transcript.tag_ranges("think_region")
            if r:
                # 展开态 → 折叠
                start, end = r[0], r[1]
                m = self.transcript.tag_ranges("think_marker")
                if m:
                    try:
                        if self.transcript.compare(m[0], ">=", start):
                            end = m[1]
                    except Exception:
                        pass
                self.transcript.delete(start, end)
                n = len(self._think_text)
                self.transcript.insert(start, _t("🤔 思考过程 ({n} 字) — 点击展开/折叠").format(n=n) + "\n", "think_marker")
                self._think_open = False
            else:
                m = self.transcript.tag_ranges("think_marker")
                if m:
                    start = m[0]
                    self.transcript.delete(start, m[1])
                    # 同位置插入会反序:按 标记→正文→头 顺序插,最终显示 头→正文→标记
                    self.transcript.insert(start, _t("🤔 思考过程 ({n} 字) — 点击折叠").format(n=len(self._think_text)) + "\n", "think_marker")
                    self.transcript.insert(start, self._think_text + "\n", "think_region")
                    self.transcript.insert(start, _t("🤔 思考过程 · {n} 字").format(n=len(self._think_text)) + "\n", "think_region")
                    self._think_open = True
            self.transcript.config(state="disabled")
            self._scroll_transcript()
        except Exception:
            pass

    def feed_transcript(self, line):
        if line.startswith("@@TOK@@"):
            self._stream_tok(line[len("@@TOK@@"):])
            return
        if line.startswith("@@THINK@@"):
            self._stream_think(line[len("@@THINK@@"):])
            return
        m = re.match(r"\[ctx: (\d+)/(\d+) = (\d+)%\]", line)
        if m:
            self._collapse_think()
            self._flush_asst()
            pt, total, pct = int(m.group(1)), int(m.group(2)), int(m.group(3))
            self.status_var.set(_t(" 上下文: {pt} / {total} ({pct}%)").format(pt=pt, total=total, pct=pct))
            self.ctx_bar["value"] = min(pct, 100)
            return
        if line.startswith("[ctx:") or line == "":
            return
        m = re.match(r"\[(\d+)\] ⚙ (\w+)\s*(\{.*\})?\s*->\s*(.*)", line)
        if m:
            self._collapse_think()
            self._flush_asst()
            name, args, res = m.group(2), m.group(3) or "", m.group(4)
            if name == "finish":
                self.transcript.config(state="normal")
                self.transcript.insert("end", "\n", "spacer")
                self.transcript.insert("end", "  ✅ " + res[:300] + "\n", "done")
                self.transcript.config(state="disabled")
            else:
                self.transcript.config(state="normal")
                self.transcript.insert("end", "  ⚙ " + name + " " + args[:60] + "\n", "tool")
                self.transcript.config(state="disabled")
            self._scroll_transcript()
            return
        m = re.match(r"\[(\d+)\] ✍ (.*)", line, re.S)
        if m:
            self._flush_asst()
            self._asst_buf = m.group(2)
            return
        if self._asst_buf:
            self._asst_buf += "\n" + line
            return
        if "TASK COMPLETE" in line or line.startswith("[TASK_COMPLETE]"):
            return
        if line.startswith(("[RESUMED", "[session", "[上下文已压缩", "[交互模式", "[已选择", "[已从历史", "=====", "[新对话")):
            self.log_note(line.strip("= ")); return
        self.log_note(line.strip("= "))

    def _flush_asst(self):
        if self._asst_buf:
            if not self._streaming_asst:
                # 非流式:整段 markdown 渲染成气泡
                self._insert_md(self._asst_buf)
                self._scroll_transcript()
            self._asst_buf = ""
            self._streaming_asst = False

    def poll_todo(self):
        tf = os.path.join(self.wd_dir(), "todo.json")
        try:
            t = json.load(open(tf, encoding="utf-8"))
            text = "\n".join(f"{'[x]' if x['done'] else '[ ]'} {i}. {x['item']}"
                             for i, x in enumerate(t, 1))
        except Exception:
            text = ""
        self.plan_txt.config(state="normal")
        if self.plan_txt.get("1.0", "end").strip() != text.strip():
            self.plan_txt.delete("1.0", "end")
            self.plan_txt.insert("1.0", text if text else _t("(尚无计划 — agent 会先建 todo 再执行)"))
        self.plan_txt.config(state="disabled")
        self.root.after(500, self.poll_todo)

    def on_close(self):
        if self.proc and self.proc.poll() is None: self.proc.kill()
        self.root.destroy()

if __name__ == "__main__":
    # 自检:打印关键依赖在冻结环境里的导入状态(定位打包缺失)
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        out = []
        for mod in ("numpy", "sounddevice", "soundfile", "sherpa_onnx", "bs4", "requests"):
            try:
                m = __import__(mod)
                out.append(f"{mod}: OK v{getattr(m,'__version__','?')}")
            except Exception as e:
                out.append(f"{mod}: FAIL {type(e).__name__}: {str(e)[:80]}")
        print("SELFTEST")
        print("\n".join(out))
        sys.exit(0)
    # 打包后:同 exe 以 agent CLI 模式运行(带 "ollama_agent.py" 标记),不弹 GUI 窗口
    if len(sys.argv) > 1 and sys.argv[1] == "ollama_agent.py":
        try:
            import ollama_agent
            sys.argv = [sys.argv[0]] + sys.argv[2:]   # 去掉标记,main() 按 [model, task, workdir, ...] 解析
            ollama_agent.main()
        except SystemExit:
            pass
        sys.exit(0)
    # 打开 GUI 时按需拉起 ollama(不在开机自启常驻)
    try:
        import ollama_agent
        ok = ollama_agent.ensure_ollama()
        if not ok:
            import tkinter.messagebox as _mb
            _mb.showwarning("蜂鸟 · 本地 AI 助手", _t("未能自动启动 ollama,请先手动运行 ollama serve。"))
    except Exception:
        pass
    root = tb.Window(themename="minty-light", title=_t("蜂鸟 · 本地 AI 助手"))
    app = AgentGUI(root)
    root.mainloop()
