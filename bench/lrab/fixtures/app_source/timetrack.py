"""TimeTrack — a minimal command-line time tracker (wf10 fixture).

The agent must read this source and write a user manual for it.
"""
import argparse
import json
import os
from datetime import datetime

DB = os.path.expanduser("~/.timetrack/entries.json")


def _load():
    if not os.path.exists(DB):
        return []
    with open(DB, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(entries):
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    with open(DB, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)


def cmd_start(args):
    entries = _load()
    active = [e for e in entries if e["end"] is None]
    if active:
        raise SystemExit(f"Timer already running for project '{active[0]['project']}'. Stop it first.")
    entries.append({"project": args.project, "start": datetime.now().isoformat(timespec="seconds"), "end": None, "note": args.note or ""})
    _save(entries)
    print(f"Started tracking '{args.project}'.")


def cmd_stop(args):
    entries = _load()
    for e in reversed(entries):
        if e["end"] is None:
            e["end"] = datetime.now().isoformat(timespec="seconds")
            if args.note:
                e["note"] = (e["note"] + " " + args.note).strip()
            _save(entries)
            print(f"Stopped '{e['project']}'.")
            return
    raise SystemExit("No running timer.")


def _hours_between(iso_a, iso_b):
    fmt = "%Y-%m-%dT%H:%M:%S"
    return (datetime.strptime(iso_b, fmt) - datetime.strptime(iso_a, fmt)).total_seconds() / 3600.0


def cmd_report(args):
    entries = _load()
    totals = {}
    for e in entries:
        if e["end"] is None:
            continue
        day = e["start"][:10]
        if args.since and day < args.since:
            continue
        totals.setdefault(e["project"], 0.0)
        totals[e["project"]] += _hours_between(e["start"], e["end"])
    for proj, hours in sorted(totals.items(), key=lambda kv: -kv[1]):
        print(f"{proj:30s} {hours:6.2f} h")


def main():
    ap = argparse.ArgumentParser(prog="timetrack", description="Minimal time tracker")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_start = sub.add_parser("start", help="start tracking a project")
    p_start.add_argument("project")
    p_start.add_argument("--note", default="", help="optional note")
    p_stop = sub.add_parser("stop", help="stop the running timer")
    p_stop.add_argument("--note", default="", help="closing note")
    p_rep = sub.add_parser("report", help="hour totals per project")
    p_rep.add_argument("--since", default="", help="YYYY-MM-DD lower bound")
    args = ap.parse_args()
    {"start": cmd_start, "stop": cmd_stop, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    main()
