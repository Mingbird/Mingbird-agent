#!/usr/bin/env python3
"""Analyze the the comparison study size-ladder matrix (results/b_matrix).

Reads one score.json per cell. A cell that timed out or produced no artifact
scores 0.0 by the artifact-completion rule; its failure mode is kept so the
analysis can report censoring separately.

Outputs
  experiments/analysis/comparison_matrix.csv    tidy per-cell rows
  experiments/analysis/comparison_summary.json  means, spans, gaps, tests
Run with -I.
"""
from __future__ import annotations

import json
import zlib
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon

# The scripts run with -I, which drops the script's own directory from
# sys.path; put it back so the shared cell filters can be imported.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from comparison_filters import died_on_connection  # noqa: E402

# Set COMPARISON_ROOT to point at a tree holding experiments/results/; the default
# is the layout this script was developed in, two directories above its own.
ROOT = Path(os.environ.get("COMPARISON_ROOT") or Path(__file__).resolve().parents[2])
RESULTS = ROOT / "experiments" / "results" / "b_matrix"
LOGS = ROOT / "experiments" / "logs"
OUT = ROOT / "experiments" / "analysis"
SEED = 42
BOOT = 10_000
N_TASKS = len(list((ROOT / "experiments" / "tasks_heldout").glob("*/*.json")))

# The four ladder rungs, in order. The 35.5B anchor is deliberately absent:
# it runs two arms on six tasks, so it is not a rung, and putting it here gave
# it a span, a paired gap, and a seat in the confirmatory family, which
# silently took the family from seven tests to eight and blanked Holm.
# ceiling_block() reads the anchor straight from the cells instead.
MODEL_ORDER = [
    "qwen3.5:0.8b",
    "openbmb/minicpm5:latest",
    "qwen3.5:2b",
    "granite4.2:3b",
    "qwen3.5:4b",
    "ingloryon/k2-horizon:7b",
]
HARNESS_ORDER = ["mingbird", "pi", "opencode", "goose", "mini"]


def slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", model.replace(":", "-").replace("/", "-"))


def server_error_windows() -> list[float]:
    """Timestamps of 5xx responses from the inference server, as epoch seconds.

    Diagnostic only. Five arms share one server and the log carries no client
    identity, so a 5xx inside a cell's window cannot be attributed to that
    cell: the concurrent arms produce overlapping windows, and a request that
    times out is stamped at its *end*, hours after it began. The preregistered
    rule keys on the cell's own transcript instead; this list is written to the
    context diagnostic so a burst is still visible to the reader.
    """
    log = ROOT / "experiments" / "logs" / "ollama_b_guard.log"
    if not log.exists():
        return []
    import datetime as _dt
    pat = re.compile(r"\[GIN\] (\d{4}/\d{2}/\d{2}) - (\d{2}:\d{2}:\d{2}) \| 5\d\d \|")
    out = []
    with log.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = pat.search(line)
            if not m:
                continue
            try:
                dt = _dt.datetime.strptime(m.group(1) + " " + m.group(2),
                                           "%Y/%m/%d %H:%M:%S")
            except ValueError:
                continue
            out.append(dt.timestamp())
    return out


def ps_context(run_id: str, model: str):
    """Context length the daemon reported for this cell's runner, if recorded.

    The cell log carries a PS snapshot taken at the end of the run. Cells from
    the 0.75B rung predate that capture and return None. A value other than
    32768 means the arm ran off-protocol and the cell is re-run rather than
    reported.
    """
    log = LOGS / f"{run_id}.log"
    if not log.exists():
        return None
    try:
        s = log.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    i = s.find("PS: ")
    if i < 0:
        return None
    lines = s[i + 4:].splitlines()
    if not lines:
        return None
    try:
        d = json.loads(lines[0])
    except (json.JSONDecodeError, ValueError):
        return None
    for m in d.get("models", []):
        if model in (m.get("name"), m.get("model")):
            return m.get("context_length")
    return None


def load() -> list[dict]:
    rows = []
    if not RESULTS.exists():
        return rows
    server_errors = server_error_windows()
    for d in sorted(RESULTS.iterdir()):
        if d.name.startswith("_"):
            continue  # archived / superseded cells kept for provenance
        p = d / "score.json"
        if not p.exists() or p.stat().st_size == 0:
            continue
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        total = j.get("total")
        # The preregistered rule: a cell whose OWN transcript records a 5xx
        # lost turns to the server and is excluded from the primary means and
        # re-run. The server log is not used for attribution: five arms share
        # one server, the log has no client identity, and a 5xx is stamped at
        # the end of the request that caused it.
        server_error = False
        tr = d / "transcript.txt"
        if tr.exists():
            try:
                txt = tr.read_text(encoding="utf-8", errors="ignore")
                server_error = ("HTTP Error 500" in txt
                                or "Internal Server Error" in txt)
            except OSError:
                pass
        # A server that is not listening at all is the same class of event as a
        # 5xx, and the same rule applies. A cell that had already produced its
        # artifacts when the server went down keeps its score: the outage cost
        # it nothing. A cell that ends at zero on an unreachable server is
        # excluded and re-run.
        conn_fail = died_on_connection(tr)
        infra = server_error or (conn_fail and float(total or 0) == 0.0)
        log_5xx_in_window = False
        if server_errors:
            end = p.stat().st_mtime
            start = end - float(j.get("wall_seconds") or 0)
            log_5xx_in_window = any(start <= t <= end for t in server_errors)
        rows.append({
            "run_id": d.name,
            "model": j.get("model", ""),
            "harness": j.get("agent", ""),
            "task": j.get("task_id", ""),
            "score": float(total) if total is not None else 0.0,
            "scored": total is not None,
            "failure_mode": j.get("failure_mode") or "ok",
            "server_error": infra,
            "infra_reason": ("5xx" if server_error else
                             "connection" if (conn_fail and float(total or 0) == 0.0)
                             else None),
            "conn_fail_unpenalised": bool(conn_fail and float(total or 0) > 0.0),
            "log_5xx_in_window": log_5xx_in_window,
            "wall_seconds": j.get("wall_seconds"),
            "ps_context": ps_context(d.name, j.get("model", "")),
        })
    return rows


def boot_ci(x: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    n = len(x)
    if n == 0:
        return (float("nan"), float("nan"))
    means = np.array([x[rng.integers(0, n, n)].mean() for _ in range(BOOT)])
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
    """P(a>b) - P(a<b) over all pairs."""
    if len(a) == 0 or len(b) == 0:
        return float("nan")
    diff = a[:, None] - b[None, :]
    return float((diff > 0).mean() - (diff < 0).mean())


def holm(pvals: dict[str, float]) -> dict[str, float]:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    out, prev = {}, 0.0
    for i, (k, p) in enumerate(items):
        adj = max(prev, min(1.0, (m - i) * p))
        out[k] = adj
        prev = adj
    return out


def mde(sd: float, n: int, power: float = 0.8, alpha: float = 0.05) -> float:
    """Approximate two-sided paired MDE: (z_{1-a/2}+z_power) * sd / sqrt(n)."""
    from scipy.stats import norm
    return float((norm.ppf(1 - alpha / 2) + norm.ppf(power)) * sd / np.sqrt(n))


SIZES = {
    "qwen3.5:0.8b": 0.75,
    "openbmb/minicpm5:latest": 1.1,
    "qwen3.5:2b": 1.9,
    "granite4.2:3b": 3.7,
    "qwen3.5:4b": 4.7,
    "ingloryon/k2-horizon:7b": 9.0,
    "ornith-1.5:35b": 35.5,
}
COVERED_HARNESSES = ["mingbird", "pi", "opencode", "goose", "mini"]
COMPARATOR = "goose"
# Five per-rung contrasts plus H1, H2 and H3; the dropped 9.0B rung takes one
# contrast away, so the assembled family is seven.
FAMILY_SIZE = 7


def _rungs(by: dict) -> list[str]:
    models = {m for (m, _h) in by}
    return sorted([m for m in models if m in SIZES], key=lambda m: SIZES[m])


def _rung_complete(by: dict, model: str) -> bool:
    """A rung enters a trend estimate only when every arm has its task set.

    One missing task per arm is tolerated for the documented exclusion and for
    a queued re-run. A rung with a handful of cells (mid-collection) used to
    enter the H1 slope with a meaningless span and is now rejected.
    """
    for h in COVERED_HARNESSES:
        v = by.get((model, h))
        if not v or len(v) < N_TASKS - 1:
            return False
    return True


FAMILY = ["qwen3.5:0.8b", "qwen3.5:2b", "qwen3.5:4b"]


def span_slope_boot(by: dict, rng, boot: int = 2000,
                    subset: list[str] | None = None,
                    harnesses: list[str] | None = None) -> dict | None:
    """H1: slope of the harness span on log10(size), task-bootstrap CI and p.

    ``subset`` restricts the rungs (used for the within-family sensitivity).
    ``harnesses`` restricts the arms whose spread defines the span (used for
    the slope without the reply-contract arm).
    """
    models = [m for m in _rungs(by)
              if _rung_complete(by, m) and (subset is None or m in subset)]
    if len(models) < 3:
        return None
    arms = harnesses if harnesses is not None else COVERED_HARNESSES
    tasks = sorted({t for k in by for t in by[k]})
    if not tasks:
        return None

    def slope_for(task_sample):
        xs, ys = [], []
        for m in models:
            per_h = []
            for h in arms:
                v = by.get((m, h))
                if not v:
                    continue
                vals = [v[t] for t in task_sample if t in v]
                if vals:
                    per_h.append(float(np.mean(vals)))
            if len(per_h) >= 2:
                xs.append(np.log10(SIZES[m]))
                ys.append(max(per_h) - min(per_h))
        if len(xs) < 3:
            return None
        X = np.column_stack([np.ones(len(xs)), xs])
        beta, *_ = np.linalg.lstsq(X, np.array(ys), rcond=None)
        return float(beta[1])

    obs = slope_for(tasks)
    if obs is None:
        return None
    draws = []
    for _ in range(boot):
        sample = list(rng.choice(tasks, size=len(tasks), replace=True))
        s = slope_for(sample)
        if s is not None:
            draws.append(s)
    draws = np.array(draws)
    p = float(2 * min((draws >= 0).mean(), (draws <= 0).mean()))
    return {"slope": obs, "ci": [float(np.percentile(draws, 2.5)),
                                 float(np.percentile(draws, 97.5))],
            "p": p, "boot": int(len(draws)), "rungs": len(models)}


def gap_slope_boot(by: dict, rng, subset=None, boot: int = 2000) -> dict | None:
    """Sensitivity for H2: linear slope of the gap on log10(size) inside one
    family.

    The quadratic in H2 pools the Qwen rungs with the Granite and K2 anchors.
    A slope over one family answers the narrower question without the
    cross-family term: within Qwen3.5 the tokenizer, training recipe, and
    quantization scheme are shared.
    """
    models = [m for m in _rungs(by)
              if _rung_complete(by, m) and (subset is None or m in subset)]
    pairs = [(m, by.get((m, "mingbird")), by.get((m, COMPARATOR))) for m in models]
    pairs = [(m, a, b) for m, a, b in pairs if a and b]
    if len(pairs) < 3:
        return None
    tasks = sorted({t for _m, a, _b in pairs for t in a if t in _b})

    def fit(sample):
        xs, ys = [], []
        for m, a, b in pairs:
            common = [t for t in sample if t in a and t in b]
            if not common:
                continue
            xs.append(np.log10(SIZES[m]))
            ys.append(float(np.mean([a[t] - b[t] for t in common])))
        X = np.column_stack([np.ones(len(xs)), np.array(xs)])
        beta, *_ = np.linalg.lstsq(X, np.array(ys), rcond=None)
        return beta

    obs = fit(tasks)
    draws = np.array([fit(list(rng.choice(tasks, size=len(tasks), replace=True)))
                      for _ in range(boot)])
    slopes = draws[:, 1]
    lo, hi = np.percentile(slopes, [2.5, 97.5])
    p = float(2 * min((slopes >= 0).mean(), (slopes <= 0).mean()))
    return {"slope": float(obs[1]), "ci": [float(lo), float(hi)],
            "p": float(min(1.0, p)), "rungs": [m for m, _a, _b in pairs]}


def gap_shape_boot(by: dict, rng, boot: int = 2000) -> dict | None:
    """H2: shape of the Mingbird-vs-goose gap against log10(size)."""
    models = [m for m in _rungs(by) if _rung_complete(by, m)]
    pairs = [(m, by.get((m, "mingbird")), by.get((m, COMPARATOR))) for m in models]
    pairs = [(m, a, b) for m, a, b in pairs if a and b]
    if len(pairs) < 3:
        return None
    tasks = sorted({t for _m, a, _b in pairs for t in a if t in _b})

    def fit(task_sample, degree=2):
        xs, ys = [], []
        for m, a, b in pairs:
            common = [t for t in task_sample if t in a and t in b]
            if not common:
                continue
            xs.append(np.log10(SIZES[m]))
            ys.append(float(np.mean([a[t] - b[t] for t in common])))
        if len(xs) < degree + 2:
            return None
        X = np.column_stack([np.ones(len(xs))] + [np.array(xs) ** k for k in range(1, degree + 1)])
        beta, *_ = np.linalg.lstsq(X, np.array(ys), rcond=None)
        return beta

    obs = fit(tasks)
    if obs is None:
        return None
    draws = []
    for _ in range(boot):
        sample = list(rng.choice(tasks, size=len(tasks), replace=True))
        b = fit(sample)
        if b is not None:
            draws.append(b)
    draws = np.array(draws)
    # flatness test: is either coefficient non-zero?
    lin = draws[:, 1]
    quad = draws[:, 2]
    p_lin = float(2 * min((lin >= 0).mean(), (lin <= 0).mean()))
    p_quad = float(2 * min((quad >= 0).mean(), (quad <= 0).mean()))
    p = float(min(1.0, min(p_lin, p_quad) * 2))  # crude union bound
    # H2 as pre-registered: report the vertex and its bootstrap interval when
    # the quadratic term is negative and the vertex lies inside the observed
    # range, and the monotone slope otherwise. Without this the analysis would
    # answer a different question than the one registered.
    xs_all = [np.log10(SIZES[m]) for m, _a, _b in pairs]
    lo_x, hi_x = min(xs_all), max(xs_all)
    vertex = None
    if obs[2] < 0:
        xv = float(-obs[1] / (2 * obs[2]))
        if lo_x <= xv <= hi_x:
            inside = [float(-d[1] / (2 * d[2])) for d in draws if d[2] < 0]
            inside = [v for v in inside if lo_x <= v <= hi_x]
            vertex = {
                "log10_size": xv,
                "size_b": float(10 ** xv),
                "ci_log10": [float(np.percentile(inside, 2.5)),
                             float(np.percentile(inside, 97.5))]
                if len(inside) >= 100 else None,
                "share_inside": (len(inside) / len(draws)) if len(draws) else None,
            }
    return {"coef": [float(obs[0]), float(obs[1]), float(obs[2])], "vertex": vertex,
            "p": p, "p_linear": p_lin, "p_quadratic": p_quad,
            "ci_linear": [float(np.percentile(lin, 2.5)), float(np.percentile(lin, 97.5))],
            "ci_quadratic": [float(np.percentile(quad, 2.5)), float(np.percentile(quad, 97.5))],
            "boot": int(len(draws)), "rungs": len(pairs)}


CEILING_MODEL = "ornith-1.5:35b"


def ceiling_reduced_tasks(n: int = 6) -> list[str]:
    """The pre-registered ceiling set: the n tasks with the fewest final
    artifacts, ties broken by task id. Deterministic from the released suite,
    so the analysis can check the ceiling ran on the set the design names.
    """
    base = ROOT / "experiments" / "tasks_heldout"
    rows = []
    for p in sorted(base.glob("*/*.json")):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows.append((len(j.get("final_artifacts") or []), p.stem))
    rows.sort()
    return [t for _k, t in rows[:n]]


def ceiling_block(by: dict) -> dict | None:
    """Descriptive 35.5B anchor: Mingbird vs goose on the reduced set.

    Not part of the confirmatory family: six tasks and two arms do not carry
    the power of a full rung. Reported with a task-bootstrap interval so the
    study can bound the effect without overclaiming.
    """
    a = by.get((CEILING_MODEL, "mingbird"))
    b = by.get((CEILING_MODEL, COMPARATOR))
    if not a or not b:
        return None
    common = sorted(set(a) & set(b))
    if not common:
        return None
    d = np.array([a[t] - b[t] for t in common])
    rng = np.random.default_rng(
        [SEED, zlib.crc32(f"ceiling|{COMPARATOR}".encode())])
    lo, hi = boot_ci(d, rng)
    design = ceiling_reduced_tasks()
    return {
        "model": CEILING_MODEL,
        "size_b": SIZES.get(CEILING_MODEL),
        "comparator": COMPARATOR,
        "n_tasks": len(common),
        "tasks": common,
        "design_tasks": design,
        "matches_design": sorted(common) == design,
        "mean_mingbird": float(np.mean([a[t] for t in common])),
        "mean_comparator": float(np.mean([b[t] for t in common])),
        "mean_diff": float(d.mean()),
        "ci": [lo, hi],
        "cliffs_delta": cliffs_delta(np.array([a[t] for t in common]),
                                     np.array([b[t] for t in common])),
        "p_wilcoxon": (float(wilcoxon(d).pvalue)
                       if len(d) >= 5 and np.any(d != 0) else None),
        "family": False,
    }


def interaction_wald(rows: list[dict]) -> dict | None:
    """Task-fixed-effects OLS with a harness x model interaction, cluster-robust
    by task; Wald test that every interaction coefficient is zero.

    Implemented directly with numpy because the environment has no statsmodels.
    """
    models = sorted({r["model"] for r in rows})
    harnesses = sorted({r["harness"] for r in rows})
    tasks = sorted({r["task"] for r in rows})
    if len(models) < 2 or len(harnesses) < 2 or len(tasks) < 3:
        return None

    def dummies(values, ref):
        return [1.0 if v == val else 0.0 for val in values if val != ref]

    cols = []
    names = []
    # task fixed effects (drop first)
    for t in tasks[1:]:
        cols.append([1.0 if r["task"] == t else 0.0 for r in rows])
        names.append(f"task:{t}")
    # harness main effects (drop first)
    for h in harnesses[1:]:
        cols.append([1.0 if r["harness"] == h else 0.0 for r in rows])
        names.append(f"harness:{h}")
    # model main effects (drop first)
    for m in models[1:]:
        cols.append([1.0 if r["model"] == m else 0.0 for r in rows])
        names.append(f"model:{m}")
    # interactions
    inter_idx = []
    for h in harnesses[1:]:
        for m in models[1:]:
            cols.append([1.0 if (r["harness"] == h and r["model"] == m) else 0.0
                         for r in rows])
            inter_idx.append(len(cols) - 1)
            names.append(f"int:{h}|{m}")

    X = np.column_stack([np.ones(len(rows))] + cols)
    y = np.array([r["score"] for r in rows], dtype=float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    # Two-way cluster-robust covariance (Cameron-Gelbach-Miller):
    # V = V_task + V_model - V_task_model. Clustering on the task alone would
    # leave the size coefficient anti-conservative, because size varies at the
    # model level and each model appears in every task.
    XtX_inv = np.linalg.pinv(X.T @ X)

    def meat_for(labels: np.ndarray) -> np.ndarray:
        out = np.zeros((X.shape[1], X.shape[1]))
        for lab in sorted(set(labels.tolist())):
            idx = np.where(labels == lab)[0]
            if len(idx) == 0:
                continue
            s = X[idx].T @ resid[idx]
            out += np.outer(s, s)
        return out

    task_arr = np.array([r["task"] for r in rows])
    model_arr = np.array([r["model"] for r in rows])
    both_arr = np.array([f"{r['task']}|{r['model']}" for r in rows])
    meat = meat_for(task_arr) + meat_for(model_arr) - meat_for(both_arr)
    cov = XtX_inv @ meat @ XtX_inv
    sel = [i + 1 for i in inter_idx]  # +1 for the intercept column
    b = beta[sel]
    V = cov[np.ix_(sel, sel)]
    # The two-way meat (task + model - intersection) is not guaranteed positive
    # semi-definite, and with a handful of clusters it can produce a negative
    # quadratic form. A negative chi-square is not a small p-value; it is a
    # failed variance estimate. Refuse to report it rather than print a number
    # that cannot exist.
    V = (V + V.T) / 2
    evals, evecs = np.linalg.eigh(V)
    if evals.size == 0 or evals.min() < -1e-8 * max(1.0, abs(evals).max()):
        return None
    from scipy.stats import chi2
    df = len(sel)
    stat = float(np.clip(b @ (evecs @ np.diag(evals) @ evecs.T) @ b, 0.0, None))
    return {"wald_chi2": stat, "df": df,
            "p": float(chi2.sf(stat, df)), "n_rows": len(rows),
            "n_clusters": len(tasks),
            "n_params": int(X.shape[1])}


def completed_only(rows: list[dict]) -> dict:
    """Sensitivity: mean score among cells that produced at least one declared
    artifact, so a timeout zero does not dominate the mean."""
    import csv
    p = ROOT / "experiments" / "analysis" / "comparison_failures.csv"
    if not p.exists():
        return {}
    keep = {}
    for r in csv.DictReader(p.open(encoding="utf-8")):
        if r["class"] in ("complete", "partial"):
            keep[r["run_id"]] = True
    out = defaultdict(list)
    for r in rows:
        if keep.get(r["run_id"]):
            out[(r["model"], r["harness"])].append(r["score"])
    return {f"{m}|{h}": {"n": len(v), "mean": float(np.mean(v))}
            for (m, h), v in out.items()}


def uniform_budget(rows: list[dict], cutoffs=(1200, 1800, 2700)) -> dict:
    """Sensitivity: the ladder under one budget instead of five.

    The study gives each rung a budget matched to its throughput (20 minutes at
    0.75B, 45 at 4.7B). A critic can therefore say the size trend is the
    budget schedule rather than the models. This recomputes the per-rung arm
    means, spans, and the H1 slope after zeroing every cell whose wall clock
    exceeds a single common cutoff, applied to all rungs and all arms alike.
    No new runs: this is the counterfactual "if every rung had this budget".

    A cell that is zeroed stays in its arm's mean as a zero, exactly as a cell
    killed at the cutoff would have been scored. Cells with no recorded wall
    time are left at their observed score and counted, so the reader can see
    how much of the sensitivity rests on that assumption.
    """
    out = {}
    for cut in cutoffs:
        by = defaultdict(dict)
        zeroed = defaultdict(int)
        unknown = 0
        for r in rows:
            w = r.get("wall_seconds")
            s = r["score"]
            if w is None:
                unknown += 1
            elif float(w) > cut:
                if s > 0:
                    zeroed[r["model"]] += 1
                s = 0.0
            by[(r["model"], r["harness"])][r["task"]] = s
        rungs = {}
        for m in _rungs(by):
            if not _rung_complete(by, m):
                continue
            means = {h: float(np.mean(list(by[(m, h)].values())))
                     for h in COVERED_HARNESSES if (m, h) in by}
            if len(means) < 2:
                continue
            rest = [v for h, v in means.items() if h != "mini"]
            rungs[m] = {
                "means": means,
                "span": max(means.values()) - min(means.values()),
                "span_excl_mini": (max(rest) - min(rest)) if len(rest) >= 2 else None,
                "cells_zeroed": zeroed.get(m, 0),
            }
        slope = span_slope_boot(by, np.random.default_rng([SEED, 21]),
                                boot=2000)
        out[str(cut)] = {
            "minutes": cut / 60.0,
            "rungs": rungs,
            "span_slope": slope,
            "cells_zeroed_total": int(sum(zeroed.values())),
            "cells_without_wall": unknown,
        }
    return out


VALID_FAILURE = {"ok", "completed", "timeout", "no_artifacts", "early_finish",
                 "stall", "empty_spin", "error",
                 # The runner's crash modes (run_bench.py sets these when the
                 # process exits nonzero, or exits fast with a Unicode error).
                 # A cell in which the agent ran and then crashed is an agent
                 # outcome and is scored as a failure, not excluded as
                 # infrastructure, which is what the threats section states.
                 "crash", "gbk_degraded"}


def main() -> int:
    rows = load()
    if not rows:
        print("no cells yet")
        return 0

    # Only a cell that lost turns to a server 5xx is excluded: the
    # infrastructure failed, not the harness. A harness crash is an outcome and
    # is scored (zero when no score was written); cells that the infrastructure
    # rule flags are re-run, and the re-run replaces the record.
    all_rows = rows
    excluded = [r for r in rows if r.get("server_error")]
    # Always rewrite, empty list included: a file that survives the condition it
    # was written for reads like a current finding. After the three excluded
    # cells were archived on 25 October this file still named them, and
    # queue_excluded_cells.py would have re-queued cells that were already
    # handled.
    p = OUT / "comparison_excluded.json"
    p.write_text(json.dumps(excluded, indent=2), encoding="utf-8")
    if excluded:
        by_reason = defaultdict(int)
        for r in excluded:
            by_reason[r.get("infra_reason") or "?"] += 1
        print(f"excluded {len(excluded)} infrastructure cells "
              f"({dict(by_reason)}) -> {p}")
    # Kept, but worth seeing: a cell that had already earned its score when the
    # server went down. Excluding it would throw away valid work.
    spared = [r for r in rows if r.get("conn_fail_unpenalised")]
    if spared:
        print(f"kept {len(spared)} scored cells that saw a connection failure "
              f"after producing artifacts: "
              f"{[r['run_id'] for r in spared]}")
    # The daemon's `/api/ps` context field is not trustworthy on this build: a
    # 20k-token request is served (so the runner holds at least 32768), while
    # the field reports 98304 for the same instance. The per-cell value is kept
    # as a diagnostic and does not exclude a cell. The context claim rests on
    # the server's `n_ctx` lines and on prompts longer than 8k being served.
    ctx_odd = [r for r in rows
               if r.get("ps_context") is not None and r["ps_context"] != 32768]
    # Always rewrite the diagnostic, empty list included: a file that is only
    # written when the condition fires outlives the condition and then reads
    # like a current finding (2026-10-25: five stale rows named the very run_ids
    # that had since been re-collected cleanly).
    p = OUT / "comparison_context_diagnostic.json"
    p.write_text(json.dumps(ctx_odd, indent=2), encoding="utf-8")
    print(f"cells with a /api/ps context other than 32768: {len(ctx_odd)} "
          f"-> {p}")
    # A mode the set does not know would otherwise disappear from every mean
    # without a trace, leaving a rung with seventeen cells where the study says
    # eighteen. Say it out loud instead.
    unknown = {}
    for r in rows:
        if r["failure_mode"] not in VALID_FAILURE:
            unknown[r["failure_mode"]] = unknown.get(r["failure_mode"], 0) + 1
    if unknown:
        print(f"WARNING: unrecognised failure modes dropped from the analysis: {unknown}")
        print("         add an agent-outcome mode to VALID_FAILURE, or exclude it on purpose")
    rows = [r for r in rows
            if r["failure_mode"] in VALID_FAILURE and not r.get("server_error")]

    by = defaultdict(dict)  # (model, harness) -> task -> score
    meta = {}
    for r in rows:
        by[(r["model"], r["harness"])][r["task"]] = r["score"]
        meta[(r["model"], r["harness"], r["task"])] = r

    with (OUT / "comparison_matrix.csv").open("w", encoding="utf-8", newline="") as f:
        f.write("model,harness,task,score,scored,failure_mode,wall_seconds\n")
        for r in all_rows:
            f.write(f"{r['model']},{r['harness']},{r['task']},{r['score']:.4f},"
                    f"{int(r['scored'])},{r['failure_mode']},{r['wall_seconds']}\n")

    rng = np.random.default_rng(SEED)
    summary: dict = {"cells": len(rows), "excluded_cells": len(excluded),
                     "by_model": {}, "gaps": {}, "tests": {}}

    print(f"{'model':26s} " + " ".join(f"{h:>9s}" for h in HARNESS_ORDER) + "    span")
    # The ceiling anchor is analysed separately: two arms and six tasks make a
    # span over it a max-minus-min of two numbers, which is not a rung.
    for m in [x for x in MODEL_ORDER if any(k[0] == x for k in by)] + \
             sorted({k[0] for k in by} - set(MODEL_ORDER) - {CEILING_MODEL}):
        vals, cells = [], {}
        for h in HARNESS_ORDER:
            v = by.get((m, h))
            if not v:
                continue
            arr = np.array([v[t] for t in sorted(v)])
            lo, hi = boot_ci(arr, rng)
            cells[h] = {"n": len(arr), "mean": float(arr.mean()),
                        "ci": [lo, hi], "tasks": sorted(v)}
            vals.append((h, float(arr.mean())))
        if not vals:
            continue
        span = max(v for _, v in vals) - min(v for _, v in vals)
        # The raw span is bounded by the floor: an arm stuck at 0.03 leaves
        # almost a full scale of headroom. Report the span as a share of the
        # room above the worst arm so a rising span cannot be read as growth
        # when it is only the floor moving.
        floor = min(v for _, v in vals)
        span_headroom = span / (1 - floor) if floor < 1 else None
        # Sensitivity: mini-swe-agent ends most cells on its own reply-format
        # contract rather than on a graded difference in capability, so the raw
        # span leans on that arm's floor. Report the span over the other four
        # as well, so a reader can see how much of the leverage is the contract.
        rest = [v for h, v in vals if h != "mini"]
        span_excl_mini = (max(rest) - min(rest)) if len(rest) >= 2 else None
        summary["by_model"][m] = {"cells": cells, "span": span,
                                  "span_headroom": span_headroom,
                                  "span_excl_mini": span_excl_mini,
                                  "floor": floor,
                                  "best": max(vals, key=lambda kv: kv[1])[0]}
        print(f"{m:26s} " + " ".join(
            f"{cells[h]['mean']:9.3f}" if h in cells else f"{'-':>9s}"
            for h in HARNESS_ORDER) + f"  {span:6.3f}")

    # Descriptive: how far a harness change moves the arm mean, against how far
    # the whole rung moves when the model changes. Both are means over the same
    # tasks; the ratio is an order-of-magnitude reading, not a test.
    ordered = sorted(summary["by_model"], key=lambda m: SIZES.get(m, float("inf")))
    prev_means = None
    summary["lever_ratio"] = {}
    for m in ordered:
        # A rung still collecting has a handful of arms and a span that is an
        # artefact of which cells landed first. It must not enter this series:
        # on 2026-10-25 the open 9.0B rung reported an arm shift of 0.013
        # against a real 0.47 and a ratio of 0.0, which would have been quoted
        # as "harness leverage collapses at 9B".
        if not _rung_complete(by, m):
            continue
        means = {h: c["mean"] for h, c in summary["by_model"][m]["cells"].items()}
        # Matched-unit comparison. The span is a range and the between-rung
        # shift is a mean, so the two are not comparable as they stand: a range
        # over five arms is larger than a mean step by construction. The mean
        # absolute difference over the ten harness pairs is the same kind of
        # quantity as the mean absolute arm change, and that is the pair of
        # numbers the "which lever" question is answered with.
        vals = list(means.values())
        pair_diffs = [abs(a - b) for i, a in enumerate(vals)
                      for b in vals[i + 1:]]
        four = [v for h, v in means.items() if h != "mini"]
        pair_diffs4 = [abs(a - b) for i, a in enumerate(four)
                       for b in four[i + 1:]]
        if prev_means is not None:
            shared = set(means) & set(prev_means)
            shift = float(np.mean([abs(means[h] - prev_means[h]) for h in shared])) \
                if shared else None
            # The model step measured over the four arms that remain when the
            # reply-contract arm is dropped. Both sides of the excl-mini
            # reading have to use the same arm set: mini's mean barely moves
            # between rungs, so leaving it in the denominator deflates the step
            # and inflates the harness lever at every rung.
            shared4 = [h for h in shared if h != "mini"] if shared else []
            shift4 = float(np.mean([abs(means[h] - prev_means[h]) for h in shared4])) \
                if shared4 else None
            span = summary["by_model"][m]["span"]
            no_mini = summary["by_model"][m].get("span_excl_mini")
            summary["lever_ratio"][m] = {
                "span": span,
                "arm_shift_from_prev": shift,
                "arm_shift_from_prev_excl_mini": shift4,
                "ratio": (span / shift) if shift else None,
                # Matched-unit version of the same comparison (see above).
                "mean_pairwise_harness_diff": float(np.mean(pair_diffs)),
                "ratio_pairwise": (float(np.mean(pair_diffs)) / shift) if shift else None,
                "mean_pairwise_excl_mini": float(np.mean(pair_diffs4)),
                "ratio_pairwise_excl_mini": (float(np.mean(pair_diffs4)) / shift4) if shift4 else None,
                # Same reading with the reply-contract arm removed: if the two
                # disagree the leverage in that rung is the contract, not the
                # spread among harnesses that can run the tasks.
                "ratio_excl_mini": (no_mini / shift4) if (shift4 and no_mini) else None,
            }
        prev_means = means

    # Paired gaps: Mingbird vs each baseline, task-paired.
    raw_p = {}
    for m in summary["by_model"]:
        mb = by.get((m, "mingbird"))
        if not mb:
            continue
        for h in HARNESS_ORDER:
            if h == "mingbird" or (m, h) not in by:
                continue
            base = by[(m, h)]
            common = sorted(set(mb) & set(base))
            if len(common) < 3:
                continue
            d = np.array([mb[t] - base[t] for t in common])
            key = f"{m}|{h}"
            # Seed each comparison from its own key, so a CI does not move
            # when other cells are added to the matrix.
            grng = np.random.default_rng([SEED, zlib.crc32(key.encode())])
            lo, hi = boot_ci(d, grng)
            try:
                p = float(wilcoxon(d).pvalue) if np.any(d != 0) else 1.0
            except ValueError:
                p = 1.0
            # The design section promises the paired sign proportion next to the
            # bootstrap interval and the signed-rank test; without this the
            # methods name a statistic the results never report.
            sign = {"positive": int((d > 0).sum()), "negative": int((d < 0).sum()),
                    "zero": int((d == 0).sum()), "n": len(d)}
            sign["prop_positive"] = sign["positive"] / len(d)
            # Saturation-robust companion to the raw gap: the same difference
            # as a share of the room left above the comparator on the tasks it
            # is computed over. At the top of the ladder both arms reach 1.000
            # on most tasks, so the raw gap is compressed by the scorer's
            # ceiling while the share of the remaining room is not.
            base_common = float(np.mean([base[t] for t in common]))
            room = 1.0 - base_common
            summary["gaps"][key] = {
                "mean_diff": float(d.mean()), "ci": [lo, hi], "n": len(d),
                "headroom_normalized": (float(d.mean()) / room
                                        if room > 1e-9 else None),
                "cliffs_delta": cliffs_delta(np.array([mb[t] for t in common]),
                                             np.array([base[t] for t in common])),
                "p_wilcoxon": p, "mde": mde(float(d.std(ddof=1)), len(d)),
                "sign": sign,
            }
            raw_p[key] = p

    summary["tests"]["holm_gap_family"] = holm(raw_p)
    # Diagnostic only. Not reported in the study: with five model clusters the
    # two-way cluster-robust covariance is not reliably positive semi-definite,
    # and the statistic moves by orders of magnitude under small data changes
    # (chi2 1050 -> 5.5 when only the 0.75B mini cells were added). The field is
    # kept for auditability but carries a status so it cannot be read as a test.
    it = interaction_wald(rows)
    if it:
        it["status"] = ("diagnostic only, not reported: five model clusters make "
                        "the two-way cluster-robust covariance unreliable")
    summary["tests"]["interaction"] = it

    # Trend estimators for H1 and H2 (H3 is added by the gradient analysis).
    trends = {"span_slope": span_slope_boot(by, np.random.default_rng([SEED, 11])),
              "span_slope_family": span_slope_boot(
                  by, np.random.default_rng([SEED, 12]), subset=FAMILY),
              "gap_shape": gap_shape_boot(by, np.random.default_rng([SEED, 13])),
              "gap_slope_family": gap_slope_boot(
                  by, np.random.default_rng([SEED, 14]), subset=FAMILY),
              # The 9.0B rung runs at 57% VRAM and about a seventh of the 4.7B
              # throughput, so its doubled budget still buys roughly a quarter
              # of the token capacity. H1 over the fully-resident rungs shows
              # whether the trend survives without that speed confound.
              "span_slope_resident": span_slope_boot(
                  by, np.random.default_rng([SEED, 15]),
                  subset=[m for m in MODEL_ORDER if m not in ("ingloryon/k2-horizon:7b",
                                                              "ornith-1.5:35b")]),
              # Same slope with the reply-contract arm removed. mini-swe-agent
              # ends most of its small-model cells on its own RepeatedFormatError
              # rather than on a graded capability gap, so a trend carried by
              # that floor should be seen as a contract effect. Reported as a
              # labelled sensitivity beside the raw slope.
              "span_slope_excl_mini": span_slope_boot(
                  by, np.random.default_rng([SEED, 16]),
                  harnesses=["mingbird", "pi", "opencode", "goose"])}
    summary["trends"] = trends

    # Confirmatory family: the per-rung Mingbird-vs-goose contrasts plus the
    # trend tests. The ceiling is analysed separately and is not in the family.
    family = {k: v["p_wilcoxon"] for k, v in summary["gaps"].items()
              if k.endswith(f"|{COMPARATOR}")}
    if trends["span_slope"]:
        family["H1_span_slope"] = trends["span_slope"]["p"]
    if trends["gap_shape"]:
        family["H2_gap_shape"] = trends["gap_shape"]["p"]
    # H3 comes from the mechanism gradient, which runs after the matrix. When
    # its result exists it joins the same pre-registered family, so the Holm
    # adjustment covers all seven tests of the post-drop family.
    grad = OUT / "comparison_gradient.json"
    if grad.exists():
        try:
            g = json.loads(grad.read_text(encoding="utf-8"))
            if g.get("slope"):
                family["H3_guard_slope"] = g["slope"]["p"]
        except (OSError, json.JSONDecodeError):
            pass
    summary["tests"]["family_size"] = len(family)
    # A partial family (rungs still collecting, or the gradient not yet run)
    # would understate every adjusted p. Emit Holm values only when the full
    # family exists; otherwise leave the field null. The family was
    # pre-registered at eight (five per-rung contrasts plus H1 to H3); the 9.0B
    # rung was dropped on 26 October, which removes one contrast and leaves
    # seven.
    summary["tests"]["holm_confirmatory"] = (holm(family)
                                             if len(family) == FAMILY_SIZE
                                             else None)
    # Sensitivity promised in the threats section: reinstate every excluded
    # cell and recompute the per-arm means and the Mingbird-minus-comparator
    # gap, so a reader can check that no ranking depends on the exclusions.
    by_all = defaultdict(dict)
    for r in all_rows:
        if r["failure_mode"] in VALID_FAILURE:
            by_all[(r["model"], r["harness"])][r["task"]] = r["score"]
    rein_means = {f"{m}|{h}": {"n": len(t), "mean": float(np.mean(list(t.values())))}
                  for (m, h), t in by_all.items()}
    rein_gaps = {}
    for m in {k[0] for k in by_all}:
        mb, base = by_all.get((m, "mingbird")), by_all.get((m, COMPARATOR))
        if not mb or not base:
            continue
        common = sorted(set(mb) & set(base))
        if len(common) >= 3:
            d = np.array([mb[t] - base[t] for t in common])
            rein_gaps[m] = {"mean_diff": float(d.mean()), "n": len(common)}
    summary["exclusions_reversed"] = {"means": rein_means,
                                      "gap_vs_comparator": rein_gaps}

    summary["completed_only"] = completed_only(rows)
    # The rungs run under different wall budgets scaled to throughput. This
    # reports what the ladder would look like under one budget for everyone, so
    # the size trend can be read against the schedule that produced it.
    summary["uniform_budget"] = uniform_budget(rows)
    summary["ceiling"] = ceiling_block(by)

    # Cost: wall-clock per cell. A timeout consumes its whole budget, so the
    # all-cells mean is the deployment cost; the completed-only mean is the
    # cost of a run that produced something.
    wall_all = defaultdict(list)
    wall_done = defaultdict(list)
    wall_pos = defaultdict(list)
    for r in rows:
        w = r.get("wall_seconds")
        if w is None:
            continue
        wall_all[(r["model"], r["harness"])].append(float(w))
        if r["scored"]:
            wall_done[(r["model"], r["harness"])].append(float(w))
        if r["score"] > 0:
            wall_pos[(r["model"], r["harness"])].append(float(w))
    summary["wall"] = {
        f"{m}|{h}": {
            "n": len(v),
            "mean_all": float(np.mean(v)),
            "n_completed": len(wall_done[(m, h)]),
            "mean_completed": (float(np.mean(wall_done[(m, h)]))
                               if wall_done[(m, h)] else None),
            "n_positive": len(wall_pos[(m, h)]),
            "mean_positive": (float(np.mean(wall_pos[(m, h)]))
                              if wall_pos[(m, h)] else None),
        }
        for (m, h), v in wall_all.items()
    }
    summary["wall_hours_total"] = float(
        sum(r.get("wall_seconds") or 0 for r in rows) / 3600.0)
    if summary["tests"]["interaction"]:
        it = summary["tests"]["interaction"]
        print(f"\nharness x model interaction (diagnostic only, not reported): "
              f"chi2={it['wald_chi2']:.2f} df={it['df']} p={it['p']:.4g}")

    # Span trend: is the span wider at the small end?
    rungs = [(m, s["span"]) for m, s in summary["by_model"].items()]
    summary["span_by_model"] = dict(rungs)

    (OUT / "comparison_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print("\nwrote", OUT / "comparison_summary.json")
    print("wrote", OUT / "comparison_matrix.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
