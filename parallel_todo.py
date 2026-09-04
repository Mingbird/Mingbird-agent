#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""并行派发的触发层:TodoProvider 抽象 + 任务分类器 + 触发判定。

要点:
- 全部在 harness 代码层判断(内存探测 / todo 计数 / 任务简单度启发式),
  不改系统提示,模型不需要预先知道子 agent 机制存在(prefill 预算零增量)。
- 分类器与安全预检都是确定性代码,不调模型;每条被拒条目带人话 reason。
- 主模型的注解(complexity/[simple])只能把条目降级,不能越过负面清单/安全预检。

设计文档: design/2026-09-01-parallel-dispatch.md §2 §3.6
"""
import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from parallel_config import get_parallel_config, hard_disabled, current_depth
from parallel_safety import (DEFAULT_SENSITIVE_DIR_PATTERNS, DEFAULT_DANGEROUS_COMMANDS,
                             norm_path, match_command, norm_command)

# 与 ollama_agent 的产物文件 token 同款规则(独立实现,避免 import 主模块副作用)
_FILE_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-一-鿿][A-Za-z0-9_\-一-鿿]*\.[A-Za-z0-9]{2,5}")
_ARTIFACT_EXTS = (".md", ".txt", ".csv", ".json", ".py", ".yaml", ".yml", ".html",
                  ".tsv", ".log", ".tex", ".svg", ".rst", ".ini", ".toml")
# 注解前缀(主模型可在条目文本里标 simple)
_SIMPLE_PREFIX = "[simple]"
_COMPLEX_PREFIX = "[complex]"
_COMPLEXITY_WORDS = ("复杂", "难", "关键", "危险", "跨文件", "核心", "critical",
                     "complex", "hard", "risky", "careful")


@dataclass
class TodoItem:
    """todo 条目的中立表示(TodoProvider 的输出;存储实现自己映射)。"""
    id: str
    text: str
    done: bool = False
    complexity: str = ""      # "simple" / "complex" / ""(未标注)


@dataclass
class ClassifyResult:
    dispatchable: bool
    reason: str = ""
    file_tokens: list = field(default_factory=list)


@dataclass
class DispatchPlan:
    should: bool = False
    reasons: list = field(default_factory=list)       # 人话原因(含不派的原因)
    items: list = field(default_factory=list)         # 可派条目 [TodoItem]
    skipped: list = field(default_factory=list)       # [(TodoItem, reason)]
    capacity: dict = field(default_factory=dict)

    @property
    def n_items(self):
        return len(self.items)


# ---------------- TodoProvider(对接 todo-0901:只定义抽象,不实现存储) ----------------

class TodoProvider(ABC):
    """todo 管线的最小接口。todo-0901 分支换存储时实现这个接口即可对接。"""

    @abstractmethod
    def all_items(self) -> list:
        """全部条目,按顺序。"""

    @abstractmethod
    def pending_items(self) -> list:
        """未完成条目,按顺序。"""

    @abstractmethod
    def mark_done(self, item_id: str, note: str = "") -> bool:
        """标记完成。必须幂等,且不得重排序其余条目。"""

    def set_complexity(self, item_id: str, level: str) -> bool:
        """主模型复杂度注解落盘(可选实现)。"""
        return False


class JsonTodoProvider(TodoProvider):
    """当前 todo.json 格式([{"item": str, "done": bool}, ...])的兼容读法。
    不是最终存储方案;todo-0901 管线换实现后在此注册新类。"""

    def __init__(self, workdir, path=None):
        self.workdir = workdir
        self.path = path or os.path.join(workdir, "todo.json")

    def _read(self):
        try:
            data = json.load(open(self.path, encoding="utf-8"))
        except Exception:
            return []
        if isinstance(data, dict):     # 容忍 {"items": [...]} 形态
            data = data.get("items") or data.get("todo") or []
        if not isinstance(data, list):
            return []
        out = []
        for i, it in enumerate(data, 1):
            if isinstance(it, str):
                it = {"item": it, "done": False}
            if not isinstance(it, dict):
                continue
            text = str(it.get("item") or it.get("text") or it.get("title") or "").strip()
            if not text:
                continue
            out.append(TodoItem(id=str(it.get("id") or i), text=text,
                                done=bool(it.get("done")),
                                complexity=str(it.get("complexity") or "")))
        return out

    def all_items(self):
        return self._read()

    def pending_items(self):
        return [x for x in self._read() if not x.done]

    def mark_done(self, item_id, note=""):
        try:
            data = json.load(open(self.path, encoding="utf-8"))
            hits = 0
            for i, it in enumerate(data):
                if str(i + 1) == str(item_id) or str(it.get("id", "")) == str(item_id):
                    it["done"] = True
                    if note:
                        it["note"] = note
                    hits += 1
            if hits:
                json.dump(data, open(self.path, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=2)
            return bool(hits)
        except Exception:
            return False

    def set_complexity(self, item_id, level):
        try:
            data = json.load(open(self.path, encoding="utf-8"))
            for i, it in enumerate(data):
                if str(i + 1) == str(item_id) or str(it.get("id", "")) == str(item_id):
                    it["complexity"] = level
                    json.dump(data, open(self.path, "w", encoding="utf-8"),
                              ensure_ascii=False, indent=2)
                    return True
        except Exception:
            pass
        return False


class HarnessTodoProvider(JsonTodoProvider):
    """todo-0901 分支 todo.json 存储的适配器(整合注册,设计文档 §8 的对接口)。

    todo-0901 确认存储仍是 <workdir>/todo.json 的 [{"item","done"},...] 列表,
    但读写的唯一实现来源是 ollama_agent.load_todo/save_todo(与 format_todo_lines、
    GUI 计划面板、todo 停滞提醒/finish 门禁同一管线)。这里只做委托,不再自持
    一份 JSON 解析 —— 避免两侧对"合法条目/字段"的判断各自漂移。
    """

    def _read(self):
        import ollama_agent as OA          # 函数内导入:避免模块级 import 副作用
        try:
            data = OA.load_todo(self.workdir) or []
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        out = []
        for i, it in enumerate(data, 1):
            if isinstance(it, str):
                it = {"item": it, "done": False}
            if not isinstance(it, dict):
                continue
            text = str(it.get("item") or it.get("text") or it.get("title") or "").strip()
            if not text:
                continue
            out.append(TodoItem(id=str(it.get("id") or i), text=text,
                                done=bool(it.get("done")),
                                complexity=str(it.get("complexity") or "")))
        return out

    def _mutate(self, item_id, mutate):
        import ollama_agent as OA
        try:
            data = OA.load_todo(self.workdir) or []
        except Exception:
            return False
        if not isinstance(data, list):
            return False
        hits = 0
        for i, it in enumerate(data):
            if not isinstance(it, dict):
                continue
            if str(i + 1) == str(item_id) or str(it.get("id", "")) == str(item_id):
                mutate(it)
                hits += 1
        if hits:
            OA.save_todo(self.workdir, data)
        return bool(hits)

    def mark_done(self, item_id, note=""):
        def _m(it):
            it["done"] = True
            if note:
                it["note"] = note
        return self._mutate(item_id, _m)

    def set_complexity(self, item_id, level):
        return self._mutate(item_id, lambda it: it.__setitem__("complexity", level))


# 设计文档 §8 的注册口:存储实现再换时,在这里按 kind 挂新类;make_provider 默认走
# 当前 harness 存储(todo-0901 的 todo.json 管线),旧的兼容读法保留为 legacy。
_PROVIDER_REGISTRY = {
    "harness-todo-json": HarnessTodoProvider,
    "legacy-json": JsonTodoProvider,
}
_DEFAULT_PROVIDER_KIND = "harness-todo-json"


def register_provider(kind, cls):
    """注册新的 TodoProvider 实现(用户侧可扩展,不特判任何具体存储名)。"""
    _PROVIDER_REGISTRY[str(kind)] = cls


def make_provider(workdir, kind=None):
    """工厂:默认返回 harness(todo-0901)存储的适配器。kind 可选 legacy-json。"""
    cls = _PROVIDER_REGISTRY.get(str(kind or _DEFAULT_PROVIDER_KIND), HarnessTodoProvider)
    return cls(workdir)


# ---------------- 分类器(确定性,不调模型) ----------------

def _hint_hit(hint, low):
    """中文/含非 ASCII 用子串;纯 ASCII 用词边界(防 "csv" 命中 "scsv")。"""
    if not hint.isascii():
        return hint in low
    return re.search(r"\b" + re.escape(hint.strip()) + r"\b", low) is not None


def _file_tokens(text):
    toks = []
    for m in _FILE_TOKEN_RE.finditer(str(text or "")):
        t = m.group(0)
        if t.lower().endswith(_ARTIFACT_EXTS):
            toks.append(t)
    return toks


def classify_task(text, cfg=None):
    """单条 todo 条目 -> 是否可派给子 agent。三层:负面硬否决 / 正向机械特征 / 主模型注解。"""
    cfg = cfg or get_parallel_config()
    raw = str(text or "")
    low = raw.lower().strip()
    if not low:
        return ClassifyResult(False, "empty_item")

    # ③ 主模型注解:只能降级(注解抬不回负面清单/安全预检)
    annotated_simple = low.startswith(_SIMPLE_PREFIX)
    annotated_complex = low.startswith(_COMPLEX_PREFIX)
    if annotated_complex:
        return ClassifyResult(False, "annotated_complex(主模型标注为复杂)")

    # ① 负面清单(硬否决)
    for pat in cfg.get("veto_patterns") or []:
        if pat and _hint_hit(str(pat).lower(), low):
            return ClassifyResult(False, f"veto_pattern({pat})")

    # 措辞里的"复杂/危险"信号也降级(注解之外的兜底)
    for w in _COMPLEXITY_WORDS:
        if w.isascii():
            if re.search(r"\b" + re.escape(w) + r"\b", low):
                return ClassifyResult(False, f"complexity_word({w})")
        elif w in low:
            return ClassifyResult(False, f"complexity_word({w})")

    # ② 正向特征:机械变换 + 单文件作用域。启发式路径要求恰好 1 个文件 token
    #    (多输入任务应被主模型拆成逐文件条目);主模型显式 [simple] 注解允许 1-2 个
    #    (一进一出),仍然有界。
    simple_hit = any(_hint_hit(str(p).lower(), low) for p in (cfg.get("simple_patterns") or []))
    toks = _file_tokens(raw)
    if annotated_simple:
        if not (1 <= len(toks) <= 2):
            return ClassifyResult(False, "annotated_simple_but_not_single_file_scope")
        return ClassifyResult(True, "annotated_simple", toks)
    if simple_hit and len(toks) == 1:
        return ClassifyResult(True, f"mechanical_single_file({toks})", toks)
    if simple_hit:
        return ClassifyResult(False, f"mechanical_but_files={len(toks)}(非单文件作用域)")
    if len(toks) == 1:
        return ClassifyResult(False, "single_file_but_not_mechanical(无机械变换特征)")
    return ClassifyResult(False, "not_mechanical_and_not_single_file")


def safety_precheck(text, cfg=None):
    """派发前的第二道闸:条目文本命中敏感目录模式或 severe 命令模式 -> 不可派。
    在 spawn 之前就拦下,而不是等子 agent 跑了半天再被杀。"""
    cfg = cfg or get_parallel_config()
    norm = norm_path(str(text or ""))
    patterns = cfg.get("sensitive_dir_patterns") or DEFAULT_SENSITIVE_DIR_PATTERNS
    for pat in patterns or []:
        p = norm_path(pat)
        if p and p in norm:
            return False, f"sensitive_in_task_text({pat})"
    rules = list(cfg.get("dangerous_command_patterns") or DEFAULT_DANGEROUS_COMMANDS)
    rules += list(cfg.get("extra_dangerous_command_patterns") or [])
    rule = match_command(norm_command(str(text or "")), rules)
    if rule and rule.get("severity") == "severe":
        return False, f"severe_command_in_task_text({rule.get('reason')})"
    return True, ""


# ---------------- 触发判定(全部 AND,任何一条不满足都不派) ----------------

def should_dispatch(probe, provider, cfg=None, environ=None, child_model=None):
    """返回 DispatchPlan。理由全部人话,可直接进日志/GUI。"""
    cfg = cfg or get_parallel_config()
    env = environ if environ is not None else os.environ
    plan = DispatchPlan()

    if not cfg.get("enabled"):
        plan.reasons.append("disabled(parallel.enabled=false,默认关,冻结期安全)")
        return plan
    if hard_disabled(env):
        plan.reasons.append("hard_kill_switch(AGENT_PARALLEL=0)")
        return plan
    depth = current_depth(env)
    if depth >= int(cfg.get("max_depth", 1)):
        plan.reasons.append(f"depth_limit(当前深度 {depth} >= max_depth {cfg.get('max_depth')},子 agent 禁止再派)")
        return plan
    model = child_model or cfg.get("child_model") or ""
    if not str(model).strip():
        plan.reasons.append("no_child_model(parallel.child_model 未配置;零硬编码,必须显式配置)")
        return plan

    # todo 条目
    try:
        pending = provider.pending_items()
    except Exception as e:
        plan.reasons.append(f"todo_provider_error({e})")
        return plan
    n_pending = len(pending)
    if n_pending < int(cfg.get("min_pending_items", 6)):
        plan.reasons.append(
            f"too_few_pending(未完成 {n_pending} < 阈值 {cfg.get('min_pending_items')})")
        return plan

    # 逐条分类 + 安全预检
    for it in pending:
        cls = classify_task(it.text, cfg)
        if not cls.dispatchable:
            plan.skipped.append((it, cls.reason))
            continue
        ok, why = safety_precheck(it.text, cfg)
        if not ok:
            plan.skipped.append((it, why))
            continue
        plan.items.append(it)
    if len(plan.items) < int(cfg.get("min_dispatchable", 2)):
        plan.reasons.append(
            f"too_few_dispatchable(可派 {len(plan.items)} < 阈值 {cfg.get('min_dispatchable')};"
            f" 其余被分类器/安全预检拒绝)")
        return plan

    # 硬件容量
    cap = probe.plan_capacity(model, cfg)
    plan.capacity = cap
    if int(cap.get("max_parallel", 0)) < 1:
        plan.reasons.append("no_capacity(放不下一个小模型) | " +
                            "; ".join(cap.get("reasons", [])))
        return plan

    plan.should = True
    plan.reasons.insert(0, f"trigger_ok(pending={n_pending}, dispatchable={len(plan.items)}, "
                           f"max_parallel={cap.get('max_parallel')}, model={model})")
    return plan
