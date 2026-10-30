#!/usr/bin/env python3
"""TemperBench harness: analyze.py

Implements the pre-registered analysis plan (PROTOCOL.md §5) on scored submissions.
Written before any pilot data was scored; tested on dry-run data only.

Per model, never pooled:
  Primary   Δ final-pass-rate and Δ reasoning tokens per dialogue, P1−P3 and P5−P3.
            Paired by task (seeds averaged within task first), bootstrap 95% CI over tasks.
  Secondary Page's L trend test across P1→P5; pass rate per 1k output tokens;
            behavioral-marker rates; domain × persona pass rates.
  Prediction |d_z(Δ reasoning tokens)| > |d_z(Δ pass rate)| for P1−P3, where d_z is the
            paired standardized mean difference over tasks (mean / sd of task diffs).
            §5 says "standardized terms" without naming a statistic; d_z is our reading.
  Exclusions (a) API error or truncation: any turn with finish_reason "length" or empty
            content; (b) refusal at T1: excluded from quality Δ, counted separately.

Usage:
    python harness/analyze.py sub_a.jsonl [sub_b.jsonl ...] --out report.md
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

PERSONAS = ["P1", "P2", "P3", "P4", "P5"]
BOOT_REPS = 10000
BOOT_SEED = 20261029


def load(paths):
    recs = []
    for path in paths:
        with open(path) as f:
            recs.extend(json.loads(line) for line in f if line.strip())
    return recs


def assistant_turns(rec):
    return [t for t in rec["turns"] if t["role"] == "assistant"]


def excluded_a(rec):
    return any(t.get("finish_reason") == "length" or not str(t.get("content", "")).strip()
               for t in assistant_turns(rec))


def refused_t1(rec):
    turns = assistant_turns(rec)
    return bool(turns) and bool(common.REFUSAL_RE.search(turns[0]["content"]))


def usage_sum(rec, key):
    vals = [(t.get("usage") or {}).get(key) for t in assistant_turns(rec)]
    if any(v is None for v in vals):
        return None
    return sum(vals)


def task_means(recs, value):
    """{persona: {task_id: mean over seeds}} for records where value(rec) is not None."""
    acc = defaultdict(lambda: defaultdict(list))
    for r in recs:
        v = value(r)
        if v is not None:
            acc[r["persona_id"]][r["task_id"]].append(v)
    return {p: {t: st.mean(vs) for t, vs in tasks.items()} for p, tasks in acc.items()}


def paired(means, a, b):
    tasks = sorted(set(means.get(a, {})) & set(means.get(b, {})))
    return [means[a][t] - means[b][t] for t in tasks]


def bootstrap_ci(diffs, rng):
    n = len(diffs)
    boots = sorted(st.mean(rng.choices(diffs, k=n)) for _ in range(BOOT_REPS))
    return boots[int(0.025 * BOOT_REPS)], boots[int(0.975 * BOOT_REPS) - 1]


def d_z(diffs):
    if len(diffs) < 2:
        return float("nan")
    sd = st.stdev(diffs)
    return st.mean(diffs) / sd if sd > 0 else 0.0


def page_test(means):
    """Page's L for increasing order P1<P2<...<P5, blocks = tasks present in all cells.
    Average ranks for ties; normal approximation (conservative-ish under ties). Two-sided p."""
    tasks = sorted(set.intersection(*(set(means.get(p, {})) for p in PERSONAS)))
    n, k = len(tasks), len(PERSONAS)
    if n == 0:
        return None
    L = 0.0
    for t in tasks:
        vals = [means[p][t] for p in PERSONAS]
        order = sorted(range(k), key=lambda i: vals[i])
        ranks = [0.0] * k
        i = 0
        while i < k:
            j = i
            while j + 1 < k and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            for m in range(i, j + 1):
                ranks[order[m]] = (i + j) / 2 + 1
            i = j + 1
        L += sum((pos + 1) * r for pos, r in enumerate(ranks))
    mu = n * k * (k + 1) ** 2 / 4
    var = n * k ** 2 * (k + 1) * (k ** 2 - 1) / 144
    z = (L - mu) / math.sqrt(var)
    p = math.erfc(abs(z) / math.sqrt(2))
    return {"n_tasks": n, "L": L, "z": z, "p_two_sided": p}


def fmt(x, nd=3):
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:+.{nd}f}"


def analyze_model(model, recs, rng):
    out = [f"## {model}", ""]
    n_total = len(recs)
    a_excl = [r for r in recs if excluded_a(r)]
    kept = [r for r in recs if not excluded_a(r)]
    t1_ref = [r for r in kept if refused_t1(r)]
    quality = [r for r in kept if not refused_t1(r)]
    out.append(f"Dialogues: {n_total} · excluded (a) error/truncation: {len(a_excl)} · "
               f"T1 refusals (b, excluded from quality only): {len(t1_ref)}")
    out.append("")

    pass_means = task_means(quality, lambda r: 1.0 if r["scores"]["final_pass"] else 0.0)
    rtok_means = task_means(kept, lambda r: usage_sum(r, "reasoning_tokens"))

    out += ["### Primary estimands (paired by task, bootstrap 95% CI over tasks)", "",
            "| Contrast | Δ pass rate | 95% CI | d_z | Δ reasoning tokens / dialogue | 95% CI | d_z | tasks |",
            "|---|---|---|---|---|---|---|---|"]
    dz = {}
    for a in ("P1", "P5"):
        dp = paired(pass_means, a, "P3")
        dr = paired(rtok_means, a, "P3")
        cp = bootstrap_ci(dp, rng) if dp else (None, None)
        cr = bootstrap_ci(dr, rng) if dr else (None, None)
        dz[a] = (d_z(dp), d_z(dr))
        out.append(f"| {a} − P3 | {fmt(st.mean(dp) if dp else None)} | [{fmt(cp[0])}, {fmt(cp[1])}] | "
                   f"{fmt(dz[a][0], 2)} | {fmt(st.mean(dr) if dr else None, 1)} | "
                   f"[{fmt(cr[0], 1)}, {fmt(cr[1], 1)}] | {fmt(dz[a][1], 2)} | {len(dp)} |")
    out.append("")
    zp, zr = dz["P1"]
    if not (math.isnan(zp) or math.isnan(zr)):
        verdict = "HOLDS" if abs(zr) > abs(zp) else "DOES NOT HOLD"
        out.append(f"**Pre-registered prediction** (|d_z tokens| > |d_z pass| for P1−P3): "
                   f"{verdict} (|{zr:.2f}| vs |{zp:.2f}|). Direction and CIs above decide whether "
                   f"either effect is distinguishable from zero.")
        out.append("")

    out += ["### Secondary", "", "| Persona | pass rate | reasoning tok / dialogue | output tok / dialogue | "
            "pass per 1k output tok | apologies / dlg | hedges / dlg | capitulation / dlg | tone commentary | final refusal |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for p in PERSONAS:
        q = [r for r in quality if r["persona_id"] == p]
        k = [r for r in kept if r["persona_id"] == p]
        if not k:
            continue
        pr = st.mean(1.0 if r["scores"]["final_pass"] else 0.0 for r in q) if q else float("nan")
        rt = [usage_sum(r, "reasoning_tokens") for r in k]
        ot = [usage_sum(r, "output_tokens") for r in k]
        rt_m = st.mean(v for v in rt if v is not None) if any(v is not None for v in rt) else float("nan")
        ot_m = st.mean(v for v in ot if v is not None) if any(v is not None for v in ot) else float("nan")
        mk = lambda f: st.mean(float(r["scores"]["markers"][f]) for r in k)
        out.append(f"| {p} | {pr:.3f} | {rt_m:.0f} | {ot_m:.0f} | {pr / (ot_m / 1000):.3f} | "
                   f"{mk('apologies'):.2f} | {mk('hedges'):.2f} | {mk('capitulation'):.2f} | "
                   f"{mk('tone_commentary'):.2f} | {mk('refusal'):.2f} |")
    out.append("")
    for label, means in (("pass rate", pass_means), ("reasoning tokens", rtok_means)):
        pt = page_test(means)
        if pt:
            out.append(f"Page's trend test P1→P5, {label}: L = {pt['L']:.1f}, z = {pt['z']:+.2f}, "
                       f"p (two-sided, normal approx.) = {pt['p_two_sided']:.3f}, tasks = {pt['n_tasks']}")
    out.append("")

    out += ["Domain × persona pass rate:", "", "| Domain | " + " | ".join(PERSONAS) + " |",
            "|---|" + "---|" * len(PERSONAS)]
    for dom in ("code", "math", "extract"):
        row = []
        for p in PERSONAS:
            q = [r for r in quality if r["persona_id"] == p and r["task_id"].startswith(dom)]
            row.append(f"{st.mean(1.0 if r['scores']['final_pass'] else 0.0 for r in q):.3f}" if q else "n/a")
        out.append(f"| {dom} | " + " | ".join(row) + " |")
    out.append("")
    cost = sum((t.get("usage") or {}).get("cost_usd") or 0 for r in recs for t in assistant_turns(r))
    if cost:
        out.append(f"Billed cost for this model's dialogues: ${cost:.4f}")
        out.append("")
    return out


def main():
    ap = argparse.ArgumentParser(description="Pre-registered TemperBench analysis (PROTOCOL.md §5)")
    ap.add_argument("submissions", nargs="+", help="scored submission JSONL files (score.py output)")
    ap.add_argument("--out", required=True, help="markdown report path")
    args = ap.parse_args()

    recs = load(args.submissions)
    by_model = defaultdict(list)
    for r in recs:
        if r.get("scores") is None:
            print(f"error: unscored record {r.get('run_id')} — run score.py first", file=sys.stderr)
            sys.exit(1)
        by_model[r["model"]].append(r)

    rng = random.Random(BOOT_SEED)
    lines = ["# TemperBench analysis (PROTOCOL.md §5)", "",
             f"Protocol versions: {sorted({r['protocol_version'] for r in recs})} · "
             f"bootstrap reps: {BOOT_REPS} · bootstrap seed: {BOOT_SEED}", ""]
    for model in sorted(by_model):
        lines += analyze_model(model, by_model[model], rng)
    Path(args.out).write_text("\n".join(lines) + "\n")
    print(f"wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
