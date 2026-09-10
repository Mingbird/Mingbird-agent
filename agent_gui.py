#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""鸣鸟 · 本地 AI 助手 — Windows 桌面 GUI v4(现代化)
基于 ttkbootstrap 的聊天工作区设计:
- 侧边栏:附件 / 会话 / 计划(todo)
- 主区:💬 对话(聊天气泡视图) + 🖥 日志(流式控制台)
- 📎 文件上传:复制到工作目录 _attachments/,agent 按需读取
- ⚙ 设置:上下文窗口 / 温度 / 输出上限 / 自定义系统提示(持久化)
- 🌓 主题切换(darkly / superhero / flatly / cosmo ...)
- 快捷键:Ctrl+N 新对话 · Ctrl+F 历史搜索 · Ctrl+Enter 发送 · Ctrl+L 清日志
"""
import tkinter as tk
from tkinter import ttk, filedialog, font as tkfont
from tkinter import scrolledtext
import ttkbootstrap as tb
import subprocess, threading, os, queue, sys, re, glob, json, time, shutil
import voice_input
import appconfig   # 统一配置层:Ollama 地址/模型映射等由用户配置,不硬编码
_dedupe_model_entries = appconfig.dedupe_model_entries   # digest 去重(GUI/WebUI 共用,勿放类体内)

# 可选拖拽支持:装了 tkinterdnd2 即可把文件直接拖进聊天框;未装则静默降级,
# 其余功能不受影响(粘贴附件不依赖它)。
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES as _DND_FILES
    _HAVE_DND = True
except Exception:
    TkinterDnD = None
    _DND_FILES = None
    _HAVE_DND = False

# 冻结(exe)时用 exe 自身目录,避免 __file__ 相对 CWD 解析错导致文件找不到
if getattr(sys, "frozen", False):
    AGENT_DIR = os.path.dirname(sys.executable)
else:
    AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_PY  = os.path.join(AGENT_DIR, "ollama_agent.py")


def _file_manager_cmd(path):
    """Open a directory in the platform file manager."""
    if os.name == "nt":
        return ["explorer", os.path.normpath(path)]
    if sys.platform == "darwin":
        return ["open", path]
    return ["xdg-open", path]


def _open_doc_cmd(path):
    """Open a document with the platform default text viewer."""
    if os.name == "nt":
        return ["notepad", path]
    if sys.platform == "darwin":
        return ["open", "-t", path]
    return ["xdg-open", path]
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
    "鸣鸟 · 本地 AI 助手": "Mingbird · Local AI Assistant",
    "模型:": "Model:", "会话:无": "Session: none", "目录:": "Dir:",
    "关闭思考": "Thinking OFF", "⚙ 设置": "⚙ Settings", "🌓 主题": "🌓 Theme",
    "＋ 新对话": "＋ New Chat", "添加附件": "Attachments", "清空": "Clear",
    "会话": "Sessions", "计划": "Plan", "💬 对话": "💬 Chat", "🖥 日志": "🖥 Logs",
    "发送": "Send", "🎤 语音": "🎤 Voice", "🎤 无音频": "🎤 No Audio", "■ 停止录音": "■ Stop",
    "允许一次": "Allow once", "允许全部(本轮)": "Allow all (this task)",
    "拒绝": "Deny", "⚠ 越界操作确认": "⚠ Outside-workspace access",
    "AI 想访问工作目录之外的文件": "The agent wants to access files outside the workspace",
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
    "鸣鸟 · 本地 AI 助手 错误": "Mingbird · Local AI Assistant Error",
    "未能自动启动 ollama,请先手动运行 ollama serve。": "Could not start Ollama automatically. Run `ollama serve` manually first.",
    "开始: ": "Started: ",
    "🤔 思考中…": "🤔 thinking…",
    "🤔 思考过程 ({n} 字) — 点击展开/折叠": "🤔 thinking ({n} chars) — click to expand/collapse",
    "🤔 思考过程 ({n} 字) — 点击折叠": "🤔 thinking ({n} chars) — click to collapse",
    "🤔 思考过程 · {n} 字": "🤔 thinking · {n} chars",
    "查看": "View",
    "计划 (todo)": "Plan (todo)",
    "任务时限:": "Time limit:",
    "[已从任务描述识别时限 {n} 分钟,优先于手填值]": "[Time limit {n} min detected in the task text — overrides the box]",
    "[任务时限 {n} 分钟,超时会收到收尾提醒]": "[Time limit {n} min — you'll get wind-down reminders]",
    "[任务时限不可用:无法加载解析器 {e}]": "[Time limit unavailable: cannot load parser {e}]",
    # v2 导航轨/页面标题
    "对话": "Chat", "历史": "History", "日志": "Logs",
    "技能": "Skills", "设置": "Settings", "关于": "About",
    "附件": "Attachments", "历史会话": "Session history",
    "运行日志": "Run log", "用户": "User", "任务结束": "Task finished",
    # 确认框 / 日志杂项
    "工作目录:": "Workdir:", "工作目录: ": "Workdir: ",
    "工具:": "Tool:", "操作:": "Action:", "目标:": "Target:",
    "允许这次访问吗?": "Allow this access?",
    "访问": "Access", "执行命令": "Run command", "读取敏感文件": "Read sensitive file",
    "[主题: ": "[Theme: ",
    "(详情见 ": "(details in ",
    "[越界操作请求,请确认]": "[Outside-workspace request, please confirm]",
    "[尝试启动 Ollama…]": "[Trying to start Ollama…]",
    "[忙:当前任务运行中,先停止再发送]": "[Busy: a task is running, stop it before sending]",
    "选择要附加的文件": "Choose files to attach",
    "[附件失败: {p} → {e}]": "[Attach failed: {p} → {e}]",
    "[已载入会话: {name}]": "[Session loaded: {name}]",
    "[文档未找到: {fn}]": "[Doc not found: {fn}]",
    "(未找到含 '{q}' 的会话)": "(No sessions containing '{q}')",
    "[从历史恢复会话: {name}]": "[Session restored from history: {name}]",
    # 并行派发(@@DISPATCH@@ 进度)
    " 已派发子任务 0/{t} 完成 (模型 {m})": " Dispatched 0/{t} done (model {m})",
    " 已派发子任务 {d}/{t} 完成": " Dispatched {d}/{t} done",
    " 已派发子任务 {o}/{t} 完成": " Dispatched {o}/{t} done",
    "[并行派发] ": "[Parallel] ",
    "{n} 条简单子任务派给 {m} 并行做": "{n} simple subtasks dispatched to {m} in parallel",
    "[并行派发] 子任务 {i}: {s}": "[Parallel] subtask {i}: {s}",
    "[并行派发] 结束: 成功 {o}/{t},回退主模型 {f},严重违规 {sv}":
        "[Parallel] done: {o}/{t} ok, {f} fell back to main model, {sv} severe violations",
    # 模型显示名:来自用户 ~/.ollama_agent/config.json 的 models 别名(本机现值),
    # _t() 已作用于显示名,未命中的别名按原样显示(与文件名同类,属用户数据)
    "qwen2b (长上下文 256K)": "qwen2b (long-ctx 256K)",
    "e2b (快速 128K)": "e2b (fast 128K)",
    "Mellum2 (代码)": "Mellum2 (code)",
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
            _mb.showerror(_t("鸣鸟 · 本地 AI 助手 错误"),
                          f"{exc_type.__name__}: {exc}\n" + _t("(详情见 ") + _ERR_LOG + ")")
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
        return ""   # VERSION 缺失时不显示版本号(旧兜底 v0.6.0 误导)

    def refresh_models(self):
        """从 ollama 动态读取已安装模型,构建 显示名→tag 映射。
        - ollama 可达:下拉 = 实际安装的模型(配置了友好名则显示友好名);
          配置里已卸载的模型不显示(它们跑不起来)。
        - ollama 不可达:下拉显示明确的离线占位,不冒充可用模型;
          _check_ollama 的自愈会在 ollama 恢复后自动重试刷新。
        查询带 3 次重试:批次满载时 /api/tags 偶发 >3s 超时,重试避免闪回陈旧列表。"""
        m = {}
        cfg_display = appconfig.model_map()          # {显示名: tag}
        tag_to_display = {v: k for k, v in cfg_display.items()}
        entries = []
        import urllib.request as _ur
        import time as _sleep_mod
        for _ in range(3):
            try:
                r = json.loads(_ur.urlopen(f"{appconfig.ollama_host()}/api/tags", timeout=6).read())
                entries = [x for x in r.get("models", []) if x.get("name")]
                break
            except Exception:
                entries = []
                _sleep_mod.sleep(0.8)
        if not entries:
            # ollama 不可达:不把配置里的陈旧映射当可用模型展示(那会让用户选到跑不起来的模型)
            self._model_map = {}
            try:
                _off = "[ Ollama 离线 — 启动后自动重试 ]"
                self.model_cb.configure(values=[_off],
                                        width=max(13, min(self._disp_units(_off), 40)))
                self.model_var.set(_off)
            except Exception:
                pass
            return
        for display, t in _dedupe_model_entries(entries, tag_to_display):
            m[_t(display)] = t
        self._model_map = m
        try:
            self.model_cb["values"] = list(m)
            need = max([13] + [self._disp_units(v) for v in m])
            self.model_cb.configure(width=min(need, 40))
            if self.model_var.get() not in m and m:
                self.model_var.set(list(m)[0])
        except Exception:
            pass

    def __init__(self, root):
        self.root = root
        if not hasattr(root, "style"):
            # 裸 Tk 根(如 tkinterdnd2 的 TkinterDnD.Tk)没有 ttkbootstrap 的
            # .style,build_minimal_theme 依赖它:这里补挂,任何根类型都能进
            try:
                root.style = tb.Style(theme="minty-light")
            except Exception:
                pass
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

        root.title(f"{_t('鸣鸟 · 本地 AI 助手')} — {self.app_version()}")
        # 窗口图标(鸣鸟图形资产暂沿用,发布前重绘)
        try:
            _ic = os.path.join(AGENT_DIR, "app.ico")
            if os.path.exists(_ic):
                root.iconbitmap(_ic)
        except Exception:
            pass
        # DPI 感知缩放系数:Tk 的点阵字体(9pt 等)随系统 DPI 自动缩放,但固定像素
        # 尺寸(轨宽/面板宽/窗口几何)不缩放 — 200% 缩放下 94px 轨只剩一半视觉宽度,
        # 这就是导航按钮文字被裁的根因。系数 = 实际DPI/96(winfo_fpixels('1i')/72
        # 即 Tk 的"每点像素数",再折算到 96DPI 基准)。
        try:
            self._ui_scale = 1.0   # Tk point 已由系统 DPI 处理,不做额外像素缩放(双重放大=巨大 UI bug)
        except Exception:
            self._ui_scale = 1.0
        # 默认开足够大的窗口,保证所有功能露出(避免小窗口只显示左上角)
        try:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            w = min(int(1400 * self._ui_scale), int(sw * 0.95))
            h = min(int(900 * self._ui_scale), int(sh * 0.95))
            root.geometry(f"{w}x{h}")
            root.minsize(min(int(980 * self._ui_scale), sw),
                         min(int(680 * self._ui_scale), sh))
        except Exception:
            root.geometry("1200x860")
            root.minsize(980, 680)
        try:
            root.state("zoomed")   # Windows 下默认最大化;Linux/mac Tk 不支持,失败保持默认尺寸
        except Exception:
            pass

        self._build_toolbar()
        self._build_body()
        self.refresh_models()          # 动态读取 ollama 里的模型(须在控件建成后:离线时用占位符覆盖,防陈旧配置回退)
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
        d = {"theme": "minty-light", "ui_mode": "auto", "ctx": 65536, "temp": 0.0,
             "num_predict": 2048, "sys_enable": False, "sys_text": ""}
        try:
            j = json.load(open(PREFS_FILE, encoding="utf-8")); d.update(j)
        except Exception:
            pass
        return d
    def save_prefs(self):
        json.dump(self.prefs, open(PREFS_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)

    # ================= DPI/排版辅助 =================
    def _scaled_geo(self, w, h):
        """对话框默认几何按 DPI 缩放(固定像素几何在高缩放下会把整页内容挤裁)。"""
        s = getattr(self, "_ui_scale", 1.0)
        return f"{int(w * s)}x{int(h * s)}"

    @staticmethod
    def _disp_units(s):
        """显示宽度估算:CJK/全角按 2 个单位,其余按 1(近似 Tk 平均字符宽度)。"""
        return sum(2 if ord(ch) > 0x2E7F else 1 for ch in str(s))


    # ================= 构建界面(v2:导航轨 + 页面栈) =================
    def _build_toolbar(self):
        """v2 外壳:左侧导航轨。模型/目录/时限等对话要素并入对话页。"""
        import ui_theme as _ut
        self._ui = _ut
        self.T = _ut.tokens("dark")   # 构建期临时配色;apply_theme 统一刷新
        self._themable = []
        self.pages = {}
        self._rail_btns = {}
        self._cur_page = "chat"

        # 轨宽 DPI 感知:按钮字体(点阵)随系统 DPI 缩放,固定 94px 轨不缩放,
        # 200% 下必裁字。改法:字体按缩放系数取整 + 按钮建完后按实测最宽行
        # (Settings/History)定轨宽,双保险保证任何 DPI/任何语言下都不裁字。
        s = getattr(self, "_ui_scale", 1.0)
        self._nav_font = tkfont.Font(family="Microsoft YaHei UI",
                                     size=max(9, int(round(9 * s))))
        rail = tk.Frame(self.root, width=int(94 * s), bd=0, highlightthickness=0)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        self.rail = rail
        tk.Label(rail, text="🐦", font=("Segoe UI Emoji", 15),
                 bg=self.T["elevated"], fg=self.T["text"]).pack(pady=(12, 0))
        tk.Label(rail, text="MB", font=("Segoe UI", 9, "bold"),
                 bg=self.T["elevated"], fg=self.T["muted"]).pack(pady=(0, 8))

        def _nav(pid, icon, label, cmd):
            b = tk.Button(rail, text=icon + "\n" + label,
                          font=self._nav_font, bd=0, relief="flat",
                          bg=self.T["elevated"], fg=self.T["muted"],
                          activebackground=self.T["sel"], activeforeground=self.T["text"],
                          command=cmd)
            b.pack(fill="x", padx=5, pady=3)
            self._rail_btns[pid] = b

        _nav("chat", "💬", _t("对话"), lambda: self.show_page("chat"))
        _nav("history", "🕘", _t("历史"), lambda: self.show_page("history"))
        _nav("logs", "🖥", _t("日志"), lambda: self.show_page("logs"))
        tk.Frame(rail, bg=self.T["elevated"]).pack(fill="both", expand=True)
        _nav("skills", "🧩", _t("技能"), self.show_skills)
        _nav("settings", "⚙", _t("设置"), self.open_settings)
        _nav("about", "ℹ", _t("关于"), self.show_about)
        self.theme_lbl = tk.Label(rail, text="🌓", font=("Segoe UI Emoji", 12),
                                  bg=self.T["elevated"], fg=self.T["muted"], cursor="hand2")
        self.theme_lbl.pack(pady=(4, 10))
        self.theme_lbl.bind("<Button-1>", lambda e: self.cycle_theme())

        # 实测定宽:取全部按钮最宽行 + 左右 padx(2*5) + 内边距余量,与 94*s 取大者
        try:
            need = 0
            for b in self._rail_btns.values():
                for line in str(b.cget("text")).split("\n"):
                    need = max(need, self._nav_font.measure(line))
            rail.configure(width=max(int(94 * s), need + int(26 * s)))
        except Exception:
            rail.configure(width=int(94 * s))

        for pid in ("chat", "history", "logs"):
            f = tk.Frame(self.root, bd=0, highlightthickness=0)
            f.pack(fill="both", expand=True)
            self.pages[pid] = f
        self.show_page("chat")

    def _build_body(self):
        self._build_chat_page()
        self._build_history_page()
        self._build_logs_page()
        self.show_page("chat")

    def show_page(self, pid):
        self._cur_page = pid
        for k, f in self.pages.items():
            if k == pid:
                f.pack(fill="both", expand=True)
            else:
                f.pack_forget()
        self.apply_theme()

    def _build_chat_page(self):
        page = self.pages["chat"]
        bar = tb.Frame(page, padding=(12, 10, 12, 4)); bar.pack(fill="x")
        tb.Label(bar, text=self.app_version(), bootstyle="secondary",
                 font=("Consolas", 9)).pack(side="left", padx=(0, 10))
        tb.Label(bar, text=_t("模型:")).pack(side="left")
        # 不再用配置映射覆盖 _model_map(修复:那会把已卸载的陈旧配置模型塞回下拉,
        # 且空映射时 list(...)[0] 会 IndexError);此处仅用现有映射(若有)建控件,
        # __init__ 紧随其后调 refresh_models() 用 ollama 实况重建。
        if not getattr(self, "_model_map", None):
            _cfg_models = appconfig.model_map()
            self._model_map = {_t(k): v for k, v in _cfg_models.items()}
        _vals = list(self._model_map) or [_t("[ Ollama 离线 — 启动后自动重试 ]")]
        self.model_var = tk.StringVar(value=_vals[0])
        # 下拉宽度按最长显示名适配(CJK 记 2 单位):否则 "qwen2b (长上下文 256K)"
        # 这类名字在闭合态被截断
        _mw = max([13] + [self._disp_units(v) for v in _vals])
        self.model_cb = tb.Combobox(bar, textvariable=self.model_var,
                                    values=_vals,
                                    state="readonly", width=min(_mw, 40),
                                    bootstyle="primary")
        self.model_cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_voice_state())
        self.model_cb.pack(side="left", padx=3)
        self.think_var = tk.BooleanVar(value=True)
        tb.Checkbutton(bar, text=_t("关闭思考"), variable=self.think_var,
                       bootstyle="round-toggle").pack(side="left", padx=6)
        self.sess_lbl = tb.Label(bar, text=_t("会话:无"), bootstyle="secondary")
        self.sess_lbl.pack(side="right")

        bar2 = tb.Frame(page, padding=(12, 0, 12, 4)); bar2.pack(fill="x")
        tb.Label(bar2, text=_t("目录:")).pack(side="left")
        self.wd_var = tk.StringVar(value=os.path.join(DEFAULT_TASKS, "work"))
        self.wd_entry = tb.Entry(bar2, textvariable=self.wd_var)
        self.wd_entry.pack(side="left", fill="x", expand=True, padx=4)
        tb.Button(bar2, text=_t("浏览"), bootstyle="secondary",
                  command=self.choose_dir).pack(side="left")
        tb.Button(bar2, text=_t("打开"), bootstyle="secondary-outline",
                  command=self.open_dir).pack(side="left", padx=(4, 0))
        tb.Label(bar2, text=_t("任务时限:")).pack(side="left", padx=(10, 0))
        self.tb_var = tk.StringVar(value="")
        self.tb_entry = tb.Entry(bar2, textvariable=self.tb_var, width=9, bootstyle="info")
        self.tb_entry.pack(side="left", padx=(2, 4))

        pw = tb.Panedwindow(page, orient="horizontal")
        pw.pack(fill="both", expand=True)
        left = tb.Frame(pw); pw.add(left, weight=1)
        self.transcript = tk.Text(left, font=("Microsoft YaHei UI", 10),
                                  state="disabled", wrap="word", relief="flat",
                                  padx=14, pady=10, bd=0)
        self.transcript.pack(fill="both", expand=True)
        self.input = tk.Text(left, height=3, font=("Microsoft YaHei UI", 10),
                             wrap="word", relief="solid", bd=1)
        self.input.pack(fill="x", padx=(0, 6), pady=(6, 4))
        # 简易交互:Ctrl+V 直接把剪贴板里的文件/截图收为附件;装了 tkinterdnd2
        # 还能把文件拖进输入框。两者都汇入 _attach_paths 的统一附件流。
        self.input.bind("<Control-v>", self._on_paste)
        if _HAVE_DND:
            try:
                self.input.drop_target_register(_DND_FILES)
                self.input.bind("<<Drop>>", self._on_drop)
            except Exception:
                pass
        crow = tb.Frame(left); crow.pack(fill="x", padx=(0, 6))
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

        right = tb.Frame(pw); pw.add(right, weight=0)
        # 固定像素宽在高 DPI 下等于逻辑减半,附件/计划内容会被挤出面板 → 随缩放
        right.configure(width=int(250 * getattr(self, "_ui_scale", 1.0)))
        right.pack_propagate(False)
        tb.Button(right, text=_t("＋ 新对话"), bootstyle="primary",
                  command=self.new_chat).pack(fill="x", padx=(2, 10), pady=(8, 6))
        att = tb.Labelframe(right, text=_t("附件"), padding=6)
        att.pack(fill="x", padx=(2, 10), pady=4)
        self.att_lb = tk.Listbox(att, height=3, font=("Consolas", 9),
                                 exportselection=False, relief="flat")
        self.att_lb.pack(fill="x")
        # 长文件名会被 Listbox 硬裁:加横向滚动,不再截断
        self.att_sb = ttk.Scrollbar(att, orient="horizontal", command=self.att_lb.xview)
        self.att_sb.pack(fill="x")
        self.att_lb.configure(xscrollcommand=self.att_sb.set)
        af = tb.Frame(att); af.pack(fill="x", pady=(3, 0))
        tb.Button(af, text=_t("添加"), bootstyle="success-outline",
                  command=self.add_files).pack(side="left")
        tb.Button(af, text=_t("清空"), bootstyle="danger-outline",
                  command=self.clear_files).pack(side="left", padx=(4, 0))
        self.plan_frame = tb.Labelframe(right, text=_t("计划 (todo)"), padding=6)
        self.plan_frame.pack(fill="both", expand=True, padx=(2, 10), pady=4)
        pf = tb.Frame(self.plan_frame); pf.pack(fill="x")
        self.plan_txt = tk.Text(pf, height=8, font=("Consolas", 9), state="disabled",
                                relief="flat", wrap="word")
        self.plan_sb = tk.Scrollbar(pf, command=self.plan_txt.yview)
        self.plan_txt.configure(yscrollcommand=self.plan_sb.set)
        self.plan_txt.pack(side="left", fill="both", expand=True)
        self.plan_sb.pack(side="right", fill="y")
        # 暗色主题刷新链:裸 Tk 控件必须注册,apply_theme 才会刷色(否则暗色下白底穿帮)
        self._themable += [(self.att_lb, "list"), (self.plan_txt, "list")]

    def _build_history_page(self):
        page = self.pages["history"]
        head = tb.Frame(page, padding=(12, 10, 12, 4)); head.pack(fill="x")
        tb.Label(head, text=_t("历史会话"),
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        self.history_search_var = tk.StringVar(value="")
        ent = tb.Entry(head, textvariable=self.history_search_var)
        ent.pack(side="right", fill="x", expand=True, padx=(16, 0))
        ent.bind("<KeyRelease>", lambda e: self.refresh_sessions())
        body = tb.Frame(page, padding=(12, 4)); body.pack(fill="both", expand=True)
        lbwrap = tb.Frame(body); lbwrap.pack(side="left", fill="both", expand=True)
        self.se_lb = tk.Listbox(lbwrap, font=("Consolas", 10),
                                exportselection=False, relief="flat")
        self.se_lb.pack(side="top", fill="both", expand=True)
        # 长会话名(名字+状态标签)会被硬裁:加横向滚动
        self.se_sb = ttk.Scrollbar(lbwrap, orient="horizontal", command=self.se_lb.xview)
        self.se_sb.pack(side="top", fill="x")
        self.se_lb.configure(xscrollcommand=self.se_sb.set)
        self._themable += [(self.se_lb, "list")]
        btns = tb.Frame(body); btns.pack(side="left", fill="y", padx=(10, 0))
        tb.Button(btns, text=_t("载入"), bootstyle="primary-outline",
                  command=self.load_selected_session).pack(fill="x", pady=(0, 4))
        tb.Button(btns, text=_t("回放"), bootstyle="secondary-outline",
                  command=self.replay_selected_session).pack(fill="x", pady=4)
        tb.Button(btns, text=_t("查看对话"), bootstyle="secondary-outline",
                  command=lambda: self.view_transcript(
                      (self.se_lb.get(self.se_lb.curselection()) or " [").split(" [")[0]
                  ) if self.se_lb.curselection() else None).pack(fill="x", pady=4)

    def _build_logs_page(self):
        page = self.pages["logs"]
        bar = tb.Frame(page, padding=(12, 10, 12, 4)); bar.pack(fill="x")
        tb.Label(bar, text=_t("运行日志"),
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        tb.Button(bar, text=_t("清空输出"), bootstyle="secondary-outline",
                  command=self.clear_log).pack(side="right")
        self.console = tk.Text(page, font=("Consolas", 9), state="disabled",
                               wrap="word", relief="flat", padx=10, pady=8)
        self.console.pack(fill="both", expand=True)
        self._themable += [(self.console, "code")]

    def _build_statusbar(self):
        bar = tb.Frame(self.root, padding=(6, 3)); bar.pack(fill="x", side="bottom")
        self.ctx_bar = tb.Progressbar(bar, maximum=100, value=0, bootstyle="info-striped")
        self.ctx_bar.pack(side="left", fill="x", expand=True)
        self.status_var = tk.StringVar(value=_t(" 上下文: - / - ( - % )"))
        # width=30 装不下 " 上下文: 262144 / 262144 (100%)"(CJK 按 2 单位 ≈32):放宽到 36
        tb.Label(bar, textvariable=self.status_var, bootstyle="secondary",
                 width=36).pack(side="left", padx=(8, 0))
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
        if os.name == "nt":
            subprocess.Popen(["explorer", os.path.normpath(d)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", d])
        else:
            subprocess.Popen(["xdg-open", d])

    # ================= 主题 =================
    def cycle_theme(self):
        order = ["auto", "light", "dark"]
        cur = self.prefs.get("ui_mode", "auto")
        if cur not in order:
            cur = "auto"
        self.prefs["ui_mode"] = order[(order.index(cur) + 1) % len(order)]
        self.save_prefs()
        self.apply_theme()
        self.log_note(_t("[主题: ") + self.prefs["ui_mode"] + "]")

    def apply_theme(self):
        """v2:双主题对等(auto=跟随系统)。颜色出自 ui_theme 令牌;排版沿用原版。"""
        import ui_theme as _ut
        mode = _ut.resolve_theme_mode(self.prefs.get("ui_mode", "auto"))
        self.T = _ut.tokens(mode)
        t = self.T
        tool_fg = "#8A6508" if mode == "light" else "#E8C87A"
        try:
            self.style.theme_use(t["ttk_theme"])
        except Exception:
            pass
        try:
            self.root.configure(bg=t["bg"])
            self.rail.configure(bg=t["elevated"])
            for ch in self.rail.winfo_children():
                try:
                    ch.configure(bg=t["elevated"])
                except Exception:
                    pass
            for k, b in self._rail_btns.items():
                selc = (k == getattr(self, "_cur_page", "chat"))
                b.configure(bg=t["sel"] if selc else t["elevated"],
                            fg=t["text"] if selc else t["muted"])
            self.theme_lbl.configure(bg=t["elevated"], fg=t["muted"])
        except Exception:
            pass
        try:
            self.transcript.configure(bg=t["bg"], fg=t["text"])
            self.input.configure(bg=t["surface"], fg=t["text"],
                                 insertbackground=t["text"])
            for w, kind in getattr(self, "_themable", []):
                if kind == "code":
                    w.configure(bg=t["code_bg"], fg=t["text"])
                elif kind == "list":
                    w.configure(bg=t["surface"], fg=t["text"],
                                selectbackground=t["sel"], selectforeground=t["text"])
                elif kind == "entry":
                    w.configure(bg=t["surface"], fg=t["text"])
        except Exception:
            pass
        if not hasattr(self, "transcript"):
            return   # 构建早期(导航轨先于对话页):transcript 尚未创建,标签重刷跳过
        self.transcript.tag_config("user", background=t["user_bubble"], foreground=t["text"],
                                   font=("Microsoft YaHei UI", 10), lmargin1=12, lmargin2=12,
                                   rmargin=12, spacing1=4, spacing3=4)
        self.transcript.tag_config("asst", foreground=t["text"], background=t["bg"],
                                   font=("Microsoft YaHei UI", 10), lmargin1=12, lmargin2=12)
        self.transcript.tag_config("tool", foreground=tool_fg, background=t["code_bg"],
                                   font=("Consolas", 9), lmargin1=12, lmargin2=12)
        self.transcript.tag_config("note", foreground=t["muted"],
                                   font=("Microsoft YaHei UI", 9))
        self.transcript.tag_config("done", foreground=t["primary"], background=t["sel"],
                                   font=("Microsoft YaHei UI", 10, "bold"),
                                   lmargin1=12, lmargin2=12)
        self.transcript.tag_config("code", foreground=t["text"], background=t["code_bg"],
                                   font=("Consolas", 9), lmargin1=20, lmargin2=20)
        self.transcript.tag_config("spacer", spacing1=6, spacing3=6)
        self.transcript.tag_config("think_region", foreground=t["muted"], background=t["code_bg"],
                                   font=("Microsoft YaHei UI", 9, "italic"),
                                   lmargin1=16, lmargin2=16, rmargin=12)
        self.transcript.tag_config("think_marker", foreground=t["muted"], background=t["code_bg"],
                                   font=("Microsoft YaHei UI", 9, "italic"),
                                   lmargin1=16, lmargin2=16, spacing1=3, spacing3=3)
        self.transcript.tag_bind("think_marker", "<Button-1>", self._toggle_think)

    def _c(self, key, fallback=None):
        return self.style.colors.get(key, fallback or "#222222")

    # ================= 附件 =================
    def add_files(self):
        paths = filedialog.askopenfilenames(title=_t("选择要附加的文件"))
        if paths: self._attach_paths(list(paths))

    def _attach_paths(self, paths, already_copied=False):
        """把文件收入工作目录 _attachments/ 并登记到附件面板。
        对话框、拖入、Ctrl+V 粘贴三个入口共用;返回登记成功的显示名列表。"""
        wd = self.wd_dir()
        attdir = os.path.join(wd, "_attachments")
        os.makedirs(attdir, exist_ok=True)
        names = []
        for p in paths:
            if already_copied:
                dest = p                      # 已在 _attachments 内(如剪贴板截图落盘)
            else:
                base = os.path.basename(p); dest = os.path.join(attdir, base)
                n = 1
                while os.path.exists(dest):
                    dest = os.path.join(attdir, f"{n}_{base}"); n += 1
                try:
                    shutil.copy2(p, dest)
                except Exception as e:
                    self.log_note(_t("[附件失败: {p} → {e}]").format(p=os.path.basename(p), e=e))
                    continue
            self.attachments.append(dest)
            names.append(os.path.basename(dest))
            self.att_lb.insert("end", names[-1])
        return names

    def _insert_attach_tag(self, names):
        """在输入框光标处插一个附件占位标记(真正的随指令发送由 attach_note 完成)。"""
        try:
            self.input.insert("insert", "[📎 " + ", ".join(names) + "] ")
        except Exception:
            pass

    def _on_paste(self, event=None):
        """输入框 Ctrl+V:剪贴板里是文件列表(CF_HDROP)或位图(截图)时直接收为附件,
        都不是则返回 None 回落到 Tk 默认的文本粘贴。"""
        try:
            from PIL import ImageGrab
            got = ImageGrab.grabclipboard()
        except Exception:
            return None
        if not got:
            return None
        if isinstance(got, list) and got:
            names = self._attach_paths([g for g in got if isinstance(g, str)])
            if names:
                self._insert_attach_tag(names)
                return "break"
            return "break"
        if hasattr(got, "save"):              # 位图(截图/复制的图片)
            wd = self.wd_dir()
            attdir = os.path.join(wd, "_attachments")
            os.makedirs(attdir, exist_ok=True)
            dest = os.path.join(attdir, time.strftime("paste_%Y%m%d_%H%M%S") + ".png")
            try:
                got.convert("RGB").save(dest, "PNG")
            except Exception:
                return None
            if self._attach_paths([dest], already_copied=True):
                self._insert_attach_tag([os.path.basename(dest)])
                return "break"
        return None

    def _on_drop(self, event=None):
        """文件拖入输入框:全部收为附件(tkdnd 提供;未装 tkinterdnd2 时无此绑定)。"""
        try:
            paths = list(self.root.tk.splitlist(event.data))
        except Exception:
            return None
        paths = [p for p in paths if os.path.exists(p)]
        if paths:
            names = self._attach_paths(paths)
            if names:
                self._insert_attach_tag(names)
        return "break"
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
        flt = ""
        if hasattr(self, "history_search_var"):
            flt = (self.history_search_var.get() or "").lower()
        files = [f for f in sorted(glob.glob(os.path.join(SESSION_DIR, "*.json")))
                 if not f.endswith(".meta.json")]
        for s in files[-200:]:
            name = os.path.basename(s)[:-5]
            if flt and flt not in name.lower():
                continue
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
        self.log_note(_t("[已载入会话: {name}]").format(name=name))
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

    # ================= 并行派发进度(@@DISPATCH@@ 行协议) =================
    def _on_dispatch(self, payload):
        """主 agent 派发子 agent 的进度:状态栏显示"已派发子任务 X/Y 完成",transcript 落备注。"""
        try:
            ev = json.loads(payload)
        except Exception:
            ev = {}
        phase = ev.get("phase", "")
        total = ev.get("total", 0)
        if phase == "start":
            self.dispatch_state = {"done": 0, "total": total,
                                   "model": ev.get("model", "")}
            self.status_var.set(_t(" 已派发子任务 0/{t} 完成 (模型 {m})").format(
                t=total, m=ev.get("model", "")))
            self.log_note(_t("[并行派发] ") + _t("{n} 条简单子任务派给 {m} 并行做").format(
                n=total, m=ev.get("model", "")))
            return
        if phase == "progress":
            st = getattr(self, "dispatch_state", None) or {}
            done = st.get("done", 0)
            if ev.get("status") in ("ok", "failed", "timeout", "severe", "aborted",
                                    "load_failure"):
                done += 1
                st["done"] = done
            self.status_var.set(_t(" 已派发子任务 {d}/{t} 完成").format(
                d=done, t=st.get("total", ev.get("total", 0))))
            if ev.get("status") not in (None, "running"):
                self.log_note(_t("[并行派发] 子任务 {i}: {s}").format(
                    i=ev.get("index", "?"), s=ev.get("status")))
            return
        if phase == "done":
            self.status_var.set(_t(" 已派发子任务 {o}/{t} 完成").format(
                o=ev.get("ok", 0), t=ev.get("total", 0)))
            self.log_note(_t("[并行派发] 结束: 成功 {o}/{t},回退主模型 {f},严重违规 {sv}").format(
                o=ev.get("ok", 0), t=ev.get("total", 0), f=ev.get("fallback", 0),
                sv=ev.get("severe_violations", 0)))
            return

    def log(self, txt):
        self.console.config(state="normal")
        self.console.insert("end", txt + "\n"); self.console.see("end")
        self.console.config(state="disabled")

    # ================= 关于 / 欢迎 =================
    def show_about(self):
        win = tb.Toplevel(self.root); win.title(_t("ℹ 关于"))
        win.geometry(self._scaled_geo(470, 380))
        win.transient(self.root); win.grab_set()
        tok = self.T   # 旧 MINIMAL 硬编码浅色在暗色主题下穿帮,改用当前主题令牌
        win.configure(bg=tok["bg"])
        # 品牌色横幅(鸣翠):不用 inverse-primary(随 ttkbootstrap 主题变成蓝/杂色)
        tk.Label(win, text=_t("鸣鸟 · 本地 AI 助手"),
                 font=("Microsoft YaHei UI", 14, "bold"),
                 bg=tok["primary"], fg=tok["primary_text"],
                 padx=16, pady=12).pack(fill="x")
        body = tk.Frame(win, bg=tok["bg"]); body.pack(fill="both", expand=True, padx=18, pady=10)
        info = (f"{_t('版本')}: {self.app_version()}\n"
                f"{_t('许可')}: Apache-2.0\n\n"
                f"{_t('全离线·小模型优先的本地 AI agent')}\n"
                f"Ollama + AMD iGPU / NVIDIA / CPU")
        tb.Label(body, text=info, font=MINIMAL["font_body"], bootstyle="secondary",
                 background=tok["bg"],
                 justify="left", anchor="w").pack(fill="x")
        tb.Label(body, text="", background=tok["bg"]).pack()
        # 打开内嵌文档(两行排布:5 个按钮挤一行在 470px 内会溢出被裁)
        df = tb.Frame(body); df.pack(fill="x", pady=(4, 0))
        docs = {"README": "README_EN.md", "RELEASE_NOTES.md": "RELEASE_NOTES.md",
                "AGENTS.md": "AGENTS.md"}
        for label, fn in docs.items():
            tb.Button(df, text=label, bootstyle="secondary-outline",
                      command=lambda n=fn: self._open_doc(n)).pack(side="left", padx=2)
        df2 = tb.Frame(body); df2.pack(fill="x", pady=(4, 0))
        tb.Button(df2, text="LICENSE", bootstyle="secondary-outline",
                  command=lambda: self._open_doc("LICENSE")).pack(side="left", padx=2)
        tb.Button(df2, text=_t("打开安装目录"), bootstyle="secondary-outline",
                  command=lambda: subprocess.Popen(_file_manager_cmd(AGENT_DIR))).pack(side="left", padx=2)
        tb.Button(win, text=_t("关闭"), bootstyle="primary",
                  command=win.destroy).pack(pady=(6, 10))

    def _open_doc(self, fn):
        """打开内嵌文档(exe 目录或 _internal 下)。"""
        for base in (AGENT_DIR, os.path.join(AGENT_DIR, "_internal"),
                     getattr(sys, "_MEIPASS", "")):
            p = os.path.join(base, fn)
            if os.path.exists(p):
                subprocess.Popen(_open_doc_cmd(p))
                return
        self.log(_t("[文档未找到: {fn}]").format(fn=fn))

    def _welcome(self):
        """空状态欢迎语:新对话时给出最快的上手提示。"""
        if self.transcript.get("1.0", "end-1c").strip():
            return
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
        win = tb.Toplevel(self.root); win.title(_t("技能列表"))
        win.geometry(self._scaled_geo(600, 440))
        tb.Label(win, text=_t("本地 agent 可用技能(渐进式:用到才加载全文)"), padding=6).pack(anchor="w")
        tok = self.T   # 暗色主题下不用默认白底
        txt = scrolledtext.ScrolledText(win, font=("Consolas", 9), wrap="word",
                                        bg=tok["surface"], fg=tok["text"],
                                        insertbackground=tok["text"])
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
        win = tb.Toplevel(self.root); win.title(_t("会话历史搜索"))
        win.geometry(self._scaled_geo(640, 480))
        top = tb.Frame(win, padding=6); top.pack(fill="x")
        tb.Label(top, text=_t("关键词:")).pack(side="left")
        kw = tk.StringVar()
        ent = tb.Entry(top, textvariable=kw, width=28); ent.pack(side="left", padx=4)
        ent.bind("<Return>", lambda e: do_search())
        tb.Button(top, text=_t("搜索"), bootstyle="primary", command=lambda: do_search()).pack(side="left")
        fr = tb.Frame(win); fr.pack(fill="both", expand=True, padx=6, pady=2)
        lbwrap = tb.Frame(fr); lbwrap.pack(side="left", fill="both", expand=True)
        tok = self.T   # 暗色主题下列表不用默认白底
        lb = tk.Listbox(lbwrap, font=("Consolas", 9), relief="flat",
                        bg=tok["surface"], fg=tok["text"],
                        selectbackground=tok["sel"], selectforeground=tok["text"])
        lb.pack(side="top", fill="both", expand=True)
        lsb = ttk.Scrollbar(lbwrap, orient="horizontal", command=lb.xview)
        lsb.pack(side="top", fill="x")
        lb.config(xscrollcommand=lsb.set)
        sb = ttk.Scrollbar(fr, orient="vertical", command=lb.yview)
        sb.pack(side="right", fill="y")
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
            if not results: lb.insert("end", _t("(未找到含 '{q}' 的会话)").format(q=q))
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
            self.log_note(_t("[从历史恢复会话: {name}]").format(name=self.session))
            win.destroy()
        bf = tb.Frame(win); bf.pack(pady=4)
        tb.Button(bf, text=_t("查看对话"), command=view_sel).pack(side="left", padx=4)
        tb.Button(bf, text=_t("恢复此会话"), bootstyle="primary", command=load_sel).pack(side="left", padx=4)
        ent.focus_set()

    def view_transcript(self, name):
        win = tb.Toplevel(self.root); win.title(_t("会话回放: {name}").format(name=name))
        win.geometry(self._scaled_geo(760, 560))
        tb.Label(win, text=_t("会话 {name} — 完整对话记录(Ctrl+F 搜索)").format(name=name),
                 padding=6,
                 wraplength=int(700 * getattr(self, "_ui_scale", 1.0))
                 ).pack(anchor="w")
        tok = self.T   # 暗色主题下回放区不用默认白底/黑字
        txt = scrolledtext.ScrolledText(win, font=("Consolas", 9), wrap="word",
                                        bg=tok["bg"], fg=tok["text"],
                                        insertbackground=tok["text"])
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
                txt.insert("end", f"\n━━━ 👤 {_t('用户')} ━━━\n{c}\n", "u")
            elif role == "assistant":
                for tc in m.get("tool_calls", []):
                    fn = tc.get("function", {})
                    txt.insert("end", f"\n⚙ {fn.get('name','')} {json.dumps(fn.get('arguments',{}), ensure_ascii=False)[:120]}\n", "t")
                if c: txt.insert("end", f"\n▸ {c}\n", "a")
            elif role == "tool":
                txt.insert("end", f"   ↳ {str(c)[:200]}\n", "r")
        txt.tag_config("u", foreground="#1a5fb4", font=("Microsoft YaHei UI", 10, "bold"))
        txt.tag_config("a", foreground=tok["text"])     # 旧值 #000000 在暗色下不可读
        txt.tag_config("t", foreground="#a34e00")
        txt.tag_config("r", foreground=tok["muted"])
        txt.config(state="disabled")

    # ================= 设置 =================
    def open_settings(self):
        win = tb.Toplevel(self.root); win.title(_t("设置"))
        win.geometry(self._scaled_geo(560, 540))
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
        # tb.Spinbox(ttkbootstrap 样式):裸 ttk.Spinbox 在暗色主题下白底白字不可读
        temp = tb.Spinbox(r1, from_=0.0, to=2.0, increment=0.1, width=6)
        temp.set(prefs["temp"]); temp.pack(side="left", padx=6)
        tb.Label(r1, text=_t("输出上限:")).pack(side="left")
        np = tb.Combobox(r1, values=[512, 1024, 2048, 4096, 8192], width=8, state="readonly")
        np.set(prefs["num_predict"]); np.pack(side="left", padx=6)
        sys_en = tk.BooleanVar(value=prefs["sys_enable"])
        tb.Checkbutton(body, text=_t("启用自定义系统提示(替代内置,可大幅改造行为)"),
                       variable=sys_en, bootstyle="round-toggle").pack(anchor="w", pady=(8,2))
        # 裸 Tk Text 按当前主题令牌上色(默认白底在暗色主题下穿帮)
        tok = self.T
        sys_txt = scrolledtext.ScrolledText(body, height=10, font=("Consolas", 9), wrap="word",
                                            bg=tok["surface"], fg=tok["text"],
                                            insertbackground=tok["text"])
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
            self.log_note(_t("[忙:当前任务运行中,先停止再发送]")); return
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
            self.mic_btn.configure(text=_t("🎤 语音") if ok else _t("🎤 无音频"))
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
            _err = str(e)
            self.root.after(0, lambda: self._voice_done("", _t("转写失败: ") + _err))
    def _kill_tree(self):
        """停止/关窗时按进程树终止(孙进程孤儿会占住 GPU 与管道)。"""
        try:
            if self.proc and self.proc.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                                   capture_output=True)
                else:
                    self.proc.kill()
        except Exception:
            pass

    def _voice_done(self, text, stt):
        self._voice_busy = False
        self._voice_rec = None
        if text:
            self.input.delete("1.0", "end")
            self.input.insert("1.0", text.strip())
            self.log_note(_t("[语音已转录({stt})并填入输入框]").format(stt=stt))
        else:
            self.log_note(_t("[语音转录无结果:{stt} 转写能力有限,可换用更强音频模型]").format(stt=stt))
        # 按当前模型能力恢复按钮态:非音频模型下不能无条件恢复"可用"
        # (旧写法先设回"🎤 语音"再比较,条件恒真,禁用态丢失)
        self.refresh_voice_state()

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
        if not self._model_map:
            self.log_note(_t("[无法启动:模型清单为空 — Ollama 未就绪,请先启动 Ollama]"))
            return
        # 查不到时用原选择本身,绝不静默回退到"第一个模型"(选 A 跑 B)
        model = self._model_map.get(self.model_var.get(), self.model_var.get())
        workdir = self.wd_var.get() if hasattr(self, "wd_var") else os.path.join(DEFAULT_TASKS, "work")
        task = task + self.attach_note()
        os.makedirs(workdir, exist_ok=True)
        taskfile = os.path.join(workdir, "task_input.txt")
        with open(taskfile, "w", encoding="utf-8") as f: f.write(task)
        if not resume_ok:
            ck = os.path.join(workdir, ".agent_state.json")
            if os.path.exists(ck): os.remove(ck); self.log_note(_t("[已清除旧进度]"))
            # 上一任务遗留的 todo.json 必须一并清掉:否则计划面板会一直显示旧清单,
            # 用户看到的是上个任务的"已勾完"列表,误以为新任务没有计划。
            try:
                tj = os.path.join(workdir, "todo.json")
                if os.path.exists(tj): os.remove(tj)
                self._render_plan([], force=True)
            except Exception:
                pass
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
        self._apply_time_budget(env, task)
        self.log(f"====== {_t('开始: ')}{model}" + (f" | {_t('会话:')}{self.session}" if self.session else "") + " ======")
        self.log(_t("工作目录: ") + workdir + "\n")
        self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,   # 守护系统:GUI 通过 stdin 回传越界确认
            text=True, encoding="utf-8", errors="replace", env=env, bufsize=1)
        threading.Thread(target=self.reader, daemon=True).start()
        self.send_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

    def _apply_time_budget(self, env, task):
        """任务时限(Task #73):输入框值(分钟/小时)→ AGENT_TIME_BUDGET_SEC 传给 harness。
        任务描述里自述的时限(如"尽量在30分钟内")优先,并回填输入框让用户看见。"""
        try:
            from ollama_agent import (parse_duration_str, parse_time_budget,
                                      budget_env_value, TIME_BUDGET_PARSE)
        except Exception as _e:
            self.log_note(_t("[任务时限不可用:无法加载解析器 {e}]").format(e=_e))
            return
        minutes = parse_duration_str(self.tb_var.get())
        src = "manual"
        if TIME_BUDGET_PARSE and task:
            hit = parse_time_budget(task)
            if hit:
                minutes, src = hit, "prompt"
                self.tb_var.set(f"{hit:g}")
        sec = budget_env_value(minutes)
        if sec:
            env["AGENT_TIME_BUDGET_SEC"] = sec
            label = (_t("[已从任务描述识别时限 {n} 分钟,优先于手填值]")
                     if src == "prompt" else _t("[任务时限 {n} 分钟,超时会收到收尾提醒]"))
            self.log_note(label.format(n=f"{minutes:g}"))

    def reader(self):
        for line in iter(self.proc.stdout.readline, ""):
            self.q.put(line.rstrip("\n"))
        self.q.put(None)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self._kill_tree(); self.log("\n" + _t("[已停止,重跑并勾选'续跑'可从中断处继续]"))
            self.log_note(_t("[已停止 — 重跑勾选'续跑'可从中断处继续]"))

    # ================= 流解析 =================
    def poll(self):
        try:
            while True:
                line = self.q.get_nowait()
                if line is None:
                    self._collapse_think()
                    self._flush_asst()
                    self.log("\n===== " + _t("任务结束") + " =====")
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
        """Ollama 在线状态灯:绿=在线有模型,黄=在线无模型,红=离线。
        自愈:在线且模型清单变化时自动刷新下拉(启动瞬间查询失败的下拉会在此自愈)。
        比较集合必须与 refresh_models 同源(同一去重规则):拿原始 tag 集合去比
        去重后的下拉值,会在存在 ollama cp 别名时恒不等 → 每 5 秒主线程重刷。"""
        up = False; has_models = False
        try:
            import urllib.request as _ur
            r = json.loads(_ur.urlopen(appconfig.ollama_host().rstrip("/") + "/api/tags", timeout=2).read())
            up = True; has_models = bool(r.get("models"))
            # 自愈条件:当前下拉框里的 tag 集合 != 去重后的应有集合
            # (覆盖:启动时 ollama 未就绪走了配置回退 / 用户 pull 了新模型 / 卸载了模型)
            cur_tags = frozenset(getattr(self, "_model_map", {}).values())
            tag_to_display = {v: k for k, v in appconfig.model_map().items()}
            want_tags = frozenset(t for _, t in _dedupe_model_entries(r.get("models", []), tag_to_display))
            if cur_tags != want_tags:
                self.refresh_models()
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
            self.log_note(_t("[尝试启动 Ollama…]"))
            self._try_start_ollama()
        else:
            from tkinter import messagebox
            messagebox.showinfo(_t("Ollama"),
                                _t("Ollama 已在线。本 agent 全离线运行,数据不离开本机。")
                                if _LANG == "zh" else
                                "Ollama is online. This agent runs fully offline — data never leaves your machine.")
        # 状态立即刷新交由已有的 5s 自续链处理,这里不再叠加一条永久链

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

    def _ask_approval(self, req):
        """守护系统:agent 请求越界操作,弹确认框,用户选择后写回 stdin。
        按钮:允许一次 / 拒绝 / 允许全部(本轮)。超时或进程退出默认拒绝。"""
        try:
            tool = req.get("tool", "?")
            path = req.get("path", "?")
            action = req.get("action", "访问")
            wd = req.get("workdir", "?")
            win = tb.Toplevel(self.root)
            win.title(_t("⚠ 越界操作确认"))
            win.geometry(self._scaled_geo(580, 300))
            win.attributes("-topmost", True)
            tb.Label(win, text=_t("AI 想访问工作目录之外的文件"), bootstyle="warning",
                     font=("Microsoft YaHei UI", 12, "bold"), padding=8).pack(anchor="w")
            txt = (f"{_t('工具:')} {tool}\n"
                   f"{_t('操作:')} {_t(str(action))}\n"
                   f"{_t('目标:')} {path}\n\n"
                   f"{_t('工作目录:')} {wd}\n\n"
                   f"{_t('允许这次访问吗?')}")
            tb.Label(win, text=txt, justify="left", padding=(10, 4),
                     font=("Microsoft YaHei UI", 10),
                     wraplength=int(540 * getattr(self, "_ui_scale", 1.0))
                     ).pack(fill="both", expand=True, padx=6)
            btnrow = tb.Frame(win); btnrow.pack(fill="x", padx=8, pady=8)
            result = {}
            def _reply(v):
                result["v"] = v
                win.destroy()
            tb.Button(btnrow, text=_t("允许一次"), bootstyle="success",
                      command=lambda: _reply("@allow")).pack(side="left", padx=4)
            tb.Button(btnrow, text=_t("允许全部(本轮)"), bootstyle="primary",
                      command=lambda: _reply("@allow_all")).pack(side="left", padx=4)
            tb.Button(btnrow, text=_t("拒绝"), bootstyle="secondary",
                      command=lambda: _reply("@deny")).pack(side="left", padx=4)
            # 超时默认拒绝:60s 后自动关(agent 侧 120s 超时,这里提前响应避免卡死)
            win.after(60000, lambda: _reply("@deny") if not result else None)
            win.grab_set()
            win.wait_window()
            choice = result.get("v", "@deny")
        except Exception:
            choice = "@deny"
        # 写回 stdin 给 agent
        try:
            if self.proc and self.proc.stdin and self.proc.poll() is None:
                self.proc.stdin.write(choice + "\n")
                self.proc.stdin.flush()
        except Exception:
            pass

    def feed_transcript(self, line):
        if line.startswith("@@ASK@@"):
            try:
                req = json.loads(line[len("@@ASK@@"):])
            except Exception:
                req = {}
            self.log_note(_t("[越界操作请求,请确认]") + " " + req.get("path", "?"))
            self._ask_approval(req)
            return
        if line.startswith("@@TOK@@"):
            self._stream_tok(line[len("@@TOK@@"):])
            return
        if line.startswith("@@THINK@@"):
            self._stream_think(line[len("@@THINK@@"):])
            return
        if line.startswith("@@DISPATCH@@"):
            self._on_dispatch(line[len("@@DISPATCH@@"):])
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
        t = None
        try:
            t = json.load(open(tf, encoding="utf-8"))
            if not isinstance(t, list): t = None
        except Exception:
            t = None
        self._render_plan(t or [])
        self.root.after(500, self.poll_todo)

    @staticmethod
    def _format_plan(todo_list):
        """与 harness 回执同一份格式化(ollama_agent.format_todo_lines);导入失败时
        本地兜底,保证计划面板在打包环境也能显示。"""
        try:
            import ollama_agent
            return ollama_agent.format_todo_lines(todo_list)
        except Exception:
            return "\n".join(f"{'[x]' if x.get('done') else '[ ]'} {i}. {x.get('item','')}"
                             for i, x in enumerate(todo_list, 1))

    def _render_plan(self, todo_list, force=False):
        """渲染计划面板:内容与 harness 回执同源(ollama_agent.format_todo_lines),
        标题带进度(x/y),内容变化时滚动到第一个未完成项——长列表 + 4 行小窗
        曾让"正在做第几项"完全落在可视区外。"""
        todo_list = todo_list or []
        done, total = 0, len(todo_list)
        for x in todo_list:
            try:
                if x.get("done"): done += 1
            except AttributeError:
                pass
        text = self._format_plan(todo_list) if total else _t("(尚无计划 — agent 会先建 todo 再执行)")
        title = _t("计划 (todo)") + (f"  {done}/{total}" if total else "")
        try:
            self.plan_frame.configure(text=title)
        except Exception:
            pass
        self.plan_txt.config(state="normal")
        if force or self.plan_txt.get("1.0", "end").strip() != text.strip():
            self.plan_txt.delete("1.0", "end")
            self.plan_txt.insert("1.0", text)
            # 滚到第一个未完成项(全部完成则滚到末尾),让"当前进度"落在可视区
            target = None
            for idx, x in enumerate(todo_list, 1):
                if not x.get("done"): target = idx; break
            if target is None and total: target = total
            if target is not None:
                self.plan_txt.see(f"{target}.0")
        self.plan_txt.config(state="disabled")

    def on_close(self):
        if self.proc and self.proc.poll() is None: self._kill_tree()
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
    if len(sys.argv) > 1 and os.path.basename(sys.argv[1]) == "ollama_agent.py":
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
            _mb.showwarning(_t("鸣鸟 · 本地 AI 助手"), _t("未能自动启动 ollama,请先手动运行 ollama serve。"))
    except Exception:
        pass
    if _HAVE_DND:
        # tkdnd 根窗口:ttkbootstrap 的 Window 自带 .style,裸 Tk 根必须补挂,
        # 否则 build_minimal_theme 读 root.style 直接 AttributeError
        root = TkinterDnD.Tk()
        root.title(_t("鸣鸟 · 本地 AI 助手"))
        try:
            root.style = tb.Style(theme="minty-light")
        except Exception:
            pass
    else:
        root = tb.Window(themename="minty-light", title=_t("鸣鸟 · 本地 AI 助手"))
    app = AgentGUI(root)
    root.mainloop()
