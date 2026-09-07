#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""子 agent 安全模型:权限严格小于主 agent,默认拒绝,无升级路径。

原则:主 agent 无人值守时还有 GUI 弹窗确认兜底;子 agent 是 headless 批量跑的,
没有任何人类在 loop 里。所以凡主 agent 里"弹窗询问后可越界"的路径,子 agent 一律
直接拒绝(default-deny),不存在"允许一次/允许全部"。

四层防线(全部数据驱动,出厂默认 = 最严档):
  1. 工具面收窄:默认只给 读/写/列目录/finish/todo,run_bash/web/MCP/enable_tools 都不给;
  2. 路径边界:工作目录(子 agent 自己的分区目录)之外一律拒写;敏感目录连读都拒,
     除非显式白名单;工作目录内命中敏感模式同样拒写;
  3. 危险命令黑名单:引号/转义归一化 + 链式命令逐段检查(&& || ; |) + 重定向目标检查;
  4. 审计:每次文件写/命令调用记 JSONL 审计行;危险行为计数;
     ≥1 次严重拒绝(虚拟机/系统区)→ 立即终止该子 agent(exit 53)并回退主模型串行。

设计文档: design/2026-09-01-parallel-dispatch.md «子 agent 安全模型»
"""
import json
import os
import re
import time

# ---------------- 出厂默认:敏感目录/文件模式(最严档) ----------------
# 两张清单,分工不同(见设计文档 §3.2):
#  (1) sensitive_dir_patterns —— 即使落在 workdir 内也必须拒:凭据/密钥/agent 数据/VM 磁盘/
#      鸣鸟自身文件。这是"在 workdir 内也有意义"的清单。
#  (2) system_dir_patterns —— 绝对系统位置(WSL/VM 子系统、Windows、Program Files、AppData…)。
#      它们天然落在 workdir 之外,由"workdir 之外一律拒写"的兜底条款覆盖;这张清单的作用是
#      ① 给审计行一个精确原因;② 防 workdir 本身被误配到系统区(此时全拒)。
#      刻意不用它去匹配 workdir 内的相对路径 —— 否则 workdir 恰好在 AppData/Temp 下时
#      (测试临时目录、Store 应用、便携安装都是)会整目录误伤,功能等于报废。
DEFAULT_SENSITIVE_DIR_PATTERNS = [
    # 虚拟机磁盘/镜像(扩展名形态;在 workdir 里出现同样是危险写目标)
    ".vhdx", ".vhd", ".vmdk", ".vdi", ".qcow2", ".vmx", ".vmsn", ".nvram",
    # 凭据/密钥/敏感配置
    ".ssh", ".aws", ".gnupg", ".gpg", ".env", "credentials", "credential",
    ".ollama", ".myagents", "id_rsa", "id_ed25519", ".pem", ".key", ".kube", "secrets",
    # 鸣鸟自身与宿主工作区
    "mcp.json", "config.json", "gui_prefs.json", "memory.json", "sessions", ".git",
    "node_modules",
]

DEFAULT_SYSTEM_DIR_PATTERNS = [
    # 虚拟机 / 子系统(真实事故教训:本地模型删过用户的虚拟机子系统)
    "\\\\wsl", "\\wsl$", "wsl.localhost", "\\wslg", "\\appdata\\local\\packages",
    "\\hyper-v", "\\virtualbox", "\\vmware", "oracle virtualbox", "\\vagrant", "\\podman",
    # 系统区
    "\\windows", "\\program files", "\\programdata", "\\system32", "\\syswow64",
    "\\drivers", "\\boot\\", "\\efi\\", "\\recycler", "\\system volume information",
    # 用户区(AppData/其他用户目录 —— 由边界条款兜底,这里给精确审计原因)
    "\\appdata", "\\application data",
]

# workdir 误配置防护用的"核心系统区"子集:任何用户工作目录都不该落在这些地方。
# 刻意不含裸 "\\appdata" —— AppData\\Local\\Temp 是临时工作目录/便携安装的合法去处,
# 用它判 workdir 会把整个功能判死(测试临时目录正是这种形态)。
DEFAULT_CORE_SYSTEM_PATTERNS = [
    "\\windows", "\\program files", "\\programdata", "\\system32", "\\syswow64",
    "\\system volume information", "\\recycler", "\\efi\\", "\\boot\\",
    "\\\\wsl", "\\wsl$", "wsl.localhost", "\\appdata\\local\\packages",
    "\\hyper-v", "\\virtualbox", "\\vmware",
]

# 敏感目录的读白名单(默认空 = 敏感目录读也拒;显式配置才放行)
DEFAULT_READ_ALLOW_PATTERNS = []

# ---------------- 出厂默认:危险命令黑名单(子 agent 版,最严档) ----------------
# severity: "severe" = 破坏性/不可逆/系统级 → 立即终止该子 agent(exit 53)
#           "deny"   = 可疑/越界 → 计数,max_denies_per_child 次后终止
DEFAULT_DANGEROUS_COMMANDS = [
    # --- 虚拟机 / 子系统(最高危) ---
    {"pattern": r"wsl\s+--unregister", "severity": "severe", "reason": "wsl --unregister 删除整个发行版"},
    {"pattern": r"wsl\s+--import", "severity": "severe", "reason": "wsl --import 覆盖发行版"},
    {"pattern": r"wsl\s+--unmount", "severity": "severe", "reason": "卸载 wsl 虚拟磁盘"},
    {"pattern": r"wsl\s+--manage.*--set-sparse|wsl\s+--export", "severity": "deny", "reason": "wsl 管理/导出"},
    {"pattern": r"\bwsl\b", "severity": "deny", "reason": "子 agent 不应触碰 wsl/虚拟机子系统"},
    {"pattern": r"\bdiskpart\b", "severity": "severe", "reason": "磁盘分区工具"},
    {"pattern": r"\bformat(\s|\.com)", "severity": "severe", "reason": "格式化驱动器"},
    {"pattern": r"cipher\s+/w", "severity": "severe", "reason": "cipher /w 抹除空闲空间"},
    {"pattern": r"\bbcdedit\b", "severity": "severe", "reason": "启动配置"},
    {"pattern": r"vssadmin\s+delete", "severity": "severe", "reason": "删除卷影副本"},
    {"pattern": r"\bwmic\s+.*(delete|shadowcopy)", "severity": "severe", "reason": "wmic 删除操作"},
    {"pattern": r"\bdism\b", "severity": "severe", "reason": "系统映像服务"},
    {"pattern": r"\bsfc\b", "severity": "deny", "reason": "系统文件检查"},
    # --- 递归/强删 ---
    {"pattern": r"\brd\s+/s", "severity": "severe", "reason": "rd /s 递归删目录"},
    {"pattern": r"\bdel\s+(/f|/s|/q)", "severity": "severe", "reason": "del 强制/递归删除"},
    {"pattern": r"remove-item\b.*(-recurse|-force)", "severity": "severe", "reason": "PowerShell 递归强删"},
    {"pattern": r"\brm\s+(-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r|-[a-z]*r|-\-recursive)", "severity": "severe", "reason": "rm 递归删除"},
    {"pattern": r"\brm\s+-[a-z]*f", "severity": "severe", "reason": "rm 强制删除"},
    {"pattern": r"-delete\b", "severity": "severe", "reason": "find -delete 递归删除"},
    {"pattern": r"(^|\s)dd\s+", "severity": "severe", "reason": "dd 裸写设备"},
    {"pattern": r"\bmkfs", "severity": "severe", "reason": "建文件系统"},
    {"pattern": r"robocopy\b.*(/mir|/purge|/mov)", "severity": "severe", "reason": "robocopy 镜像/清除"},
    {"pattern": r"\bxcopy\b.*(/y|/q)", "severity": "deny", "reason": "xcopy 覆盖复制"},
    # --- 注册表 / 服务 / 网络 ---
    {"pattern": r"\breg(\.exe)?\s+(add|delete|import|restore|load|unload|save|export)", "severity": "severe", "reason": "注册表写入/删除"},
    {"pattern": r"\breg(\.exe)?\s+query", "severity": "deny", "reason": "注册表读取"},
    {"pattern": r"\bsc(\.exe)?\s+(create|delete|config|stop)", "severity": "severe", "reason": "服务管理"},
    {"pattern": r"\bschtasks\b", "severity": "severe", "reason": "计划任务(持久化)"},
    {"pattern": r"\bnetsh\b", "severity": "severe", "reason": "网络栈配置"},
    {"pattern": r"\bnet\s+(user|localgroup|share)\b", "severity": "severe", "reason": "用户/共享管理"},
    {"pattern": r"\bshutdown\b", "severity": "severe", "reason": "关机"},
    {"pattern": r"\btaskkill\b", "severity": "deny", "reason": "杀进程"},
    {"pattern": r"\bbcdboot\b|\breagentc\b|\bsetx\b", "severity": "severe", "reason": "系统级配置"},
    {"pattern": r"\bmklink\b", "severity": "severe", "reason": "符号链接(可指向系统路径)"},
    {"pattern": r"\b attrib\s*\+s|\b attrib\s*\+h", "severity": "deny", "reason": "隐藏/系统属性"},
    # --- 远程执行 / 下载执行 ---
    {"pattern": r"(curl|wget|invoke-webrequest|invoke-restmethod|iex|invoke-expression|irm)\b.*(\|\s*(bash|sh|powershell|iex))", "severity": "severe", "reason": "下载并执行"},
    {"pattern": r"(curl|wget)\b", "severity": "deny", "reason": "子 agent 无网络需求"},
    {"pattern": r"\bpip\s+install|\bnpm\s+install|\bnpx\b", "severity": "deny", "reason": "安装依赖不在子 agent 职责内"},
    # --- 特权提升 ---
    {"pattern": r"\bsudo\b|\brunas\b|\bstart-process\b.*-verb\s+runas", "severity": "severe", "reason": "提权"},
    {"pattern": r"\btakeown\b|\bicacls\b|\bcacls\b", "severity": "severe", "reason": "改所有权/ACL"},
]

# 子 agent 默认工具面(严格小于主 agent:不给 run_bash/web/MCP/删除/编辑/enable_tools)
DEFAULT_CHILD_ALLOWED_TOOLS = ["read_file", "list_dir", "create_file", "todo", "finish"]

# 链式命令分隔符(模型会拼 r1 && r2 / ; / |)
_CHAIN_SPLIT_RE = re.compile(r"&&|\|\||;|\||\n|&")
# 重定向目标提取(> >> 1> 2> 以及 out-file / tee)
_REDIRECT_RE = re.compile(r"(?:\d)?>{1,2}\s*([^\s&|;]+)|\b(?:out-file|tee)\s+([^\s&|;]+)")


# ---------------- 归一化 ----------------

def norm_path(p):
    """路径归一化:去引号、统一小写、正斜杠→反斜杠、折叠重复分隔符。"""
    s = str(p or "").strip().strip('"').strip("'").strip()
    s = s.replace("/", "\\")
    s = re.sub(r"\\+", lambda m: "\\", s)
    return s.lower()


def norm_command(cmd):
    """命令归一化:剥引号/转义、cmd 转义(^)与 PowerShell 转义(`)直接删除,
    空白折叠,小写。目的:让 `wsl --unregister "Ubuntu"`、`wsl --unregister 'Ubuntu'`、
    `w^sl --unregister Ubuntu`、`WSL  --UNREGISTER  Ubuntu` 全部落到同一形态被命中。"""
    s = str(cmd or "")
    for a in ("\u201c", "\u201d", "\u2018", "\u2019"):
        s = s.replace(a, " ")
    s = s.replace("^", "")            # cmd 转义符:w^sl == wsl
    s = s.replace("`", "")            # PowerShell 转义符:w`sl == wsl
    s = re.sub(r"\\[\"']", " ", s)
    s = s.replace('"', " ").replace("'", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def split_chain(cmd):
    """链式命令拆段:&& || ; | & 换行 全部切开(逐段独立检查)。"""
    return [seg.strip() for seg in _CHAIN_SPLIT_RE.split(str(cmd or "")) if seg.strip()]


# ---------------- 路径判定 ----------------

def resolve_inside(workdir, path):
    """解析路径并判断是否在 workdir 内(abspath 折叠 .. + commonpath 判边界)。
    返回 (real_abs, inside_bool)。子 agent 不支持额外允许目录(严格小于主 agent)。"""
    try:
        base = os.path.normcase(os.path.abspath(workdir))
        real = os.path.normcase(os.path.abspath(os.path.join(workdir, str(path or ""))))
        common = os.path.commonpath([base, real])
        return real, common == base
    except Exception:
        return os.path.normcase(os.path.abspath(os.path.join(workdir, str(path or "")))), False


def match_sensitive(norm, patterns):
    """归一化路径是否命中敏感模式。"""
    for pat in patterns or []:
        p = norm_path(pat)
        if p and p in norm:
            return pat
    return None


# ---------------- 命令判定 ----------------

def match_command(segment_norm, rules):
    """归一化命令段是否命中黑名单。返回 (rule_dict|None)。"""
    for r in rules or []:
        try:
            if re.search(r["pattern"], segment_norm):
                return r
        except Exception:
            continue
    return None


def redirect_targets(cmd):
    """提取重定向/tee/out-file 的目标路径(它们是"写到哪"的另一种表达)。"""
    out = []
    for m in _REDIRECT_RE.finditer(str(cmd or "")):
        tok = (m.group(1) or m.group(2) or "").strip()
        if tok and tok not in ("nul", "/dev/null", "null"):
            out.append(tok)
    return out


# ---------------- 子 agent 沙箱 ----------------

class ChildSandbox:
    """子 agent 侧的强制沙箱:默认拒绝、无升级路径、带审计与危险行为计数。

    用法(子进程内,由 ollama_agent 在 child mode 下安装):
        sb = ChildSandbox(workdir, cfg)
        verdict = sb.check_tool(name, args)      # -> {"verdict": "allow"|"deny"|"severe", ...}
    主 harness 侧只读它的审计与计数结果(通过 audit.log 与子进程退出码)。
    """

    SEVERE_EXIT_CODE = 53

    def __init__(self, workdir, cfg, audit_path=None, clock=None):
        self.workdir = os.path.abspath(workdir)
        self.cfg = cfg or {}
        self.audit_path = audit_path or os.path.join(self.workdir, "audit.log")
        self._clock = clock or time.time
        self.allowed_tools = set(self.cfg.get("child_allowed_tools")
                                 or DEFAULT_CHILD_ALLOWED_TOOLS)
        self.sensitive = list(self.cfg.get("sensitive_dir_patterns")
                              or DEFAULT_SENSITIVE_DIR_PATTERNS)
        self.system_dirs = list(self.cfg.get("system_dir_patterns")
                                or DEFAULT_SYSTEM_DIR_PATTERNS)
        self.read_allow = list(self.cfg.get("read_allow_patterns")
                               or DEFAULT_READ_ALLOW_PATTERNS)
        self.rules = list(self.cfg.get("dangerous_command_patterns")
                          or DEFAULT_DANGEROUS_COMMANDS)
        self.rules += list(self.cfg.get("extra_dangerous_command_patterns") or [])
        self.max_denies = int(self.cfg.get("max_denies_per_child", 3))
        # workdir 本身被误配进核心系统区(如 C:\Windows)→ 一切写拒绝(防误配置)。
        # 用"核心系统区"子集而非全量系统区清单:AppData\\Local\\Temp 是合法工作目录去处。
        self.workdir_is_system_area = bool(
            match_sensitive(norm_path(self.workdir),
                            self.cfg.get("core_system_dir_patterns")
                            or DEFAULT_CORE_SYSTEM_PATTERNS))
        self.denies = 0
        self.severes = 0
        self.events = 0
        self._terminated = False

    # ---- 审计 ----
    def _audit(self, kind, target, verdict, severity, reason):
        self.events += 1
        rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "mono": round(self._clock(), 3),
               "kind": kind, "target": str(target)[:300], "verdict": verdict,
               "severity": severity, "reason": reason,
               "workdir": self.workdir}
        try:
            with open(self.audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass  # 审计写失败绝不阻塞主流程(审计文件在 workdir 内,通常不会失败)

    # ---- 计数与终止 ----
    def should_terminate(self):
        return self._terminated

    def _register(self, verdict):
        if verdict == "severe":
            self.severes += 1
            self._terminated = True    # ≥1 次严重拒绝 → 立即终止
        elif verdict == "deny":
            self.denies += 1
            if self.denies >= self.max_denies:
                self._terminated = True

    # ---- 三道检查 ----
    def check_tool_allowed(self, name):
        """第 1 道:工具面收窄。不在白名单 = deny(severe for 命令/网络/删除类)。"""
        if name in self.allowed_tools:
            return True, "", ""
        severe = name in ("run_bash", "run_command", "shell", "bash", "delete_file",
                          "web_search", "web_fetch", "mcp_call", "enable_tools",
                          "web_search_multi")
        return False, ("severe" if severe else "deny"), (
            f"tool_not_allowed(子 agent 工具面已收窄,只有 {sorted(self.allowed_tools)}; "
            f"{name} 不可用,也不要尝试绕道)")

    def check_path(self, path, action):
        """第 2 道:路径边界 + 敏感目录。写=只许 workdir 内且不命中敏感;读=敏感需白名单。
        判定顺序:
          1) workdir 之外 → 写 severe / 读 deny(兜底条款,无升级);命中系统区清单时给精确原因;
          2) workdir 之内 → 只看"在 workdir 内也有意义"的敏感清单(凭据/VM 磁盘/agent 数据)。
        刻意不用系统区清单匹配 workdir 内的相对路径:workdir 的位置由派发器选定、天然可信,
        否则 workdir 在 AppData/Temp 下时会整目录误伤。"""
        real, inside = resolve_inside(self.workdir, path)
        norm = norm_path(real)
        if not inside:
            verdict = "severe" if action == "write" else "deny"
            hit = match_sensitive(norm, self.system_dirs)
            why = f"sensitive_path({hit}) " if hit else ""
            return verdict, real, f"{why}outside_workdir(workdir 之外一律拒绝{action})"
        if self.workdir_is_system_area and action == "write":
            return "severe", real, "workdir_misconfigured_into_system_area(写拒绝)"
        hit = match_sensitive(norm, self.sensitive)
        if hit:
            # 敏感面:写一律 severe;读默认拒,显式白名单才放行
            if action == "write":
                return "severe", real, f"sensitive_path({hit}) 写敏感路径"
            for allow in self.read_allow:
                if norm_path(allow) and norm_path(allow) in norm:
                    return "allow", real, ""
            return "deny", real, f"sensitive_path({hit}) 读敏感路径(无白名单)"
        return "allow", real, ""

    def check_command(self, command):
        """第 3 道:危险命令黑名单。归一化 + 整条检查 + 链式拆段逐个检查 + 重定向目标检查。
        整条先查一次,是为了抓跨段的组合形态(curl … | bash)——链式拆分会把管道切开,
        单看每段反而漏掉"下载并执行"这种组合语义。"""
        norm_all = norm_command(command)
        for scope in ([norm_all] + (split_chain(norm_all) or [norm_all])):
            rule = match_command(scope, self.rules)
            if rule:
                sev = rule.get("severity", "deny")
                return sev, command, f"dangerous_command({rule.get('reason', rule.get('pattern'))})"
        # 重定向目标 = 写路径,按 workdir 边界与敏感面检查
        for tgt in redirect_targets(norm_all):
            verdict, real, reason = self.check_path(tgt, "write")
            if verdict != "allow":
                return verdict, command, f"redirect_target({reason})"
        return "allow", command, ""

    # ---- 统一入口 ----
    def check_tool(self, name, args):
        """依次过三道闸,返回 (verdict, reason, audit_target)。verdict∈allow/deny/severe。"""
        # 1) 工具面
        ok, sev, reason = self.check_tool_allowed(name)
        if not ok:
            self._register(sev)
            self._audit("tool", name, sev, sev, reason)
            return sev, reason, name
        # 2) 命令(子 agent 默认拿不到命令工具;显式开启时这里仍是硬闸)
        if name in ("run_bash", "run_command", "shell", "bash"):
            verdict, target, reason = self.check_command(args.get("command", ""))
            self._register(verdict)
            self._audit("command", target, verdict, verdict, reason)
            return verdict, reason, target
        # 3) 路径(读写两类)
        if name in ("create_file", "edit_file", "append_file", "delete_file"):
            action = "write"
        elif name in ("read_file", "list_dir", "search_files"):
            action = "read"
        else:
            # fail-closed:未映射工具不允许免检放行(显式加白名单才是放行通道)
            return "deny", "unmapped tool · 未映射工具,默认拒绝(default-deny)", name
        path = (args.get("path") or args.get("dir") or args.get("filepath") or "")
        verdict, real, reason = self.check_path(path, action)
        self._register(verdict)
        self._audit(action, real or path, verdict, verdict, reason)
        return verdict, reason, real or path


def read_audit(audit_path):
    """读子 agent 审计日志(harness 侧用)。返回事件列表;文件缺失返回 []。"""
    out = []
    try:
        with open(audit_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return out


def audit_summary(events):
    """审计事件 -> 摘要(denies / severes / 危险行为清单)。"""
    denies = [e for e in events if e.get("verdict") == "deny"]
    severes = [e for e in events if e.get("verdict") == "severe"]
    return {"events": len(events), "denies": len(denies), "severes": len(severes),
            "detail": [{"target": e.get("target"), "severity": e.get("severity"),
                        "reason": e.get("reason")} for e in (severes + denies)[:10]]}
