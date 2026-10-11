# -*- coding: utf-8 -*-
"""Compare the ternary-27b Mingbird-arm row against the published
ornith-1.5:35b Mingbird arm (lrab_scores.csv) per task + segment means."""
import csv, glob, json, os, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PUB = r"C:\Users\99491\dev\mingbird-v16\benchmarks\lrab_scores.csv"
NEWDIR = r"C:\Users\99491\dev\mingbird-v16\eval_results\lrab_ternary27b_2610"

ornith = {}
with open(PUB, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        if row["harness"] == "Mingbird" and row["model"] == "ornith1.5_35b":
            ornith[row["task"]] = (float(row["score"]), float(row["wall_seconds"]))

new = {}
for sj in glob.glob(os.path.join(NEWDIR, "*", "score.json")):
    with open(sj, encoding="utf-8") as f:
        s = json.load(f)
    if s.get("failure_mode") in ("timeout",):
        new[s["task_id"]] = (None, s.get("wall_seconds", 0), s.get("failure_mode"))
        continue
    new[s["task_id"]] = (float(s.get("score", 0)), float(s.get("wall_seconds", 0)),
                         s.get("failure_mode", "completed"))

def norm(tid):
    return tid.replace("-", "")

order = (["LH-%02d" % i for i in range(1, 4)] +
         ["WF-%02d" % i for i in range(1, 16)])
print("%-6s %10s %8s  %10s %9s  %s" % ("task", "ornith35b", "wall_s", "ternary27b", "wall_s", "delta"))
seg = {"LH": [0, 0, 0], "WF": [0, 0, 0]}  # sum_ornith, sum_new, n_scored
o_all = n_all = []
so = sn = cnt = 0.0
per_seg = {"LH": [0.0, 0.0, 0], "WF": [0.0, 0.0, 0]}
for tid in order:
    o = ornith.get(tid.replace("-", ""))
    n = new.get(tid)
    os_, ow = o if o else (None, None)
    ns, nw, nfm = (n + (None,))[:3] if n else (None, None, None)
    d = ""
    if os_ is not None and ns is not None:
        d = "%+.3f" % (ns - os_)
        so += os_; sn += ns; cnt += 1
        segkey = tid[:2]
        per_seg[segkey][0] += os_; per_seg[segkey][1] += ns; per_seg[segkey][2] += 1
    print("%-6s %10s %8s  %10s %9s  %s  %s" % (
        tid,
        "%s" % os_ if os_ is not None else "-", "%d" % ow if ow else "-",
        ("%s" % ns if ns is not None else ("timeout" if nfm == "timeout" else "-")),
        "%d" % nw if nw else "-", d,
        ("(%s)" % nfm) if nfm and nfm != "completed" else ""))

print("\npaired cells: %d" % cnt)
if cnt:
    print("ornith  mean over paired: %.3f" % (so / cnt))
    print("ternary mean over paired: %.3f" % (sn / cnt))
for k, (a, b, n) in per_seg.items():
    if n:
        print("%s segment (%d cells): ornith %.3f vs ternary %.3f" % (k, n, a / n, b / n))
tot_n = sum(v[2] for v in per_seg.values())
if tot_n == 18:
    to = sum(v[0] for v in per_seg.values()) / 18
    tn = sum(v[1] for v in per_seg.values()) / 18
    print("overall (18): ornith %.3f vs ternary %.3f" % (to, tn))
