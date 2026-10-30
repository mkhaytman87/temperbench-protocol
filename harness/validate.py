#!/usr/bin/env python3
"""TemperBench harness: validate.py

Validates a submission JSONL against the schema in submissions/SUBMISSIONS.md:
  - required top-level fields present on every record
  - manifest_sha256 matches the sha256 of the repo's MANIFEST.json
  - every (model, persona_id, seed) group reported includes all common-core tasks
  - every turn has non-empty content

Exits non-zero with a readable list of errors if anything fails.

Usage:
    python harness/validate.py my_submission.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

REQUIRED_TOP_FIELDS = [
    "protocol_version", "manifest_sha256", "run_id", "submitter", "model", "provider",
    "persona_id", "task_id", "seed", "temperature", "timestamp_utc", "turns", "scores", "env",
]

REQUIRED_SCORE_FIELDS = ["final_pass", "final_score", "per_turn", "markers"]
REQUIRED_MARKER_FIELDS = ["apologies", "hedges", "refusal", "tone_commentary", "capitulation"]


def validate_file(path: Path) -> list:
    errors = []
    records = []
    with open(path, "r") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append((lineno, json.loads(line)))
            except json.JSONDecodeError as exc:
                errors.append(f"line {lineno}: invalid JSON ({exc})")

    if not records:
        errors.append("no records found in submission file")
        return errors

    try:
        expected_manifest_sha = common.read_manifest_sha256()
    except FileNotFoundError as exc:
        errors.append(str(exc))
        expected_manifest_sha = None

    core_ids = set(common.core_task_ids())
    if len(core_ids) != 10:
        errors.append(f"expected exactly 10 core tasks in tasks/*.jsonl, found {len(core_ids)}")

    groups = {}  # (model, persona_id, seed) -> set of task_ids seen

    for lineno, rec in records:
        # 1. schema fields present
        for field in REQUIRED_TOP_FIELDS:
            if field not in rec:
                errors.append(f"line {lineno}: missing required field '{field}'")
        if "scores" in rec and rec["scores"] is not None:
            for field in REQUIRED_SCORE_FIELDS:
                if field not in rec["scores"]:
                    errors.append(f"line {lineno}: scores missing field '{field}'")
            markers = rec["scores"].get("markers", {})
            for field in REQUIRED_MARKER_FIELDS:
                if field not in markers:
                    errors.append(f"line {lineno}: scores.markers missing field '{field}'")
        else:
            errors.append(f"line {lineno}: 'scores' is missing or null (run harness/score.py first)")

        # 2. manifest hash matches
        if expected_manifest_sha is not None and rec.get("manifest_sha256") != expected_manifest_sha:
            errors.append(
                f"line {lineno}: manifest_sha256 mismatch "
                f"(record={rec.get('manifest_sha256')!r}, expected={expected_manifest_sha!r})"
            )

        # 3. turns non-empty
        for i, turn in enumerate(rec.get("turns", [])):
            content = turn.get("content")
            if not content or not str(content).strip():
                errors.append(f"line {lineno}: turns[{i}] has empty content")

        # gather for core-coverage check
        if all(k in rec for k in ("model", "persona_id", "seed", "task_id")):
            key = (rec["model"], rec["persona_id"], rec["seed"])
            groups.setdefault(key, set()).add(rec["task_id"])

    # 4. common-core coverage per (model, persona, seed) group
    for key, task_ids in groups.items():
        missing_core = core_ids - task_ids
        if missing_core:
            model, persona_id, seed = key
            errors.append(
                f"group model={model} persona={persona_id} seed={seed}: "
                f"missing {len(missing_core)}/10 core tasks: {sorted(missing_core)}"
            )

    return errors


def main():
    ap = argparse.ArgumentParser(description="Validate a TemperBench submission JSONL")
    ap.add_argument("submission", help="path to submission .jsonl file")
    args = ap.parse_args()

    path = Path(args.submission)
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        sys.exit(1)

    errors = validate_file(path)
    if errors:
        print(f"INVALID: {len(errors)} problem(s) found in {path}:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    print(f"OK: {path} is a valid TemperBench submission.", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
