#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GAIA scorer: deterministic port of the official gaia-benchmark/GAIA
validation question_scorer (rules only, NO LLM judge).

Faithful to the official rules:
- numeric ground truth -> normalize_number_str (strip $ , % €) + float equality
- list ground truth ("," or ";") -> per-element normalized match, fuzzy ratio
  >= 85 accepted (difflib.SequenceMatcher, deterministic, no fuzzywuzzy dep)
- otherwise -> normalize_str (lowercase, strip punctuation, drop articles
  a/an/the, collapse whitespace) equality

Deliberate deviation (disclosed in methods): strict answer.txt-only protocol —
the model answer is read from workdir/answer.txt (all four agents can write
files; identical requirement, byte-identical prompt). No transcript parsing.
"""
import difflib
import string

ARTICLES = {"a", "an", "the"}


def normalize_number_str(number_str: str) -> float:
    for char in ["$", "%", ",", "€"]:
        number_str = str(number_str).replace(char, "")
    try:
        return float(number_str)
    except ValueError:
        return float("nan")


def normalize_str(input_str: str, remove_punct: bool = True) -> str:
    s = str(input_str)
    if remove_punct:
        s = s.translate(str.maketrans("", "", string.punctuation))
    words = [w for w in s.lower().split() if w not in ARTICLES]
    return " ".join(words)


def _is_float(x) -> bool:
    try:
        float(x)
        return True
    except (ValueError, TypeError):
        return False


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def question_scorer(model_answer, ground_truth) -> bool:
    gt = str(ground_truth).strip()
    ma = str(model_answer).strip()
    if _is_float(gt):
        return normalize_number_str(ma) == float(gt)
    if any(c in gt for c in [",", ";"]):
        import re
        gt_list = [normalize_str(s) for s in re.split(r"[,;]", gt) if s.strip()]
        ans_list = [normalize_str(s) for s in re.split(r"[,;]", ma) if s.strip()]
        for g in gt_list:
            if not any(g == a or _ratio(g, a) >= 0.85 for a in ans_list):
                return False
        return True
    return normalize_str(ma) == normalize_str(gt)


def score_answer(workdir, gold_answer):
    """Read workdir/answer.txt, score against gold. Returns (total, detail)."""
    import json
    import os

    ans_path = os.path.join(workdir, "answer.txt")
    if not os.path.isfile(ans_path):
        return 0.0, {"error": "answer.txt missing", "model_answer": None}
    raw = open(ans_path, encoding="utf-8", errors="replace").read()
    model_answer = raw.strip()
    # GAIA convention: bare answer. Take the last non-empty line if the agent
    # wrote explanation lines despite the instruction (uniform for all agents).
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    candidate = lines[-1] if lines else ""
    correct = question_scorer(candidate, gold_answer) or question_scorer(model_answer, gold_answer)
    return (1.0 if correct else 0.0), {
        "model_answer_raw": model_answer[:500],
        "model_answer_candidate": candidate[:500],
        "gold_answer": gold_answer,
    }


if __name__ == "__main__":
    # self-test on hand cases mirroring official scorer expectations
    cases = [
        ("17", "17", True), ("17.0", "17", True), ("$17", "17", True),
        ("1,234", "1234", True), ("50%", "50", True),
        ("17 hours", "17", False),              # units on numeric GT = wrong (official strict)
        ("The Blue Whale", "blue whale", True),
        ("a blue whale", "blue whale", True),
        ("in the morning", "morning", False),   # extra word: official normalize_str is whole-string
        ("yes", "no", False),
        ("Paris", "paris!", True),
        ("red, green, blue", "blue, red, green", True),   # order-insensitive list
        ("red, green", "red, green, blue", False),        # missing element
        ("Mercury and Venus", "venus; mercury", False),   # non-list answer vs list GT: official fails too
        ("venus, mercury", "venus; mercury", True),       # list vs ;-list: ok
    ]
    bad = 0
    for ma, gt, want in cases:
        got = question_scorer(ma, gt)
        mark = "ok" if got == want else "MISMATCH"
        if got != want:
            bad += 1
        print(f"{mark:9s} scorer({ma!r:>24}, {gt!r:>22}) = {got} (want {want})")
    print("SELF-TEST:", "PASS" if bad == 0 else f"{bad} FAILURES")
