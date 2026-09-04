#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""并行派发配置层:所有阈值/模型名/并发数/内存系数都从这里读,零硬编码。

用户配置:~/.ollama_agent/config.json 的 "parallel" 段(深合并到默认值上)。
环境变量:
  AGENT_PARALLEL=0      无条件硬闸(优先级最高,bench 冻结期/子进程用它整体关掉)
  HUMMINGBIRD_DEPTH     派发深度(子进程由 dispatcher 置 1,达到 max_depth 即拒绝)

设计文档: design/2026-09-01-parallel-dispatch.md
"""
import os

try:
    import appconfig
except Exception:  # pragma: no cover - 允许在无 appconfig 的环境单测
    appconfig = None

# ---------------- 默认值(唯一事实来源,config.json 可逐项覆盖) ----------------
DEFAULT_PARALLEL = {
    # 总开关:默认关(基准冻结期安全;开启只改 config.json 一行)
    "enabled": False,
    # 子模型 tag。空 = 功能关。刻意不写死任何模型名(零硬编码要求)
    "child_model": "",
    # 子模型上下文。KV 成本的主要杠杆;子任务只需单文件作用域,不需要大上下文
    "child_ctx": 8192,
    # 触发:todo 未完成条目阈值(低于此值,子 agent 加载开销摊不回来)
    "min_pending_items": 6,
    # 触发:其中"可派"条目阈值(只为 1 条开子进程不划算)
    "min_dispatchable": 2,
    # 并发硬上限(与容量公式结果取小)
    "hard_cap": 2,
    # 可用内存利用率上限(UMA:共享显存由物理内存背书,真正的预算是内存)
    "ram_utilization_cap": 0.70,
    # 绝对预留(OS / GUI / 杂项),字节。默认 1.5GB
    "ram_reserve_bytes": 1610612736,
    # 权重估算:每参数量(B)占用字节,默认 1.0GB/B(Q4~Q8 区间取上限 = 高估 = 保守)
    "bytes_per_param": 1000000000.0,
    # 权重的计算缓冲/激活系数
    "weight_overhead": 1.25,
    # llama runner / GPU host 侧固定开销
    "runtime_overhead_bytes": 858993459,
    # 子 agent python 进程本身开销
    "process_overhead_bytes": 214748365,
    # KV 估算:参数量上限(键) -> 每 1K token 字节(值)。命中取该档,超过最大档拒派
    "kv_bytes_per_1k_token": {"2.5": 67108864, "4.5": 157286400, "8.0": 262144000},
    # 子模型参数量上限,超过拒派(子 agent 必须是小模型)
    "max_child_params_b": 8.0,
    # 是否允许把父模型从显存挤出去(默认禁止:同实例换模型 = 抖动,拖垮主任务)
    "allow_parent_eviction": False,
    # 是否允许覆盖父目录已有文件(默认禁止:并行收益不以静默覆盖用户文件为代价)
    "allow_overwrite_existing": False,
    # 单条子任务硬超时(秒)
    "per_task_timeout_s": 900,
    # 可选 verify 命令超时(秒)
    "verify_timeout_s": 300,
    # 失败重试次数(重试仍失败 → 回退主模型串行)
    "max_retries": 1,
    # 派发深度上限(1 = 子 agent 禁止再派)
    "max_depth": 1,
    # 工作区子目录名
    "dispatch_dirname": "_dispatch",
    # 主 agent 入口文件名(子进程以 <模块目录>/agent_entry 起 headless 实例)
    "agent_entry": "ollama_agent.py",
    # 子进程存活轮询间隔(秒)
    "poll_interval_s": 0.5,
    # workdir 误配进系统区的守卫子集(裸 \appdata 不在内:合法 workdir 常在
    # AppData\Local\Temp 下)。空 = 用出厂默认(parallel_safety.DEFAULT_CORE_SYSTEM_PATTERNS)
    "core_system_dir_patterns": [],
    # ===== 子 agent 安全模型(出厂默认 = 最严档;规则全部数据驱动) =====
    # 子 agent 工具面(严格小于主 agent:不给 命令/网络/MCP/删除/编辑/enable_tools)
    "child_allowed_tools": ["read_file", "list_dir", "create_file", "todo", "finish"],
    # 敏感目录/文件模式(在 workdir 内也拒:凭据/VM磁盘/agent数据;写一律 severe 终止;
    # 读默认拒,read_allow_patterns 才放行)。空 = 用出厂最严默认
    "sensitive_dir_patterns": [],
    # 绝对系统位置(WSL/VM 子系统、Windows、Program Files、AppData…)。workdir 之外由
    # 兜底条款拒;这张清单给审计精确原因 + 防 workdir 误配进系统区。空 = 出厂最严默认
    "system_dir_patterns": [],
    "read_allow_patterns": [],         # 敏感路径读白名单(默认空 = 敏感路径读也拒)
    # 危险命令黑名单(空 = 出厂最严默认;extra_* 追加而不替换)
    "dangerous_command_patterns": [],
    "extra_dangerous_command_patterns": [],
    # 子 agent 允许命令工具(默认 False:命令工具根本不进工具面;True 也仍过黑名单)
    "child_allow_commands": False,
    # 危险行为计数:非严重拒绝累计到此值即终止该子 agent
    "max_denies_per_child": 3,
    # 严重拒绝(虚拟机/系统区写)后是否还重试(默认不重试:直接回退主模型串行)
    "retry_on_severe": False,
    # 子 agent 审计进度采样间隔(秒)
    "audit_poll_interval_s": 5.0,

    # 分类器负面清单(硬否决,任何注解都抬不回来)。可追加/精简
    "veto_patterns": [
        # 破坏性
        "删除", "删掉", "清空", "覆盖", "重置", "format ", "delete ", "remove ",
        "truncate", "drop ",
        # 对外写
        "git push", "push to", "发布", "上传", "提交到", "发送给", "upload", "publish",
        # 敏感面
        ".env", "config.json", "mcp.json", "credential", "token", "secret",
        "密码", "凭据", "api key", "apikey",
        # 跨文件 / 高歧义
        "重构", "refactor", "合并", "merge ", "迁移", "migration", "架构", "数据库",
        "pip install", "npm install", "安装依赖", "全局替换", "所有文件", "整个项目",
        # 只能靠命令的(失败模式不可枚举)
        "运行测试", "跑测试", "部署", "deploy",
    ],
    # 正向特征(机械变换,子模型擅长)。可追加/精简
    "simple_patterns": [
        "改名", "重命名", "rename", "转换", "convert", "格式化", "format as",
        "统计", "计数", "count ", "抽取", "提取", "extract", "翻译", "translate",
        "总结", "汇总", "summarize", "罗列", "列出", "list all", "生成模板",
        "补全注释", "排序", "sort ", "去重", "dedupe", "按字母", "转成", "导出为",
        "export to", "csv", "markdown 表格",
    ],
}

# 允许覆盖的类型(防止用户在 config 里把数字写成字符串后炸掉逻辑)
_NUM_KEYS = {"child_ctx", "min_pending_items", "min_dispatchable", "hard_cap",
             "ram_reserve_bytes", "runtime_overhead_bytes", "process_overhead_bytes",
             "per_task_timeout_s", "verify_timeout_s", "max_retries", "max_depth"}
_FLOAT_KEYS = {"ram_utilization_cap", "bytes_per_param", "weight_overhead",
               "max_child_params_b"}
_BOOL_KEYS = {"enabled", "allow_parent_eviction", "allow_overwrite_existing",
              "child_allow_commands", "retry_on_severe"}
_LIST_KEYS = {"veto_patterns", "simple_patterns", "child_allowed_tools",
              "sensitive_dir_patterns", "system_dir_patterns", "read_allow_patterns",
              "dangerous_command_patterns", "extra_dangerous_command_patterns"}

_ENV_KEYS = {
    "child_model": "AGENT_PARALLEL_MODEL",
    "child_ctx": "AGENT_PARALLEL_CTX",
    "min_pending_items": "AGENT_PARALLEL_MIN_ITEMS",
    "min_dispatchable": "AGENT_PARALLEL_MIN_DISPATCH",
    "hard_cap": "AGENT_PARALLEL_MAX",
    "per_task_timeout_s": "AGENT_PARALLEL_TIMEOUT",
    "max_depth": "AGENT_PARALLEL_DEPTH",
}


def _coerce(key, val, cur):
    """把用户/环境变量给来的值收敛到正确类型;非法值回退默认(不抛异常)。"""
    try:
        if key in _NUM_KEYS:
            v = int(float(val)); return v
        if key in _FLOAT_KEYS:
            v = float(val); return v
        if key in _BOOL_KEYS:
            if isinstance(val, str):
                return val.strip().lower() in ("1", "true", "yes", "on")
            return bool(val)
        if key in _LIST_KEYS:
            if isinstance(val, str):
                return [x.strip() for x in val.split(",") if x.strip()]
            # 危险命令黑名单的元素是 {"pattern","severity","reason"} 对象,不能 str 化
            if key in ("dangerous_command_patterns", "extra_dangerous_command_patterns"):
                out = []
                for it in (val or []):
                    if isinstance(it, dict) and it.get("pattern"):
                        out.append({"pattern": str(it["pattern"]),
                                    "severity": str(it.get("severity", "deny")),
                                    "reason": str(it.get("reason", ""))})
                    elif isinstance(it, str) and it.strip():
                        out.append({"pattern": it.strip(), "severity": "deny",
                                    "reason": "user_rule"})
                return out
            return [str(x) for x in (val or [])]
        if key == "kv_bytes_per_1k_token":
            if isinstance(val, dict):
                return {str(k): float(v) for k, v in val.items()}
            return cur
        if key == "dispatch_dirname":
            s = str(val).strip()
            return s if s and not os.path.isabs(s) and ".." not in s else cur
        return val
    except Exception:
        return cur


def get_parallel_config(config=None, environ=None):
    """默认值 <- config.json 的 parallel 段(深合并) <- 环境变量。永不抛异常。"""
    env = os.environ if environ is None else environ
    cfg = dict(DEFAULT_PARALLEL)
    cfg["kv_bytes_per_1k_token"] = dict(DEFAULT_PARALLEL["kv_bytes_per_1k_token"])
    cfg["veto_patterns"] = list(DEFAULT_PARALLEL["veto_patterns"])
    cfg["simple_patterns"] = list(DEFAULT_PARALLEL["simple_patterns"])
    try:
        src = config if config is not None else (
            (appconfig.load_config() or {}) if appconfig else {})
        user = src.get("parallel") or {}
        if isinstance(user, dict):
            for k, v in user.items():
                if k in cfg:
                    cfg[k] = _coerce(k, v, cfg[k])
    except Exception:
        pass
    for k, ev in _ENV_KEYS.items():
        if env.get(ev):
            cfg[k] = _coerce(k, env[ev], cfg[k])
    return cfg


def hard_disabled(environ=None):
    """无条件硬闸:AGENT_PARALLEL=0 时无论 config 怎么写都不派。"""
    env = os.environ if environ is None else environ
    return str(env.get("AGENT_PARALLEL", "")).strip().lower() in ("0", "false", "off", "no")


def current_depth(environ=None):
    """当前派发深度(主 agent = 0;子进程由 dispatcher 置 1)。"""
    env = os.environ if environ is None else environ
    try:
        return int(str(env.get("HUMMINGBIRD_DEPTH", "0")).strip() or 0)
    except Exception:
        return 0
