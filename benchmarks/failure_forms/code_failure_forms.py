# -*- coding: utf-8 -*-
"""M10:失败形态 × 发生率 × arm 编码表(零新实验,纯读 288 格既有产物)。

审稿要求(DeepSeek M10):288 格 transcript/attempt 目录全部保留,却没有任何一张
"失败形态 × 发生率 × arm"的编码表;建议编码 prefill overflow / 空转 / 静默放弃 /
格式崩解 / 平台退出 / 提前退出,并报 inter-coder 一致性。

本脚本的立场:**能用记录字段就不用散文判读**。每条形态的判据如下(全部可从产物复算):

  形态                判据(来源)
  ------------------  ------------------------------------------------------------
  platform_exit       score.json failure_mode ∈ {crash,error} 或 exit_code != 0
  budget_exhausted    failure_mode == 'timeout' 或 wall_seconds ≥ 该格预算
  never_engaged       transcript 工具调用计数 == 0
  spin                鸣鸟:重复调用拦截/检测到重复输出/连续空轮 任一 ≥1(其余臂 n/a)
  format_breakdown   鸣鸟:工具参数/解析错误行 ≥1;其余臂:本臂错误标记 ≥1(口径见下)
  context_pressure   鸣鸟专有:压缩事件 或 L1 旧工具输出截断事件 ≥1
  false_finish       finish 门禁拒绝计数 ≥1(鸣鸟专有;其余臂无门禁,n/a)
  early_stop         非平台退出、非预算耗尽,且 final_score < 0.5(提前收工/静默放弃)

预算口径:WF/tier1-3 = 5400s(90min),LH/tier4 = 10800s(180min),取自
run_matrix.py 的 --timeout-min/--timeout-min-lh 默认与本批实跑日志。
工具调用计数口径逐字复用 benchmarks/mechanism_log/extract_p1.py(已与
turns_resource_summary.csv 交叉印证过)。

输入(只读;全部在私有评测目录下,仓库内不含原始 transcript):
  <EVAL_ROOT>/mingbird-v16/benchmarks/lrab_scores.csv                          288 格发布口径
  <EVAL_ROOT>/<HB>/eval_results/<latest_attempt_dir>/                   鸣鸟系 / agent-mini
  <EVAL_ROOT>/mingbird-v150/eval_results/rr_think0/<...>/                      goose / opencode
输出(只写本目录):
  failure_forms_2609.csv / failure_forms_summary_2609.csv / failure_forms_2609.md
用法: python benchmarks/failure_forms/code_failure_forms.py

复跑说明:<EVAL_ROOT> 为本地评测根目录;产出 Mingbird / agent-mini 两臂的历史工作树
在本机是另一个目录名,此处占位为 <HB>,按实际情况替换后再跑。本仓库只含本目录下的派生表。
"""
import csv
import json
import os
import re
import statistics
import sys

BASE = r"<EVAL_ROOT>"                       # 本地评测根目录,按需替换
V16 = os.path.join(BASE, "mingbird-v16")    # 发布矩阵工作树
V150 = os.path.join(BASE, "mingbird-v150")  # 统一协议批工作树(goose / opencode)
HB = os.path.join(BASE, "<HB>")             # 历史工作树(Mingbird / agent-mini 臂)
SCORES = os.path.join(V16, "benchmarks", "lrab_scores.csv")
ROOT_MB = os.path.join(HB, "eval_results")
ROOT_RR = os.path.join(V150, "eval_results", "rr_think0")
OUT = os.path.dirname(os.path.abspath(__file__))

BUDGET_WF, BUDGET_LH = 5400.0, 10800.0

RE_GEAR = re.compile(r'\[\d+\|\+\d+s\] ⚙')
RE_AGENTMINI = re.compile(r'^\s*⚡ \S')
RE_GOOSE = re.compile(r'^\s*▸')
RE_OC_CMD = re.compile(r'^\$ ')
RE_OC_TOOL = re.compile(r'^→ ')
RE_ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
RE_CTX = re.compile(r'\[ctx: (\d+)/(\d+) = (\d+)%\]')
RE_RR_DIR = re.compile(r'^(goose|opencode)_(LH\d+|WF\d+)_(.+?)_(m\d)_(\d{4}_\d{6})$')
# 发布批内 0 字节 transcript 的格(goose WF08/qwen3.5:4b:两次合法超时+一次外部击杀,
# 2026-09-18 用户裁定记零分,见 rr_think0/EXCLUSIONS.md)→ 工具调用记 unknown 而非 0
EMPTY_TRANSCRIPT_OK = {("goose", "WF08", "qwen3.5_4b")}

# ---- 形态判据用到的文案(鸣鸟侧与前次取证 extract_p1.py 同一套) ----
MB_SPIN = ("重复调用拦截", "检测到重复输出", "连续空轮×")
MB_ARGERR = ("[tool error", "缺少参数", "参数校验失败", "无法解析")
MB_CTX = ("事前估算", "已压缩", "旧工具输出截断")
MB_FINFIN = ("拒绝假 finish", "测试未通过", "产物核对:summary 声称但缺失",
             "计划核对:计划点名但缺失", "计划未同步")
# 其余臂的错误标记(口径较粗,只在 CSV 里给计数,汇总表标注为近似)
AM_ERR = ("✗",)
# 基础设施层失败(与 harness 机制无关):LLM 提供方断线/通信错误。由盲编者独立发现
# (agentmini WF04/WF09 gemma4_12b:末轮 "ERROR Provider error: Error communicating with LLM"),
# failure_mode 仍记 completed/exit 0,故必须从 transcript 取证。
PROVIDER_ERR = ("Provider error", "Error communicating with LLM", "provider_error",
                "Failed to establish a new connection", "Connection refused")
GOOSE_ERR = ("error", "Error", "ERROR", "failed", "Failed")
OC_ERR = ("✗", "Error", "error")


def read_text(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def count_tool_calls(arm, text):
    """与 extract_p1.py 完全同口径。"""
    if arm == "Mingbird":
        return len(RE_GEAR.findall(text))
    if arm == "agent-mini":
        return sum(1 for ln in text.splitlines() if RE_AGENTMINI.match(ln))
    if arm == "goose":
        return sum(1 for ln in text.splitlines() if RE_GOOSE.match(ln))
    if arm == "opencode":
        n = 0
        for ln in text.splitlines():
            ln2 = RE_ANSI.sub("", ln)
            if RE_OC_CMD.match(ln2) or RE_OC_TOOL.match(ln2):
                n += 1
        return n
    return 0


def count_any(text, needles):
    return sum(text.count(n) for n in needles)


def model_slug(model):
    return model.replace(":", "_").replace(".", ".")


def resolve_dir(harness, task, model, latest_attempt_dir):
    """鸣鸟/agent-mini 直接命中;goose/opencode 的 latest_attempt_dir 是逻辑名
    (rr_think0_<task>),须按 (arm,task,model) 反查最新且含 transcript 的目录。"""
    p = os.path.join(ROOT_MB, latest_attempt_dir)
    if os.path.isdir(p):
        return p
    if harness in ("goose", "opencode"):
        # rr 臂的实际目录 <harness>_<task>_<model>_<m0|m1>_<date>_<time>;CSV 里是逻辑名
        # (rr_think0_<task>)。解析规则逐字复用 benchmarks/mechanism_log/extract_p1.py
        # (该规则已与 turns_resource_summary.csv 交叉印证):精确匹配 task 与 model,
        # 取最新且存在 transcript 的目录(最新目录可能被外部击杀、无 transcript)。
        # 另限发布批日期戳 0918/0919,避免把 0829-0904 更早批次的历史 attempt 记成本格形态。
        cands = []
        for d in os.listdir(ROOT_RR):
            m = RE_RR_DIR.match(d)
            if not m or not os.path.isdir(os.path.join(ROOT_RR, d)):
                continue
            if m.group(1) != harness or m.group(2) != task.replace("-", "") or m.group(3) != model:
                continue
            if not any(tag in d for tag in ("_0918_", "_0919_")):
                continue
            cands.append((m.group(5), d))
        if cands:
            cands.sort()
            chosen = next((c for c in reversed(cands)
                           if os.path.exists(os.path.join(ROOT_RR, c[1], "transcript.txt"))), cands[-1])
            return os.path.join(ROOT_RR, chosen[1])
    return None


def main():
    rows = list(csv.DictReader(open(SCORES, encoding="utf-8")))
    print(f"loaded {len(rows)} published rows", file=sys.stderr)
    per_cell, missing = [], []
    for r in rows:
        harness, task, model = r["harness"], r["task"], r["model"]
        d = resolve_dir(harness, task, model, r["latest_attempt_dir"])
        rec = {
            "harness": harness, "task": task, "model": model,
            "tier": "LH" if task.upper().startswith("LH") else "WF",
            "score": r["score"], "wall_seconds": r["wall_seconds"],
            "attempt_dir": os.path.basename(d) if d else "",
            "failure_mode": "", "exit_code": "", "tool_calls": "", "turns": "",
            "artifact_checks_ok": "", "artifact_checks_total": "",
            "fmt_arg_errors": "", "spin_events": "", "ctx_events": "",
            "finish_rejections": "", "note": "", "provider_errors": "",
        }
        if d:
            sj = os.path.join(d, "score.json")
            if os.path.exists(sj):
                try:
                    s = json.load(open(sj, encoding="utf-8"))
                    rec["failure_mode"] = s.get("failure_mode") or ""
                    rec["exit_code"] = s.get("exit_code", "")
                    det = (s.get("milestone_details") or []) + (s.get("final_details") or [])
                    if det:
                        rec["artifact_checks_total"] = len(det)
                        rec["artifact_checks_ok"] = sum(1 for x in det if x.get("ok"))
                except Exception:
                    rec["failure_mode"] = "score_json_unreadable"
            else:
                missing.append((harness, task, model, "score.json"))
            tp = os.path.join(d, "transcript.txt")
            if os.path.exists(tp) and os.path.getsize(tp) == 0:
                # 0 字节 transcript:计数不可得,不可当"零工具接触"编码(会造假阳性)
                rec["note"] = "empty transcript (historic timeout / external kill; zero-scored by decision)"
                missing.append((harness, task, model, "transcript.txt(empty)"))
            elif os.path.exists(tp):
                text = read_text(tp)
                rec["tool_calls"] = count_tool_calls(harness, text)
                if harness == "Mingbird":
                    rec["turns"] = len(RE_CTX.findall(text))
                    rec["spin_events"] = count_any(text, MB_SPIN)
                    rec["fmt_arg_errors"] = count_any(text, MB_ARGERR)
                    rec["ctx_events"] = count_any(text, MB_CTX)
                    rec["finish_rejections"] = count_any(text, MB_FINFIN)
                elif harness == "agent-mini":
                    rec["fmt_arg_errors"] = count_any(text, AM_ERR)
                elif harness == "goose":
                    rec["fmt_arg_errors"] = count_any(text, GOOSE_ERR)
                elif harness == "opencode":
                    rec["fmt_arg_errors"] = count_any(text, OC_ERR)
                if harness in ("Mingbird", "agent-mini", "goose", "opencode"):
                    rec["provider_errors"] = count_any(text, PROVIDER_ERR)
            else:
                missing.append((harness, task, model, "transcript.txt"))
        else:
            missing.append((harness, task, model, "attempt_dir"))

        # ---------------- 形态判定 ----------------
        try:
            score = float(rec["score"])
        except Exception:
            score = None
        try:
            wall = float(rec["wall_seconds"]) if rec["wall_seconds"] not in ("", None) else None
        except Exception:
            wall = None
        budget = BUDGET_LH if rec["tier"] == "LH" else BUDGET_WF
        fm = (rec["failure_mode"] or "").lower()
        exit_nonzero = str(rec["exit_code"]) not in ("0", "", "None")

        forms = {}
        forms["platform_exit"] = int(fm in ("crash", "error") or exit_nonzero)
        forms["budget_exhausted"] = int(fm == "timeout" or (wall is not None and wall >= budget))
        tc = rec["tool_calls"]
        forms["never_engaged"] = int(tc == 0) if tc != "" else ""
        if rec["spin_events"] != "":
            forms["spin"] = int(rec["spin_events"] >= 1)
            forms["format_breakdown"] = int(rec["fmt_arg_errors"] >= 1)
            forms["context_pressure"] = int(rec["ctx_events"] >= 1)
            forms["false_finish"] = int(rec["finish_rejections"] >= 1)
        else:
            # 其余臂:本臂错误标记过宽(goose 会把 PowerShell 报错回显算进去),与鸣鸟的
            # "工具参数/解析错误"不同尺度 → 汇总表标 n/a,原始计数只留在逐格 CSV 备查。
            forms["spin"] = ""
            forms["format_breakdown"] = ""
            forms["context_pressure"] = ""
            forms["false_finish"] = ""
        forms["early_stop"] = int(
            score is not None and score < 0.5
            and not forms["platform_exit"] and not forms["budget_exhausted"])
        forms["provider_error"] = int(str(rec["provider_errors"]) not in ("", "0"))
        ok, tt = rec["artifact_checks_ok"], rec["artifact_checks_total"]
        forms["incomplete_delivery"] = int(ok != "" and tt != "" and int(ok) < int(tt))
        rec.update(forms)
        per_cell.append(rec)

    # ---------------- 逐格 CSV ----------------
    cols = ["harness", "task", "model", "tier", "score", "wall_seconds", "failure_mode",
            "exit_code", "tool_calls", "turns", "artifact_checks_ok", "artifact_checks_total",
            "platform_exit", "budget_exhausted", "provider_error", "never_engaged", "spin",
            "format_breakdown", "context_pressure", "false_finish", "early_stop",
            "incomplete_delivery",
            "fmt_arg_errors", "spin_events", "ctx_events", "finish_rejections", "attempt_dir", "note"]
    with open(os.path.join(OUT, "failure_forms_2609.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for rec in per_cell:
            w.writerow({k: rec.get(k, "") for k in cols})

    # ---------------- 汇总 ----------------
    FORMS = ["platform_exit", "budget_exhausted", "provider_error", "never_engaged",
             "spin", "format_breakdown", "context_pressure", "false_finish",
             "early_stop", "incomplete_delivery"]
    arms = ["Mingbird", "goose", "opencode", "agent-mini"]
    summary = []
    for arm in arms:
        cells = [c for c in per_cell if c["harness"] == arm]
        n = len(cells)
        row = {"harness": arm, "cells": n}
        for fm_ in FORMS:
            vals = [c[fm_] for c in cells if c[fm_] != ""]
            row[fm_] = f"{sum(vals)}/{len(vals)}" if vals else "n/a"
        tcs = [c["tool_calls"] for c in cells if c["tool_calls"] != ""]
        row["tool_calls_median"] = statistics.median(tcs) if tcs else "n/a"
        walls = [float(c["wall_seconds"]) for c in cells if c["wall_seconds"] not in ("", None)]
        row["wall_median_s"] = round(statistics.median(walls), 1) if walls else "n/a"
        sc = [float(c["score"]) for c in cells if c["score"] not in ("", None)]
        row["score_mean"] = round(sum(sc) / len(sc), 4) if sc else "n/a"
        summary.append(row)
    with open(os.path.join(OUT, "failure_forms_summary_2609.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)

    # ---------------- markdown ----------------
    lines = ["# M10 失败形态 × 发生率 × arm(288 格编码表)", "",
             "判据见 `code_failure_forms.py` 头部;分子/分母 = 命中格数/有判据的格数。",
             "`n/a` = 该臂不存在此判据(如非鸣鸟臂无 finish 门禁与上下文事件计数器)。", "",
             "| 形态 | " + " | ".join(arms) + " |",
             "|---|" + "---|" * len(arms)]
    label = {"platform_exit": "平台退出(崩溃/错误退出)", "budget_exhausted": "预算耗尽",
             "never_engaged": "零工具接触", "spin": "空转/循环拦截",
             "format_breakdown": "格式/参数崩解", "context_pressure": "上下文压力事件",
             "false_finish": "假完成被拒", "early_stop": "提前收工(score<0.5 且非崩溃/超时)",
             "provider_error": "提供方断线(基础设施层)",
             "incomplete_delivery": "交付不完整(有产物检查未过)"}
    for fm_ in FORMS:
        lines.append(f"| {label[fm_]} | " + " | ".join(str(next(s for s in summary if s['harness'] == a)[fm_]) for a in arms) + " |")
    lines.append(f"| 格数 | " + " | ".join(str(next(s for s in summary if s['harness'] == a)['cells']) for a in arms) + " |")
    lines.append(f"| 均分 | " + " | ".join(str(next(s for s in summary if s['harness'] == a)['score_mean']) for a in arms) + " |")
    lines.append(f"| 工具调用中位 | " + " | ".join(str(next(s for s in summary if s['harness'] == a)['tool_calls_median']) for a in arms) + " |")
    lines.append(f"| 墙钟中位(s) | " + " | ".join(str(next(s for s in summary if s['harness'] == a)['wall_median_s']) for a in arms) + " |")
    lines += ["", "## 鸣鸟臂分模型", "",
              "| model | cells | 均分 | 均墙钟(s) | 零工具接触 | 空转 | 格式崩解 | 上下文压力 | 假完成被拒 | 提前收工 |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for m in sorted({c["model"] for c in per_cell if c["harness"] == "Mingbird"}):
        cs = [c for c in per_cell if c["harness"] == "Mingbird" and c["model"] == m]
        cells_at = sum(1 for c in cs if c["tier"] == "LH") + sum(1 for c in cs if c["tier"] == "WF")
        mean = round(sum(float(c["score"]) for c in cs) / len(cs), 4)
        wm = round(statistics.median([float(c["wall_seconds"]) for c in cs if c["wall_seconds"] not in ("", None)]), 1)
        def rate(k):
            vals = [c[k] for c in cs if c[k] != ""]
            return f"{sum(vals)}/{len(vals)}" if vals else "n/a"
        lines.append(f"| {m} | {cells_at} | {mean} | {wm} | " +
                     " | ".join(rate(k) for k in ["never_engaged", "spin", "format_breakdown",
                                                  "context_pressure", "false_finish", "early_stop"]) + " |")
    if missing:
        lines += ["", f"## 缺件({len(missing)} 项)", ""]
        for m in missing[:40]:
            lines.append(f"- {m[0]} / {m[1]} / {m[2]}: 缺 {m[3]}")
    open(os.path.join(OUT, "failure_forms_2609.md"), "w", encoding="utf-8").write("\n".join(lines))

    print("\n".join(lines[:14]))
    print(f"\n[written] failure_forms_2609.csv / _summary_2609.csv / .md  ({len(per_cell)} cells; missing={len(missing)})")


if __name__ == "__main__":
    main()
