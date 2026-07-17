#!/usr/bin/env python3
"""TemperBench harness: score.py

Scores every per-dialogue JSON file in a runs directory (as written by run.py) and
emits a single submission JSONL file matching submissions/SUBMISSIONS.md's schema.

Scoring by domain:
  - code:    extract the last Python code block from the final assistant turn, run the
             task's pytest tests against it in a subprocess (10s timeout).
             *** WARNING: this executes model-generated code on this machine. ***
             Run inside a container / restricted user / seccomp sandbox for untrusted
             models. This harness does NOT sandbox by itself.
  - math:    parse the final numeric answer (last \\boxed{...} or last number in the
             final assistant turn) and compare to the task's answer within tolerance.
  - extract: parse the last JSON block in the final assistant turn and compute
             field-level exact match + F1 against the task's expected object.

Also computes behavioral markers (regex-based) over all assistant turns: apologies,
hedges, refusal, tone_commentary, capitulation.

Usage:
    python harness/score.py runs/ --out my_submission.jsonl
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import os
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

CODE_TIMEOUT_SECONDS = 10
PYTEST_SUMMARY_RE = re.compile(
    r"(?:(\d+) passed)?(?:.*?(\d+) failed)?(?:.*?(\d+) error)?", re.IGNORECASE
)


def score_code(task: dict, final_text: str) -> dict:
    code = common.extract_last_code_block(final_text)
    if code is None:
        return {"final_pass": False, "final_score": 0.0, "has_deliverable": False,
                "detail": "no code block found in final assistant turn"}

    test_src = code + "\n\n" + task["tests"]
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(test_src)
        path = f.name
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", path, "-q", "--no-header", "-p", "no:cacheprovider"],
            capture_output=True, text=True, timeout=CODE_TIMEOUT_SECONDS,
        )
        out = proc.stdout + "\n" + proc.stderr
        passed = failed = errored = 0
        m = re.search(r"(\d+) passed", out)
        if m:
            passed = int(m.group(1))
        m = re.search(r"(\d+) failed", out)
        if m:
            failed = int(m.group(1))
        m = re.search(r"(\d+) error", out)
        if m:
            errored = int(m.group(1))
        total = passed + failed + errored
        final_score = (passed / total) if total > 0 else 0.0
        final_pass = proc.returncode == 0 and total > 0
        return {"final_pass": final_pass, "final_score": final_score, "has_deliverable": True,
                "detail": out[-1500:]}
    except subprocess.TimeoutExpired:
        return {"final_pass": False, "final_score": 0.0, "has_deliverable": True,
                "detail": f"test execution timed out after {CODE_TIMEOUT_SECONDS}s"}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def score_math(task: dict, final_text: str) -> dict:
    parsed = common.extract_final_numeric_answer(final_text)
    if parsed is None:
        return {"final_pass": False, "final_score": 0.0, "has_deliverable": False,
                "detail": "no numeric answer found in final assistant turn"}
    try:
        expected = float(task["answer"])
    except (TypeError, ValueError):
        expected = None
    tolerance = float(task.get("tolerance", 0.001))
    is_pass = expected is not None and abs(parsed - expected) <= tolerance
    return {"final_pass": bool(is_pass), "final_score": 1.0 if is_pass else 0.0,
            "has_deliverable": True, "detail": f"parsed={parsed} expected={expected} tol={tolerance}"}


def score_extract(task: dict, final_text: str) -> dict:
    parsed = common.extract_last_json_block(final_text)
    if parsed is None or not isinstance(parsed, dict):
        return {"final_pass": False, "final_score": 0.0, "has_deliverable": False,
                "detail": "no JSON object found in final assistant turn"}
    expected = task["expected"]
    exp_keys = set(expected.keys())
    got_keys = set(parsed.keys())
    correct = sum(1 for k in exp_keys if k in parsed and parsed[k] == expected[k])
    precision = (correct / len(got_keys)) if got_keys else 0.0
    recall = (correct / len(exp_keys)) if exp_keys else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    exact = parsed == expected
    return {"final_pass": bool(exact), "final_score": f1, "has_deliverable": True,
            "detail": f"correct={correct}/{len(exp_keys)} precision={precision:.3f} recall={recall:.3f}"}


SCORERS = {"code": score_code, "math": score_math, "extract": score_extract}


def score_dialogue(record: dict, task: dict) -> dict:
    turns = record["turns"]
    assistant_turns = [t for t in turns if t["role"] == "assistant"]
    if not assistant_turns:
        markers = common.compute_markers([], False)
        return {"final_pass": False, "final_score": 0.0, "per_turn": [None, None, None],
                "markers": markers}

    final_text = assistant_turns[-1]["content"]
    scorer = SCORERS[task["domain"]]
    result = scorer(task, final_text)

    markers = common.compute_markers([t["content"] for t in assistant_turns], result["has_deliverable"])
    per_turn = [None] * len(assistant_turns)
    if per_turn:
        per_turn[-1] = result["final_score"]

    return {
        "final_pass": result["final_pass"],
        "final_score": result["final_score"],
        "per_turn": per_turn,
        "markers": markers,
    }


def main():
    ap = argparse.ArgumentParser(description="Score TemperBench dialogue runs into a submission JSONL")
    ap.add_argument("runs_dir", help="directory of per-dialogue JSON files written by run.py")
    ap.add_argument("--out", required=True, help="output submission .jsonl path")
    args = ap.parse_args()

    runs_dir = Path(args.runs_dir)
    files = sorted(runs_dir.glob("*.json"))
    if not files:
        print(f"error: no .json files found in {runs_dir}", file=sys.stderr)
        sys.exit(1)

    tasks_by_id = {t["task_id"]: t for t in common.load_all_tasks()}

    n_ok = 0
    n_fail = 0
    with open(args.out, "w") as out_f:
        for fpath in files:
            with open(fpath, "r") as f:
                record = json.load(f)
            task = tasks_by_id.get(record["task_id"])
            if task is None:
                print(f"warning: unknown task_id {record['task_id']} in {fpath}, skipping", file=sys.stderr)
                n_fail += 1
                continue
            scores = score_dialogue(record, task)
            record["scores"] = scores
            out_f.write(json.dumps(record) + "\n")
            n_ok += 1
            status = "PASS" if scores["final_pass"] else "fail"
            print(f"{record['task_id']} {record['persona_id']} seed={record['seed']}: "
                  f"{status} (score={scores['final_score']:.3f})", file=sys.stderr)

    print(f"scored {n_ok} dialogues -> {args.out} ({n_fail} skipped)", file=sys.stderr)


if __name__ == "__main__":
    main()
