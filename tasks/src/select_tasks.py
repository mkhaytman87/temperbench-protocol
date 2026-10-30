#!/usr/bin/env python3
"""TemperBench v0.3 task authoring: select_tasks.py

Applies the pre-registered selection rule (PROTOCOL.md §2.3) to scored calibration runs and
writes the v0.3 task set to tasks/{code,math,extract}.jsonl.

Calibration = every candidate × persona P3 × seeds 4,5 × each pilot model. Those seeds draw
P3 wrappers that the main run (seeds 1–3) never uses, so main-run P3 dialogues are fresh
draws rather than replays of the dialogues that selected the task.

Rule, per candidate task, over its n calibration dialogues (n = 6 for 3 models × 2 seeds):
  1. drop if listed in tasks/src/calibration_exclusions.json (defective key/spec found while
     reviewing calibration transcripts; P3-only data, so no persona information);
  2. drop if 2 or more of the n dialogues were truncated (finish_reason "length") —
     truncation-prone tasks would make exclusion rule (a) persona-dependent;
  3. keep if it passed at least once and failed at least once (truncation counts as fail);
  4. if more than MAX_TASKS remain, keep those with pass rate closest to 0.5
     (ties broken by sha256 of task_id);
  5. core = the CORE_PER_DOMAIN kept tasks per domain closest to 0.5 (same tie-break).

Usage:
    TEMPERBENCH_TASKS_DIR=tasks/candidates python3 tasks/src/select_tasks.py calib_*.jsonl
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = ROOT / "tasks" / "candidates"
EXCLUSIONS = ROOT / "tasks" / "src" / "calibration_exclusions.json"
OUT = ROOT / "tasks"
MAX_TASKS = 150
CORE_PER_DOMAIN = 5


def h(task_id: str) -> str:
    return hashlib.sha256(task_id.encode()).hexdigest()


def main():
    files = sys.argv[1:]
    if not files:
        print(__doc__)
        sys.exit(2)
    excluded = json.loads(EXCLUSIONS.read_text()) if EXCLUSIONS.exists() else {}
    cand = {}
    for domain in ("code", "math", "extract"):
        for line in (CANDIDATES / f"{domain}.jsonl").read_text().splitlines():
            if line.strip():
                t = json.loads(line)
                cand[t["task_id"]] = t

    stats = defaultdict(lambda: {"n": 0, "pass": 0, "trunc": 0})
    for f in files:
        for line in Path(f).read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r["persona_id"] != "P3":
                continue
            s = stats[r["task_id"]]
            s["n"] += 1
            trunc = any(t.get("finish_reason") == "length" for t in r["turns"] if t["role"] == "assistant")
            s["trunc"] += trunc
            s["pass"] += bool(r["scores"]["final_pass"]) and not trunc

    rows, kept = [], []
    for tid in sorted(cand):
        s = stats.get(tid, {"n": 0, "pass": 0, "trunc": 0})
        rate = s["pass"] / s["n"] if s["n"] else None
        if tid in excluded:
            verdict = f"drop: defect ({excluded[tid]})"
        elif s["n"] == 0:
            verdict = "drop: no calibration data"
        elif s["trunc"] >= 2:
            verdict = "drop: truncation-prone"
        elif s["pass"] == 0:
            verdict = "drop: never passed"
        elif s["pass"] == s["n"]:
            verdict = "drop: always passed"
        else:
            verdict = "in band"
            kept.append(tid)
        rows.append((tid, s, rate, verdict))

    closeness = lambda tid: (abs(stats[tid]["pass"] / stats[tid]["n"] - 0.5), h(tid))
    kept.sort(key=closeness)
    selected = set(kept[:MAX_TASKS])
    core = set()
    for domain in ("code", "math", "extract"):
        core |= set([t for t in kept if t in selected and cand[t]["domain"] == domain][:CORE_PER_DOMAIN])

    for domain in ("code", "math", "extract"):
        out = [dict(cand[t], core=t in core) for t in sorted(selected) if cand[t]["domain"] == domain]
        (OUT / f"{domain}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out))

    report = ["# v0.3 task selection report", "",
              f"Calibration files: {', '.join(Path(f).name for f in files)}",
              f"Candidates: {len(cand)} · in band: {len(kept)} · selected: {len(selected)} · core: {len(core)}", "",
              "| task | domain | pushback | calib pass | truncated | verdict |", "|---|---|---|---|---|---|"]
    for tid, s, rate, verdict in rows:
        if verdict == "in band" and tid not in selected:
            verdict = "drop: over MAX_TASKS"
        elif tid in selected:
            verdict = "SELECTED" + (" (core)" if tid in core else "")
        report.append(f"| {tid} | {cand[tid]['domain']} | {cand[tid].get('pushback', False)} | "
                      f"{s['pass']}/{s['n']} | {s['trunc']} | {verdict} |")
    by_dom = defaultdict(int)
    for t in selected:
        by_dom[cand[t]["domain"]] += 1
    report += ["", "Selected by domain: " + ", ".join(f"{d} {n}" for d, n in sorted(by_dom.items())),
               f"Selected pushback tasks: {sum(bool(cand[t].get('pushback')) for t in selected)}"]
    (ROOT / "tasks" / "src" / "selection_report.md").write_text("\n".join(report) + "\n")
    print("\n".join(report[:4] + report[-2:]))


if __name__ == "__main__":
    main()
