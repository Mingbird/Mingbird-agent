#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aggregate the 2026-08-29 64-cell batch into the canonical results table.

Handles retry attempts (m0/m1/...): a cell's authoritative result is its
LATEST attempt; earlier attempts are shown as superseded. Writes
eval_results/BATCH64_SUMMARY.md. Deterministic; run any time after the batch.

Usage: python analyze_batch64.py [--out BATCH64_SUMMARY.md]
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent.parent / "eval_results"
TASKS = ("WF-01", "WF-03", "WF-09", "WF-15")
MODELS = ["ornith-1.5:35b", "gemma4:12b", "qwen3.5:4b", "gemma4:e2b"]
AGENTS = ["hummingbird", "opencode", "agent-mini", "goose"]
# Canonical 64-cell batch (launched 08-29 09:17, ran past midnight): non-goose
# cells are all stamped 0829; goose finished on 0830. Pinned per agent+date so a
# later same-day hummingbird "after" rerun can never leak into this summary.
CANONICAL = ["*_WF01_*_0829_*", "*_WF03_*_0829_*", "*_WF09_*_0829_*", "*_WF15_*_0829_*",
             "goose_WF01_*_0830_*", "goose_WF03_*_0830_*", "goose_WF09_*_0830_*", "goose_WF15_*_0830_*"]


def latest_attempt_dirs(patterns=None):
    runs = []
    for pat in (patterns or CANONICAL):
        runs.extend(EVAL.glob(pat))
    cells = defaultdict(list)
    for d in sorted(set(runs)):
        m = re.match(r"^(.+)_m(\d+)_(\d{4}_\d{6})$", d.name)
        key = m.group(1) if m else d.name
        cells[key].append(d)
    out = {}
    for key, dirs in cells.items():
        out[key] = max(dirs, key=lambda d: d.name)   # latest attempt wins
    return out, cells


def slug(model):
    return model.replace("-", "").replace(":", "_")


def load_scores(patterns=None):
    latest, attempts = latest_attempt_dirs(patterns)
    slug2model = {slug(m): m for m in MODELS}
    rows = {}
    for key, d in latest.items():
        m = re.match(r"^(?P<agent>.+)_(?P<task>[A-Z]{2}\d{2})_(?P<model>.+)$", key)
        if not m or m["model"] not in slug2model:
            continue
        agent = "agent-mini" if m["agent"] == "agentmini" else m["agent"]
        if agent not in AGENTS:
            continue
        task = f"{m['task'][:2]}-{m['task'][2:]}"
        model = slug2model[m["model"]]
        sj = d / "score.json"
        if not sj.exists():
            rows[(agent, task, model)] = {
                "total": None, "wall": None, "fm": "incomplete",
                "run_id": d.name, "attempts": len(attempts[key]), "note": "no score.json"}
            continue
        s = json.load(open(sj, encoding="utf-8"))
        rows[(agent, task, model)] = {
            "total": s.get("total"), "wall": round(s.get("wall_seconds") or 0),
            "fm": s.get("failure_mode", "completed"), "run_id": d.name,
            "attempts": len(attempts[key]), "note": ""}
    return rows


def fmt(v):
    if v["total"] is None:
        return f"TMO({v['wall']}s)" if v["fm"] == "timeout" else v["fm"]
    return f"{v['total']:.2f}({v['wall']}s)"


def main():
    def opt(flag, default=None):
        return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default
    patterns = opt("--patterns")
    patterns = patterns.split(",") if patterns else None
    agents = opt("--agents")
    agents = agents.split(",") if agents else AGENTS
    tasks_arg = opt("--tasks")
    tasks = tasks_arg.split(",") if tasks_arg else TASKS
    rows = load_scores(patterns)
    out = opt("--out", "BATCH64_SUMMARY.md")
    title = opt("--title", "LRAB 64-cell batch summary (2026-08-29/30, tasks WF-01/03/09/15 x 4 agents x 4 models)")
    lines = [f"# {title}",
             "", "Latest attempt per cell; score = deterministic total (timeout counts 0).", "",
             "| cell | " + " | ".join(MODELS) + " |",
             "|---|" + "---|" * len(MODELS)]
    agent_scores = defaultdict(list)
    model_scores = defaultdict(lambda: defaultdict(list))
    retry_cells = []
    for a in agents:
        for t in tasks:
            cells = [rows.get((a, t, m)) for m in MODELS]
            line = [f"| {a} {t}"]
            for i, m in enumerate(MODELS):
                v = cells[i]
                if v is None:
                    line.append(" | —")
                    continue
                line.append(f" | {fmt(v)}")
                if v["total"] is not None:
                    agent_scores[a].append(v["total"])
                    model_scores[a][m].append(v["total"])
                if v.get("attempts", 1) > 1:
                    retry_cells.append((a, t, m, v))
            lines.append("".join(line) + " |")
    lines += ["", "## Means (scored cells; missing model cells excluded from that mean)",
              "", "| agent | " + " | ".join(MODELS) + " | overall |",
              "|---|" + "---|" * (len(MODELS) + 1) + ""]
    for a in AGENTS:
        if not agent_scores[a]:
            continue
        cells = [f"{sum(model_scores[a][m])/len(model_scores[a][m]):.3f} (n={len(model_scores[a][m])})"
                 if model_scores[a][m] else "—" for m in MODELS]
        overall = sum(agent_scores[a]) / len(agent_scores[a])
        lines.append(f"| **{a}** | " + " | ".join(cells) + f" | **{overall:.3f}** |")
    if retry_cells:
        lines += ["", "## Retried cells (attempt-1 result superseded by latest attempt)", ""]
        for a, t, m, v in retry_cells:
            lines.append(f"- {a} {t} {m}: {v['attempts']} attempts -> {fmt(v)} ({v['run_id']})")
    missing = [(a, t, m) for a in agents for t in tasks for m in MODELS
               if (a, t, m) not in rows or rows[(a, t, m)]["fm"] == "incomplete"]
    if missing:
        lines += ["", f"## Incomplete cells ({len(missing)})"]
        for a, t, m in missing:
            lines.append(f"- {a} {t} {m}")
    text = "\n".join(lines) + "\n"
    (EVAL / out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
