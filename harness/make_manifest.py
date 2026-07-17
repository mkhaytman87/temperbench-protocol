#!/usr/bin/env python3
"""TemperBench harness: make_manifest.py

Writes MANIFEST.json at the protocol root, hashing personas/personas.json and each
tasks/*.jsonl file plus the protocol_version. harness/validate.py checks submissions'
manifest_sha256 against sha256(MANIFEST.json) to prove an unmodified protocol was run.

Usage:
    python harness/make_manifest.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def main():
    files = {}
    rel = common.PERSONAS_PATH.relative_to(common.PROTOCOL_ROOT)
    files[str(rel)] = common.sha256_file(common.PERSONAS_PATH)
    for domain in ("code", "math", "extract"):
        path = common.TASK_FILES[domain]
        rel = path.relative_to(common.PROTOCOL_ROOT)
        files[str(rel)] = common.sha256_file(path)

    manifest = {
        "protocol_version": common.protocol_version(),
        "files": files,
    }

    with open(common.MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")

    print(f"wrote {common.MANIFEST_PATH}")
    for k, v in files.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
