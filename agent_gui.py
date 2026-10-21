#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""鸣鸟 · 本地 AI 助手 — Windows 桌面 GUI v4(现代化)
基于 ttkbootstrap 的聊天工作区设计:
- 侧边栏:附件 / 会话 / 计划(todo)
- 主区:💬 对话(聊天气泡视图) + 🖥 日志(流式控制台)
- 📎 文件上传:复制到工作目录 _attachments/,agent 按需读取
- ⚙ 设置:上下文窗口 / 温度 / 输出上限 / 自定义系统提示(持久化)
- 🌓 主题切换(darkly / superhero / flatly / cosmo ...)
- 快捷键:Ctrl+N 新对话 · Ctrl+F 历史搜索 · Enter 发送 · Shift+Enter 换行 · Ctrl+L 清日志
"""
import tkinter as tk
from tkinter import ttk, filedialog, font as tkfont
from tkinter import scrolledtext
import ttkbootstrap as tb
import subprocess, threading, os, queue, sys, re, glob, json, time, shutil
import voice_input
import appconfig   # 统一配置层:Ollama 地址/模型映射等由用户配置,不硬编码
import platform_profile   # v3.0.0:平台差异单一事实源(文件管理器/编辑器命令等共用)
import ui_v4 as v4        # v4.0:侧边栏/圆角按钮/主题化 UI 原语
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
    """Open a directory in the platform file manager.(v3.0.0:收敛到 platform_profile)"""
    return platform_profile.open_folder_cmd(path)


def _open_doc_cmd(path):
    """Open a document with the platform default text viewer.(v3.0.0:同上)"""
    return platform_profile.open_doc_cmd(path)


def _atomic_json(path, data):
    """GUI 侧 JSON 落盘:临时文件 + os.replace(进程中途被杀不截断原文件)。"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
# ============ 国际化:自动检测语言(OS 中文→中文,否则英文),可用 AGENT_LANG 强制 ============
def _os_ui_lang_zh():
    """v2.0.0:OS 界面语言探测。GUI 程序在 mac/win 上拿不到 shell 的 LANG 环境变量
    (mac 从 Finder/Dock 启动无 LANG;win 图形/服务环境也常无),中文系统用户会被
    误判成英文——mac 用户实测反馈"装完没有中文"。env 缺失时再问系统本体。"""
    try:
        if sys.platform == "win32":
            import ctypes
            # 0x0804 zh-CN / 0x0404 zh-TW / 0x0C04 zh-HK / 0x1004 zh-SG / 0x1404 zh-MO
            return ctypes.windll.kernel32.GetUserDefaultUILanguage() in (
                0x0804, 0x0404, 0x0C04, 0x1004, 0x1404)
        if sys.platform == "darwin":
            out = subprocess.run(["defaults", "read", "-g", "AppleLocale"],
                                 capture_output=True, timeout=5,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                                 ).stdout.decode("utf-8", "replace")
            return out.strip().lower().startswith("zh")
        if sys.platform.startswith("linux"):
            import locale
            loc = (os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES")
                   or os.environ.get("LANG") or "")
            if not loc:
                try:
                    loc = locale.getlocale()[0] or ""
                except Exception:
                    loc = ""
            return str(loc).lower().startswith("zh")
    except Exception:
        pass
    return False


_LANG = os.environ.get("AGENT_LANG", "")
if not _LANG:
    try:
        if (os.environ.get("LANG", "") or "").startswith("zh") or \
                "Chinese" in os.environ.get("LANGUAGE", ""):
            _LANG = "zh"
        elif _os_ui_lang_zh():
            _LANG = "zh"
        else:
            _LANG = "en"
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
    "思考:": "Thinking:", "默认": "Default", "开": "On", "关": "Off",
    "[思考: ": "[Thinking: ", "留空=用 Ollama 默认": "(empty = Ollama default)",
    "温度输入无效,已保留原设置": "Invalid temperature; previous setting kept",
    "⚙ 设置": "⚙ Settings", "🌓 主题": "🌓 Theme",
    "＋ 新对话": "＋ New Chat", "添加附件": "Attachments", "清空": "Clear",
    "[新对话已开启:上下文与工作目录已重置]":
        "[New chat started: context and working directory reset]",
    "[断网模式已开启:本任务无联网工具与云端 — 联网搜索类请求无法满足,请先点 🔒 切回联网]":
        "[Offline mode is ON: no web tools or cloud for this task — web-search "
        "requests cannot be fulfilled; toggle 🔒 back online first]",
    "会话": "Sessions", "计划": "Plan", "💬 对话": "💬 Chat", "🖥 日志": "🖥 Logs",
    "发送": "Send", "换行": "New line", "🎤 语音": "🎤 Voice", "🎤 无音频": "🎤 No Audio", "■ 停止录音": "■ Stop",
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
    "输入任务或对话,Enter 发送。可以直接说:": "Type a task or chat — Enter to send. Try:",
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
    "输入任务或对话…(Enter 发送 · Shift+Enter 换行)": "Type a task or chat… (Enter to send · Shift+Enter for newline)",
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
    "[语音语言: 中文]": "[Voice language: Chinese]",
    "[语音语言: 英文]": "[Voice language: English]",
    "[设置已保存:自下一个任务起生效(运行中的任务不受影响)]":
        "[Settings saved: takes effect from the next task (running task unaffected)]",
    "技能目录": "Skill directories",
    "已装技能": "Installed skills",
    "已配置 MCP 服务器": "Configured MCP servers",
    "(未配置 MCP 服务器)": "(No MCP servers configured)",
    "配置文件": "Config file",
    "对话中说\"用 MCP\"或让它 enable_tools 即可调用;配置文件:": "Say \"use MCP\" in chat or let the agent enable_tools; config:",
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

def _first_msg_title(msg, limit=15):
    """v2.0.2 会话命名:新对话第一句话前 15 字(首行、去文件名非法字符、
    折叠空白)。空 → ""(调用方退回 chat_ 前缀)。纯程序,不起模型调用。"""
    s = str(msg or "").split("\n")[0].strip()
    s = re.sub(r'[\\/:*?"<>|\r\t]', "", s)
    s = re.sub(r"\s+", " ", s).strip().strip(". ")
    return s[:limit].rstrip()

# v1.8.0 一键断网/联网(offline mode):断网=仅本地模型+禁联网工具+禁 url 型 MCP,
# 零出站(netstat 可验证);联网=本地+搜索+已配置的 MCP/云端 provider。
# v4 桌面 UI 新增文案(侧边栏/计划抽屉/输入卡/空状态)
_T["鸣鸟 · 本地 AI 助手"] = "Mingbird · Local AI Assistant"
_T["鸣鸟"] = "Mingbird"
_T["你"] = "You"
_T["新对话"] = "New chat"
_T["搜索对话"] = "Search chats"
_T["语音"] = "Voice"
_T["目录"] = "Folder"
_T["目录 · "] = "Folder · "
_T["时限"] = "Limit"
_T["时限 "] = "Limit "
_T["任务设置"] = "Task settings"
_T["工作目录"] = "Working directory"
_T["任务时限(分钟或小时,留空=不限)"] = "Time limit (minutes or hours; empty = none)"
_T["例: 40 / 1.5h"] = "e.g. 40 / 1.5h"
_T["浏览"] = "Browse"
_T["打开"] = "Open"
_T["保存"] = "Save"
_T["取消"] = "Cancel"
_T["本地优先 · 小模型优先"] = "Local-first · small-model-first"
_T["历史会话 · 下一条消息接续上下文"] = "History · the next message continues this context"
_T["有什么可以帮你?"] = "What can I help you with?"
_T["本地优先 · 小模型优先 · 数据不出本机"] = \
    "Local-first · small-model-first · data never leaves this machine"
_T["写一个 Python 脚本并跑测试"] = "Write a Python script and run its tests"
_T["整理这个目录里的文件"] = "Organize the files in this folder"
_T["查资料并汇总成报告"] = "Research a topic and write a report"
_T["解释这段代码在做什么"] = "Explain what this code does"
_T["Enter 发送 · Shift+Enter 换行;点上面的建议可直接填入输入框。"] = \
    "Enter to send · Shift+Enter for a new line; click a suggestion to fill the composer."
_T["(尚无计划 — agent 会先建 todo 再执行)"] = \
    "(no plan yet — the agent creates a todo list first)"
_T["实时"] = "live"
# 命名口径:联网模式下推理仍在本地,但搜索/MCP/云端会出站,不能标"零出站"。
_T["联网 · 本地推理"] = "Online · local inference"
_T["断网 · 零出站"] = "Offline · zero egress"
_T["联网 · 云端模型"] = "Online · cloud model"
_T["云端 API"] = "Cloud API"
_T["云端仅联网可用；api_key 只存本机"] =     "Cloud needs network; api_key stays in the local config only"
_T["云端配置不完整:需要端点与模型名,未启用"] =     "Incomplete cloud config: endpoint and model are required (not enabled)"
_T["云端模型需联网:先在顶部切回本地模型,再开断网"] =     "Cloud models need network; switch back to a local model before going offline"
# v4.1 设置对话框分区/提示
_T["设置"] = "Settings"
_T["上下文窗口"] = "Context window"
_T["温度"] = "Temperature"
_T["输出上限"] = "Max output"
_T["留空=用 Ollama 默认"] = "empty = Ollama default"
_T["推理引擎"] = "Inference engine"
_T["生成参数"] = "Generation"
_T["命令输出"] = "Command output"
_T["系统提示"] = "System prompt"
_T["保存后自下一个任务起生效"] = "Applies from the next task"
_T["本地服务 API Key 可空"] = "local service API key (optional)"
_T["端点"] = "Endpoint"
_T["启用自定义系统提示(替代内置,可大幅改造行为)"] = \
    "Use a custom system prompt (replaces the built-in one)"
# v4.1 深层对话框(关于/技能/搜索/回放/越界确认)
_T["关于"] = "About"
_T["版本"] = "Version"
_T["许可"] = "License"
_T["全离线·小模型优先的本地 AI agent"] = \
    "An offline-first, small-model-first local AI agent"
_T["打开安装目录"] = "Open install folder"
_T["关闭"] = "Close"
_T["技能列表"] = "Skills"
_T["已装技能"] = "Installed"
_T["技能目录"] = "Skill folders"
_T["(暂无技能)"] = "(no skills yet)"
_T["渐进式加载 · 只列名字与一句话描述"] = \
    "Progressive disclosure · names and one-line descriptions"
_T["会话历史搜索"] = "Search chats"
_T["搜索"] = "Search"
_T["查看对话"] = "View chat"
_T["恢复此会话"] = "Restore this chat"
_T["双击结果查看完整对话"] = "Double-click a result to view the full chat"
_T["会话回放"] = "Chat replay"
_T["(读取失败)"] = "(read failed)"
_T["(输入关键词再搜索)"] = "(type a keyword and search)"
_T["(未找到含 '{q}' 的会话)"] = "(no chat contains '{q}')"
_T["⚠ 越界操作确认"] = "⚠ Out-of-workspace access"
_T["AI 想访问工作目录之外的文件"] = \
    "The AI wants to access a file outside the working folder"
_T["目标不在当前工作目录内,需要你确认这一次的访问。"] = \
    "The target is outside the working folder; confirm this one access."
_T["工具"] = "Tool"
_T["操作"] = "Action"
_T["目标"] = "Target"
_T["允许一次"] = "Allow once"
_T["允许全部(本轮)"] = "Allow all (this run)"
_T["拒绝"] = "Deny"
_T["上下文: - / - ( - % )"] = "Context: - / - ( - % )"
_T["模型"] = "Model"
_T["思考 · "] = "Thinking · "
_T["● 联网"] = "● Online"
_T["● 断网"] = "● Offline"
_T["☁ 云端"] = "☁ Cloud"
_T["☁ 断网禁用"] = "☁ disabled offline"
_T["还没有对话"] = "No conversations yet"
_T["今天"] = "Today"
_T["昨天"] = "Yesterday"
_T["更早"] = "Earlier"

_T["任务完成"] = "Task complete"
_T["不限"] = "Unlimited"
_T["命令输出精简"] = "Compact command output"
_T["自动(≤32K)"] = "Auto (≤32K)"
_T["环境变量覆盖中"] = "overridden by env var"
_T["超长输出只留末尾"] = "trim long outputs to the tail"
# v3.1.1 会话管理(侧栏右键菜单)
_T["打开"] = "Open"
_T["归档(移出列表,文件保留)"] = "Archive (hide from list, files kept)"
_T["删除…"] = "Delete…"
_T["删除对话"] = "Delete conversation"
_T["确定彻底删除对话(转录/计划一并删除,不可恢复;只想移出列表请用「归档」)?"] = \
    "Permanently delete this conversation (transcript and plan included, unrecoverable; use Archive to just hide it)?"
_T["[已归档会话(文件移入 sessions/_archived,可随时找回)]"] = \
    "[Archived (files moved to sessions/_archived, recoverable anytime)]"
_T["[已删除会话(不可恢复)]"] = "[Conversation deleted (unrecoverable)]"
_T["[归档失败:找不到会话文件]"] = "[Archive failed: session files not found]"
_T["[任务运行中暂不能归档当前会话——请先停止或等它完成]"] = \
    "[Cannot archive the current conversation while a task is running — stop it or wait]"
_T["[任务运行中暂不能删除当前会话——请先停止或等它完成]"] = \
    "[Cannot delete the current conversation while a task is running — stop it or wait]"
_T["开"] = "On"
_T["关"] = "Off"
# v2.1.1 多引擎(OpenAI 兼容本地服务)
_T["本地引擎:"] = "Local engine:"
_T["自定义 OpenAI 兼容"] = "Custom OpenAI-compatible"
_T["端点(Ollama 引擎忽略);本地服务 API Key 可空:"] = \
    "Endpoint (ignored on Ollama); API key optional for local servers:"
_T["本地引擎"] = "Local engine"
_T["OpenAI 兼容引擎需要手动启动:\n请先打开 LM Studio / llama.app,\n或运行 llama-server 后再试。\n端点: {url}"] = \
    "The OpenAI-compatible engine must be started manually:\nopen LM Studio / llama.app,\nor run llama-server first.\nEndpoint: {url}"
_T["OpenAI 兼容引擎未就绪:{url}\n请先启动 LM Studio / llama.app / llama-server。"] = \
    "OpenAI-compatible engine not reachable: {url}\nStart LM Studio / llama.app / llama-server first."
_T["{eng} ✓(无模型)"] = "{eng} ✓ (no models)"
_T["{eng} ✗ 未启动"] = "{eng} ✗ not running"
_T["[ {eng} 离线 — 启动后自动重试 ]"] = "[ {eng} offline — auto-retry once started ]"
# v2.1.3 会话绑定工作目录
_T["[已恢复该会话的工作目录: {d}]"] = "[Restored this conversation's workdir: {d}]"
# v2.1.4 会话切换防护
_T["[任务运行中暂不能切换会话——请先停止或等它完成]"] = \
    "[Can't switch conversations while a task is running — stop it or wait]";
_T["🌐 联网"] = "🌐 Online"
_T["🔒 断网"] = "🔒 Offline"
_T["(本地)"] = "(local)"
_T["☁ 未配置"] = "☁ not configured"
_T["[请先在左侧选择本地模型,或在右侧选择云端模型]"] = \
    "[Pick a local model on the left, or a cloud model on the right, first]"
_T["[已切回本地模型]"] = "[Switched back to the local model]"
_T["[已切回本地模型:云端开关关闭]"] = "[Switched back to the local model: cloud toggle off]"
_T["[云端已启用:后续任务改经 {m} 推理,api_key 只存本机;随时可切回]"] = \
    "[Cloud enabled: subsequent tasks run via {m}; api_key stays on this machine; switch back anytime]"
_T["云端模型配置(可选)"] = "Cloud model setup (optional)"
_T["[断网模式:仅本地模型,联网工具与云端已禁用 — 零出站]"] = \
    "[Offline mode: local model only; web tools & cloud disabled — zero outbound]"
_T["[联网模式:搜索/已配置的 MCP/云端可用]"] = \
    "[Online mode: search / configured MCP / cloud available]"
_T["[断网开关写入配置失败]"] = "[Failed to save the offline toggle]"
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

# 与 appconfig 同源:便携/隔离模式(MINGBIRD_HOME)下会话/偏好/技能必须一起搬。
# 旧版这里硬编码 ~/.ollama_agent,agent 存到 MINGBIRD_HOME、GUI 却读旧目录(复审发现)。
AGENT_HOME = appconfig.AGENT_HOME
SESSION_DIR = os.path.join(AGENT_HOME, "sessions")
def _skill_scan_dirs():
    """技能扫描目录。PyInstaller 6 onedir 把 datas 装进 _internal(=sys._MEIPASS),
    安装版 EXE 根目录下没有 skills/,不扫打包资源目录就列不出内置技能(#6)。"""
    dirs = []
    if getattr(sys, "_MEIPASS", ""):
        dirs.append(os.path.join(sys._MEIPASS, "skills"))
    dirs += [os.path.join(AGENT_DIR, "skills"),
             os.path.join(AGENT_HOME, "skills")]
    return dirs
SKILL_DIRS = _skill_scan_dirs()
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

    def refresh_models(self, quick=False):
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
        _lb = appconfig.backend_openai()
        for _ in range(1 if quick else 3):
            try:
                if _lb:
                    # v2.1.1 OpenAI 兼容引擎:GET /models(OpenAI 形态 {"data":[{"id":..}]},
                    # LM Studio/llama.app/llama-server 同构)→ 归一成 /api/tags 的 entries 形态
                    r = json.loads(_ur.urlopen(_lb["base_url"] + "/models",
                                               timeout=2 if quick else 6).read())
                    entries = [{"name": x.get("id")} for x in (r.get("data") or []) if x.get("id")]
                else:
                    r = json.loads(_ur.urlopen(f"{appconfig.ollama_host()}/api/tags",
                                               timeout=2 if quick else 6).read())
                    entries = [x for x in r.get("models", []) if x.get("name")]
                break
            except Exception:
                entries = []
                if not quick:
                    _sleep_mod.sleep(0.8)
        if not entries:
            # 引擎不可达:不把配置里的陈旧映射当可用模型展示(那会让用户选到跑不起来的模型)
            self._model_map = {}
            try:
                if appconfig.cloud_provider():
                    self.model_var.set("")
                else:
                    _off = f"[ {appconfig.engine_display_name()} 离线 — 启动后自动重试 ]"
                    self.model_var.set(_off)
                self._sync_model_btn()
            except Exception:
                pass
            return
        for display, t in _dedupe_model_entries(entries, tag_to_display):
            m[_t(display)] = t
        self._model_map = m
        try:
            if appconfig.cloud_provider():
                self.model_var.set("")
            elif self.model_var.get() not in m and m:
                self.model_var.set(list(m)[0])
            self._sync_model_btn()
            self._sync_cloud_box()
        except Exception:
            pass

    def __init__(self, root):
        self.root = root
        # 先按平台挑可用字体族,再建控件(ui_v4 的 FONT_* 会被就地刷新)
        try:
            v4.init_fonts(root)
        except Exception:
            pass
        for _k, _v in (("font_title", v4.FONT_TITLE), ("font_body", v4.FONT),
                       ("font_small", v4.FONT_SM), ("font_mono", v4.MONO)):
            try:
                MINIMAL[_k] = _v
            except Exception:
                pass
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
        self.session_title = ""       # 旧版会话的模型标题(仅加载历史时从 meta 恢复显示)
        self._sess_names = []         # v2.0.1 会话列表行号→文件名(显示名加了标题前缀,不再反解字符串)
        self.attachments = []      # 已复制的附件绝对路径
        self._rendered_session = None  # 当前 transcript 对应的会话名
        self._new_chat_guard = False
        self._asst_buf = ""            # 多行助手回答缓冲
        self._voice_busy = False
        self._voice_rec = None
        self._voice_stop_timer = None
        self._vad_timer = None
        # 流式思考状态
        self._think_text = ""        # 当前活动块的累计思考内容
        self._think_live = False     # 思考正在流式显示
        self._think_hdr = False      # 活动块的"思考中…"块头已上屏
        # v2.0.1 思考块按块存档:uid → 全文。旧版只有单个全局 _think_text,任务里
        # 多个思考块(每轮工具调用一块)收尾后,点旧标记要么没反应(新任务已清空)
        # 要么展开的是最后一块的内容/位置(2026-10-07 实测反馈)。
        self._think_store = {}
        self._think_seq = 0
        self._streaming_asst = False # 当前助手内容是否已流式上屏(避免重复渲染)
        # v1.8.2 流式渲染节流:token 只进缓冲,由 150ms 周期渲染器批量上屏。
        # 旧实现每 token 一次 state 切换+insert+see("end") 强制同步重排,
        # 思考模型几千 token 会把 Tk 事件循环榨干,表现为"折叠/思考时卡死很久"。
        self._think_shown = 0        # 已上屏的思考字符数
        self._asst_shown = 0         # 已上屏的回答字符数
        self._selecting = False      # 用户正在鼠标选中(渲染器此时不锁回只读态)

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
        # 实测(200% DPI):Tk 的 winfo_width/geometry 都是物理像素,而字号按点
        # 乘 tk scaling。像素尺寸不缩 = 侧栏只够 8 个字、对话框装不下内容。
        # 正确做法:像素标尺按 DPI 放大,字号只吃一次点缩放。
        try:
            self._ui_scale = max(1.0, root.winfo_fpixels("1i") / 96.0)
        except Exception:
            self._ui_scale = 1.0
        try:
            v4.set_scale(self._ui_scale)
        except Exception:
            pass
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
        self.refresh_models(quick=True)   # 启动只探测一次,避免离线引擎阻塞 UI;5s 自愈链会重试
        self._build_statusbar()

        # 快捷键
        root.bind("<Control-n>", lambda e: self.new_chat())
        root.bind("<Control-f>", lambda e: self.search_history())
        root.bind("<Control-l>", lambda e: self.clear_log())
        root.bind("<Control-i>", lambda e: self.send_chat())
        # v3.0.0:Enter 发送 · Shift+Enter 换行(输入卡处的同名绑定更具体,两处都挂保平安)
        self.input.bind("<Return>", self._on_enter_key)
        self.input.bind("<Control-Return>", lambda e: (self.send_chat(), "break")[1])
        root.bind("<F5>", lambda e: self.run_agent())

        self.apply_theme()
        self._welcome()               # 空状态欢迎语
        self.refresh_sessions()
        self.refresh_voice_state()
        self.root.after(100, self.poll)
        self.root.after(150, self._stream_render_tick)
        self.root.after(500, self.poll_todo)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ================= 偏好 =================
    def load_prefs(self):
        # v1.7.0 采样三态:temp/think 为 None = 未设置 = 请求不带字段,用 ollama 默认。
        # prefver 标记:旧版(无标记)文件里的 temp=0.0 是隐藏默认值而非用户显式选择,
        # 一次性迁移为未设置;标记存在后,用户显式设置的 0 不再被抹掉。
        d = {"theme": "minty-light", "ui_mode": "auto", "ctx": 65536, "temp": None,
             "num_predict": 2048, "sys_enable": False, "sys_text": "",
             "think": None, "prefver": 2, "stt_lang": "zh"}
        try:
            j = json.load(open(PREFS_FILE, encoding="utf-8")); d.update(j)
            # 与 webui/server.py _prefs_load 同口径:旧版隐藏默认(温度 0、思考开)
            # 不是用户显式选择,一次性迁为"未设置"(gui_prefs.json 由两端共用,
            # think=true 可能是旧 webui 默认写入的)。
            if "prefver" not in j:
                if d.get("temp") in (0, 0.0):
                    d["temp"] = None
                if d.get("think") is True:
                    d["think"] = None
        except Exception:
            pass
        return d
    def save_prefs(self):
        try:
            os.makedirs(os.path.dirname(PREFS_FILE), exist_ok=True)
            _atomic_json(PREFS_FILE, self.prefs)
        except Exception:
            pass

    # ================= 思考三态(工具栏快切) =================
    def _think_states(self):
        """思考下拉的(显示值→prefs 值)映射,None=未设置=ollama 默认。"""
        return {_t("默认"): None, _t("开"): True, _t("关"): False}

    def _on_think_selected(self, _e=None):
        self.prefs["think"] = self._think_states().get(self.think_var.get())
        self.save_prefs()
        v = self.prefs["think"]
        _shown = _t("默认") if v is None else (_t("开") if v else _t("关"))
        self.log_note(_t("[思考: ") + _shown + "]")

    # ================= DPI/排版辅助 =================
    def _scaled_geo(self, w, h):
        """对话框默认几何按 DPI 缩放(固定像素几何在高缩放下会把整页内容挤裁)。"""
        s = getattr(self, "_ui_scale", 1.0)
        return f"{int(w * s)}x{int(h * s)}"

    @staticmethod
    def _disp_units(s):
        """显示宽度估算:CJK/全角按 2 个单位,其余按 1(近似 Tk 平均字符宽度)。"""
        return sum(2 if ord(ch) > 0x2E7F else 1 for ch in str(s))


    # ================= 构建界面(v4:会话侧边栏 + 对话 + 计划抽屉) =================
    def _build_toolbar(self):
        """v4 外壳:常驻会话侧边栏 + 单列对话区 + 可折叠计划抽屉。

        旧版是"左侧导航轨 + 两条工具栏 + 右侧常驻 todo 栏"——会话切换要跳页,
        控件全部平铺,计划面板长期占地。v4 把会话变成一等公民,其余收进二级入口。
        """
        import ui_theme as _ut
        self._ui = _ut
        self.T = _ut.tokens("dark")   # 构建期临时配色;apply_theme 统一刷新
        self._themable = []
        self._themed = []             # [(widget, bg_key, fg_key)] 供主题刷新
        self._log_buf = []
        self.console = None
        self.plan_open = False
        self._plan_items = []
        self._plan_done = 0
        self._plan_total = 0
        self.search_var = tk.StringVar(value="")
        self._plan_source = "run"
        self._sess_w = 0
        self._search_after = None
        self._build_shell()

    # ---- 主题登记辅助(避免逐个控件手写 apply_theme) ----
    def _frame(self, parent, bg_key="bg", **kw):
        w = tk.Frame(parent, bg=self.T[bg_key], bd=0, highlightthickness=0, **kw)
        self._themed.append((w, bg_key, None))
        return w

    def _lab(self, parent, text="", bg_key="bg", fg_key="text", **kw):
        w = tk.Label(parent, text=text, bg=self.T[bg_key],
                     fg=self.T[fg_key], bd=0, **kw)
        self._themed.append((w, bg_key, fg_key))
        return w

    def _entry(self, parent, bg_key="surface", fg_key="text", **kw):
        w = tk.Entry(parent, bg=self.T[bg_key], fg=self.T[fg_key],
                     insertbackground=self.T[fg_key], bd=0,
                     highlightthickness=0, **kw)
        self._themed.append((w, bg_key, fg_key))
        return w

    def _build_shell(self):
        T = self.T
        S = self._ui_scale
        self.root.configure(bg=T["bg"])
        self.sidebar = tk.Frame(self.root, bg=T["side"], width=int(280 * S),
                                bd=0, highlightthickness=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self.plan_rail = tk.Frame(self.root, bg=T["bg"], width=int(46 * S),
                                  bd=0, highlightthickness=0)
        self.plan_rail.pack(side="right", fill="y")
        self.plan_rail.pack_propagate(False)
        self.main = tk.Frame(self.root, bg=T["bg"], bd=0, highlightthickness=0)
        self.main.pack(side="left", fill="both", expand=True)
        self._build_sidebar()

    def _build_sidebar(self):
        T = self.T
        S = self._ui_scale
        s = self.sidebar
        head = self._frame(s, "side", height=int(56 * S))
        head.pack(fill="x", padx=int(16 * S), pady=(int(10 * S), int(2 * S)))
        head.pack_propagate(False)
        self._brand_img = None
        mw = None
        try:
            from PIL import Image, ImageTk
            p = os.path.join(AGENT_DIR, "app.png")
            if os.path.exists(p):
                _m = int(34 * S)
                im = Image.open(p).convert("RGBA").resize((_m, _m), Image.LANCZOS)
                self._brand_img = ImageTk.PhotoImage(im)
                mw = tk.Label(head, image=self._brand_img, bg=T["side"], bd=0)
        except Exception:
            mw = None
        if mw is None:
            mw = self._lab(head, "🐦", "side", "primary",
                           font=(v4.EMOJI_FAMILY, 16))
        mw.pack(side="left")
        self._themed.append((mw, "side", None))   # theme_use 会把图片 Label 刷成 #222
        self._brand_mark = mw
        box = self._frame(head, "side")
        box.pack(side="left", padx=(int(10 * S), 0))
        self._brand_name = self._lab(box, _t("鸣鸟"), "side", "text",
                                     font=v4.FONT_BRAND)
        self._brand_name.pack(anchor="w")
        self._brand_sub = self._lab(
            box, "MINGBIRD  " + (self.app_version() or ""), "side", "faint",
            font=(v4.DISPLAY_FAMILY, 9))
        self._brand_sub.pack(anchor="w")

        # 宽度 = 侧栏内容宽(280 - 左右各 16);之前写死 220,比搜索框窄一截
        _btn_w = 280 - 32
        self.new_btn = v4.Pill(s, "＋   " + _t("新对话"), self.new_chat, T,
                               kind="primary", h=38, padx=0, width=_btn_w,
                               font=v4.FONT_BOLD, radius=10)
        self.new_btn.pack(pady=(int(8 * S), int(10 * S)), padx=int(16 * S),
                          fill="x")

        # 搜索框:圆角面板(自绘图片),不再用方形 1px 边框——旧样式最显"复古"
        sbox = tk.Frame(s, bg=T["side"], height=int(44 * S))
        self._themed.append((sbox, "side", None))
        sbox.pack(fill="x", padx=int(16 * S), pady=(0, int(8 * S)))
        sbox.pack_propagate(False)
        sbox.bind("<Configure>", self._paint_search)
        self._search_bg = tk.Label(sbox, bg=T["side"], bd=0)
        self._search_bg.place(x=0, y=0, relwidth=1, relheight=1)
        self._search_border = sbox
        self._lab(sbox, "⌕", "surface", "faint",
                  font=(v4.DISPLAY_FAMILY, 14)).place(x=int(13 * S), rely=0.5,
                                               anchor="w")
        self.search_entry = self._entry(sbox, font=v4.FONT_SM,
                                        textvariable=self.search_var)
        self.search_entry.place(x=int(38 * S), y=int(8 * S),
                                relwidth=1.0, width=-int(50 * S),
                                height=int(28 * S))
        self._search_hint = _t("搜索对话")
        self.search_var.set(self._search_hint)
        self.search_entry.configure(fg=T["faint"])
        self.search_entry.bind("<FocusIn>", self._search_focus_in)
        self.search_entry.bind("<FocusOut>", self._search_focus_out)
        self.search_entry.bind("<KeyRelease>", self._search_changed)

        self.sess_canvas = tk.Canvas(s, bg=T["side"], bd=0, highlightthickness=0,
                                     yscrollincrement=int(24 * S))
        self.sess_canvas.pack(fill="both", expand=True)
        self.sess_canvas.bind("<MouseWheel>", self._sidebar_wheel)
        self.sess_canvas.bind("<Configure>", self._on_sess_resize)

        foot = self._frame(s, "side")
        foot.pack(fill="x", padx=int(14 * S), pady=(int(2 * S), int(8 * S)))
        for label, cmd in ((_t("技能"), self.show_skills),
                           (_t("日志"), self._open_logs),
                           (_t("设置"), self.open_settings),
                           (_t("关于"), self.show_about)):
            b = self._lab(foot, label, "side", "muted",
                          font=v4.FONT_XS, cursor="hand2", padx=int(2 * S))
            b.pack(side="left", padx=(0, int(6 * S)))
            b.bind("<Button-1>", lambda e, c=cmd: c())
            b.bind("<Enter>", lambda e, w=b: w.configure(fg=self.T["primary"]))
            b.bind("<Leave>", lambda e, w=b: w.configure(fg=self.T["muted"]))
        th = self._lab(foot, "◐", "side", "muted",
                       font=(v4.DISPLAY_FAMILY, 14), cursor="hand2")
        th.pack(side="right")
        th.bind("<Button-1>", lambda e: self.cycle_theme())
        self._theme_icon = th

    def _paint_search(self, _e=None):
        if not hasattr(self, "_search_bg"):
            return
        w = self._search_border.winfo_width()
        h = self._search_border.winfo_height()
        if w < 60 or h < 30:
            return
        img = v4.card_img(max(2, w - 2), max(2, h - 2), v4.px(12),
                          self.T["surface"], self.T["border"], self.T["side"])
        if img is not None:
            self._search_img = img
            self._search_bg.configure(image=img, bg=self.T["side"])
            self._search_bg.lower()

    def _search_focus_in(self, _e=None):
        if self.search_var.get() == self._search_hint:
            self.search_var.set("")
            self.search_entry.configure(fg=self.T["text"])

    def _search_focus_out(self, _e=None):
        if not self.search_var.get().strip():
            self.search_var.set(self._search_hint)
            self.search_entry.configure(fg=self.T["faint"])

    def _sidebar_wheel(self, e):
        try:
            self.sess_canvas.yview_scroll(int(-e.delta / 120), "units")
        except Exception:
            pass
        return "break"

    def _search_changed(self, _e=None):
        try:
            if self._search_after:
                self.root.after_cancel(self._search_after)
        except Exception:
            pass
        self._search_after = self.root.after(160, self.refresh_sessions)

    def _on_sess_resize(self, _e=None):
        w = self.sess_canvas.winfo_width()
        if abs(w - getattr(self, "_sess_w", 0)) < 4:
            return
        self._sess_w = w
        if getattr(self, "_sess_names", None) is not None:
            self.refresh_sessions()

    def _build_body(self):
        self._build_chat_page()

    def _build_chat_page(self):
        self._build_header()
        self._build_transcript()
        self._build_composer()

    # ------------------------------------------------------------ header
    def _build_header(self):
        T = self.T
        S = self._ui_scale
        self.wd_var = tk.StringVar(value=os.path.join(DEFAULT_TASKS, "work"))
        self.tb_var = tk.StringVar(value="")

        h = self._frame(self.main, "bg", height=int(64 * S))
        h.pack(fill="x", padx=(int(24 * S), int(18 * S)),
               pady=(int(10 * S), 0))
        h.pack_propagate(False)
        self.header = h

        right = self._frame(h, "bg")
        right.pack(side="right", fill="y")
        left = self._frame(h, "bg")
        left.pack(side="left", fill="y")
        self._header_left = left
        self.conv_title = self._lab(left, _t("新对话"), "bg", "text",
                                    font=v4.FONT_TITLE, anchor="w")
        self.conv_title.pack(anchor="w", pady=(int(2 * S), 0))
        self.conv_sub = self._lab(left, _t("本地优先 · 小模型优先"), "bg", "faint",
                                  font=v4.FONT_XS, anchor="w")
        self.conv_sub.pack(anchor="w")

        _vals = list(getattr(self, "_model_map", {}) or {})
        self.model_var = tk.StringVar(value=(_vals[0] if _vals else ""))
        self.think_var = tk.StringVar(
            value={None: _t("默认"), True: _t("开"), False: _t("关")}.get(
                self.prefs.get("think"), _t("默认")))
        self.cloud_var = tk.StringVar(value="")

        self.model_btn = v4.Pill(right, "", self._model_menu, T, kind="surface",
                                 h=30, padx=12, radius=8)
        self.model_btn.pack(side="left", padx=(0, int(6 * S)), pady=int(12 * S))
        self.think_btn = v4.Pill(right, "", self._cycle_think, T, kind="surface",
                                 h=30, padx=12, radius=8)
        self.think_btn.pack(side="left", padx=(0, int(6 * S)), pady=int(12 * S))
        self.offline_btn = v4.Pill(right, "", self._toggle_offline, T,
                                   kind="surface", h=30, padx=12, radius=8)
        self.offline_btn.pack(side="left", padx=(0, int(6 * S)), pady=int(12 * S))
        self.cloud_btn = v4.Pill(right, "", self._cloud_menu, T, kind="surface",
                                 h=30, padx=12, radius=8)
        # cloud_btn 由 _sync_cloud_box 决定是否 pack(未配置时不占位)
        self.plan_btn = v4.Pill(right, "", self._toggle_plan, T, kind="surface",
                                h=30, padx=12, radius=8)

        self._sync_model_btn()
        self._sync_think_btn()
        self._sync_offline_ui()
        self._sync_cloud_box()
        self._sync_plan_btn()

    def _sync_model_btn(self):
        if not hasattr(self, "model_btn"):
            return
        txt = self.model_var.get() if hasattr(self, "model_var") else ""
        if not txt:
            _c = appconfig.load_config().get("cloud") or {}
            if _c.get("enabled") and _c.get("model"):
                txt = "☁ " + str(_c["model"])
        if not txt:
            txt = _t("模型")
        if len(txt) > 26:
            txt = txt[:25] + "…"
        self.model_btn.set_text(txt + "  ▾")

    def _sync_think_btn(self):
        if not hasattr(self, "think_btn"):
            return
        self.think_btn.set_text(_t("思考 · ") + self.think_var.get())

    def _cloud_ready(self):
        """云端配置完整且启用 = 当前推理走云端(仅联网可用)。"""
        c = appconfig.load_config().get("cloud") or {}
        return bool(c.get("enabled") and c.get("base_url") and c.get("model"))

    def _sync_offline_ui(self):
        if not hasattr(self, "offline_btn"):
            return
        off = appconfig.offline_mode()
        if self._cloud_ready():
            # 云端模型只能联网:断网按钮置灰,先切回本地才能断网
            self.offline_btn.set_text(_t("● 联网"))
            self.offline_btn.set_kind("surface")
            self.offline_btn.set_enabled(False)
            return
        self.offline_btn.set_enabled(True)
        self.offline_btn.set_text(_t("● 断网") if off else _t("● 联网"))
        self.offline_btn.set_kind("danger" if off else "surface")

    def _model_menu(self):
        names = list(getattr(self, "_model_map", {}) or {})
        if not names:
            self.log_note(_t("[模型清单为空 — 等引擎就绪后再试]"))
            return
        menu = tk.Menu(self.root, tearoff=0, bg=self.T["surface"],
                       fg=self.T["text"], activebackground=self.T["soft"],
                       activeforeground=self.T["primary"], bd=0,
                       font=v4.FONT_SM)
        for n in names:
            menu.add_command(label=n, command=lambda x=n: self._pick_model(x))
        menu.tk_popup(self.model_btn.winfo_rootx(),
                      self.model_btn.winfo_rooty() + self.model_btn.winfo_height() + 4)

    def _pick_model(self, name):
        self.model_var.set(name)
        self._on_model_selected()
        self._sync_cloud_box()
        self._sync_model_btn()

    def _cycle_think(self):
        states = list(self._think_states().keys())
        cur = self.think_var.get()
        nxt = states[(states.index(cur) + 1) % len(states)] if cur in states else states[0]
        self.think_var.set(nxt)
        self._on_think_selected()
        self._sync_think_btn()

    def _cloud_menu(self):
        m = (appconfig.load_config().get("cloud") or {}).get("model") or ""
        if not m:
            return
        menu = tk.Menu(self.root, tearoff=0, bg=self.T["surface"],
                       fg=self.T["text"], activebackground=self.T["soft"],
                       activeforeground=self.T["primary"], bd=0,
                       font=v4.FONT_SM)
        menu.add_command(label=_t("仅本地模型"),
                         command=lambda: self._select_cloud(""))
        menu.add_command(label="☁ " + m, command=lambda: self._select_cloud(m))
        menu.tk_popup(self.cloud_btn.winfo_rootx(),
                      self.cloud_btn.winfo_rooty() + self.cloud_btn.winfo_height() + 4)

    def _select_cloud(self, val):
        self.cloud_var.set(val or "")
        self._on_cloud_selected()
        self._sync_cloud_box()
        self._sync_model_btn()

    # ------------------------------------------------------------ transcript
    def _build_transcript(self):
        S = self._ui_scale
        wrap = self._frame(self.main, "bg")
        wrap.pack(fill="both", expand=True,
                  padx=(int(24 * S), int(18 * S)), pady=(int(4 * S), 0))
        self.transcript = tk.Text(wrap, bd=0, highlightthickness=0, wrap="word",
                                  font=v4.FONT, padx=0, pady=int(8 * S),
                                  cursor="arrow")
        self.transcript.pack(fill="both", expand=True)
        self.transcript.bind("<Button-1>", self._sel_press)
        self.transcript.bind("<ButtonRelease-1>", self._sel_release)
        self.transcript.bind("<Control-c>", self._copy_selection)
        self.transcript.bind("<Key>", lambda e: "break")
        self.transcript.bind("<MouseWheel>", self._transcript_wheel)
        self.transcript.configure(state="disabled")
        self._configure_transcript_tags()

    def _transcript_wheel(self, e):
        try:
            self.transcript.yview_scroll(int(-e.delta / 120), "units")
        except Exception:
            pass
        return "break"

    def _configure_transcript_tags(self):
        T = self.T
        S = self._ui_scale
        px = lambda n: int(n * S)
        tx = self.transcript
        tx.configure(bg=T["bg"], fg=T["text"], insertbackground=T["text"],
                     selectbackground=T["soft"], selectforeground=T["text"])
        tx.tag_configure("day", justify="center", foreground=T["faint"],
                         font=v4.FONT_XS, spacing1=px(14), spacing3=px(16))
        tx.tag_configure("who", foreground=T["primary"],
                         font=(v4.UI_FAMILY, 10, "bold"),
                         lmargin1=0, lmargin2=0, spacing1=px(12), spacing3=px(2))
        tx.tag_configure("you_line", justify="right", foreground=T["primary"],
                         font=(v4.UI_FAMILY, 10, "bold"),
                         lmargin1=px(220), lmargin2=px(220), rmargin=px(28),
                         spacing1=px(10), spacing3=0)
        tx.tag_configure("user", justify="right", foreground=T["text"],
                         font=v4.FONT, lmargin1=px(220), lmargin2=px(220),
                         rmargin=px(28), spacing1=px(6), spacing3=px(12))
        tx.tag_configure("asst", foreground=T["text"], font=v4.FONT,
                         lmargin1=0, lmargin2=0, rmargin=px(140),
                         spacing1=px(8), spacing3=px(8))
        tx.tag_configure("tool", foreground=T["muted"], background=T["code_bg"],
                         font=v4.MONO_SM, lmargin1=px(4), lmargin2=px(4),
                         rmargin=px(100), spacing1=px(4), spacing3=px(4))
        tx.tag_configure("note", foreground=T["muted"],
                         font=(v4.UI_FAMILY, 11),
                         lmargin1=px(4), lmargin2=px(4))
        tx.tag_configure("done", foreground=T["primary"], background=T["soft"],
                         font=(v4.UI_FAMILY, 12, "bold"),
                         lmargin1=px(12), lmargin2=px(12), rmargin=px(120),
                         spacing1=px(6), spacing3=px(8))
        tx.tag_configure("code", foreground=T["text"], background=T["code_bg"],
                         font=v4.MONO, lmargin1=px(4), lmargin2=px(12),
                         rmargin=px(100), spacing1=px(2), spacing3=px(2))
        tx.tag_configure("spacer", spacing1=px(6), spacing3=px(6))
        tx.tag_configure("think_region", foreground=T["muted"],
                         background=T["code_bg"],
                         font=(v4.UI_FAMILY, 11, "italic"),
                         lmargin1=px(16), lmargin2=px(16), rmargin=px(120))
        tx.tag_configure("think_marker", foreground=T["muted"],
                         background=T["code_bg"],
                         font=(v4.UI_FAMILY, 11, "italic"),
                         lmargin1=px(16), lmargin2=px(16),
                         spacing1=px(3), spacing3=px(3))
        tx.tag_configure("welcome_title", foreground=T["text"],
                         font=(v4.UI_FAMILY, 20, "bold"),
                         lmargin1=px(8), lmargin2=px(8),
                         spacing1=px(18), spacing3=px(8))
        tx.tag_configure("welcome_sub", foreground=T["muted"],
                         font=(v4.UI_FAMILY, 12),
                         lmargin1=px(8), lmargin2=px(8), spacing3=px(18))
        tx.tag_configure("sugg", foreground=T["primary"], font=v4.FONT,
                         lmargin1=px(8), lmargin2=px(8),
                         spacing1=px(4), spacing3=px(4), underline=1)
        tx.tag_bind("sugg", "<Button-1>", self._click_suggestion)

    def _click_suggestion(self, e):
        try:
            line = self.transcript.get(f"@{e.x},{e.y} linestart",
                                       f"@{e.x},{e.y} lineend").strip()
            if line.startswith("·"):
                line = line[1:].strip()
            if line:
                self.input.delete("1.0", "end")
                self.input.insert("1.0", line)
                self.input.configure(fg=self.T["text"])
                self.input.focus_set()
        except Exception:
            pass

    # ------------------------------------------------------------ composer
    def _build_composer(self):
        T = self.T
        S = self._ui_scale
        self.composer_wrap = tk.Frame(self.main, bg=T["bg"], height=int(142 * S))
        self.composer_wrap.pack(fill="x", padx=(int(24 * S), int(18 * S)),
                                pady=(int(6 * S), int(4 * S)))
        self.composer_wrap.pack_propagate(False)
        self.composer_wrap.bind("<Configure>", self._paint_composer)
        self.composer_bg = tk.Label(self.composer_wrap, bg=T["bg"], bd=0)
        self.composer_bg.place(x=0, y=0, relwidth=1, relheight=1)

        self.input = tk.Text(self.composer_wrap, height=3, bd=0,
                             highlightthickness=0, wrap="word",
                             bg=T["surface"], fg=T["text"],
                             insertbackground=T["primary"], font=v4.FONT,
                             padx=int(4 * S), pady=int(2 * S))
        self._themed.append((self.input, "surface", "text"))
        self._hint = _t("输入任务或对话…(Enter 发送 · Shift+Enter 换行)")
        self._set_input_hint(True)
        self.input.bind("<FocusIn>", self._input_focus_in)
        self.input.bind("<FocusOut>", self._input_focus_out)
        self.input.bind("<Return>", self._on_enter_key)
        self.input.bind("<Control-Return>", lambda e: (self.send_chat(), "break")[1])
        self.input.bind("<Control-v>", self._on_paste)
        if _HAVE_DND:
            try:
                self.input.drop_target_register(_DND_FILES)
                self.input.bind("<<Drop>>", self._on_drop)
            except Exception:
                pass

        self.att_chips = tk.Frame(self.composer_wrap, bg=T["surface"])
        self._themed.append((self.att_chips, "surface", None))

        self.composer_row = tk.Frame(self.composer_wrap, bg=T["surface"])
        self._themed.append((self.composer_row, "surface", None))

        self.attach_btn = v4.Pill(self.composer_row, _t("附件"), self.add_files, T,
                                  kind="ghost", h=28, padx=8)
        self.attach_btn.pack(side="left")
        self.mic_btn = v4.Pill(self.composer_row, _t("语音"), self.voice_input, T,
                               kind="ghost", h=28, padx=8)
        self.mic_btn.pack(side="left", padx=(int(2 * S), 0))
        self.mic_btn.set_enabled(False)
        _sl = "EN" if self.prefs.get("stt_lang", "zh") == "en" else "中"
        self.stt_lang_btn = v4.Pill(self.composer_row, _sl, self.toggle_stt_lang, T,
                                   kind="ghost", h=28, padx=8, width=32)
        self.stt_lang_btn.pack(side="left", padx=(int(2 * S), 0))
        self.dir_btn = v4.Pill(self.composer_row, _t("目录"),
                               self._open_task_settings, T, kind="ghost", h=28, padx=8)
        self.dir_btn.pack(side="left", padx=(int(6 * S), 0))
        self.resume_var = tk.BooleanVar(value=True)
        # 原生 Checkbutton 的方框是系统画的老式 bevel,和圆角输入卡冲突;
        # 换成 v4.Check(圆角描边 + 主色勾),BooleanVar 接口不变。
        self.resume_chk = v4.Check(self.composer_row, _t("续跑"),
                                   self.resume_var, T, font=v4.FONT_XS)
        self.resume_chk.pack(side="left", padx=(int(8 * S), 0))

        self.send_btn = v4.Pill(self.composer_row, "↑", self.send_chat, T,
                                kind="primary", h=34, padx=0, width=34, radius=17,
                                font=(v4.DISPLAY_FAMILY, 13, "bold"))
        self.send_btn.pack(side="right")
        self.stop_btn = v4.Pill(self.composer_row, _t("停止"), self.stop, T,
                                kind="danger", h=30, padx=12)
        self.stop_btn.pack(side="right", padx=(0, int(6 * S)))
        self.stop_btn.pack_forget()
        self.hint_lbl = self._lab(self.composer_row,
                                  "Enter " + _t("发送") + " · Shift+Enter " + _t("换行"),
                                  "surface", "faint", font=v4.FONT_XS)
        self.hint_lbl.pack(side="right", padx=(0, int(12 * S)))

        self._layout_composer()
        self._refresh_att_chips()
        self._sync_dir_btn()
        self.root.after(30, self._paint_composer)

    def _input_focus_in(self, _e=None):
        if self.input.get("1.0", "end-1c") == self._hint:
            self.input.delete("1.0", "end")
            self.input.configure(fg=self.T["text"])

    def _input_focus_out(self, _e=None):
        if not self.input.get("1.0", "end-1c").strip():
            self._set_input_hint(True)

    def _set_input_hint(self, on):
        try:
            if on:
                if not self.input.get("1.0", "end-1c").strip():
                    self.input.delete("1.0", "end")
                    self.input.insert("1.0", self._hint)
                    self.input.configure(fg=self.T["faint"])
            elif self.input.get("1.0", "end-1c") == self._hint:
                self.input.delete("1.0", "end")
                self.input.configure(fg=self.T["text"])
        except Exception:
            pass

    def _layout_composer(self):
        if not hasattr(self, "composer_wrap"):
            return
        S = self._ui_scale
        att_h = int(30 * S) if self.attachments else 0
        try:
            self.composer_wrap.configure(height=int(142 * S) + att_h)
        except Exception:
            pass
        self.input.place(x=int(20 * S), y=int(16 * S) + att_h, relwidth=1.0,
                         width=-int(40 * S), height=int(70 * S))
        self.composer_row.place(x=int(16 * S), y=int(94 * S) + att_h,
                                relwidth=1.0, width=-int(32 * S),
                                height=int(36 * S))
        if self.attachments:
            self.att_chips.place(x=int(18 * S), y=int(10 * S), relwidth=1.0,
                                 width=-int(36 * S), height=int(26 * S))
        else:
            self.att_chips.place_forget()

    def _paint_composer(self, _e=None):
        if not hasattr(self, "composer_bg"):
            return
        w = self.composer_wrap.winfo_width()
        h = self.composer_wrap.winfo_height()
        if w < 80 or h < 60:
            return
        img = v4.card_img(max(2, w - 2), max(2, h - 2), v4.px(14),
                          self.T["surface"], self.T["border"], self.T["bg"])
        if img is not None:
            self._composer_img = img
            self.composer_bg.configure(image=img, bg=self.T["bg"])
            self.composer_bg.lower()

    def _refresh_att_chips(self):
        if not hasattr(self, "att_chips"):
            return
        for w in self.att_chips.winfo_children():
            w.destroy()
        if self.attachments:
            for i, p in enumerate(self.attachments[:3]):
                name = v4.ellipsize(os.path.basename(p), 150, v4.FONT_XS)
                chip = tk.Label(self.att_chips, text="📎 " + name + "  ×",
                                font=v4.FONT_XS, bg=self.T["code_bg"],
                                fg=self.T["muted"], padx=7, pady=2,
                                cursor="hand2")
                chip.pack(side="left", padx=(0, 6))
                chip.bind("<Button-1>", lambda e, idx=i: self._remove_att(idx))
                self._themed.append((chip, "code_bg", "muted"))
            if len(self.attachments) > 3:
                self._lab(self.att_chips, "+%d" % (len(self.attachments) - 3),
                          "surface", "muted", font=v4.FONT_XS).pack(side="left")
        self._layout_composer()
        self.root.after(10, self._paint_composer)

    def _remove_att(self, i):
        try:
            self.attachments.pop(i)
        except Exception:
            pass
        self._refresh_att_chips()

    def _sync_dir_btn(self):
        if not hasattr(self, "dir_btn"):
            return
        wd = self.wd_dir()
        name = os.path.basename(os.path.normpath(wd)) or wd
        txt = _t("目录 · ") + v4.ellipsize(name, 80, v4.FONT_SM)
        tl = (self.tb_var.get() or "").strip() if hasattr(self, "tb_var") else ""
        if tl:
            txt += "  ·  " + _t("时限 ") + tl
        self.dir_btn.set_text(txt)

    def _open_task_settings(self):
        """工作目录 / 任务时限(旧版常驻两条工具栏,现收进二级入口)。"""
        T = self.T
        win = tk.Toplevel(self.root)
        win.title(_t("任务设置"))
        win.geometry(self._scaled_geo(560, 250))
        win.configure(bg=T["bg"])
        self._theme_titlebar(win)
        body = tk.Frame(win, bg=T["bg"])
        body.pack(fill="both", expand=True, padx=18, pady=14)
        tk.Label(body, text=_t("工作目录"), bg=T["bg"], fg=T["muted"],
                 font=v4.FONT_SM).pack(anchor="w")
        r1 = tk.Frame(body, bg=T["bg"])
        r1.pack(fill="x", pady=(4, 10))
        ent = tk.Entry(r1, textvariable=self.wd_var, bg=T["surface"],
                       fg=T["text"], insertbackground=T["text"], bd=0,
                       highlightthickness=1, highlightbackground=T["border"],
                       highlightcolor=T["primary"], font=v4.FONT_SM)
        ent.pack(side="left", fill="x", expand=True, ipady=6)
        for label, cmd in ((_t("浏览"), self.choose_dir), (_t("打开"), self.open_dir)):
            b = v4.Pill(r1, label, cmd, T, kind="surface", h=30, padx=10)
            b.pack(side="left", padx=(6, 0))

        tk.Label(body, text=_t("任务时限(分钟或小时,留空=不限)"),
                 bg=T["bg"], fg=T["muted"], font=v4.FONT_SM).pack(anchor="w")
        r2 = tk.Frame(body, bg=T["bg"])
        r2.pack(fill="x", pady=(4, 12))
        tk.Entry(r2, textvariable=self.tb_var, bg=T["surface"], fg=T["text"],
                 insertbackground=T["text"], bd=0, highlightthickness=1,
                 highlightbackground=T["border"], highlightcolor=T["primary"],
                 font=v4.FONT_SM, width=16).pack(side="left", ipady=6)
        tk.Label(r2, text=_t("例: 40 / 1.5h"), bg=T["bg"], fg=T["faint"],
                 font=v4.FONT_XS).pack(side="left", padx=10)

        btns = tk.Frame(body, bg=T["bg"])
        btns.pack(fill="x", side="bottom")

        def _save():
            self._sync_dir_btn()
            win.destroy()

        v4.Pill(btns, _t("保存"), _save, T, kind="primary", h=32, padx=14).pack(side="right")
        v4.Pill(btns, _t("取消"), win.destroy, T, kind="surface", h=32, padx=14).pack(
            side="right", padx=(0, 6))
        ent.focus_set()
        win.bind("<Return>", lambda e: _save())
        win.bind("<Escape>", lambda e: win.destroy())

    def _toggle_offline(self):
        """一键断网/联网:翻转 offline_mode 写入 config.json(appconfig 缓存随
        save_config 失效),GUI 按钮即时变色;下一次任务的装配层即刻生效。"""
        if self._cloud_ready():
            self.log_note(_t("[云端模型需联网:先在顶部切回本地模型,再开断网]"))
            return
        cfg = appconfig.load_config()
        cfg["offline_mode"] = not appconfig.offline_mode()
        if appconfig.save_config(cfg):
            off = appconfig.offline_mode()
            self._sync_offline_ui()
            self._sync_mode_lbl()
            self.log_note(_t("[断网模式:仅本地模型,联网工具与云端已禁用 — 零出站]") if off
                          else _t("[联网模式:搜索/已配置的 MCP/云端可用]"))
        else:
            self.log_note(_t("[断网开关写入配置失败]"))
        self._sync_cloud_box()

    # ================= 云端模型选择(v1.8.2) =================
    def _on_model_selected(self):
        """互斥门:左侧选了本地模型 = 右侧云端框清空、云端开关关闭。"""
        self.refresh_voice_state()
        if not self.model_var.get():
            return
        cfg = appconfig.load_config()
        cloud = cfg.get("cloud") or {}
        changed = False
        if cloud.get("enabled"):
            cloud["enabled"] = False
            cfg["cloud"] = cloud
            appconfig.save_config(cfg)
            changed = True
        self.cloud_var.set("")
        if changed:
            self.log_note(_t("[已切回本地模型:云端开关关闭]"))
        self._sync_offline_ui()
        self._sync_mode_lbl()

    def _sync_cloud_box(self):
        """云端入口状态:未配置→隐藏;断网→灰色禁用;可用→显示当前选择。
        每次都从 config 重读(与 runner 的 cloud_provider 同源)。"""
        if not hasattr(self, "cloud_btn"):
            return
        _c = appconfig.load_config().get("cloud") or {}
        _m = _c.get("model") or ""
        off = appconfig.offline_mode()
        if not _m:
            try:
                self.cloud_btn.pack_forget()
            except Exception:
                pass
            self.cloud_var.set("")
            return
        if off:
            self.cloud_var.set("")
            self.cloud_btn.set_text(_t("☁ 断网禁用"))
            self.cloud_btn.set_kind("surface")
            self.cloud_btn.set_enabled(False)
        else:
            on = bool(_c.get("enabled"))
            self.cloud_btn.set_text(("☁ " + _m) if on else _t("☁ 云端"))
            self.cloud_btn.set_kind("soft" if on else "surface")
            self.cloud_btn.set_enabled(True)
            if self.cloud_var.get() not in ("", _m):
                self.cloud_var.set("")
        try:
            if not self.cloud_btn.winfo_manager():
                self.cloud_btn.pack(side="left", padx=(0, int(6 * S)), pady=int(12 * S))
        except Exception:
            pass

    def _on_cloud_selected(self, _e=None):
        """互斥门:右侧选了云端模型 = 左侧本地框清空、cloud.enabled=true;
        选回空 = 回本地(本地框不清,由用户另选)。"""
        sel = self.cloud_var.get()
        cfg = appconfig.load_config()
        cloud = cfg.get("cloud") or {}
        m = cloud.get("model") or ""
        if m and sel == m:
            cloud["enabled"] = True
            cfg["cloud"] = cloud
            if appconfig.save_config(cfg):
                self.model_var.set("")
                self.log_note(_t("[云端已启用:后续任务改经 {m} 推理,api_key 只存本机;随时可切回]").format(m=m))
        else:
            if cloud.get("enabled"):
                cloud["enabled"] = False
                cfg["cloud"] = cloud
                appconfig.save_config(cfg)
            self.log_note(_t("[已切回本地模型]"))
        self._sync_cloud_box()
        self._sync_model_btn()
        self._sync_offline_ui()
        self._sync_mode_lbl()

    def _cloud_help(self):
        from tkinter import messagebox
        messagebox.showinfo(_t("云端模型配置(可选)"), _t(
            "在 设置 → 推理引擎 里把引擎切到「云端 API」,填端点、API Key 与模型名后保存即可。\n\n"
            "说明:\n"
            "- 任何 OpenAI 兼容端点均可(DeepSeek / 通义 / Moonshot / OpenRouter 等)\n"
            "- api_key 只存本机 config.json,不进仓库、不进日志\n"
            "- 云端模型只能联网使用;启用时自动关闭断网模式\n"
            "- 顶部「☁」胶囊可随时切回本地模型\n"
            "- 详细说明见仓库 README 的 \"Cloud model (optional)/云端模型(可选)\" 一节"))

    def _build_statusbar(self):
        T = self.T
        bar = tk.Frame(self.main, bg=T["bg"], height=int(26 * self._ui_scale))
        # main 里已有 transcript(expand) 与 composer;先让状态条占住最底部,
        # 再把 composer 压回它上面,避免状态条被挤到右侧/抽屉区域。
        try:
            self.composer_wrap.pack_forget()
        except Exception:
            pass
        bar.pack(side="bottom", fill="x")
        try:
            self.composer_wrap.pack(side="bottom", fill="x",
                                    padx=(24, 18), pady=(6, 4))
        except Exception:
            pass
        self.statusbar = bar
        self.ctx_bar = v4.CtxBar(bar, T)
        self.ctx_bar.pack(fill="x")
        row = self._frame(bar, "bg")
        row.pack(fill="x", padx=int(16 * self._ui_scale))
        self.status_var = tk.StringVar(value=_t("上下文: - / - ( - % )"))
        # 用 _lab 登记,主题切换时背景/前景跟着令牌走(此前裸 Label 不登记,
        # 切主题后残留构建期底色,底部出现色差条)。
        self.status_lbl = self._lab(row, "", "bg", "faint",
                                    font=v4.FONT_XS, anchor="w")
        self.status_lbl.configure(textvariable=self.status_var)
        self.status_lbl.pack(side="left")
        self.mode_lbl = self._lab(row, "", "bg", "faint", font=v4.FONT_XS)
        self.mode_lbl.pack(side="right", padx=(12, 0))
        self.ollama_lbl = self._lab(row, "Ollama …", "bg", "warn",
                                    font=(v4.UI_FAMILY, 9, "bold"),
                                    cursor="hand2")
        self.ollama_lbl.bind("<Button-1>", self._ollama_click)
        self.ollama_lbl.pack(side="right")
        self._sync_mode_lbl()
        self.root.after(800, self._check_ollama)

    def _sync_mode_lbl(self):
        if not hasattr(self, "mode_lbl"):
            return
        try:
            if self._cloud_ready() and not appconfig.offline_mode():
                txt = _t("联网 · 云端模型")
            elif appconfig.offline_mode():
                txt = _t("断网 · 零出站")
            else:
                txt = _t("联网 · 本地推理")
            self.mode_lbl.configure(text=txt)
        except Exception:
            pass

    def _open_logs(self):
        T = self.T
        if self.console is not None:
            try:
                if self.console.winfo_exists():
                    self.console.winfo_toplevel().lift()
                    return
            except Exception:
                pass
        win = tk.Toplevel(self.root)
        win.title(_t("运行日志"))
        win.geometry(self._scaled_geo(760, 520))
        win.configure(bg=T["bg"])
        self._theme_titlebar(win)
        head = tk.Frame(win, bg=T["bg"])
        head.pack(fill="x", padx=14, pady=(10, 4))
        tk.Label(head, text=_t("运行日志"), bg=T["bg"], fg=T["text"],
                 font=v4.FONT_TITLE).pack(side="left")
        v4.Pill(head, _t("清空输出"), self.clear_log, T, kind="surface",
                h=30, padx=10).pack(side="right")
        self.console = tk.Text(win, font=v4.MONO, state="disabled", wrap="word",
                               bg=T["code_bg"], fg=T["text"], bd=0,
                               padx=px(10), pady=px(8))
        self.console.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self.console.config(state="normal")
        self.console.insert("1.0", "\n".join(self._log_buf))
        self.console.see("end")
        self.console.config(state="disabled")
        win.protocol("WM_DELETE_WINDOW", lambda: self._close_logs(win))

    def _close_logs(self, win):
        self.console = None
        try:
            win.destroy()
        except Exception:
            pass

    # ------------------------------------------------------------ plan drawer
    def _toggle_plan(self):
        self.plan_open = not self.plan_open
        self._build_plan_rail()

    def _build_plan_rail(self):
        T = self.T
        S = self._ui_scale
        r = self.plan_rail
        for w in r.winfo_children():
            w.destroy()
        self.plan_txt = None
        if not self.plan_open:
            # 收起时整个抽屉从 pack 中移除:不再留一条竖窄条
            # (用户反馈"看起来很奇怪"),计划入口改到顶部胶囊。
            try:
                r.pack_forget()
            except Exception:
                pass
            r.configure(width=1, highlightthickness=0, bg=T["bg"])
            self._sync_plan_btn()
            return
        r.configure(bg=T["surface"], width=int(320 * S),
                    highlightthickness=v4.px(1),
                    highlightbackground=T["border"])
        try:
            if not r.winfo_ismapped():
                r.pack(side="right", fill="y", before=self.main)
        except Exception:
            pass
        self._sync_plan_btn()

        head = tk.Frame(r, bg=T["surface"])
        head.pack(fill="x", padx=int(16 * S), pady=(int(14 * S), int(6 * S)))
        tk.Label(head, text=_t("计划"), bg=T["surface"], fg=T["text"],
                 font=v4.FONT_BOLD).pack(side="left")
        self._plan_count = tk.Label(
            head, text=f"{self._plan_done}/{self._plan_total}",
            bg=T["surface"], fg=T["faint"], font=v4.FONT_SM)
        self._plan_count.pack(side="left", padx=(int(6 * S), 0))
        x = tk.Label(head, text="×", bg=T["surface"], fg=T["faint"],
                     font=(v4.DISPLAY_FAMILY, 15), cursor="hand2")
        x.pack(side="right")
        x.bind("<Button-1>", lambda e: self._toggle_plan())

        track = tk.Frame(r, bg=T["border"], height=v4.px(3))
        track.pack(fill="x", padx=int(16 * S), pady=(0, int(10 * S)))
        track.pack_propagate(False)
        if self._plan_total:
            frac = self._plan_done / float(self._plan_total)
            tk.Frame(track, bg=T["primary"], height=v4.px(3)).place(
                x=0, y=0, relwidth=frac, relheight=1)

        self.plan_txt = tk.Text(r, bg=T["surface"], fg=T["text"], bd=0,
                                highlightthickness=0, wrap="word",
                                font=v4.FONT_SM, padx=int(16 * S),
                                pady=int(4 * S))
        self.plan_txt.pack(fill="both", expand=True)
        self.plan_txt.tag_configure("done", foreground=T["faint"],
                                    font=v4.FONT_SM)
        self.plan_txt.tag_configure("todo", foreground=T["text"],
                                    font=v4.FONT_SM)
        self.plan_txt.tag_configure("cur", foreground=T["primary"],
                                    font=(v4.UI_FAMILY, 11, "bold"))
        self.plan_txt.bind("<MouseWheel>", self._plan_wheel)
        self.plan_txt.configure(state="normal")
        self._render_plan_body()
        self.plan_txt.configure(state="disabled")
        tk.Label(r, text="todo.json · " + _t("实时"), bg=T["surface"],
                 fg=T["faint"], font=v4.FONT_XS).pack(side="bottom",
                                                      pady=int(10 * S))

    def _sync_plan_btn(self):
        """顶部计划胶囊:仅在有 todo 时出现;收起时显示 ▸,展开时 ▾。"""
        b = getattr(self, "plan_btn", None)
        if b is None:
            return
        S = self._ui_scale
        if not self._plan_total:
            try:
                b.pack_forget()
            except Exception:
                pass
            return
        if b.winfo_manager() != "pack":
            try:
                b.pack(side="left", padx=(0, int(6 * S)),
                       pady=int(12 * S))
            except Exception:
                pass
        arrow = "▾" if self.plan_open else "▸"
        b.set_text(_t("计划") + f" {self._plan_done}/{self._plan_total}  {arrow}")
        b.set_kind("soft" if self.plan_open else "surface")

    def _plan_wheel(self, e):
        try:
            self.plan_txt.yview_scroll(int(-e.delta / 120), "units")
        except Exception:
            pass
        return "break"

    def _render_plan_body(self):
        tx = getattr(self, "plan_txt", None)
        if tx is None:
            return
        try:
            if not tx.winfo_exists():
                return
        except Exception:
            return
        tx.configure(state="normal")
        tx.delete("1.0", "end")
        items = self._plan_items or []
        first_open = None
        for i, x in enumerate(items, 1):
            if not isinstance(x, dict):
                continue
            done = bool(x.get("done"))
            if not done and first_open is None:
                first_open = i
            mark = "✓" if done else "○"
            tag = "done" if done else ("cur" if i == first_open else "todo")
            tx.insert("end", f"{mark}  {i}. {x.get('item', '')}\n", tag)
        if not items:
            tx.insert("end", _t("(尚无计划 — agent 会先建 todo 再执行)"), "done")
        tx.configure(state="disabled")
        if first_open:
            try:
                tx.see(f"{max(1, first_open - 1)}.0")
            except Exception:
                pass

    # ================= 目录 =================
    def choose_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.wd_var.set(d)
            self.clear_files()
            self._sync_dir_btn()
    def open_dir(self):
        d = self.wd_var.get(); os.makedirs(d, exist_ok=True)
        # v3.0.0 单一事实源:不再手写三平台分支
        subprocess.Popen(_file_manager_cmd(d))

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

    def _walk(self, w):
        yield w
        try:
            for c in w.winfo_children():
                yield from self._walk(c)
        except Exception:
            return

    def apply_theme(self):
        """v4:令牌刷新所有登记控件 + 重绘会话/标签/计划抽屉/标题栏。"""
        import ui_theme as _ut
        mode = _ut.resolve_theme_mode(self.prefs.get("ui_mode", "auto"))
        self.T = _ut.tokens(mode)
        T = self.T
        try:
            self.style.theme_use(T["ttk_theme"])
        except Exception:
            pass
        try:
            self.root.configure(bg=T["bg"])
        except Exception:
            pass
        for w, bg_key, fg_key in list(getattr(self, "_themed", [])):
            try:
                if not w.winfo_exists():
                    continue
                w.configure(bg=T[bg_key])
                if fg_key:
                    w.configure(fg=T[fg_key])
            except Exception:
                pass
        # 先复位容器底色,再重绘 Pill/Check:theme_use 会把原生 Frame/Label
        # 统一刷成 ttk 主题底色(#222222),Pill 又按 master 底色合成图片。
        # 顺序反了就会在新对话按钮、状态栏周围留下深灰方块(用户报的色差)。
        for name, key in (("sidebar", "side"), ("main", "bg"),
                          ("plan_rail", "side"), ("composer_wrap", "bg"),
                          ("header", "bg"), ("statusbar", "bg")):
            w = getattr(self, name, None)
            if w is not None:
                try:
                    w.configure(bg=T[key])
                except Exception:
                    pass
        for w in self._walk(self.root):
            try:
                if isinstance(w, v4.Pill):
                    w.apply_theme(T)
                elif isinstance(w, v4.Icon):
                    w.apply_theme(T)
                elif isinstance(w, v4.CtxBar):
                    w.apply_theme(T)
                elif isinstance(w, v4.Check):
                    w.apply_theme(T)
            except Exception:
                pass
        if hasattr(self, "sess_canvas"):
            try:
                self.sess_canvas.configure(bg=T["side"])
            except Exception:
                pass
        if hasattr(self, "composer_bg"):
            try:
                self.composer_bg.configure(bg=T["bg"])
            except Exception:
                pass
        if hasattr(self, "statusbar"):
            try:
                self.statusbar.configure(bg=T["bg"])
            except Exception:
                pass
        self._paint_search()
        if hasattr(self, "search_entry") and hasattr(self, "_search_hint"):
            try:
                self.search_entry.configure(
                    fg=T["faint"] if self.search_var.get() == self._search_hint
                    else T["text"])
            except Exception:
                pass
        self._reset_native_text_borders()
        if hasattr(self, "transcript"):
            self._configure_transcript_tags()
        if hasattr(self, "input") and hasattr(self, "_hint"):
            try:
                if self.input.get("1.0", "end-1c") == self._hint:
                    self.input.configure(fg=T["faint"])
                else:
                    self.input.configure(fg=T["text"])
            except Exception:
                pass
        self._paint_composer()
        if hasattr(self, "sess_canvas"):
            try:
                self.refresh_sessions()
            except Exception:
                pass
        self._build_plan_rail()
        self._sync_model_btn()
        self._sync_think_btn()
        self._sync_offline_ui()
        self._sync_cloud_box()
        self._sync_dir_btn()
        self._sync_mode_lbl()
        self.root.after(60, lambda m=mode: self._apply_titlebar_theme(m))

    def _reset_native_text_borders(self):
        """ttkbootstrap 2.0 的 theme_use 会遍历所有 tk.Text 并写回
        highlightthickness=1(主题重绘)。v4 用无边框文本区,主题切换后必须复位。"""
        T = self.T
        items = (
            (getattr(self, "transcript", None), T["bg"]),
            (getattr(self, "input", None), T["surface"]),
            (getattr(self, "plan_txt", None), T["side"]),
            (getattr(self, "console", None), T["code_bg"]),
            # theme_use 同样会给 tk.Entry 写回 2px 高亮边(#454545)——搜索框
            # 圆角面板里会多出一圈方框,必须一并复位。
            (getattr(self, "search_entry", None), T["surface"]),
        )
        for w, bg in items:
            if w is None:
                continue
            try:
                w.configure(highlightthickness=0, borderwidth=0, relief="flat",
                            highlightbackground=bg, highlightcolor=T["primary"])
            except Exception:
                pass

    def _apply_titlebar_theme(self, mode):
        """Windows 11:标题栏随主题走(深色不再一条白条)。失败静默。"""
        if os.name != "nt":
            return
        try:
            import ctypes
            hwnd = 0
            try:
                hwnd = int(self.root.wm_frame(), 16)
            except Exception:
                hwnd = 0
            if not hwnd:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                hwnd = self.root.winfo_id()
            dark = 1 if mode == "dark" else 0
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(ctypes.c_int(dark)), 4)

            def _bgr(hexs):
                h = str(hexs).lstrip("#")
                r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
                return (b << 16) | (g << 8) | r

            for attr, key in ((35, "bg"), (36, "text")):
                c = ctypes.c_int(_bgr(self.T[key]))
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(c), 4)
        except Exception:
            pass

    def _theme_titlebar(self, win):
        """把 DWM 深/浅标题栏套到任意 Toplevel(设置/技能等对话框不再顶着白条)。"""
        if os.name != "nt":
            return
        try:
            import ctypes
            import ui_theme as _ut
            mode = _ut.resolve_theme_mode(self.prefs.get("ui_mode", "auto"))
            hwnd = 0
            try:
                hwnd = int(win.wm_frame(), 16)
            except Exception:
                hwnd = 0
            if not hwnd:
                hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
            if not hwnd:
                hwnd = win.winfo_id()
            dark = 1 if mode == "dark" else 0
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(ctypes.c_int(dark)), 4)
        except Exception:
            pass

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
        self._refresh_att_chips()
        return names

    def _insert_attach_tag(self, names):
        """在输入框光标处插一个附件占位标记(真正的随指令发送由 attach_note 完成)。"""
        try:
            self._set_input_hint(False)
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
            dest = os.path.join(attdir, time.strftime("paste_%Y%m%d_%H%M%S_")
                                + f"{time.time_ns() % 1000000:06d}.png")
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
        self.attachments = []
        self._refresh_att_chips()
    def attach_note(self):
        if not self.attachments: return ""
        names = ", ".join(os.path.basename(a) for a in self.attachments)
        return (f"\n\n[📎 附件已放入工作目录 _attachments/ 下: {names}。"
                f"需要用它们时用 list_dir 查看 _attachments/,用 read_file 读取具体文件。]")

    def wd_dir(self):
        return self.wd_var.get() if hasattr(self, "wd_var") else os.path.join(DEFAULT_TASKS, "work")

    # ================= 会话 =================
    def refresh_sessions(self):
        """把历史会话画进侧边栏(标题 + 摘要 + 状态点 + 时间,按日期分组)。"""
        c = getattr(self, "sess_canvas", None)
        if c is None:
            return
        c.delete("all")
        self._sess_names = []
        self._sess_imgs = []
        flt = (self.search_var.get() or "").strip().lower()
        if hasattr(self, "_search_hint") and flt == self._search_hint.lower():
            flt = ""
        files = [f for f in sorted(glob.glob(os.path.join(SESSION_DIR, "*.json")),
                                   key=os.path.getmtime, reverse=True)
                 if not f.endswith((".meta.json", ".todo.json"))][:200]
        today = time.strftime("%Y-%m-%d")
        yesterday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
        buckets = {"今天": [], "昨天": [], "更早": []}
        for s in files:
            name = os.path.basename(s)[:-5]
            meta_p = os.path.join(SESSION_DIR, name + ".meta.json")
            title = ""
            status = ""
            task = ""
            mtime = os.path.getmtime(s)
            if os.path.exists(meta_p):
                try:
                    m = json.load(open(meta_p, encoding="utf-8"))
                    title = str(m.get("title", "") or "")
                    status = str(m.get("status", "") or "")
                    task = str(m.get("task", "") or "")
                    mtime = os.path.getmtime(meta_p) or mtime
                except Exception:
                    pass
            hay = (name + " " + title + " " + task).lower()
            if flt and flt not in hay:
                continue
            d = time.strftime("%Y-%m-%d", time.localtime(mtime))
            g = "今天" if d == today else ("昨天" if d == yesterday else "更早")
            buckets[g].append((name, title or name, mtime, status, task))
        S = self._ui_scale
        cw = max(c.winfo_width(), int(280 * S))
        y = int(4 * S)
        idx = 0
        for g in ("今天", "昨天", "更早"):
            rows = buckets[g]
            if not rows:
                continue
            c.create_text(int(18 * S), y + int(10 * S), text=_t(g), anchor="w",
                          font=v4.FONT_XS, fill=self.T["faint"])
            y += int(24 * S)
            for name, title, mtime, status, task in rows:
                sel = (name == self.session)
                row_w = cw - int(24 * S)
                if sel:
                    img = v4._rr_img(row_w, int(58 * S), v4.px(9),
                                     self.T["soft"], self.T["side"])
                    if img is not None:
                        c.create_image(int(12 * S), y, image=img, anchor="nw")
                        self._sess_imgs.append(img)
                dot = (self.T["ok"] if status == "done" else
                       (self.T["warn"] if status == "interrupted" else self.T["border"]))
                c.create_oval(int(20 * S), y + int(13 * S),
                              int(26 * S), y + int(19 * S), fill=dot, outline="")
                maxpx = row_w - int(28 * S) - int(46 * S)
                c.create_text(int(32 * S), y + int(21 * S),
                              text=v4.ellipsize(title, maxpx, v4.FONT_BOLD),
                              anchor="w", font=v4.FONT_BOLD,
                              fill=self.T["primary"] if sel else self.T["text"])
                sub = task if task and task != title else status
                c.create_text(int(32 * S), y + int(41 * S),
                              text=v4.ellipsize(sub, maxpx, v4.FONT_XS),
                              anchor="w", font=v4.FONT_XS, fill=self.T["faint"])
                when = (time.strftime("%H:%M", time.localtime(mtime))
                        if g in ("今天", "昨天")
                        else time.strftime("%m-%d", time.localtime(mtime)))
                c.create_text(cw - int(18 * S), y + int(21 * S), text=when,
                              anchor="e", font=v4.FONT_XS, fill=self.T["faint"])
                c.create_rectangle(int(12 * S), y, cw - int(12 * S),
                                   y + int(58 * S), outline="",
                                   fill="", tags=(f"sess{idx}",))
                c.tag_bind(f"sess{idx}", "<Button-1>",
                           lambda e, n=name: self._on_session_click(n))
                # v3.1.1:右键菜单(归档/删除)——会话列表多了以后的管理出口;
                # Button-2 兼容 macOS(那边右键是 Button-2),Win/Linux 中键同触发无害
                c.tag_bind(f"sess{idx}", "<Button-3>",
                           lambda e, n=name: self._session_menu(n, e))
                c.tag_bind(f"sess{idx}", "<Button-2>",
                           lambda e, n=name: self._session_menu(n, e))
                self._sess_names.append(name)
                idx += 1
                y += int(62 * S)
        if idx == 0:
            c.create_text(cw // 2, 24, text=_t("还没有对话"), anchor="n",
                          font=v4.FONT_SM, fill=self.T["faint"])
        c.configure(scrollregion=(0, 0, cw, max(y + 8, 60)))

    def _on_session_click(self, name):
        self._switch_session(name)

    # ---------------- v3.1.1 会话管理:归档 / 删除 ----------------
    def _session_files(self, name):
        """一个会话在磁盘上的全部侧车文件(主 JSON/转录/meta/todo),只返回存在的。"""
        return [p for p in (os.path.join(SESSION_DIR, name + ext)
                for ext in (".json", ".transcript.jsonl", ".meta.json", ".todo.json"))
                if os.path.exists(p)]

    def _session_menu(self, name, event):
        busy = bool(self.proc and self.proc.poll() is None)
        cur = (name == self.session)
        m = tk.Menu(self.root, tearoff=0, bg=self.T["surface"], fg=self.T["text"],
                    activebackground=self.T["soft"], activeforeground=self.T["text"],
                    bd=0, relief="flat")
        m.add_command(label=_t("打开"),
                      command=lambda: self._switch_session(name),
                      state="disabled" if (busy and cur) else "normal")
        m.add_command(label=_t("归档(移出列表,文件保留)"),
                      command=lambda: self._archive_session(name),
                      state="disabled" if (busy and cur) else "normal")
        m.add_command(label=_t("删除…"),
                      command=lambda: self._delete_session(name),
                      state="disabled" if (busy and cur) else "normal")
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _archive_session(self, name):
        """归档:整套会话文件移入 sessions/_archived/,侧栏/搜索不再显示;
        需要时把文件移回 sessions/ 即恢复。"""
        if name == self.session and self.proc and self.proc.poll() is None:
            self.log_note(_t("[任务运行中暂不能归档当前会话——请先停止或等它完成]"))
            return
        dst_dir = os.path.join(SESSION_DIR, "_archived")
        os.makedirs(dst_dir, exist_ok=True)
        moved = 0
        for p in self._session_files(name):
            try:
                shutil.move(p, os.path.join(dst_dir, os.path.basename(p)))
                moved += 1
            except Exception:
                pass
        if not moved:
            self.log_note(_t("[归档失败:找不到会话文件]"))
            return
        if name == self.session:
            self.new_chat()          # 归档的是当前会话:重置到新对话态
        self.refresh_sessions()
        self.log_note(_t("[已归档会话(文件移入 sessions/_archived,可随时找回)]")
                      + f" {name} ×{moved}")

    def _delete_session(self, name):
        """删除:确认后整套会话文件彻底移除(不可恢复;想保留请用归档)。"""
        if name == self.session and self.proc and self.proc.poll() is None:
            self.log_note(_t("[任务运行中暂不能删除当前会话——请先停止或等它完成]"))
            return
        import tkinter.messagebox as _mb
        if not _mb.askyesno(_t("删除对话"),
                            _t("确定彻底删除对话(转录/计划一并删除,不可恢复;只想移出列表请用「归档」)?")
                            + f"\n  {name}"):
            return
        gone = 0
        for p in self._session_files(name):
            try:
                os.remove(p)
                gone += 1
            except Exception:
                pass
        if name == self.session:
            self.new_chat()
        self.refresh_sessions()
        self.log_note(_t("[已删除会话(不可恢复)]") + f" {name} ({gone})")

    def _switch_session(self, name):
        """载入历史会话(完整转录优先,旧会话回退上下文 JSON)。
        运行中切换会串档(token 渲进被载入的会话、stop 保存错会话),所有入口
        (侧边栏/搜索窗)统一在这里拦截。"""
        if not name:
            return
        if self.proc and self.proc.poll() is None:
            self.log_note(_t("[任务运行中暂不能切换会话——请先停止或等它完成]"))
            return
        self.session = name
        self.session_title = ""
        _mt = {}
        try:
            _mt = json.load(open(os.path.join(SESSION_DIR, name + ".meta.json"),
                                 encoding="utf-8"))
        except Exception:
            pass
        self.session_title = str(_mt.get("title", "") or "")
        _swd = str(_mt.get("workdir", "") or "")
        if _swd and os.path.isdir(_swd) and _swd != self.wd_var.get():
            self.wd_var.set(_swd)
            self.log_note(_t("[已恢复该会话的工作目录: {d}]").format(d=_swd))
        self._set_session_label(name, self.session_title)
        msgs = None
        _tp = os.path.join(SESSION_DIR, name + ".transcript.jsonl")
        if os.path.exists(_tp):
            try:
                msgs = [json.loads(_ln) for _ln in open(_tp, encoding="utf-8")
                        if _ln.strip()]
            except Exception:
                msgs = None
        if msgs is None:
            p = os.path.join(SESSION_DIR, name + ".json")
            try:
                msgs = json.load(open(p, encoding="utf-8"))
            except Exception:
                msgs = None
        self.render_session(msgs, name)
        # 计划抽屉:优先该会话自己保存的 todo 快照;共享工作目录里的 todo.json
        # 可能属于别的任务(跨会话串计划,复审 P2)。
        try:
            _snap = os.path.join(SESSION_DIR, name + ".todo.json")
            _plan = json.load(open(_snap, encoding="utf-8")) if os.path.exists(_snap) else []
            if not isinstance(_plan, list):
                _plan = []
        except Exception:
            _plan = []
        self._plan_source = "session"
        self._render_plan(_plan, force=True)
        self.refresh_sessions()
        self._sync_dir_btn()
        # 载入提示进运行日志即可;会话标题已换成该会话,不必再往正文塞系统消息
        self.log(_t("[已载入会话: {name}]").format(name=name))

    def _set_session_label(self, name=None, title=""):
        self.session = name or None
        if not hasattr(self, "conv_title"):
            return
        if name:
            txt = (title + " · " + name) if title else name
            sub = _t("历史会话 · 下一条消息接续上下文")
        else:
            txt = _t("新对话")
            sub = _t("本地优先 · 小模型优先")
        try:
            self.conv_title.configure(text=v4.ellipsize(txt, 520, v4.FONT_TITLE))
            self.conv_sub.configure(text=sub)
        except Exception:
            pass

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
            if role == "user" and self._is_internal_user_msg(c):
                continue
            if role == "user":
                self._insert_user(c)
            elif role == "assistant":
                # v2.0.1 历史思考也渲染成可展开标记(会话 JSON 存有 m["thinking"],
                # 旧版直接丢弃——加载历史后再也看不到当时的思考过程)
                th = m.get("thinking")
                if th:
                    self.transcript.config(state="normal")
                    self._think_freeze(str(th))
                    self.transcript.config(state="disabled")
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
                if str(c).startswith("[TASK_COMPLETE]"):
                    continue          # 内部收尾标记,不属于对话内容
                self.transcript.config(state="normal")
                self.transcript.insert("end", "      ↳ " + str(c)[:160] + "\n", "note")
                self.transcript.config(state="disabled")
        self._scroll_transcript()

    @staticmethod
    def _is_internal_user_msg(c):
        """历史会话里混有 harness 注入的推进/自查消息,不是用户说的,不上屏。"""
        c = str(c or "").strip()
        return (c.startswith("Continue: keep making")
                or c == _t("继续之前的对话,完成或回答当前需求。")
                or c.startswith("回答已经足够")
                or "立即调用 finish" in c[:160]
                or c.startswith("任务已收尾")
                or c.startswith("⚠️ 交付前自查")
                or c.startswith("提示:run_bash 执行的是 Windows shell 命令")
                or c.startswith("[时间预算]"))

    def _insert_md(self, text):
        """轻量 markdown:代码块 → 等宽;正文前落一行"鸣鸟"标识。"""
        self.transcript.config(state="normal")
        self.transcript.insert("end", "\n", "spacer")
        self.transcript.insert("end", _t("鸣鸟") + "\n", "who")
        in_code = False
        for line in text.split("\n"):
            if line.strip().startswith("```"):
                in_code = not in_code
                continue
            tag = "code" if in_code else "asst"
            self.transcript.insert("end", line + "\n", tag)
        self.transcript.insert("end", "\n", "spacer")
        self.transcript.config(state="disabled")

    def _insert_user(self, text):
        self.transcript.config(state="normal")
        self.transcript.insert("end", "\n", "spacer")
        self.transcript.insert("end", _t("你") + "\n", "you_line")
        self.transcript.insert("end", str(text) + "\n", "user")
        self.transcript.config(state="disabled")
        self._scroll_transcript()

    def add_user_bubble(self, text):
        self._insert_user(text)

    def _scroll_transcript(self):
        self.transcript.see("end")

    def _sel_press(self, _e=None):
        self._selecting = True
        self.transcript.config(state="normal")
        return None   # 不拦默认:光标定位/拖选仍由 Tk 类绑定处理

    def _sel_release(self, _e=None):
        self._selecting = False
        self.transcript.config(state="disabled")
        return None

    def _copy_selection(self, _e=None):
        try:
            txt = self.transcript.get("sel.first", "sel.last")
            if txt:
                self.root.clipboard_clear()
                self.root.clipboard_append(txt)
        except Exception:
            pass
        return "break"

    def clear_transcript(self):
        self._set_text(self.transcript)
        self._rendered_session = None
        # 流式缓冲一并复位:否则切换会话后旧缓冲继续往新屏上写
        self._think_text = ""; self._think_live = False; self._think_hdr = False
        self._think_shown = 0; self._think_store = {}; self._think_seq = 0
        self._asst_buf = ""; self._asst_shown = 0; self._streaming_asst = False
    def _set_text(self, w):
        if w is None:
            return
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
        txt = str(txt)
        self._log_buf.append(txt)
        if len(self._log_buf) > 1000:
            del self._log_buf[:-1000]
        if self.console is not None:
            try:
                self.console.config(state="normal")
                self.console.insert("end", txt + "\n")
                self.console.see("end")
                self.console.config(state="disabled")
            except Exception:
                self.console = None

    def clear_log(self):
        self._log_buf.clear()
        if self.console is not None:
            try:
                self._set_text(self.console)
            except Exception:
                pass

    # ================= 关于 / 欢迎 =================
    def show_about(self):
        T = self.T
        S = self._ui_scale
        px = lambda n: int(n * S)
        win = tk.Toplevel(self.root)
        win.title(_t("关于"))
        win.geometry(self._scaled_geo(520, 440))
        win.configure(bg=T["bg"])
        self._theme_titlebar(win)
        win.transient(self.root)
        win.grab_set()

        banner = tk.Frame(win, bg=T["primary"], height=px(92))
        banner.pack(fill="x")
        banner.pack_propagate(False)
        tk.Label(banner, text=_t("鸣鸟 · 本地 AI 助手"), bg=T["primary"],
                 fg=T["primary_text"],
                 font=(v4.UI_FAMILY, 18, "bold")).pack(
                     anchor="w", padx=px(22), pady=(px(18), px(2)))
        tk.Label(banner, text=_t("本地优先 · 小模型优先 · 数据不出本机"),
                 bg=T["primary"], fg=T["primary_text"],
                 font=v4.FONT_SM).pack(anchor="w", padx=px(22))

        body = tk.Frame(win, bg=T["bg"])
        body.pack(fill="both", expand=True, padx=px(22), pady=px(14))
        info = (f"{_t('版本')}  {self.app_version()}\n"
                f"{_t('许可')}  Apache-2.0\n\n"
                f"{_t('全离线·小模型优先的本地 AI agent')}\n"
                f"Ollama + iGPU / NVIDIA / CPU")
        tk.Label(body, text=info, bg=T["bg"], fg=T["muted"],
                 font=v4.FONT_SM, justify="left", anchor="w").pack(fill="x")

        docs = {"README": "README_EN.md",
                "RELEASE_NOTES.md": "RELEASE_NOTES.md",
                "AGENTS.md": "AGENTS.md",
                "LICENSE": "LICENSE"}
        df = tk.Frame(body, bg=T["bg"])
        df.pack(fill="x", pady=(14, 0))
        for label, fn in docs.items():
            v4.Pill(df, label, lambda n=fn: self._open_doc(n), T,
                    kind="surface", h=30, padx=12,
                    font=v4.FONT_XS).pack(side="left", padx=(0, 6))
        df2 = tk.Frame(body, bg=T["bg"])
        df2.pack(fill="x", pady=(8, 0))
        v4.Pill(df2, _t("打开安装目录"),
                lambda: subprocess.Popen(_file_manager_cmd(AGENT_DIR)), T,
                kind="ghost", h=30, padx=12,
                font=v4.FONT_XS).pack(side="left")

        foot = tk.Frame(win, bg=T["bg"])
        foot.pack(fill="x", padx=px(22), pady=(0, px(16)))
        v4.Pill(foot, _t("关闭"), win.destroy, T, kind="primary", h=32,
                padx=18).pack(side="right")
        win.bind("<Escape>", lambda e: win.destroy())

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
        """空状态:一句产品定位 + 四条可点的上手建议。"""
        if self.transcript.get("1.0", "end-1c").strip():
            return
        self.transcript.config(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.insert("end", "\n", "spacer")
        self.transcript.insert("end", _t("有什么可以帮你?") + "\n", "welcome_title")
        self.transcript.insert("end", _t("本地优先 · 小模型优先 · 数据不出本机") + "\n",
                               "welcome_sub")
        for t in (_t("写一个 Python 脚本并跑测试"),
                  _t("整理这个目录里的文件"),
                  _t("查资料并汇总成报告"),
                  _t("解释这段代码在做什么")):
            self.transcript.insert("end", "· " + t + "\n", "sugg")
        self.transcript.insert("end", "\n", "spacer")
        self.transcript.insert("end", _t("Enter 发送 · Shift+Enter 换行;点上面的建议可直接填入输入框。") + "\n",
                               "note")
        self.transcript.config(state="disabled")

    # ================= 技能 / 搜索 =================
    def show_skills(self):
        """技能列表(v4 皮肤):同一份内容,改成主题化滚动卡片,
        不再用 ttkbootstrap 默认白底 + Consolas 8 号字的记事本观感。"""
        T = self.T
        S = self._ui_scale
        px = lambda n: int(n * S)
        win = tk.Toplevel(self.root)
        win.title(_t("技能列表"))
        win.geometry(self._scaled_geo(700, 640))
        win.configure(bg=T["bg"])
        self._theme_titlebar(win)
        win.transient(self.root)

        head = tk.Frame(win, bg=T["bg"])
        head.pack(fill="x", padx=px(20), pady=(px(16), px(2)))
        tk.Label(head, text=_t("技能列表"), bg=T["bg"], fg=T["text"],
                 font=v4.FONT_TITLE).pack(side="left")
        v4.Icon(head, "×", win.destroy, T,
                font=(v4.DISPLAY_FAMILY, 13)).pack(side="right")
        tk.Label(win, text=_t("本地 agent 可用技能(渐进式:用到才加载全文)"),
                 bg=T["bg"], fg=T["muted"], font=v4.FONT_SM).pack(
                     anchor="w", padx=px(20))

        card = tk.Frame(win, bg=T["surface"], highlightthickness=1,
                        highlightbackground=T["border"])
        card.pack(fill="both", expand=True, padx=px(20), pady=(px(10), px(12)))
        txt = tk.Text(card, wrap="word", width=1, height=1, bd=0,
                      highlightthickness=0, bg=T["surface"], fg=T["text"],
                      font=v4.FONT_SM, padx=px(16), pady=px(12),
                      spacing1=px(1), spacing3=px(2), cursor="arrow")
        txt.pack(fill="both", expand=True)
        txt.tag_configure("h", foreground=T["text"], font=v4.FONT_BOLD,
                          spacing1=14, spacing3=6)
        txt.tag_configure("name", foreground=T["text"], font=v4.FONT_BOLD,
                          spacing1=9, spacing3=1)
        txt.tag_configure("desc", foreground=T["muted"], font=v4.FONT_SM,
                          lmargin1=18, lmargin2=18)
        txt.tag_configure("path", foreground=T["faint"], font=v4.MONO_SM,
                          lmargin1=18, lmargin2=18, spacing3=2)
        txt.tag_configure("muted", foreground=T["faint"], font=v4.FONT_SM)
        txt.bind("<MouseWheel>",
                 lambda e: (txt.yview_scroll(int(-e.delta / 120), "units"),
                            "break")[1])

        seen = {}
        for base in SKILL_DIRS:
            if os.path.isdir(base):
                for f in sorted(os.listdir(base)):
                    if f.endswith((".md", ".txt", ".py")):
                        name = f.rsplit(".", 1)[0]
                        if name not in seen:
                            seen[name] = self._skill_desc(os.path.join(base, f))
        # v1.9.1:自装技能与 MCP 的可见性(用户问过"怎么装自己的技能/MCP")
        txt.insert("end", "〔" + _t("技能目录") + "〕\n", "h")
        for d in SKILL_DIRS:
            txt.insert("end", d + "\n", "path")
        txt.insert("end", _t("  自定义技能:把 .md 文件(开头写 name/description)放进上面的\"技能\"目录即可,重启后生效\n"),
                   "muted")
        txt.insert("end", "〔MCP〕\n", "h")
        txt.insert("end", self._mcp_summary() + "\n", "desc")
        txt.insert("end", _t("已装技能") + " · " + str(len(seen)) + "\n", "h")
        if not seen:
            txt.insert("end", _t("(暂无技能)") + "\n", "muted")
        for n in sorted(seen):
            txt.insert("end", n + "\n", "name")
            if seen[n]:
                txt.insert("end", seen[n] + "\n", "desc")
        txt.config(state="disabled")

        foot = tk.Frame(win, bg=T["bg"])
        foot.pack(fill="x", padx=px(20), pady=(0, px(14)))
        tk.Label(foot, text=_t("渐进式加载 · 只列名字与一句话描述"),
                 bg=T["bg"], fg=T["faint"], font=v4.FONT_XS).pack(side="left")
        v4.Pill(foot, _t("关闭"), win.destroy, T, kind="surface", h=32,
                padx=16).pack(side="right")
        win.bind("<Escape>", lambda e: win.destroy())

    def _mcp_summary(self):
        """技能窗里的 MCP 一览:配置了几台服务器、名字,以及没配时的上手提示。"""
        try:
            import ollama_agent as _oa
            servers = list(_oa.load_mcp_servers().keys())
        except Exception:
            servers = []
        if servers:
            return (_t("已配置 MCP 服务器") + f": {', '.join(servers)}\n" +
                    _t("对话中说\"用 MCP\"或让它 enable_tools 即可调用;配置文件:"))
        return (_t("(未配置 MCP 服务器)") + "\n" +
                _t("配置文件") + f": {os.path.join(AGENT_HOME, 'mcp.json')}\n" +
                _t("示例仓库根目录有 mcp_utils_server.py(时间/计算/哈希)可直接体验"))
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
        """历史搜索(v4 皮肤):同一份检索逻辑,换成主题化输入框/列表/底栏。"""
        T = self.T
        S = self._ui_scale
        px = lambda n: int(n * S)
        win = tk.Toplevel(self.root)
        win.title(_t("会话历史搜索"))
        win.geometry(self._scaled_geo(700, 520))
        win.configure(bg=T["bg"])
        self._theme_titlebar(win)
        win.transient(self.root)

        head = tk.Frame(win, bg=T["bg"])
        head.pack(fill="x", padx=px(20), pady=(px(16), px(8)))
        tk.Label(head, text=_t("会话历史搜索"), bg=T["bg"], fg=T["text"],
                 font=v4.FONT_TITLE).pack(side="left")
        v4.Icon(head, "×", win.destroy, T,
                font=(v4.DISPLAY_FAMILY, 13)).pack(side="right")

        top = tk.Frame(win, bg=T["bg"])
        top.pack(fill="x", padx=px(20))
        wrap = tk.Frame(top, bg=T["surface"], highlightthickness=1,
                        highlightbackground=T["border"],
                        highlightcolor=T["primary"])
        wrap.pack(side="left", fill="x", expand=True)
        kw = tk.StringVar()
        ent = tk.Entry(wrap, textvariable=kw, bg=T["surface"], fg=T["text"],
                       insertbackground=T["text"], bd=0,
                       highlightthickness=0, font=v4.FONT_SM)
        ent.pack(fill="x", padx=px(9), pady=px(7))
        ent.bind("<Return>", lambda e: do_search())
        v4.Pill(top, _t("搜索"), lambda: do_search(), T, kind="primary",
                h=32, padx=16).pack(side="left", padx=(8, 0))

        card = tk.Frame(win, bg=T["surface"], highlightthickness=1,
                        highlightbackground=T["border"])
        card.pack(fill="both", expand=True, padx=px(20), pady=(px(10), px(8)))
        lb = tk.Listbox(card, font=v4.FONT_SM, relief="flat", bd=0,
                        highlightthickness=0, activestyle="none",
                        bg=T["surface"], fg=T["text"],
                        selectbackground=T["sel"], selectforeground=T["text"])
        lb.pack(fill="both", expand=True, padx=px(6), pady=px(6))
        results = []

        def _row(text):
            lb.insert("end", v4.ellipsize(text, 600, v4.FONT_SM))

        def do_search():
            q = kw.get().strip().lower()
            lb.delete(0, "end")
            results.clear()
            if not q:
                _row(_t("(输入关键词再搜索)"))
                return
            files = [f for f in glob.glob(os.path.join(SESSION_DIR, "*.json"))
                     if not f.endswith((".meta.json", ".todo.json"))]
            for s in sorted(files):
                name = os.path.basename(s)[:-5]
                try:
                    msgs = json.load(open(s, encoding="utf-8"))
                except Exception:
                    continue
                text = " ".join(str(m.get("content", "")) for m in msgs)
                idx = text.lower().find(q)
                if idx < 0:
                    continue
                snip = text[max(0, idx - 55):idx + 120].replace("\n", " ")
                results.append(name)
                _row(f"{name}  ·  …{snip}…")
            if not results:
                _row(_t("(未找到含 '{q}' 的会话)").format(q=q))

        def view_sel():
            sel = lb.curselection()
            if sel and results:
                self.view_transcript(results[sel[0]])

        def load_sel():
            sel = lb.curselection()
            if not sel or not results:
                return
            self._switch_session(results[sel[0]])
            win.destroy()

        lb.bind("<Double-Button-1>", lambda e: view_sel())

        foot = tk.Frame(win, bg=T["bg"])
        foot.pack(fill="x", padx=px(20), pady=(0, px(14)))
        tk.Label(foot, text=_t("双击结果查看完整对话"), bg=T["bg"],
                 fg=T["faint"], font=v4.FONT_XS).pack(side="left")
        v4.Pill(foot, _t("恢复此会话"), load_sel, T, kind="primary", h=32,
                padx=14).pack(side="right")
        v4.Pill(foot, _t("查看对话"), view_sel, T, kind="surface", h=32,
                padx=14).pack(side="right", padx=(0, 8))
        ent.focus_set()
        win.bind("<Escape>", lambda e: win.destroy())

    def view_transcript(self, name):
        """会话回放(v4 皮肤):等宽/正文分标签,颜色全走令牌。"""
        T = self.T
        S = self._ui_scale
        px = lambda n: int(n * S)
        win = tk.Toplevel(self.root)
        win.title(_t("会话回放: {name}").format(name=name))
        win.geometry(self._scaled_geo(820, 620))
        win.configure(bg=T["bg"])
        self._theme_titlebar(win)
        win.transient(self.root)

        head = tk.Frame(win, bg=T["bg"])
        head.pack(fill="x", padx=px(20), pady=(px(16), px(2)))
        tk.Label(head, text=_t("会话回放"), bg=T["bg"], fg=T["text"],
                 font=v4.FONT_TITLE).pack(side="left")
        v4.Icon(head, "×", win.destroy, T,
                font=(v4.DISPLAY_FAMILY, 13)).pack(side="right")
        tk.Label(win, text=name, bg=T["bg"], fg=T["muted"],
                 font=v4.FONT_SM).pack(anchor="w", padx=px(20))

        card = tk.Frame(win, bg=T["surface"], highlightthickness=1,
                        highlightbackground=T["border"])
        card.pack(fill="both", expand=True, padx=px(20), pady=(px(10), px(16)))
        txt = tk.Text(card, wrap="word", width=1, height=1, bd=0,
                      highlightthickness=0, bg=T["surface"], fg=T["text"],
                      font=v4.FONT, padx=px(16), pady=px(12),
                      spacing1=px(2), spacing3=px(3), cursor="arrow")
        txt.pack(fill="both", expand=True)
        txt.bind("<MouseWheel>",
                 lambda e: (txt.yview_scroll(int(-e.delta / 120), "units"),
                            "break")[1])

        p = os.path.join(SESSION_DIR, name + ".json")
        try:
            msgs = json.load(open(p, encoding="utf-8"))
        except Exception:
            txt.insert("end", _t("(读取失败)"))
            txt.config(state="disabled")
            return
        for m in msgs:
            role = m.get("role")
            c = m.get("content", "") or ""
            if role == "system":
                continue
            if role == "user" and self._is_internal_user_msg(c):
                continue
            if role == "user":
                txt.insert("end", f"\n{_t('你')}\n", "u")
                txt.insert("end", f"{c}\n", "a")
            elif role == "assistant":
                for tc in m.get("tool_calls", []):
                    fn = tc.get("function", {})
                    txt.insert("end", "\n⚙ " + fn.get('name', '') + " " +
                               json.dumps(fn.get('arguments', {}),
                                          ensure_ascii=False)[:120] + "\n", "t")
                if c:
                    txt.insert("end", f"\n▸ {c}\n", "a")
            elif role == "tool":
                txt.insert("end", f"   ↳ {str(c)[:200]}\n", "r")
        txt.tag_config("u", foreground=T["primary"], font=v4.FONT_BOLD,
                       spacing1=px(12), spacing3=px(2))
        txt.tag_config("a", foreground=T["text"], font=v4.FONT)
        txt.tag_config("t", foreground=T["warn"], font=v4.MONO_SM,
                       lmargin1=px(4), lmargin2=px(4))
        txt.tag_config("r", foreground=T["muted"], font=v4.FONT_XS,
                       lmargin1=px(8), lmargin2=px(8))
        txt.config(state="disabled")
        win.bind("<Escape>", lambda e: win.destroy())

    # ================= 设置 =================
    # v2.1.1 引擎预设:名字 → OpenAI 兼容 base_url(端口为各家出厂默认)。
    # llama.app = llama.cpp 官方桌面应用的本地服务;选预设只填 base_url,均可手改。
    ENGINE_PRESETS = [("Ollama", ""),
                      ("LM Studio", "http://127.0.0.1:1234/v1"),
                      ("llama.app", "http://127.0.0.1:9931/v1"),
                      ("llama.cpp server", "http://127.0.0.1:8080/v1")]

    def open_settings(self):
        """设置对话框(v4 皮肤):配置项与保存逻辑不变,只把 ttkbootstrap 的
        灰底输入框/蓝按钮换成令牌化控件,与主界面同一套视觉。"""
        T = self.T
        S = self._ui_scale
        px = lambda n: int(n * S)
        win = tk.Toplevel(self.root)
        win.title(_t("设置"))
        win.geometry(self._scaled_geo(660, 820))
        win.configure(bg=T["bg"])
        self._theme_titlebar(win)
        win.transient(self.root)
        prefs = dict(self.prefs)

        # ttk 下拉/微调也走令牌:否则浅色下是系统灰边,深色下白底。
        try:
            st = self.style
            st.configure("V4.TCombobox", fieldbackground=T["surface"],
                         background=T["surface"], foreground=T["text"],
                         arrowcolor=T["muted"], bordercolor=T["border"],
                         lightcolor=T["surface"], darkcolor=T["surface"],
                         padding=(px(9), px(5)))
            st.map("V4.TCombobox",
                   fieldbackground=[("readonly", T["surface"])],
                   foreground=[("readonly", T["text"])],
                   bordercolor=[("focus", T["primary"])],
                   arrowcolor=[("active", T["primary"])])
            st.configure("V4.TSpinbox", fieldbackground=T["surface"],
                         background=T["surface"], foreground=T["text"],
                         arrowcolor=T["muted"], bordercolor=T["border"],
                         lightcolor=T["surface"], darkcolor=T["surface"],
                         padding=(px(8), px(5)))
            st.map("V4.TSpinbox",
                   fieldbackground=[("readonly", T["surface"])],
                   foreground=[("readonly", T["text"])],
                   bordercolor=[("focus", T["primary"])])
        except Exception:
            pass

        head = tk.Frame(win, bg=T["bg"])
        head.pack(fill="x", padx=px(22), pady=(px(16), px(2)))
        tk.Label(head, text=_t("设置"), bg=T["bg"], fg=T["text"],
                 font=v4.FONT_TITLE).pack(side="left")
        v4.Icon(head, "×", win.destroy, T, font=(v4.DISPLAY_FAMILY, 13)).pack(side="right")

        # 底部按钮条先占位(云端协议多两行后,后 pack 的按钮会被挤出窗口)
        bottom = tk.Frame(win, bg=T["bg"])
        bottom.pack(side="bottom", fill="x", padx=px(22),
                    pady=(px(10), px(16)))
        body = tk.Frame(win, bg=T["bg"])
        body.pack(fill="both", expand=True, padx=px(22), pady=(px(4), 0))

        def section(text, first=False):
            tk.Label(body, text=text, bg=T["bg"], fg=T["faint"],
                     font=v4.FONT_XS).pack(anchor="w",
                                           pady=(0 if first else px(12), px(5)))

        def card():
            outer = tk.Frame(body, bg=T["surface"], highlightthickness=1,
                             highlightbackground=T["border"],
                             highlightcolor=T["border"])
            outer.pack(fill="x")
            inner = tk.Frame(outer, bg=T["surface"])
            inner.pack(fill="x", padx=px(16), pady=px(12))
            return inner

        def lab(parent, text, fg="text", font=v4.FONT_SM):
            return tk.Label(parent, text=text, bg=T["surface"], fg=T[fg],
                            font=font)

        def entry(parent, width=20, show=None):
            wrap = tk.Frame(parent, bg=T["surface"], highlightthickness=1,
                            highlightbackground=T["border"],
                            highlightcolor=T["primary"])
            e = tk.Entry(wrap, bg=T["surface"], fg=T["text"],
                         insertbackground=T["text"], bd=0,
                         highlightthickness=0, font=v4.FONT_SM, width=width)
            if show:
                e.configure(show=show)
            e.pack(fill="x", padx=px(8), pady=px(5))
            return wrap, e

        def combo(parent, values, width=10):
            return ttk.Combobox(parent, values=values, width=width,
                                state="readonly", style="V4.TCombobox")

        # ---- 引擎 ----
        section(_t("推理引擎"), first=True)
        c1 = card()
        c1.columnconfigure(1, weight=1)
        _lb = appconfig.local_backend()
        _cur_base = _lb.get("base_url", "") if _lb.get("type") == "openai" else ""
        _CUSTOM = _t("自定义 OpenAI 兼容")
        _CLOUD = _t("云端 API")
        _cloud = dict(appconfig.load_config().get("cloud") or {})
        _cloud_on = bool(_cloud.get("enabled") and _cloud.get("base_url")
                         and _cloud.get("model"))

        lab(c1, _t("推理引擎")).grid(row=0, column=0, sticky="w", pady=px(4))
        r0 = tk.Frame(c1, bg=T["surface"])
        r0.grid(row=0, column=1, sticky="ew", padx=(px(14), 0), pady=px(4))
        eng = combo(r0, [p[0] for p in self.ENGINE_PRESETS] + [_CUSTOM, _CLOUD], 14)
        _sel = "Ollama" if _lb.get("type") == "ollama" else _CUSTOM
        for _n, _u in self.ENGINE_PRESETS[1:]:
            if _cur_base == _u:
                _sel = _n
        if _cloud_on:
            _sel = _CLOUD
        eng.set(_sel)
        eng.pack(side="left")

        # 端点 / Key 两行本地与云端共用;云端多一行模型名。
        _model_row = {"lab": None, "frame": None}

        lab(c1, _t("端点")).grid(row=1, column=0, sticky="w", pady=px(4))
        r1 = tk.Frame(c1, bg=T["surface"])
        r1.grid(row=1, column=1, sticky="ew", padx=(px(14), 0), pady=px(4))
        base_wrap, base = entry(r1, width=1)
        base.insert(0, (_cloud.get("base_url") or "") if _cloud_on
                    else (_cur_base or self.ENGINE_PRESETS[1][1]))
        base_wrap.pack(fill="x", expand=True)

        lab(c1, "API Key").grid(row=2, column=0, sticky="w", pady=px(4))
        r2 = tk.Frame(c1, bg=T["surface"])
        r2.grid(row=2, column=1, sticky="ew", padx=(px(14), 0), pady=px(4))
        key_wrap, key = entry(r2, width=1, show="•")
        key.insert(0, (_cloud.get("api_key") or "") if _cloud_on
                   else ((_lb.get("api_key") or "") if _lb.get("type") == "openai" else ""))
        key_wrap.pack(fill="x", expand=True)

        _model_lab = lab(c1, _t("模型"))
        _model_lab.grid(row=3, column=0, sticky="w", pady=px(4))
        r3 = tk.Frame(c1, bg=T["surface"])
        r3.grid(row=3, column=1, sticky="ew", padx=(px(14), 0), pady=px(4))
        cloud_model_wrap, cloud_model = entry(r3, width=1)
        cloud_model.insert(0, _cloud.get("model") or "")
        cloud_model_wrap.pack(fill="x", expand=True)
        _model_row["lab"], _model_row["frame"] = _model_lab, r3

        _hint = lab(c1, "", fg="faint", font=v4.FONT_XS)
        _hint.grid(row=4, column=1, sticky="w", padx=(px(14), 0), pady=(0, px(4)))

        def _sync_eng_rows(*_e):
            cloud = eng.get() == _CLOUD
            for w in (_model_row["lab"], _model_row["frame"]):
                try:
                    w.grid() if cloud else w.grid_remove()
                except Exception:
                    pass
            _hint.configure(text=(_t("云端仅联网可用；api_key 只存本机")
                                  if cloud else _t("本地服务 API Key 可空")))
        _sync_eng_rows()

        def _eng_picked(_e=None):
            if eng.get() == _CLOUD:
                base.delete(0, "end")
                base.insert(0, _cloud.get("base_url") or "")
                key.delete(0, "end")
                key.insert(0, _cloud.get("api_key") or "")
                cloud_model.delete(0, "end")
                cloud_model.insert(0, _cloud.get("model") or "")
            else:
                for _n, _u in self.ENGINE_PRESETS[1:]:
                    if eng.get() == _n:
                        base.delete(0, "end")
                        base.insert(0, _u)
                key.delete(0, "end")
                if _lb.get("type") == "openai":
                    key.insert(0, _lb.get("api_key") or "")
            _sync_eng_rows()
        eng.bind("<<ComboboxSelected>>", _eng_picked)

        # ---- 生成参数 ----
        section(_t("生成参数"))
        c2 = card()
        r2a = tk.Frame(c2, bg=T["surface"])
        r2a.pack(fill="x")
        lab(r2a, _t("上下文窗口")).pack(side="left")
        # v2.1.3:补 512K/1M 档;模型实际低于所选档位时由引擎侧截断/告警。
        ctx = combo(r2a, [16384, 32768, 65536, 131072, 262144,
                          524288, 1048576], 8)
        # v2.0.0 修复:tk values 读回是字符串,int 与 str 恒不等会把每次打开
        # 的显示值重置成 32768。统一转 int 再比。
        _ctx_vals = [int(v) for v in ctx["values"]]
        if prefs["ctx"] not in _ctx_vals:
            prefs["ctx"] = 32768
        ctx.set(prefs["ctx"])
        ctx.pack(side="left", padx=(px(8), px(20)))
        lab(r2a, _t("输出上限")).pack(side="left")
        np = combo(r2a, [512, 1024, 2048, 4096, 8192,
                        16384, 32768, _t("不限")], 7)
        np.set(_t("不限") if prefs["num_predict"] == -1 else prefs["num_predict"])
        np.pack(side="left", padx=(px(8), 0))

        r2b = tk.Frame(c2, bg=T["surface"])
        r2b.pack(fill="x", pady=(px(8), 0))
        lab(r2b, _t("温度")).pack(side="left")
        temp = ttk.Spinbox(r2b, from_=0.0, to=2.0, increment=0.1, width=5,
                           style="V4.TSpinbox")
        temp.set("" if prefs.get("temp") is None else prefs["temp"])
        temp.pack(side="left", padx=(px(8), px(12)))
        lab(r2b, _t("留空=用 Ollama 默认"), fg="faint",
            font=v4.FONT_XS).pack(side="left")

        # ---- 命令输出 ----
        section(_t("命令输出"))
        c3 = card()
        r3 = tk.Frame(c3, bg=T["surface"])
        r3.pack(fill="x")
        # v3.0.0 三态:自动(≤32K)/强制开/强制关;旧布尔在 ≤32K 时关不掉。
        _slim_map = {None: _t("自动(≤32K)"), True: _t("开"), False: _t("关")}
        _slim_rev = {v: k for k, v in _slim_map.items()}
        # 显示 config 层手动值,而非环境变量覆盖后的有效值(否则会被写回)。
        _slim_cfg = appconfig.load_config().get("slim_output", "auto")
        if isinstance(_slim_cfg, bool):
            _slim_cur = True if _slim_cfg else None
        else:
            _v = str(_slim_cfg).strip().lower()
            _slim_cur = (True if _v in ("on", "1", "true", "yes")
                         else (False if _v in ("off", "0", "false", "no") else None))
        _env_slim = os.environ.get("AGENT_SLIM_OUTPUT", "").strip().lower()
        lab(r3, _t("命令输出精简")).pack(side="left")
        slim_var = tk.StringVar(value=_slim_map.get(_slim_cur, _slim_map[None]))
        ttk.Combobox(r3, textvariable=slim_var, state="readonly",
                     width=14, values=list(_slim_map.values()),
                     style="V4.TCombobox").pack(side="left",
                                                   padx=(px(8), px(12)))
        lab(r3, _t("超长输出只留末尾"), fg="faint",
            font=v4.FONT_XS).pack(side="left")
        if _env_slim in ("1", "true", "yes", "on", "0", "false", "no", "off"):
            lab(r3, _t("环境变量覆盖中"), fg="warn",
                font=v4.FONT_XS).pack(side="left", padx=(px(10), 0))

        # ---- 系统提示 ----
        section(_t("系统提示"))
        c4 = card()
        sys_en = tk.BooleanVar(value=prefs["sys_enable"])
        v4.Check(c4, _t("启用自定义系统提示(替代内置,可大幅改造行为)"),
                 sys_en, T, font=v4.FONT_SM).pack(anchor="w")
        tw = tk.Frame(c4, bg=T["surface"], highlightthickness=1,
                      highlightbackground=T["border"],
                      highlightcolor=T["primary"])
        tw.pack(fill="both", expand=True, pady=(px(10), 0))
        sys_txt = tk.Text(tw, height=5, width=1, bd=0, highlightthickness=0,
                          wrap="word",
                          bg=T["code_bg"], fg=T["text"],
                          insertbackground=T["text"], font=v4.MONO,
                          padx=10, pady=8)
        sys_txt.pack(fill="both", expand=True)
        sys_txt.insert("1.0", prefs["sys_text"])

        tk.Label(bottom, text=_t("保存后自下一个任务起生效"), bg=T["bg"],
                 fg=T["faint"], font=v4.FONT_XS).pack(side="left")

        def save():
            # v2.1.1 引擎持久化:写 config.json(config.json 是 agent 子进程的
            # 同源配置,不进 gui_prefs)。Ollama=清回默认;openai=base_url 归一。
            _sel = eng.get()
            _base = base.get().strip().rstrip("/")
            _cfg = dict(appconfig.load_config())
            if _sel == _CLOUD:
                # 云端是互斥协议:启用后仅联网可用(cloud_provider 会拦断网),
                # 这里顺手把 offline_mode 关掉,避免"云端 + 断网"的矛盾状态。
                _c = dict(_cfg.get("cloud") or {})
                _c["base_url"] = _base
                _k = key.get().strip()
                if _k:
                    _c["api_key"] = _k
                _c["model"] = cloud_model.get().strip()
                _c["enabled"] = bool(_c["base_url"] and _c["model"])
                _cfg["cloud"] = _c
                if _c["enabled"]:
                    _cfg["offline_mode"] = False
                else:
                    self.log_note(_t("[云端配置不完整:需要端点与模型名,未启用]"))
            else:
                _c = dict(_cfg.get("cloud") or {})
                if _c.get("enabled"):
                    _c["enabled"] = False
                    _cfg["cloud"] = _c
                if _sel == "Ollama" or not _base.startswith("http"):
                    _cfg["local_backend"] = {"type": "ollama"}
                else:
                    _cfg["local_backend"] = {"type": "openai", "base_url": _base,
                                             "api_key": key.get().strip()}
            # 命令输出精简三态进 config 层(agent 子进程同源读取)
            _slim_pick = _slim_rev.get(slim_var.get(), None)
            _cfg["slim_output"] = ("auto" if _slim_pick is None
                                   else ("on" if _slim_pick else "off"))
            appconfig.save_config(_cfg)
            _raw_t = temp.get().strip()
            if _raw_t == "":
                prefs["temp"] = None            # 留空=未设置 → ollama 默认
            else:
                try:
                    prefs["temp"] = max(0.0, min(2.0, float(_raw_t)))
                except ValueError:
                    # 手误输入不崩、不静默改语义:保留原设置并提示
                    prefs["temp"] = self.prefs.get("temp")
                    self.log_note(_t("温度输入无效,已保留原设置"))
            prefs["ctx"] = int(ctx.get())
            # 输出上限:"不限" → -1(ollama 无限生成);数字形态走 int
            _np_raw = np.get()
            prefs["num_predict"] = -1 if _np_raw in (_t("不限"), "Unlimited", "-1") else int(_np_raw)
            prefs["sys_enable"] = sys_en.get()
            prefs["sys_text"] = sys_txt.get("1.0", "end").strip()
            self.prefs.update(prefs)
            if prefs["sys_enable"] and prefs["sys_text"]:
                open(SYS_OVERRIDE_FILE, "w", encoding="utf-8").write(prefs["sys_text"])
            self.save_prefs()
            # 引擎切换立即生效:重刷模型下拉(下个任务起 agent 读同一 config)
            try:
                self.refresh_models()
            except Exception:
                pass
            if _sel == _CLOUD and (_cfg.get("cloud") or {}).get("enabled"):
                self.model_var.set("")     # 云端模式清空本地选择,顶部胶囊显示 ☁ model
            self._sync_cloud_box()
            self._sync_offline_ui()
            self._sync_mode_lbl()
            self._sync_model_btn()
            self.log_note(_t("[设置已保存:自下一个任务起生效(运行中的任务不受影响)]"))
            win.destroy()

        v4.Pill(bottom, _t("保存"), save, T, kind="primary", h=34,
                padx=20).pack(side="right")
        v4.Pill(bottom, _t("取消"), win.destroy, T, kind="ghost", h=34,
                padx=16).pack(side="right", padx=(0, 8))
        win.bind("<Escape>", lambda e: win.destroy())

    # ================= 运行 =================
    def _input_text(self):
        t = self.input.get("1.0", "end").strip()
        return None if t in (_t("输入任务或对话…(Enter 发送 · Shift+Enter 换行)"), "") else t

    def run_agent(self):
        # 统一为一个发送入口:模型自己判断是聊天还是任务
        self.send_chat()

    def _on_enter_key(self, e):
        """v3.0.0 输入快捷键与主流对齐:Enter=发送,Shift+Enter=换行。
        Shift 走默认行为(插入换行);发送路径必须 break——否则默认换行会
        跟在已被清空的输入框后面。Ctrl+Enter 保留为发送别名(独立绑定更具体,
        Tk 只触发它,不会同时触发本绑定)。Windows IME 组合中的 Enter 由输入法
        消费(VK_PROCESSKEY),不会到这里,中文打字不受影响。"""
        if e.state & 0x0001:          # Shift 按下 → 换行
            return None
        self.send_chat()
        return "break"

    def send_chat(self):
        if self.proc and self.proc.poll() is None:
            self.log_note(_t("[忙:当前任务运行中,先停止再发送]")); return
        msg = self._input_text()
        if not msg: return
        self.input.delete("1.0", "end")
        if not self.session:
            self.clear_transcript()   # 新对话的第一条消息:清掉欢迎空状态
        self._flush_asst()
        self.add_user_bubble(msg)
        # v1.8.2 会话隔离:新对话的第一条消息强制清掉工作目录里上一任务遗留的
        # .agent_state.json/todo.json(错误记忆的第三条通道);同一对话内的追问
        # 才按"续跑"勾选决定是否续接进度。
        fresh = not self.session
        if fresh:
            # v2.0.2 会话命名:新对话第一句话前 15 字 + 时间后缀,纯程序实现
            # (v2.0.1 的模型起名实测不出,弃用;首行全空/非法 → 退回 chat_ 前缀)
            _name15 = _first_msg_title(msg)
            self.session = (f"{_name15}_" if _name15 else "chat_") + time.strftime("%m%d_%H%M%S")
            self.session_title = ""
            self._set_session_label(self.session, self.session_title)
        self.launch(msg, use_session=True,
                    resume_ok=(self.resume_var.get() and not fresh))

    # ================= 语音输入 =================
    def toggle_stt_lang(self):
        """语音语言 中↔EN(v1.9.1 双语内置模型);选择持久化到 gui_prefs。"""
        cur = self.prefs.get("stt_lang", "zh")
        self.prefs["stt_lang"] = "en" if cur == "zh" else "zh"
        self.save_prefs()
        self.stt_lang_btn.set_text("EN" if self.prefs["stt_lang"] == "en" else "中")
        self.log_note(_t("[语音语言: 中文]") if self.prefs["stt_lang"] == "zh"
                      else _t("[语音语言: 英文]"))
        self.refresh_voice_state()

    def refresh_voice_state(self):
        # STT 已独立(本地 sherpa-onnx 中英双语内置),所有模型都可用语音;
        # 若所选语言的本地 STT 不可用则回退到模型音频能力
        def _check():
            lang = self.prefs.get("stt_lang", "zh")
            model = self._model_map.get(self.model_var.get())
            ok = voice_input.local_stt_available(lang) or (model and voice_input.model_audio_capable(model))
            self.mic_btn.set_enabled(ok)
            self.mic_btn.set_text(_t("语音") if ok else _t("无音频"))
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
            self.mic_btn.set_text(_t("转写中…")); self.mic_btn.set_enabled(False)
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
                self.mic_btn.set_text(_t("■ 停止录音")); self.mic_btn.set_kind("danger")
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
            lang = self.prefs.get("stt_lang", "zh")
            text = voice_input.transcribe(stt, wav, lang)
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
                                   capture_output=True,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                else:
                    import signal
                    try:
                        os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
                    except Exception:
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

    def _set_running(self, running):
        try:
            self.send_btn.set_enabled(not running)
        except Exception:
            pass
        try:
            if running:
                self.stop_btn.pack(side="right", padx=(0, 6))
                self.stop_btn.set_enabled(True)
            else:
                self.stop_btn.pack_forget()
                self.stop_btn.set_enabled(False)
        except Exception:
            pass

    def new_chat(self):
        """整场重开:会话、上下文、工作目录、计划面板全部复位。"""
        if self.proc and self.proc.poll() is None:
            self._kill_tree()
        self._run_seq = int(getattr(self, "_run_seq", 0)) + 1
        self._run_id = self._run_seq
        self._drain_q()
        _old_wd = self.wd_var.get() if hasattr(self, "wd_var") else None
        for _wd in {_old_wd, os.path.join(DEFAULT_TASKS, "work")}:
            if not _wd:
                continue
            for _stale in ("todo.json", ".agent_state.json"):
                try:
                    _p = os.path.join(_wd, _stale)
                    if os.path.exists(_p):
                        os.remove(_p)
                except Exception:
                    pass
        self._set_session_label(None)
        self.session_title = ""
        self._plan_source = "run"
        self.clear_transcript()
        self.wd_var.set(os.path.join(DEFAULT_TASKS, "work"))
        self._render_plan([], force=True)
        self._welcome()
        self.attachments = []
        self._refresh_att_chips()
        self.status_var.set(_t("上下文: - / - ( - % )"))
        if hasattr(self, "ctx_bar"):
            self.ctx_bar.set(0)
        self.input.delete("1.0", "end")
        self._set_input_hint(True)
        self._set_running(False)
        self.refresh_sessions()
        self._sync_dir_btn()
        self.log_note(_t("[新对话已开启:上下文与工作目录已重置]"))

    def launch(self, task, use_session, resume_ok):
        # 查不到时用原选择本身,绝不静默回退到"第一个模型"(选 A 跑 B)。
        # 云端启用时 model_var 为空,argv 仍带云端模型名(仅日志/能力探测用,
        # 云端路由下 runner 不调本地 ollama)。本地清单为空不再直接拒绝——
        # 只配云端(LM Studio 未开/无本地模型)时任务仍应能发。
        _pick = self.model_var.get() if hasattr(self, "model_var") else ""
        model = self._model_map.get(_pick, _pick) if _pick else ""
        _cloud = appconfig.cloud_provider()
        if not model and _cloud:
            model = _cloud.get("model") or ""
        if not model and self._model_map:
            _first = next(iter(self._model_map))
            self.model_var.set(_first)
            model = self._model_map[_first]
            self._sync_model_btn()
        if not model:
            self.log_note(_t("[请先选择本地模型,或配置并启用云端模型]"))
            return
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
        else:
            # v2.0.0 todo 会话绑定:恢复旧对话(续跑)时,把该会话保存时快照的
            # todo.json 写回工作目录——计划面板与 agent 上下文都拿到当时的
            # 未完成清单;会话没有快照则清掉现场残留,杜绝串到别的任务的计划。
            try:
                _snap = os.path.join(SESSION_DIR, self.session + ".todo.json") if self.session else None
                tj = os.path.join(workdir, "todo.json")
                if _snap and os.path.exists(_snap):
                    import shutil
                    shutil.copyfile(_snap, tj)
                elif os.path.exists(tj):
                    os.remove(tj)
            except Exception:
                pass
        env = dict(os.environ); env["PYTHONIOENCODING"]="utf-8"
        env["AGENT_STREAM"] = "1"   # 对话流式输出 + 思考流
        env["AGENT_LANG"] = _LANG   # v2.0.1 会话标题按界面语言起名(中文界面→中文标题)
        # 采样三态(v1.7.0):未设置 → 从 env 里删掉继承值,agent 载荷即不带
        # temperature/think 字段(ollama 默认);显式选择(含 0/关)才透传。
        _tv = self.prefs.get("think")
        if _tv is None:
            env.pop("AGENT_THINK", None)
        else:
            env["AGENT_THINK"] = "1" if _tv else "0"
        env["AGENT_CTX"] = str(self.prefs["ctx"])
        _tp = self.prefs.get("temp")
        if _tp is None:
            env.pop("AGENT_TEMP", None)
        else:
            env["AGENT_TEMP"] = str(_tp)
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
        # 断网模式可见性(v1.8.2):用户要求联网搜索而工具未装配时,模型只能
        # 就地扑腾(2026-09-21 事故成因之一)——起跑前把状态说进会话里。
        if appconfig.offline_mode():
            self.log_note(_t("[断网模式已开启:本任务无联网工具与云端 — 联网搜索类请求无法满足,请先点 🔒 切回联网]"))
        self.log(f"====== {_t('开始: ')}{model}" + (f" | {_t('会话:')}{self.session}" if self.session else "") + " ======")
        self.log(_t("工作目录: ") + workdir + "\n")
        _popen_kw = {}
        if os.name != "nt":
            # POSIX:独立进程组,kill 时能连孙进程一起收掉(对齐 Windows taskkill /T)
            _popen_kw["start_new_session"] = True
        self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,   # 守护系统:GUI 通过 stdin 回传越界确认
            text=True, encoding="utf-8", errors="replace", env=env, bufsize=1,
            **_popen_kw)
        # 每次任务一个 run id:旧任务的残留行/哨兵不得污染新任务(队列是共享的)
        self._run_seq = int(getattr(self, "_run_seq", 0)) + 1
        self._run_id = self._run_seq
        self._run_wd = workdir
        self._run_session = self.session
        self._plan_source = "run"
        self._drain_q()
        threading.Thread(target=self.reader, args=(self._run_id,), daemon=True).start()
        self._set_running(True)

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

    def reader(self, run_id=None):
        proc = self.proc
        try:
            for line in iter(proc.stdout.readline, ""):
                self.q.put((run_id, line.rstrip("\n")))
        finally:
            self.q.put((run_id, None))

    def _drain_q(self):
        try:
            while True:
                self.q.get_nowait()
        except queue.Empty:
            pass
        except Exception:
            pass

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self._kill_tree(); self.log("\n" + _t("[已停止,重跑并勾选'续跑'可从中断处继续]"))
            self.log_note(_t("[已停止 — 重跑勾选'续跑'可从中断处继续]"))
            self._save_interrupted_session()

    def _save_interrupted_session(self):
        """v2.0.0:停止任务时把检查点落成会话文件。此前只有自然结束才 save_session,
        用户手动停止的对话在历史列表里根本不存在——换窗口就再也找不回。现在停止即
        存(含 todo 快照,与 agent 侧 save_session 同构),历史里可加载、可续跑。"""
        try:
            _sess = getattr(self, "_run_session", None) or self.session
            _wd = getattr(self, "_run_wd", None) or (
                self.wd_var.get() if hasattr(self, "wd_var")
                else os.path.join(DEFAULT_TASKS, "work"))
            if not _sess:
                return
            ck = os.path.join(_wd, ".agent_state.json")
            if not os.path.exists(ck):
                return
            msgs = json.load(open(ck, encoding="utf-8"))
            if not isinstance(msgs, list) or len(msgs) < 2:
                return
            _atomic_json(os.path.join(SESSION_DIR, _sess + ".json"), msgs)
            # v2.0.1 合并写:标题等已有字段不丢(agent 侧 save_session 同构)
            _old_meta = {}
            try:
                _old_meta = json.load(open(os.path.join(SESSION_DIR, _sess + ".meta.json"),
                                           encoding="utf-8"))
            except Exception:
                pass
            _old_meta.update({"updated": time.strftime("%Y-%m-%d %H:%M"),
                    "task": next((str(m.get("content", "")) for m in msgs
                                  if m.get("role") == "user" and not m.get("tool_calls")), "")[:200],
                    "status": "interrupted", "msgs": len(msgs)})
            _atomic_json(os.path.join(SESSION_DIR, _sess + ".meta.json"), _old_meta)
            import shutil
            tj = os.path.join(_wd, "todo.json")
            snap = os.path.join(SESSION_DIR, _sess + ".todo.json")
            if os.path.exists(tj):
                shutil.copyfile(tj, snap)
            elif os.path.exists(snap):
                os.remove(snap)
            self.refresh_sessions()
        except Exception:
            pass

    # ================= 流解析 =================
    def poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                if isinstance(item, tuple):
                    rid, line = item
                else:
                    rid, line = getattr(self, "_run_id", 0), item
                if rid is not None and rid != getattr(self, "_run_id", rid):
                    continue                       # 旧任务的残留行/哨兵:丢弃
                if line is None:
                    self._collapse_think()
                    self._flush_asst()
                    self.log("\n===== " + _t("任务结束") + " =====")
                    self._set_running(False); self.proc = None
                    self.refresh_sessions()
                elif line:
                    self.log(line)
                    self.feed_transcript(line)
        except queue.Empty:
            pass
        except Exception:
            pass       # 单条坏载荷不得杀死轮询链(否则转写永久冻结)
        finally:
            try:
                self.root.after(100, self.poll)
            except Exception:
                pass

    def _check_ollama(self):
        """本地引擎在线状态灯:绿=在线有模型,黄=在线无模型,红=离线。
        v2.1.1 按 engine 分流探测(Ollama /api/tags vs OpenAI 兼容 GET /models)。
        自愈:在线且模型清单变化时自动刷新下拉(启动瞬间查询失败的下拉会在此自愈)。
        比较集合必须与 refresh_models 同源(同一去重规则):拿原始 tag 集合去比
        去重后的下拉值,会在存在 ollama cp 别名时恒不等 → 每 5 秒主线程重刷。"""
        up = False; has_models = False
        try:
            import urllib.request as _ur
            _lb = appconfig.backend_openai()
            if _lb:
                r = json.loads(_ur.urlopen(_lb["base_url"] + "/models", timeout=2).read())
                _live = [{"name": x.get("id")} for x in (r.get("data") or []) if x.get("id")]
            else:
                r = json.loads(_ur.urlopen(appconfig.ollama_host().rstrip("/") + "/api/tags", timeout=2).read())
                _live = r.get("models", [])
            up = True; has_models = bool(_live)
            # 自愈条件:当前下拉框里的 tag 集合 != 去重后的应有集合
            # (覆盖:启动时引擎未就绪走了配置回退 / 用户装载了新模型 / 卸载了模型)
            cur_tags = frozenset(getattr(self, "_model_map", {}).values())
            tag_to_display = {v: k for k, v in appconfig.model_map().items()}
            want_tags = frozenset(t for _, t in _dedupe_model_entries(_live, tag_to_display))
            if cur_tags != want_tags:
                self.refresh_models()
        except Exception:
            pass
        _eng = appconfig.engine_display_name()
        if up and has_models:
            self.ollama_lbl.configure(text=f"{_eng} ✓", fg=self.T["ok"])
        elif up:
            self.ollama_lbl.configure(text=_t("{eng} ✓(无模型)").format(eng=_eng),
                                      fg=self.T["warn"])
        else:
            self.ollama_lbl.configure(text=_t("{eng} ✗ 未启动").format(eng=_eng),
                                      fg=self.T["danger"])
        self.root.after(5000, self._check_ollama)

    def _try_start_ollama(self):
        """拉起 ollama serve(后台进程,不弹窗)。
        v2.1.1:OpenAI 兼容引擎无权重启,提示用户手动打开对应服务。"""
        try:
            if appconfig.backend_openai():
                from tkinter import messagebox
                _lb = appconfig.backend_openai()
                messagebox.showwarning(
                    _t("本地引擎"),
                    _t("OpenAI 兼容引擎需要手动启动:\n请先打开 LM Studio / llama.app,\n"
                       "或运行 llama-server 后再试。\n端点: {url}").format(url=_lb["base_url"]))
                return
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

    def _flush_stream_pending(self):
        """把缓冲里未上屏的流式内容一次性补进控件(折叠/收尾/切换前必须先调,
        保证顺序:标记行的字数、_flush_asst 的'已在屏'假设都依赖尾部已上屏)。"""
        try:
            if self._think_live and self._think_shown < len(self._think_text):
                self.transcript.config(state="normal")
                self.transcript.insert("end", self._think_text[self._think_shown:], ("think_region", "think_live"))
                if not self._selecting:
                    self.transcript.config(state="disabled")
                self._think_shown = len(self._think_text)
            if self._streaming_asst and self._asst_shown < len(self._asst_buf):
                self.transcript.config(state="normal")
                self.transcript.insert("end", self._asst_buf[self._asst_shown:], "asst")
                if not self._selecting:
                    self.transcript.config(state="disabled")
                self._asst_shown = len(self._asst_buf)
        except Exception:
            pass

    def _stream_render_tick(self):
        """150ms 批量渲染:几千思考 token 也只是字符串追加,UI 不再卡死。"""
        try:
            at_bottom = self.transcript.yview()[1] >= 0.995
        except Exception:
            at_bottom = True
        had = bool(self._think_text or self._asst_buf)
        self._flush_stream_pending()
        if had and at_bottom:
            try:
                self._scroll_transcript()
            except Exception:
                pass
        self.root.after(150, self._stream_render_tick)

    def _stream_tok(self, tok):
        """流式回答 token:只进缓冲,由 _stream_render_tick 批量上屏。"""
        try:
            if self._think_live:
                self._collapse_think()   # 回答开始前先把活动思考块收成标记
            # 用户手动展开过的旧块保持展开:按块存档后块与块互不影响
            if not self._asst_buf:
                self.transcript.config(state="normal")
                self.transcript.insert("end", "\n", "spacer")
                self.transcript.insert("end", _t("鸣鸟") + "\n", "who")
                self.transcript.config(state="disabled")
            self._asst_buf += tok
            self._streaming_asst = True
        except Exception:
            pass

    def _stream_think(self, tok):
        """流式思考 token:只进缓冲;块头缺失时补建。"""
        try:
            if not self._think_live:
                self._collapse_think()   # 冻结上一个活动块(若有)
                self._think_text = ""
                self._think_shown = 0
                self._think_live = True
                self._think_hdr = False
            if not self._think_hdr:
                self.transcript.config(state="normal")
                self.transcript.insert("end", _t("🤔 思考中…") + "\n", ("think_region", "think_live"))
                self.transcript.config(state="disabled")
                self._think_hdr = True
            self._think_text += tok
        except Exception:
            pass

    def _think_freeze(self, text, at=None):
        """在 at 位置落一行可点击的思考标记,并把全文登记进 _think_store。
        每块独立 uid + 独立点击绑定;加载历史会话渲染 thinking 时也走这里。"""
        self._think_seq += 1
        uid = f"thinkmk{self._think_seq}"
        self._think_store[uid] = text
        self.transcript.insert(at or "end",
            _t("🤔 思考过程 ({n} 字) — 点击展开/折叠").format(n=len(text)) + "\n",
            ("think_marker", uid))
        self.transcript.tag_bind(uid, "<Button-1>",
                                 lambda e=None, u=uid: self._toggle_think(u))
        # e=None 兜底(issue #4 附报的 GUI 崩溃):有零参调用路径会触发
        # "missing 1 required positional argument: 'e'"——tag 绑定本身总是
        # 传 event,但任何其他 dispatch 形态都应无代价容忍。
        return uid

    def _collapse_think(self):
        """把活动思考块(think_live)折叠成一行可点击标记;只动活动块,不碰正文,
        也不碰用户展开过的旧块。"""
        try:
            self._flush_stream_pending()   # 先补齐尾部:标记行字数才准确
            self.transcript.config(state="normal")
            r = self.transcript.tag_ranges("think_live")
            if r:
                start, end = r[0], r[1]
                self.transcript.delete(start, end)
                if self._think_text:
                    self._think_freeze(self._think_text, start)
            self.transcript.config(state="disabled")
        except Exception:
            pass
        self._think_live = False
        self._think_hdr = False
        self._think_text = ""
        self._think_shown = 0

    def _toggle_think(self, uid):
        """点击思考标记:展开/折叠对应块(store 按块取全文,块与块互不干扰)。"""
        text = self._think_store.get(uid)
        if not text:
            return
        try:
            self.transcript.config(state="normal")
            body = uid + "_body"
            r = self.transcript.tag_ranges(body)
            if r:
                self.transcript.delete(r[0], r[1])      # 展开 → 折叠
            else:
                m = self.transcript.tag_ranges(uid)     # 折叠 → 标记行下方展开
                if m:
                    self.transcript.insert(m[1], text + "\n", ("think_region", body))
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
            T = self.T
            S = self._ui_scale
            px = lambda n: int(n * S)
            win = tk.Toplevel(self.root)
            win.title(_t("⚠ 越界操作确认"))
            win.geometry(self._scaled_geo(600, 360))
            win.configure(bg=T["bg"])
            self._theme_titlebar(win)
            win.transient(self.root)
            win.attributes("-topmost", True)

            head = tk.Frame(win, bg=T["bg"])
            head.pack(fill="x", padx=px(22), pady=(px(18), px(2)))
            tk.Label(head, text=_t("AI 想访问工作目录之外的文件"),
                     bg=T["bg"], fg=T["danger"],
                     font=v4.FONT_TITLE).pack(side="left")
            tk.Label(win, text=_t("目标不在当前工作目录内,需要你确认这一次的访问。"),
                     bg=T["bg"], fg=T["muted"],
                     font=v4.FONT_SM).pack(anchor="w", padx=px(22))

            card = tk.Frame(win, bg=T["surface"], highlightthickness=1,
                            highlightbackground=T["border"])
            card.pack(fill="both", expand=True, padx=px(22), pady=(px(12), px(8)))

            def row(label, value, mono=False, last=False):
                r = tk.Frame(card, bg=T["surface"])
                r.pack(fill="x", padx=px(16), pady=(px(10) if not last else px(6), 0))
                tk.Label(r, text=label, bg=T["surface"], fg=T["faint"],
                         font=v4.FONT_XS, width=8,
                         anchor="w").pack(side="left", anchor="n")
                tk.Label(r, text=str(value), bg=T["surface"], fg=T["text"],
                         font=v4.MONO_SM if mono else v4.FONT_SM,
                         justify="left", anchor="w",
                         wraplength=int(430 * getattr(self, "_ui_scale", 1.0))
                         ).pack(side="left", fill="x", expand=True)

            row(_t("工具"), tool)
            row(_t("操作"), _t(str(action)))
            row(_t("目标"), path, mono=True)
            row(_t("工作目录"), wd, mono=True)
            tk.Frame(card, bg=T["surface"], height=10).pack()

            btnrow = tk.Frame(win, bg=T["bg"])
            btnrow.pack(fill="x", padx=px(22), pady=(0, px(16)))
            result = {}

            def _reply(v):
                result["v"] = v
                win.destroy()

            v4.Pill(btnrow, _t("允许一次"), lambda: _reply("@allow"), T,
                    kind="primary", h=34, padx=16).pack(side="left")
            v4.Pill(btnrow, _t("允许全部(本轮)"),
                    lambda: _reply("@allow_all"), T, kind="surface",
                    h=34, padx=14).pack(side="left", padx=(8, 0))
            v4.Pill(btnrow, _t("拒绝"), lambda: _reply("@deny"), T,
                    kind="ghost", h=34, padx=14).pack(side="right")
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
            self._stream_tok(self._decode_stream_frame(line[len("@@TOK@@"):]))
            return
        if line.startswith("@@THINK@@"):
            self._stream_think(self._decode_stream_frame(line[len("@@THINK@@"):]))
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
            self.ctx_bar.set(min(pct, 100))
            return
        if line.startswith("[ctx:") or line == "":
            return
        m = re.match(r"\[(\d+)[^\]]*\] ⚙ (\w+)\s*(\{.*\})?\s*->\s*(.*)", line)
        if m:
            self._collapse_think()
            self._flush_asst()
            name, args, res = m.group(2), m.group(3) or "", m.group(4)
            if name == "finish":
                # 完成卡片:剥掉 harness 的 [TASK_COMPLETE] 内部前缀,只给用户看 summary
                if res.startswith("[TASK_COMPLETE] "):
                    res = res[len("[TASK_COMPLETE] "):]
                res = res.strip() or _t("任务完成")
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
        m = re.match(r"\[(\d+)[^\]]*\] ✍ (.*)", line, re.S)
        if m:
            self._flush_asst()
            self._asst_buf = m.group(2)
            return
        # 协议行不得并进回答气泡(旧版 _asst_buf 非空时会把它们全部追加进去)
        if line.startswith(("[TASK_COMPLETE]", "[session saved", "=====")):
            self._flush_asst()
            return
        if self._asst_buf:
            self._asst_buf += "\n" + line
            return
        if "TASK COMPLETE" in line or line.startswith("[TASK_COMPLETE]"):
            return
        if line.startswith(("[RESUMED", "[session", "[上下文已压缩", "[交互模式", "[已选择", "[已从历史", "=====", "[新对话")):
            self.log_note(line.strip("= ")); return
        self.log_note(line.strip("= "))

    @staticmethod
    def _decode_stream_frame(payload):
        """新版是 JSON 字符串帧(换行不拆帧);旧版裸文本原样返回。"""
        try:
            v = json.loads(payload)
            return v if isinstance(v, str) else payload
        except Exception:
            return payload

    def _flush_asst(self):
        self._flush_stream_pending()   # 流式尾部先上屏,再按"已在屏"语义收尾
        if self._asst_buf:
            if not self._streaming_asst:
                # 非流式:整段 markdown 渲染成气泡
                self._insert_md(self._asst_buf)
                self._scroll_transcript()
            self._asst_buf = ""
            self._asst_shown = 0
            self._streaming_asst = False

    def poll_todo(self):
        if getattr(self, "_plan_source", "run") == "session" \
                and not (self.proc and self.proc.poll() is None):
            self.root.after(500, self.poll_todo)
            return
        tf = os.path.join(self.wd_dir(), "todo.json")
        t = None
        try:
            t = json.load(open(tf, encoding="utf-8"))
            if not isinstance(t, list): t = None
        except Exception:
            t = None
        try:
            self._render_plan(t or [])
        except Exception:
            pass
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
        """渲染计划抽屉:关闭时只更新角标;打开时更新正文。内容不变不重建。"""
        todo_list = todo_list or []
        done = 0
        for x in todo_list:
            try:
                if isinstance(x, dict) and x.get("done"):
                    done += 1
            except Exception:
                pass
        self._plan_items = list(todo_list)
        self._plan_done = done
        self._plan_total = len(todo_list)
        if not self._plan_total and self.plan_open:
            # 计划清空后收起抽屉,避免留一个空面板
            self.plan_open = False
        self._sync_plan_btn()
        try:
            sig = json.dumps(todo_list, ensure_ascii=False, sort_keys=True)
        except Exception:
            sig = repr(todo_list)
        if force or sig != getattr(self, "_plan_sig", None):
            self._plan_sig = sig
            self._build_plan_rail()

    def _route_wheel(self, event):
        """滚轮路由:指针在计划面板内 → 滚 plan_txt 并拦截;其余情况放行
        (焦点控件的默认滚动不受影响)。"""
        try:
            w = self.root.winfo_containing(event.x_root, event.y_root)
            while w is not None:
                if w is getattr(self, "plan_txt", None):
                    self.plan_txt.yview_scroll(int(-1 * (event.delta / 120)), "units")
                    return "break"
                w = w.master
        except Exception:
            pass
        return None

    def on_close(self):
        if self.proc and self.proc.poll() is None:
            self._kill_tree()
            self._save_interrupted_session()   # 关窗也保留中断会话(复审 P2)
        self.root.destroy()

if __name__ == "__main__":
    # v1.9.1 run_python 底座:--run-py <script> 用本程序自带解释器执行后退出,
    # 不弹 GUI(冻结版由 LocalAgent.exe --run-py 调入;开发版由 python agent_gui.py --run-py)
    if len(sys.argv) > 2 and sys.argv[1] == "--run-py":
        import ollama_agent as _oa
        try:
            _rc = _oa.run_python_file(sys.argv[2])   # 脚本内 sys.exit 经 runpy 自然传播
            sys.exit(_rc if isinstance(_rc, int) else 0)
        except SystemExit:
            raise
        except Exception:
            import traceback
            traceback.print_exc()
            sys.exit(1)
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
    # 打开 GUI 时按需拉起 ollama(不在开机自启常驻);
    # v2.1.1:OpenAI 兼容引擎无权重启,只探测并提示用户手动打开对应服务
    try:
        if appconfig.backend_openai():
            import ollama_agent
            if not ollama_agent.probe_openai_backend():
                import tkinter.messagebox as _mb
                _lb = appconfig.backend_openai()
                _mb.showwarning(_t("鸣鸟 · 本地 AI 助手"),
                                _t("OpenAI 兼容引擎未就绪:{url}\n请先启动 LM Studio / llama.app / llama-server。")
                                .format(url=_lb["base_url"]))
        else:
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
