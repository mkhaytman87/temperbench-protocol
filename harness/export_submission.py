#!/usr/bin/env python3
"""TemperBench harness: export_submission.py

Copies a scored submission JSONL for publication: replaces the `submitter` field (run.py
defaults it to the local $USER) with a public handle, and writes it gzipped. Transcripts,
usage, scores and provider request IDs are kept: raw transcripts are the trust model
(PROTOCOL.md §6).

Usage:
    python harness/export_submission.py scored.jsonl --submitter HANDLE --out results/x.jsonl.gz
"""
import argparse
import gzip
import json

ap = argparse.ArgumentParser()
ap.add_argument("submission")
ap.add_argument("--submitter", required=True)
ap.add_argument("--out", required=True)
args = ap.parse_args()
n = 0
with open(args.submission) as f, gzip.open(args.out, "wt") as out:
    for line in f:
        if line.strip():
            rec = json.loads(line)
            rec["submitter"] = args.submitter
            out.write(json.dumps(rec) + "\n")
            n += 1
print(f"exported {n} records -> {args.out}")
