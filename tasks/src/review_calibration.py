#!/usr/bin/env python3
"""TemperBench v0.3 task authoring: review_calibration.py

Flags candidate tasks whose calibration failures look like task defects rather than model
errors, for the defect review in PROTOCOL.md §2.3 step 2. Calibration is P3-only, so this
review carries no persona information.

Signals:
  math     ≥2 failing dialogues agree on the same final answer (independent models
           converging on one "wrong" value suggests a wrong key or ambiguous wording)
  extract  ≥2 failing dialogues give the same wrong value for a field
  code     one hidden test fails in ≥ half of a task's dialogues (suggests a test the spec
           doesn't determine)
  any      no dialogue passed (too hard, or defective — read before deciding)

Output is a worklist for a human/agent reader; it decides nothing by itself.

Usage:
    TEMPERBENCH_TASKS_DIR=tasks/candidates python3 tasks/src/review_calibration.py scored_*.jsonl
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
import common  # noqa: E402


def main():
    tasks = {t["task_id"]: t for t in common.load_all_tasks()}
    by_task = defaultdict(list)
    for f in sys.argv[1:]:
        for line in Path(f).read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                by_task[r["task_id"]].append(r)

    flags = []
    for tid, recs in sorted(by_task.items()):
        t = tasks[tid]
        fails = [r for r in recs if not r["scores"]["final_pass"]
                 and not any(x.get("finish_reason") == "length" for x in r["turns"] if x["role"] == "assistant")]
        notes = []
        if not any(r["scores"]["final_pass"] for r in recs):
            notes.append(f"never passed ({len(recs)} dialogues)")
        if t["domain"] == "math" and len(fails) >= 2:
            vals = Counter()
            for r in fails:
                final = [x for x in r["turns"] if x["role"] == "assistant"][-1]["content"]
                v, _ = common.extract_final_answer(final)
                if v is not None:
                    vals[round(v, 4)] += 1
            agreed = [(v, n) for v, n in vals.items() if n >= 2]
            if agreed:
                notes.append(f"failing answers agree: {agreed} vs key {t['answer']}"
                             + (f" (pushback value {t['pushback_value']})" if t.get("pushback") else ""))
        if t["domain"] == "extract" and len(fails) >= 2:
            wrong = Counter()
            for r in fails:
                final = [x for x in r["turns"] if x["role"] == "assistant"][-1]["content"]
                got = common.extract_json_object(final) or {}
                tol = float(t.get("numeric_tolerance", 1e-6))
                for k, e in t["expected"].items():
                    if k in got and not common.values_match(e, got[k], tol):
                        wrong[(k, json.dumps(got[k]))] += 1
            agreed = [(k, v, n) for (k, v), n in wrong.items() if n >= 2]
            if agreed:
                notes.append("same wrong field values: " + "; ".join(
                    f"{k}={v} ×{n} (key {json.dumps(t['expected'][k])})" for k, v, n in agreed))
        if t["domain"] == "code" and recs:
            failed_tests = Counter()
            for r in recs:
                failed_tests.update(set(re.findall(r"::(test_\w+)", r["scores"].get("detail", ""))))
            common_fail = [(name, n) for name, n in failed_tests.items() if n * 2 >= len(recs)]
            if common_fail:
                notes.append(f"tests failing in ≥ half of {len(recs)} dialogues: {common_fail}")
        if notes:
            passed = sum(r["scores"]["final_pass"] for r in recs)
            flags.append(f"- **{tid}** ({passed}/{len(recs)} passed): " + " · ".join(notes))
    print(f"# Calibration defect worklist ({len(flags)} tasks flagged of {len(by_task)})\n")
    print("\n".join(flags))


if __name__ == "__main__":
    main()
