#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LRAB deterministic scoring engine.

Checks (from task JSON):
  exists          -> artifact exists
  contains_any    -> file contains any of the strings
  contains_groups -> N groups of format-variants; group hit if any variant present;
                     score = hit_groups/N, capped below 1.0 unless ratio >= min_ratio
  contains_ordered-> strings appear in the given relative order (first-occurrence
                     positions strictly increasing; other text may sit between)
  not_contains    -> file contains none of the strings
  min_words       -> word count >= min_words
  structure       -> all required_sections appear as markdown headings
  python_compiles -> py_compile succeeds
  script_pass     -> run a command in the workdir, substring must appear in stdout
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
    """Return (score 0..1, detail: str) for a single check against an artifact.
    Partial credit: min_words within 15% of target gets 0.5 (avoids 1-word cliffs)."""
    p = os.path.join(workdir, artifact)
    kind = check["check"]
    params = check.get("params", {}) or {}
    if kind == "exists":
        return (1.0 if os.path.exists(p) else 0.0), ("exists" if os.path.exists(p) else "missing")
    if not os.path.exists(p):
        return 0.0, "missing"
    if kind == "contains_any":
        text = _read(p)
        hits = [s for s in params.get("any_of", []) if s in text]
        return (1.0 if hits else 0.0), (f"matched {hits[:3]}" if hits else "no expected strings found")
    if kind == "contains_groups":
        # N 组格式变体,组内任一命中即该组得分;总分组数比例给分,
        # 达到 min_ratio 才给满分(梯度分暴露"跳步",不是全有全无)。
        text = _read(p)
        groups = params.get("groups", [])
        if not groups:
            return 0.0, "no groups configured"
        hit = sum(1 for g in groups if any(s in text for s in g))
        ratio = hit / len(groups)
        min_ratio = float(params.get("min_ratio", 1.0))
        sc = 1.0 if ratio >= min_ratio else round(min(ratio, 0.999), 3)
        miss = [g[0] for g in groups if not any(s in text for s in g)]
        return sc, (f"{hit}/{len(groups)} groups (min_ratio {min_ratio})"
                    + (f"; missing e.g. {miss[:3]}" if miss else ""))
    if kind == "contains_ordered":
        # 相对顺序:各串首次出现位置严格递增(中间可有其他文本),对分隔符鲁棒。
        text = _read(p)
        ordered = params.get("ordered", [])
        if not ordered:
            return 0.0, "no ordered list configured"
        pos, last, ok = [], -1, True
        for s in ordered:
            i = text.find(s, last + 1)
            if i < 0:
                ok = False
                break
            pos.append(i)
            last = i
        return (1.0 if ok else 0.0), ("order matched" if ok else f"order broken at '{ordered[len(pos)] if len(pos) < len(ordered) else '?'}'")
    if kind == "not_contains":
        text = _read(p)
        bad = [s for s in params.get("none_of", []) if s in text]
        return (0.0 if bad else 1.0), (f"still contains {bad[:3]}" if bad else "clean")
    if kind == "min_words":
        n = len(_read(p).split())
        need = params.get("min_words", 0)
        if n >= need:
            return 1.0, f"{n} words (need {need})"
        # 软目标: 差 15% 以内给部分分(避免 1 词翻盘)
        if need > 0 and n >= need * 0.85:
            return 0.5, f"{n} words (need {need}, within 15%)"
        return 0.0, f"{n} words (need {need})"
    if kind == "structure":
        text = _read(p).lower()
        missing = [s for s in params.get("required_sections", []) if s.lower() not in text]
        return (0.0 if missing else 1.0), (f"missing sections {missing}" if missing else "all sections present")
    if kind == "python_compiles":
        try:
            py_compile.compile(p, doraise=True)
            return 1.0, "compiles"
        except Exception as e:
            return 0.0, f"syntax error: {str(e)[:120]}"
    if kind == "script_pass":
        # 在 workdir 里跑一条命令,stdout 含 expect 子串即过(LH-03: python test_suite.py
        # 须打 "10 passed, 0 failed" —— 模块真被修好,而不是只改到"能编译")。
        import subprocess as _sp
        cmd = params.get("command", "")
        expect = params.get("expect_stdout", "")
        if not cmd:
            return 0.0, "no command configured"
        try:
            r = _sp.run(cmd, shell=True, capture_output=True, text=True,
                        timeout=int(params.get("timeout_s", 120)), cwd=workdir,
                        encoding="utf-8", errors="replace")
            out = (r.stdout or "") + (r.stderr or "")
            if expect and expect in out:
                return 1.0, f"exit={r.returncode}, expected output present"
            if not expect and r.returncode == 0:
                return 1.0, "exit=0"
            tail = " | ".join((r.stdout or "").strip().splitlines()[-1:])[:100]
            return 0.0, f"exit={r.returncode}, expected '{expect}' not in output (tail: {tail})"
        except Exception as e:
            return 0.0, f"script failed: {str(e)[:100]}"
    if kind == "file_min_bytes":
        size = os.path.getsize(p) if os.path.exists(p) else 0
        return (1.0 if size >= params.get("min_bytes", 1) else 0.0), f"{size} bytes"
    if kind == "min_urls":
        n = len(re.findall(r"https?://", _read(p)))
        return (1.0 if n >= params.get("min_urls", 1) else 0.0), f"{n} urls (need {params.get('min_urls')})"
    if kind == "image_valid":
        # 真伪校验: PNG 签名 + IEND + PIL 可解码 + 最小分辨率(自省P0-6, 防手拼字节伪造图)
        try:
            data = open(p, "rb").read()
            if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                return 0.0, "not a PNG (bad signature)"
            if b"IEND" not in data:
                return 0.0, "PNG truncated (no IEND)"
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(data))
            img.load()
            min_w = params.get("min_width", 1)
            min_h = params.get("min_height", 1)
            w, h = img.size
            if w < min_w or h < min_h:
                return 0.0, f"image too small {w}x{h} (need {min_w}x{min_h})"
            return 1.0, f"valid PNG {w}x{h}"
        except Exception as e:
            return 0.0, f"invalid image: {str(e)[:80]}"
    return 0.0, f"unknown check kind {kind}"


def score_group(workdir, group):
    """group: list of {artifact, check, params}. Returns (score 0..1, details).
    Partial credit: check_one returns a score 0..1; 'ok' mirrors score>=0.5 for display."""
    if not group:
        return 1.0, []
    details, total = [], 0.0
    for entry in group:
        artifact = entry["artifact"]
        sc, detail = check_one(entry, workdir, artifact)
        total += sc
        details.append({"artifact": artifact, "check": entry["check"],
                        "ok": sc >= 0.5, "score": round(sc, 3), "detail": detail})
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
