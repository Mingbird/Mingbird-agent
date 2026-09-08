#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GAIA scorer: verbatim port of the OFFICIAL leaderboard scorer
(gaia-benchmark/leaderboard space, scorer.py @ main, retrieved 2026-09-08
via hf-mirror; the original file is archived at
bench/gaia/official_leaderboard_scorer.reference.py).

Rules (exact port):
- numeric ground truth -> normalize_number_str (strip $ % ,) float equality
- list ground truth ("," or ";") -> equal element count, element-wise compare
  (numeric elements via normalize_number_str, string elements via
  normalize_str with punctuation KEPT)
- otherwise -> normalize_str equality (ALL whitespace removed, lowercase,
  punctuation stripped)

Deliberate deviations (disclosed in methods):
- answer.txt-only protocol — the model answer is read from
  workdir/answer.txt (all four agents can write files; identical
  requirement, byte-identical prompt). No transcript parsing.
- the wrapper accepts either the last non-empty line or the full text.

NOTE (2026-09-08): an earlier local port followed the 2023-era official
rules (article removal + fuzzywuzzy list matching). The official scorer
has since changed; this file tracks the current leaderboard semantics.
"""
import re
import string


def normalize_number_str(number_str: str) -> float:
    # we replace these common units and commas to allow
    # conversion to float
    for char in ["$", "%", ","]:
        number_str = str(number_str).replace(char, "")
    try:
        return float(number_str)
    except ValueError:
        return float("inf")


def split_string(s: str, char_list: list = None) -> list:
    char_list = char_list or [",", ";"]
    pattern = f"[{''.join(char_list)}]"
    return re.split(pattern, s)


def normalize_str(input_str, remove_punct=True) -> str:
    """Official normalization: remove ALL white spaces, optionally remove
    punctuation, lowercase. (No article removal in the current official
    scorer.)"""
    no_spaces = re.sub(r"\s", "", input_str)
    if remove_punct:
        translator = str.maketrans("", "", string.punctuation)
        return no_spaces.lower().translate(translator)
    return no_spaces.lower()


def question_scorer(model_answer, ground_truth) -> bool:
    def is_float(element) -> bool:
        try:
            float(element)
            return True
        except (ValueError, TypeError):
            return False

    if model_answer is None:
        model_answer = "None"

    # if gt is a number
    if is_float(ground_truth):
        normalized_answer = normalize_number_str(model_answer)
        return normalized_answer == float(ground_truth)

    # if gt is a list
    elif any(char in ground_truth for char in [",", ";"]):
        gt_elems = split_string(ground_truth)
        ma_elems = split_string(model_answer)
        if len(gt_elems) != len(ma_elems):
            return False
        comparisons = []
        for ma_elem, gt_elem in zip(ma_elems, gt_elems):
            if is_float(gt_elem):
                comparisons.append(normalize_number_str(ma_elem) == float(gt_elem))
            else:
                # punctuation is kept for list elements (official behavior)
                comparisons.append(
                    normalize_str(ma_elem, remove_punct=False)
                    == normalize_str(gt_elem, remove_punct=False)
                )
        return all(comparisons)

    # if gt is a str
    return normalize_str(model_answer) == normalize_str(ground_truth)


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
    # self-test on hand cases mirroring the CURRENT official leaderboard
    # scorer semantics (whitespace-removed equality; no articles; no fuzzy;
    # order- and length-sensitive lists)
    cases = [
        ("17", "17", True), ("17.0", "17", True), ("$17", "17", True),
        ("1,234", "1234", True), ("50%", "50", True),
        ("17 hours", "17", False),              # units on numeric GT = wrong (official strict)
        ("Sea Gull", "seagull", True),          # official removes ALL whitespace
        ("the blue whale", "blue whale", False),  # official keeps articles, removes spaces
        ("Paris", "paris!", True),
        ("red, green, blue", "blue, red, green", False),  # list order matters now
        ("red, green", "red, green, blue", False),        # list length mismatch
        ("Mercury and Venus", "venus; mercury", False),   # single answer vs list GT
        ("venus, mercury", "venus; mercury", True),       # list vs ;-list: ok
        ("yes", "no", False),
    ]
    bad = 0
    for ma, gt, want in cases:
        got = question_scorer(ma, gt)
        mark = "ok" if got == want else "MISMATCH"
        if got != want:
            bad += 1
        print(f"{mark:9s} scorer({ma!r:>22}, {gt!r:>22}) = {got} (want {want})")
    print("SELF-TEST:", "PASS" if bad == 0 else f"{bad} FAILURES")
