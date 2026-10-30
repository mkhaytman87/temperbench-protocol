#!/usr/bin/env python3
"""TemperBench v0.3 task authoring: check_code_tasks.py

Validates candidate code tasks before they enter calibration. For each task:
  1. schema: required fields present and well-typed;
  2. the reference solution passes every hidden test;
  3. every mutant (a plausible wrong solution) fails at least one test;
  4. tests run in under TIME_LIMIT_S seconds.

Pushback tasks (pushback: true) have a T3 that falsely claims a bug. The final spec is the
T2 spec, so the reference and tests describe the T2 behaviour and the reference must NOT
change in response to T3.

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
REQUIRED = {"task_id": str, "domain": str, "family": str, "entry_point": str, "t1": str,
            "t2": str, "t3": str, "tests": str, "reference": str, "mutants": list,
            "pushback": bool, "notes": str}


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
    if f"`{task['entry_point']}" not in task["t1"] and task["entry_point"] not in task["t1"]:
        problems.append("t1 does not name the entry_point")
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
