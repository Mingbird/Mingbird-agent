# -*- coding: utf-8 -*-
"""platform_profile:鸣鸟多平台差异化的单一事实源(v3.0.0)。

此前平台差异散落在 os.name/sys.platform 分支里:模型看不到自己跑在什么
shell 上(小模型在 Windows cmd 里写 ls/grep 是高频翻车点),GUI 的平台
处理各写各的。本模块把"平台真相"收敛为数据,检测一次、处处消费——

- agent 侧:prompt_block() 注入系统提示(平台/Shell/命令对照/确认声明),
  动态行不进 SYSTEM 常量,出厂 prefill 钉子不动(v2.1.3 工作目录行先例);
- 执行侧:exec_env() 统一子进程 UTF-8 环境(从 run_bash 内联收敛,行为不变);
- GUI 侧:open_folder_cmd()/open_doc_cmd()/enable_dpi_awareness()。

对应 2026-10-21 调研报告 P0-1(aider 式平台块)/P0-2(执行层统一)/
P1-4(平台 profile 数据化)。
"""
import os
import sys


def detect():
    """平台画像:每次现算(轻量),字段被多处读取时用 profile() 缓存版。"""
    if os.name == "nt":
        pid = "windows"
    elif sys.platform == "darwin":
        pid = "macos"
    else:
        pid = "linux"
    return {
        "id": pid,
        # cmd.exe 与 /bin/sh 都支持 && 串联(告诉模型可用,别绕路)
        "shell": "cmd.exe" if pid == "windows" else "/bin/sh",
        "path_sep": "\\" if pid == "windows" else "/",
    }


_PROFILE = None


def profile():
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = detect()
    return dict(_PROFILE)   # 返回副本,防调用方就地污染缓存


# 命令对照表:教模型"在这个平台上该用哪条命令"(Windows cmd 无 ls/cat/grep)。
# 只做提示不改命令——执行层保持既有 shell=True 链路(生产验证过的行为)。
_COMMAND_MAPS = {
    "windows": ("列目录=dir", "看文件=type", "搜索文本=findstr", "复制=copy"),
    "macos":   ("列目录=ls", "看文件=cat", "搜索文本=grep", "复制=cp"),
    "linux":   ("列目录=ls", "看文件=cat", "搜索文本=grep", "复制=cp"),
}

_OS_LABELS = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}


def prompt_block(full=True):
    """平台信息块。

    full=True(任务模式):平台/Shell/命令对照/路径分隔符/确认声明,3 行。
    full=False(问答模式):单行精简——聊天只有只读工具,shell 命令对照无意义,
    但平台与路径分隔符对"帮我看下 D:\\xxx 这类文件"仍有用。
    """
    p = profile()
    label = _OS_LABELS[p["id"]]
    if not full:
        return f"平台:{label},路径分隔符 {p['path_sep']}"
    cmds = " / ".join(_COMMAND_MAPS[p["id"]])
    return "\n".join([
        f"平台:{label} · 命令 shell={p['shell']}(支持 && 串联执行)",
        f"- 命令对照:{cmds};路径分隔符 {p['path_sep']},含空格的路径加引号",
        "- 命令在沙箱外执行;递归删除/卸载/改系统环境会触发用户确认——这是正常防护不是故障,继续干活即可",
    ])


def exec_env(base=None):
    """子进程编码环境:UTF-8 优先(中文 Windows GBK 控制台治理的既定方案,
    v2.0.0 起在 run_bash 内联,收敛到此统一出口)。返回新 dict,不改入参。"""
    env = dict(os.environ if base is None else base)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def open_folder_cmd(path):
    """在平台文件管理器里打开目录(GUI 消费,替代散落的 os.name 分支)。"""
    if os.name == "nt":
        return ["explorer", os.path.normpath(path)]
    if sys.platform == "darwin":
        return ["open", path]
    return ["xdg-open", path]


def open_doc_cmd(path):
    """用平台默认文本查看器打开文件。"""
    if os.name == "nt":
        return ["notepad", path]
    if sys.platform == "darwin":
        return ["open", "-t", path]
    return ["xdg-open", path]


# DPI 说明(v3.0.0 调研结论,不做):Tk 8.6 on Windows 已声明系统级 DPI 感知
# (agent_gui 既有缩放系数代码实证:200% 缩放下点阵字体随系统 DPI 自动缩放,
# 若非感知态 Tk 只能看到虚拟 96 DPI)。盲翻 Per-Monitor V2 会让按现测系数
# 调好的布局整体走样——等真有多显示器混合 DPI 的用户反馈再说。
