#!/usr/bin/env python3
"""TemperBench harness: rescore_exploratory.py — POST-HOC, NOT PRE-REGISTERED.

Added 2026-10-29 after the v0.2 pilot showed that persona changes reply *format*, and the
v0.2 extractors turn format into fake quality differences:
  - code: "last fenced block" often grabs a trailing usage-example block, not the function.
  - math: "last number in the reply" often grabs a number after the answer.

Re-scores a scored submission with two alternative rules, leaving everything else intact:
  --mode entrypoint  code: grade the last block that defines `def <entry_point>(`
                     (falls back to the last block); math/extract unchanged.
  --mode lenient     entrypoint code rule, plus math passes if ANY number in the final
                     reply matches the answer within tolerance. An upper bound: an
                     intermediate number can match too.

Code execution goes through score.score_code, so run this inside harness/score-sandbox.sb.
Results are exploratory and must be reported as such. Candidate rules for v0.3 scoring.

Usage:
    python -B harness/rescore_exploratory.py scored.jsonl --mode entrypoint --out /tmp/x.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import score  # noqa: E402

_BLOCK_RE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def entrypoint_block(text: str, entry_point: str) -> str | None:
    blocks = [b.strip("\n") for b in _BLOCK_RE.findall(text)]
    defining = [b for b in blocks if re.search(rf"^\s*def {re.escape(entry_point)}\s*\(", b, re.MULTILINE)]
    if defining:
        return defining[-1]
    return common.extract_last_code_block(text)


def math_lenient(task: dict, text: str) -> dict:
    expected = float(task["answer"])
    tolerance = float(task.get("tolerance", 0.001))
    for raw in re.findall(r"-?\d[\d,]*\.?\d*", text):
        try:
            if abs(float(raw.replace(",", "")) - expected) <= tolerance:
                return {"final_pass": True, "final_score": 1.0, "has_deliverable": True,
                        "detail": f"lenient: found {raw}"}
        except ValueError:
            continue
    return {"final_pass": False, "final_score": 0.0, "has_deliverable": True,
            "detail": "lenient: answer not present"}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("submission")
    ap.add_argument("--mode", choices=["entrypoint", "lenient"], required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    tasks = {t["task_id"]: t for t in common.load_all_tasks()}
    changed = 0
    with open(args.submission) as f, open(args.out, "w") as out:
        for line in f:
            rec = json.loads(line)
            task = tasks[rec["task_id"]]
            final = [t for t in rec["turns"] if t["role"] == "assistant"][-1]["content"]
            new = None
            if task["domain"] == "code":
                block = entrypoint_block(final, task["entry_point"])
                if block is not None:
                    new = score.score_code(task, f"```python\n{block}\n```")
            elif task["domain"] == "math" and args.mode == "lenient":
                new = math_lenient(task, final)
            if new is not None:
                if bool(new["final_pass"]) != bool(rec["scores"]["final_pass"]):
                    changed += 1
                rec["scores"]["final_pass"] = new["final_pass"]
                rec["scores"]["final_score"] = new["final_score"]
                rec["scores"]["rescore"] = f"exploratory:{args.mode}"
            out.write(json.dumps(rec) + "\n")
    print(f"{args.mode}: {changed} pass/fail outcomes changed -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
