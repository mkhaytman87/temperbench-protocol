#!/usr/bin/env python3
"""TemperBench v0.3 task authoring: check_code_tasks.py

Validates candidate code tasks before they enter calibration. For each task:
  1. schema: required fields present and well-typed;
  2. the reference solution passes every hidden test;
  3. every mutant (a plausible wrong solution) fails at least one test;
  4. tests run in under TIME_LIMIT_S seconds.

Tasks follow tasks/src/SCHEMA_v03.md: exactly 5 turns. Pushback tasks (pushback: true) put
the whole spec in turns 1-3; turns 4-5 falsely claim a bug, so the reference and tests
describe the turn-3 behaviour and the reference must NOT change in response to them.

Usage:
    .venv/bin/python -B tasks/src/check_code_tasks.py tasks/src/code_batch_A.jsonl [...]
Exit status is non-zero if any task fails a check.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

TIME_LIMIT_S = 10
REQUIRED = {"task_id": str, "domain": str, "family": str, "entry_point": str, "turns": list,
            "tests": str, "reference": str, "mutants": list, "pushback": bool, "notes": str}
KINDS = {False: ["first", "req", "req", "req", "final"], True: ["first", "req", "req", "pb1", "pb2"]}


def run_tests(solution: str, tests: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="tb-check-") as d:
        path = Path(d) / "test_candidate.py"
        path.write_text(solution + "\n\n" + tests)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", str(path), "-q", "--no-header",
                 "-p", "no:cacheprovider", "-x"],
                capture_output=True, text=True, timeout=TIME_LIMIT_S, cwd=d)
        except subprocess.TimeoutExpired:
            return False, "timeout"
        out = proc.stdout + proc.stderr
        return proc.returncode == 0 and re.search(r"\d+ passed", out) is not None, out[-800:]


def check(task: dict) -> list[str]:
    problems = []
    for key, typ in REQUIRED.items():
        if not isinstance(task.get(key), typ):
            problems.append(f"field {key!r} missing or not {typ.__name__}")
    if problems:
        return problems
    if task["domain"] != "code":
        problems.append("domain must be 'code'")
    if not re.search(rf"^def {re.escape(task['entry_point'])}\s*\(", task["reference"], re.M):
        problems.append("reference does not define entry_point at top level")
    kinds = [t.get("kind") for t in task["turns"] if isinstance(t, dict)]
    if kinds != KINDS[task["pushback"]]:
        problems.append(f"turn kinds {kinds} != {KINDS[task['pushback']]} (see tasks/src/SCHEMA_v03.md)")
    if any(not isinstance(t, dict) or not str(t.get("text", "")).strip() for t in task["turns"]):
        problems.append("every turn needs non-empty text")
    elif task["entry_point"] not in task["turns"][0]["text"]:
        problems.append("turn 1 does not name the entry_point")
    if len(task["mutants"]) < 2:
        problems.append("need at least 2 mutants")
    n_tests = len(re.findall(r"^def test_", task["tests"], re.M))
    if n_tests < 5:
        problems.append(f"only {n_tests} test functions (need >= 5)")
    ok, out = run_tests(task["reference"], task["tests"])
    if not ok:
        problems.append(f"reference FAILS tests:\n{out}")
    for i, mutant in enumerate(task["mutants"]):
        m_ok, _ = run_tests(mutant, task["tests"])
        if m_ok:
            problems.append(f"mutant {i} PASSES all tests (tests don't catch it)")
    return problems


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    bad = 0
    seen = set()
    for file in sys.argv[1:]:
        for n, line in enumerate(Path(file).read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                task = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"{file}:{n}: invalid JSON: {e}")
                bad += 1
                continue
            tid = task.get("task_id", f"<line {n}>")
            if tid in seen:
                print(f"{tid}: duplicate task_id")
                bad += 1
            seen.add(tid)
            problems = check(task)
            if problems:
                bad += 1
                print(f"FAIL {tid}")
                for p in problems:
                    print("   - " + p.replace("\n", "\n     "))
            else:
                print(f"ok   {tid}  (pushback={task['pushback']}, mutants={len(task['mutants'])})")
    print(f"\n{bad} task(s) with problems")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    main()
