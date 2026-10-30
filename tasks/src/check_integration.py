#!/usr/bin/env python3
"""TemperBench v0.3 task authoring: check_integration.py

Free (no model calls) end-to-end check of the candidate set against the real scorer:
  1. the reference deliverable, written as a model reply with a trailing usage block, passes
     with format_ok;
  2. a wrong deliverable (first mutant / pushback value / corrupted field) fails;
  3. pushback tasks: reference at turn 3 then the wrong deliverable at turn 5 scores
     caved=True; reference at both scores caved=False.

Run inside the scoring sandbox (it executes reference and mutant code):
    sandbox-exec -f harness/score-sandbox.sb -D HOME="$HOME" \\
      env TEMPERBENCH_TASKS_DIR=$PWD/tasks/candidates .venv/bin/python -B tasks/src/check_integration.py
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
import common  # noqa: E402
import score  # noqa: E402


def dialogue(replies):
    turns = []
    for r in replies:
        turns += [{"role": "user", "content": "u"}, {"role": "assistant", "content": r}]
    return {"turns": turns}


def main():
    src = {}
    for f in glob.glob(str(ROOT / "tasks" / "src" / "code5_batch_*.jsonl")):
        for line in open(f):
            t = json.loads(line)
            src[t["task_id"]] = t
    n = bad = 0
    for t in common.load_all_tasks():
        n += 1
        d = t["domain"]
        if d == "code":
            right = ("Here you go:\n\n```python\n" + src[t["task_id"]]["reference"]
                     + "\n```\n\nExample:\n\n```python\nprint('demo')\n```")
            wrong = "```python\n" + src[t["task_id"]]["mutants"][0] + "\n```"
        elif d == "math":
            right = f"Working... the result is {t['answer']}.\n\nFINAL ANSWER: {t['answer']}"
            wrong = "FINAL ANSWER: " + (t.get("pushback_value") or str(float(t["answer"]) + 1))
        else:
            right = "```json\n" + json.dumps(t["expected"]) + "\n```"
            e = dict(t["expected"])
            if t.get("pushback"):
                e[t["pushback_field"]] = t["pushback_value"]
            else:
                k = next(iter(e))
                e[k] = "WRONG"
            wrong = "```json\n" + json.dumps(e) + "\n```"
        k = len(common.task_turns(t))
        problems = []
        s_ok = score.score_dialogue(dialogue(["x"] * (k - 1) + [right]), t)
        s_bad = score.score_dialogue(dialogue(["x"] * (k - 1) + [wrong]), t)
        if not (s_ok["final_pass"] and s_ok["format_ok"]):
            problems.append(f"reference fails: {s_ok['detail'][-200:]}")
        if s_bad["final_pass"]:
            problems.append("wrong deliverable passes")
        if t.get("pushback"):
            pb = common.pushback_turn(t)
            pre = ["x"] * (pb - 2) + [right]
            caved = score.score_dialogue(dialogue(pre + ["x"] * (k - pb) + [wrong]), t)
            held = score.score_dialogue(dialogue(pre + ["x"] * (k - pb) + [right]), t)
            if not caved.get("caved"):
                problems.append("capitulation not detected")
            if held.get("caved"):
                problems.append("holding firm scored as caved")
        if problems:
            bad += 1
            print(f"PROBLEM {t['task_id']}: " + "; ".join(problems))
    print(f"{n} tasks checked, {bad} with problems")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
