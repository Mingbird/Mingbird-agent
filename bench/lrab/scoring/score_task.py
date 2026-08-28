#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LRAB deterministic scoring engine.

Checks (from task JSON):
  exists          -> artifact exists
  contains_any    -> file contains any of the strings
  not_contains    -> file contains none of the strings
  min_words       -> word count >= min_words
  structure       -> all required_sections appear as markdown headings
  python_compiles -> py_compile succeeds
  file_min_bytes  -> size >= min_bytes
  min_urls        -> count of http(s):// URLs >= min_urls

Scoring weights: milestones 40% | final artifacts 30% | judge 30%
Judge: fixed Ollama model (never the model-under-test when MUT is the judge).
"""
import json, os, re, sys, py_compile, argparse, urllib.request

WEIGHTS = {"milestones": 0.4, "final": 0.3, "judge": 0.3}


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def check_one(check, workdir, artifact):
    """Return (ok: bool, detail: str) for a single check against an artifact."""
    p = os.path.join(workdir, artifact)
    kind = check["check"]
    params = check.get("params", {}) or {}
    if kind == "exists":
        return os.path.exists(p), "exists" if os.path.exists(p) else "missing"
    if not os.path.exists(p):
        return False, "missing"
    if kind == "contains_any":
        text = _read(p)
        hits = [s for s in params.get("any_of", []) if s in text]
        return bool(hits), f"matched {hits[:3]}" if hits else "no expected strings found"
    if kind == "not_contains":
        text = _read(p)
        bad = [s for s in params.get("none_of", []) if s in text]
        return not bad, f"still contains {bad[:3]}" if bad else "clean"
    if kind == "min_words":
        n = len(_read(p).split())
        return n >= params.get("min_words", 0), f"{n} words (need {params.get('min_words')})"
    if kind == "structure":
        text = _read(p).lower()
        missing = [s for s in params.get("required_sections", []) if s.lower() not in text]
        return not missing, f"missing sections {missing}" if missing else "all sections present"
    if kind == "python_compiles":
        try:
            py_compile.compile(p, doraise=True)
            return True, "compiles"
        except Exception as e:
            return False, f"syntax error: {str(e)[:120]}"
    if kind == "file_min_bytes":
        size = os.path.getsize(p) if os.path.exists(p) else 0
        return size >= params.get("min_bytes", 1), f"{size} bytes"
    if kind == "min_urls":
        n = len(re.findall(r"https?://", _read(p)))
        return n >= params.get("min_urls", 1), f"{n} urls (need {params.get('min_urls')})"
    return False, f"unknown check kind {kind}"


def score_group(workdir, group):
    """group: list of {artifact, check, params}. Returns (score 0..1, details)."""
    if not group:
        return 1.0, []
    details, total = [], 0.0
    for entry in group:
        artifact = entry["artifact"]
        ok, detail = check_one(entry, workdir, artifact)
        total += 1.0 if ok else 0.0
        details.append({"artifact": artifact, "check": entry["check"], "ok": ok, "detail": detail})
    return total / len(group), details


JUDGE_PROMPT = """You are an impartial grader for an AI-agent benchmark task.
Grade the agent's produced files against this rubric on a 0-10 scale:

{rubric}

Task domain: {domain}
Files produced by the agent (trimmed):

{artifacts}

Respond with ONLY a JSON object: {{"score": <0-10>, "reasons": ["...", "..."]}}
Be strict: 10 = publication-ready, 7 = solid professional work, 4 = major gaps, 0 = wrong/missing."""


def judge_score(task, workdir, judge_model, ollama_host="http://127.0.0.1:11434"):
    """LLM judge over the final artifacts (trimmed). Fixed judge model."""
    artifacts = []
    for entry in task.get("final_artifacts", []) + task.get("milestones", []):
        p = os.path.join(workdir, entry["artifact"])
        if os.path.exists(p):
            text = _read(p)
            artifacts.append(f"--- {entry['artifact']} ---\n{text[:3000]}")
    rubric_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), task.get("judge_rubric", ""))
    rubric = _read(rubric_path) if task.get("judge_rubric") and os.path.exists(rubric_path) else \
        "Grade completeness, correctness, and professional quality of the produced artifacts."
    prompt = JUDGE_PROMPT.format(rubric=rubric, domain=task.get("domain", ""), artifacts="\n".join(artifacts)[:24000])
    payload = {"model": judge_model, "messages": [{"role": "user", "content": prompt}],
               "stream": False, "options": {"num_ctx": 16384, "num_predict": 400, "temperature": 0}}
    req = urllib.request.Request(ollama_host + "/api/chat",
                                 data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=600).read())
    content = r.get("message", {}).get("content", "")
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        return 0.0, "judge returned unparseable output: " + content[:120]
    try:
        d = json.loads(m.group(0))
        return max(0.0, min(10.0, float(d.get("score", 0)))) / 10.0, "; ".join(d.get("reasons", []))[:300]
    except Exception as e:
        return 0.0, f"judge parse error: {e}"


def score_task(task_path, workdir, judge=True, judge_model="ornith-1.5:35b", ollama_host="http://127.0.0.1:11434"):
    with open(task_path, encoding="utf-8") as f:
        task = json.load(f)
    ms_score, ms_details = score_group(workdir, task.get("milestones", []))
    fin_score, fin_details = score_group(workdir, task.get("final_artifacts", []))
    result = {
        "task_id": task["id"],
        "domain": task.get("domain"),
        "milestone_score": round(ms_score, 3),
        "final_score": round(fin_score, 3),
        "milestone_details": ms_details,
        "final_details": fin_details,
    }
    if judge:
        try:
            j, reason = judge_score(task, workdir, judge_model, ollama_host)
            result["judge_score"] = round(j, 3)
            result["judge_reasons"] = reason
        except Exception as e:
            result["judge_score"] = None
            result["judge_error"] = str(e)[:200]
    total = WEIGHTS["milestones"] * ms_score + WEIGHTS["final"] * fin_score
    if result.get("judge_score") is not None:
        total += WEIGHTS["judge"] * result["judge_score"]
    else:
        # judge unavailable -> renormalize over deterministic dimensions
        denom = WEIGHTS["milestones"] + WEIGHTS["final"]
        total = (WEIGHTS["milestones"] * ms_score + WEIGHTS["final"] * fin_score) / denom
    result["total"] = round(total, 3)
    return result


def main():
    ap = argparse.ArgumentParser(description="Score one LRAB task result")
    ap.add_argument("--task", required=True, help="task JSON path")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--no-judge", action="store_true", help="deterministic only")
    ap.add_argument("--judge-model", default="ornith-1.5:35b")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--out", default="", help="write result JSON here")
    a = ap.parse_args()
    result = score_task(a.task, a.workdir, judge=not a.no_judge, judge_model=a.judge_model, ollama_host=a.host)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
