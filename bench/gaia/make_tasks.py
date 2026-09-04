#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate GAIA task JSONs (LRAB-compatible schema) from the local
2023/validation parquet files. One JSON per task, stable IDs by parquet order.

Usage: python make_tasks.py            # writes tasks/GAIA-L1-01..53.json
"""
import json
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
VAL = os.path.join(HERE, "2023", "validation")
OUT = os.path.join(HERE, "tasks")

PROMPT_TMPL = """You are an autonomous agent working in the current directory.

Complete the following task:

{question}
{attachment_line}
When you have determined the final answer, write ONLY the final answer itself \
to a file named `answer.txt` in the current directory. The final answer must be \
as short as possible: no explanation, no reasoning, no full sentence — just the \
answer the task asks for (a number, a name, a comma-separated list, etc.)."""


def main():
    os.makedirs(OUT, exist_ok=True)
    n = 0
    for level in (1, 2, 3):
        pq = os.path.join(VAL, f"metadata.level{level}.parquet")
        if not os.path.isfile(pq):
            continue
        df = pd.read_parquet(pq)
        for i, row in df.iterrows():
            n += 1
            fname = row["file_name"] if pd.notna(row["file_name"]) else ""
            fixtures = []
            attachment_line = ""
            if fname:
                rel = os.path.join("..", "gaia", "2023", "validation", fname)
                fixtures = [rel]  # resolved against bench/lrab by run_bench.prepare_workdir
                attachment_line = (f"\nThe task includes the file `{fname}` in the "
                                   "current directory. Use it as needed.\n")
            task = {
                "id": f"GAIA-L{level}-{i + 1:02d}",
                "domain": "gaia-external-anchor",
                "version": "gaia-2023-validation",
                "gaia_task_id": str(row["task_id"]),
                "level": int(level),
                "fixtures": fixtures,
                "gaia_file_name": fname,
                "prompt": PROMPT_TMPL.format(question=str(row["Question"]).strip(),
                                             attachment_line=attachment_line),
                "gold_answer": str(row["Final answer"]),
                "max_wall_minutes": 30,
                "notes": str(row.get("Annotator Metadata", "") or "")[:2000],
            }
            path = os.path.join(OUT, f"GAIA-L{level}-{i + 1:02d}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(task, f, ensure_ascii=False, indent=2)
    print(f"wrote {n} task JSONs to {OUT}")


if __name__ == "__main__":
    main()
