#!/usr/bin/env python3
"""TemperBench v0.3 task authoring: build_candidates.py

Merges authored/generated candidate tasks into the calibration task set
tasks/candidates/{code,math,extract}.jsonl:
  - appends the domain's fixed format line (harness/common.py FORMAT_LINES) to every turn,
    so all personas get byte-identical task content including the format request;
  - keeps only the fields the harness needs (authoring fields such as reference solutions
    and mutants stay in tasks/src/).

Usage:
    python3 tasks/src/build_candidates.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
import common  # noqa: E402

SRC = ROOT / "tasks" / "src"
OUT = ROOT / "tasks" / "candidates"
KEEP = {
    "code": ["task_id", "domain", "family", "pushback", "t1", "t2", "t3", "entry_point", "tests"],
    "math": ["task_id", "domain", "family", "pushback", "t1", "t2", "t3", "answer", "tolerance",
             "pushback_value"],
    "extract": ["task_id", "domain", "family", "pushback", "t1", "t2", "t3", "expected",
                "numeric_tolerance"],
}
SOURCES = {
    "code": sorted(SRC.glob("code_batch_*.jsonl")),
    "math": [SRC / "math_candidates.jsonl"],
    "extract": [SRC / "extract_candidates.jsonl"],
}


def main():
    OUT.mkdir(exist_ok=True)
    seen = set()
    for domain, files in SOURCES.items():
        rows = []
        for f in files:
            if not f.exists():
                print(f"warning: {f.relative_to(ROOT)} missing", file=sys.stderr)
                continue
            for line in f.read_text().splitlines():
                if not line.strip():
                    continue
                t = json.loads(line)
                assert t["domain"] == domain, t["task_id"]
                assert t["task_id"] not in seen, f"duplicate {t['task_id']}"
                seen.add(t["task_id"])
                row = {k: t[k] for k in KEEP[domain] if k in t}
                row.setdefault("pushback", False)
                for slot in ("t1", "t2", "t3"):
                    row[slot] = f"{t[slot].rstrip()}\n\n{common.FORMAT_LINES[domain]}"
                rows.append(row)
        path = OUT / f"{domain}.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        print(f"{domain}: {len(rows)} candidates ({sum(r['pushback'] for r in rows)} pushback) -> "
              f"{path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
