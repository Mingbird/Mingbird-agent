#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""硬件探测:UMA(Intel Arc 核显共享显存)下真正的预算是物理内存。

- 内存读数:psutil -> Windows GlobalMemoryStatusEx(ctypes) -> os.sysconf 三级回退。
- 已加载模型:GET {ollama_host}/api/ps 的 model / size / size_vram。
- 容量公式:usable = available × cap;budget = usable − reserve;
            max_parallel = floor(budget / per_child_cost),再与 hard_cap 取小。
- 父模型共存门:已有已加载模型且 tag != 子模型,默认拒绝(避免同实例换模型抖动)。

所有外部依赖(内存读数器、HTTP)都是构造参数注入,测试不打真机器。
设计文档: design/2026-09-01-parallel-dispatch.md §1
"""
import json
import re
import urllib.request

from parallel_config import get_parallel_config

# 与 ollama_agent._model_params_b 同款规则(独立实现,避免 import 主模块的副作用)
_PARAMS_RE = re.compile(r"(\d+(?:\.\d+)?)b\b")
_GIB = 1024 ** 3


def parse_params_b(model):
    """模型名 -> 参数量(B)。解析失败返回 None(调用方按大模型处理)。"""
    m = _PARAMS_RE.search(str(model or "").lower())
    return float(m.group(1)) if m else None


# ---------------- 内存读数(三级回退,全部可注入) ----------------

def _mem_via_psutil():
    try:
        import psutil
        vm = psutil.virtual_memory()
        return float(vm.total), float(vm.available)
    except Exception:
        return None


def _mem_via_winapi():
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return float(st.ullTotalPhys), float(st.ullAvailPhys)
    except Exception:
        return None
    return None


def _mem_via_sysconf():
    try:
        page = os_sysconf("SC_PAGE_SIZE")
        pages = os_sysconf("SC_AVPHYS_PAGES")
        total = os_sysconf("SC_PHYS_PAGES")
        return float(total * page), float(pages * page)
    except Exception:
        return None


def os_sysconf(name):
    import os
    return os.sysconf(name)


_MEM_READERS = (_mem_via_psutil, _mem_via_winapi, _mem_via_sysconf)


def read_system_memory():
    """返回 (total_bytes, available_bytes) 或 None(三级读数器都失败)。"""
    for fn in _MEM_READERS:
        r = fn()
        if r and r[0] > 0:
            return r
    return None


# ---------------- ollama /api/ps ----------------

def read_loaded_models(host, timeout=4.0):
    """返回 [{"model","size","size_vram"}] 或 None(不可达)。

    None 与 [] 语义不同:None = 探测失败(按无法确认容量处理 -> 不派);
    [] = ollama 活着但没加载模型(可以派)。
    """
    try:
        req = urllib.request.Request(host.rstrip("/") + "/api/ps",
                                     headers={"User-Agent": "hummingbird-parallel"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
        out = []
        for m in data.get("models", []) or []:
            try:
                out.append({"model": str(m.get("model") or m.get("name") or ""),
                            "size": float(m.get("size") or 0),
                            "size_vram": float(m.get("size_vram") or 0)})
            except Exception:
                continue
        return out
    except Exception:
        return None


# ---------------- 成本估算 ----------------

def kv_bytes_for(params_b, ctx_tokens, cfg):
    """KV 缓存估算:命中参数量档位取该档的每 1K token 字节;超过最大档返回 None(拒派)。"""
    table = cfg.get("kv_bytes_per_1k_token") or {}
    keys = []
    for k, v in table.items():
        try:
            keys.append((float(k), float(v)))
        except Exception:
            continue
    if not keys:
        return None
    keys.sort()
    for limit, per_1k in keys:
        if params_b is None or params_b <= limit:
            return per_1k * (float(ctx_tokens) / 1000.0)
    return None   # 超过最大档:子模型必须是小的


def estimate_child_cost(child_model, cfg, loaded_size=None):
    """单条子任务内存成本(字节)。返回 (bytes, breakdown_dict)。

    loaded_size: /api/ps 已给出的该模型权重实测值(有则优先,比按参数量估的准)。
    返回 bytes=None 表示拒绝(参数量超上限且无实测权重)。
    """
    params_b = parse_params_b(child_model)
    if loaded_size and loaded_size > 0:
        weights = float(loaded_size)
    else:
        if params_b is None:
            return None, {"reason": "child_model_unparsable", "params_b": None}
        if params_b > float(cfg["max_child_params_b"]):
            return None, {"reason": "child_model_too_large", "params_b": params_b}
        weights = params_b * float(cfg["bytes_per_param"])
    if params_b is not None and params_b > float(cfg["max_child_params_b"]):
        return None, {"reason": "child_model_too_large", "params_b": params_b}
    kv = kv_bytes_for(params_b, cfg.get("child_ctx", 8192), cfg)
    if kv is None:
        return None, {"reason": "kv_table_missing_for_params", "params_b": params_b}
    total = (weights * float(cfg["weight_overhead"]) + kv
             + float(cfg["runtime_overhead_bytes"]) + float(cfg["process_overhead_bytes"]))
    return total, {"params_b": params_b, "weights_bytes": weights, "kv_bytes": kv,
                   "runtime_bytes": float(cfg["runtime_overhead_bytes"]),
                   "process_bytes": float(cfg["process_overhead_bytes"]),
                   "total_bytes": total, "ctx": cfg.get("child_ctx", 8192)}


# ---------------- 探测器 ----------------

class ResourceProbe:
    """硬件探测器。mem_reader / models_reader 可注入(测试不打真机器)。"""

    def __init__(self, ollama_host="http://127.0.0.1:11434",
                 mem_reader=None, models_reader=None, http_timeout=4.0):
        self.ollama_host = ollama_host
        self._mem_reader = mem_reader or read_system_memory
        self._models_reader = models_reader or (lambda: read_loaded_models(
            ollama_host, timeout=http_timeout))

    def snapshot(self):
        """返回 {"total_ram","available_ram","loaded":[...],"models_ok":bool} 或 None。"""
        mem = self._mem_reader()
        if not mem:
            return None
        models = self._models_reader()
        return {"total_ram": float(mem[0]), "available_ram": float(mem[1]),
                "loaded": models if models is not None else [],
                "models_ok": models is not None}

    def plan_capacity(self, child_model, cfg=None):
        """容量计划。返回 CapacityPlan(dict):
        max_parallel=0 一定带 reasons(人话),供日志与 GUI 解释为什么没派。"""
        cfg = cfg or get_parallel_config()
        reasons = []
        snap = self.snapshot()
        if not snap:
            return {"max_parallel": 0, "per_child_cost_bytes": None,
                    "reasons": ["memory_probe_failed(无法确认物理内存,按不派处理)"],
                    "snapshot": None}
        available = snap["available_ram"]
        usable = available * float(cfg["ram_utilization_cap"])
        budget = max(0.0, usable - float(cfg["ram_reserve_bytes"]))
        reasons.append(
            f"available={available/_GIB:.1f}GB cap={float(cfg['ram_utilization_cap']):.2f} "
            f"reserve={float(cfg['ram_reserve_bytes'])/_GIB:.1f}GB budget={budget/_GIB:.1f}GB")

        if not snap["models_ok"]:
            reasons.append("ollama_ps_unreachable(按无法确认容量处理,不派)")
            return {"max_parallel": 0, "per_child_cost_bytes": None, "reasons": reasons,
                    "snapshot": snap}

        # 父模型共存门:同实例换模型会把父模型挤出显存 -> 抖动,默认禁止
        loaded = snap["loaded"]
        resident = sum(m.get("size") or 0 for m in loaded)
        others = [m["model"] for m in loaded
                  if str(m.get("model") or "") and str(m.get("model")) != str(child_model)]
        if others and not cfg.get("allow_parent_eviction"):
            reasons.append(
                "parent_model_would_be_evicted(已加载: " + ", ".join(others[:3])
                + "; 与子模型不同 tag,同实例换模型会抖动) -> 0")
            return {"max_parallel": 0, "per_child_cost_bytes": None, "reasons": reasons,
                    "snapshot": snap}

        # 子模型权重:已加载则用实测 size,否则按参数量估
        loaded_size = None
        for m in loaded:
            if str(m.get("model")) == str(child_model):
                loaded_size = m.get("size")
                break
        cost, br = estimate_child_cost(child_model, cfg, loaded_size=loaded_size)
        if cost is None:
            reasons.append(f"child_model_rejected({br.get('reason')}, params_b={br.get('params_b')})")
            return {"max_parallel": 0, "per_child_cost_bytes": None, "reasons": reasons,
                    "snapshot": snap}
        if cost <= 0:
            reasons.append("child_cost_non_positive(配置异常)")
            return {"max_parallel": 0, "per_child_cost_bytes": cost, "reasons": reasons,
                    "snapshot": snap}

        n = int(budget // cost)
        reasons.append(f"per_child={cost/_GIB:.1f}GB -> floor({budget/_GIB:.1f}/{cost/_GIB:.1f})={n}")
        cap = int(cfg.get("hard_cap", 2))
        if n > cap:
            reasons.append(f"clamped_to_hard_cap={cap}")
            n = cap
        if n < 1:
            reasons.append("no_headroom_for_even_one_child(放不下一个小模型)")
        return {"max_parallel": max(0, n), "per_child_cost_bytes": cost,
                "breakdown": br, "reasons": reasons, "snapshot": snap}


def format_capacity_table(plan, cfg=None):
    """人话容量表(CLI `plan` 与日志用)。"""
    cfg = cfg or get_parallel_config()
    lines = ["[parallel] 容量计划"]
    for r in plan.get("reasons", []):
        lines.append("  - " + r)
    if plan.get("per_child_cost_bytes"):
        br = plan.get("breakdown") or {}
        lines.append("  - child_ctx={} weights={:.1f}GB kv={:.1f}GB runtime={:.1f}GB proc={:.1f}GB".format(
            br.get("ctx"), (br.get("weights_bytes") or 0) / _GIB, (br.get("kv_bytes") or 0) / _GIB,
            (br.get("runtime_bytes") or 0) / _GIB, (br.get("process_bytes") or 0) / _GIB))
    lines.append("  => max_parallel = {}".format(plan.get("max_parallel")))
    return "\n".join(lines)
