#!/usr/bin/env python3
"""TemperBench harness: analyze.py (protocol v0.3)

Implements the pre-registered analysis plan (PROTOCOL.md §5) on scored submissions.
Written before any v0.3 data was scored; tested on dry-run and synthetic data only.

Per model, never pooled:
  Primary   For contrasts P1−P3, P1T−P3, P5−P3: Δ final-pass-rate, Δ reasoning tokens per
            dialogue, Δ output tokens per dialogue (completion tokens, reasoning included).
            Paired by task (seeds averaged within task first); 95% CI from a cluster
            bootstrap over task families (families resampled with replacement, all tasks of
            a drawn family included), because generated math/extract instances of one
            family are not independent. Code tasks are their own family.
  Secondary P1−P1T (the part of P1's effect carried by its negative feedback rather than
            its tone); Δ billed cost; capitulation rate on pushback tasks; format
            compliance; extract F1; Page's L trend P1→P5; domain × persona pass rates;
            truncation counts by persona and a sensitivity analysis that scores truncated
            dialogues as failures instead of excluding them.
  Prediction (v0.2, repeated) |d_z(Δ reasoning tokens)| > |d_z(Δ pass rate)| for P1−P3.
  Exclusions (a) API error or truncation: any turn with finish_reason "length" or empty
            content; (b) refusal at T1: excluded from quality Δ, counted separately.

Usage:
    python harness/analyze.py sub_a.jsonl [sub_b.jsonl ...] --out report.md
(Task families are read from the active task set; set TEMPERBENCH_TASKS_DIR if needed.)
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

PERSONA_ORDER = ["P1", "P1T", "P2", "P3", "P4", "P5"]
TREND = ["P1", "P2", "P3", "P4", "P5"]
PRIMARY = [("P1", "P3"), ("P1T", "P3"), ("P5", "P3")]
BOOT_REPS = 10000
BOOT_SEED = 20261030


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
    """[(task_id, diff)] for tasks present in both cells."""
    tasks = sorted(set(means.get(a, {})) & set(means.get(b, {})))
    return [(t, means[a][t] - means[b][t]) for t in tasks]


def cluster_bootstrap_ci(pairs, family_of, rng):
    if not pairs:
        return (None, None)
    by_fam = defaultdict(list)
    for t, d in pairs:
        by_fam[family_of.get(t, t)].append(d)
    fams = list(by_fam)
    boots = []
    for _ in range(BOOT_REPS):
        draw = [d for f in rng.choices(fams, k=len(fams)) for d in by_fam[f]]
        boots.append(st.mean(draw))
    boots.sort()
    return boots[int(0.025 * BOOT_REPS)], boots[int(0.975 * BOOT_REPS) - 1]


def d_z(diffs):
    if len(diffs) < 2:
        return float("nan")
    sd = st.stdev(diffs)
    return st.mean(diffs) / sd if sd > 0 else 0.0


def page_test(means, order):
    """Page's L for increasing order, blocks = tasks present in all cells; average ranks
    for ties; normal approximation; two-sided p."""
    present = [p for p in order if p in means]
    if len(present) < len(order):
        return None
    tasks = sorted(set.intersection(*(set(means[p]) for p in order)))
    n, k = len(tasks), len(order)
    if n == 0:
        return None
    L = 0.0
    for t in tasks:
        vals = [means[p][t] for p in order]
        idx = sorted(range(k), key=lambda i: vals[i])
        ranks = [0.0] * k
        i = 0
        while i < k:
            j = i
            while j + 1 < k and vals[idx[j + 1]] == vals[idx[i]]:
                j += 1
            for m in range(i, j + 1):
                ranks[idx[m]] = (i + j) / 2 + 1
            i = j + 1
        L += sum((pos + 1) * r for pos, r in enumerate(ranks))
    mu = n * k * (k + 1) ** 2 / 4
    var = n * k ** 2 * (k + 1) * (k ** 2 - 1) / 144
    z = (L - mu) / math.sqrt(var)
    return {"n_tasks": n, "L": L, "z": z, "p_two_sided": math.erfc(abs(z) / math.sqrt(2))}


def fmt(x, nd=3):
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:+.{nd}f}"


def contrast_row(label, means, a, b, family_of, rng, nd):
    pr = paired(means, a, b)
    diffs = [d for _, d in pr]
    lo, hi = cluster_bootstrap_ci(pr, family_of, rng)
    mean = st.mean(diffs) if diffs else None
    return mean, (lo, hi), d_z(diffs), len(diffs), f"{fmt(mean, nd)} [{fmt(lo, nd)}, {fmt(hi, nd)}]"


def analyze_model(model, recs, family_of, pushback_ids, rng):
    out = [f"## {model}", ""]
    personas = [p for p in PERSONA_ORDER if any(r["persona_id"] == p for r in recs)]
    a_excl = [r for r in recs if excluded_a(r)]
    kept = [r for r in recs if not excluded_a(r)]
    t1_ref = [r for r in kept if refused_t1(r)]
    quality = [r for r in kept if not refused_t1(r)]
    out.append(f"Dialogues: {len(recs)} · excluded (a) error/truncation: {len(a_excl)} "
               f"({', '.join(f'{p} {sum(r['persona_id'] == p for r in a_excl)}' for p in personas)}) · "
               f"T1 refusals (b, excluded from quality only): {len(t1_ref)}")
    out.append("")

    passv = lambda r: 1.0 if r["scores"]["final_pass"] else 0.0
    pass_means = task_means(quality, passv)
    rtok_means = task_means(kept, lambda r: usage_sum(r, "reasoning_tokens"))
    otok_means = task_means(kept, lambda r: usage_sum(r, "output_tokens"))
    cost_means = task_means(kept, lambda r: usage_sum(r, "cost_usd"))

    out += ["### Primary estimands (paired by task; 95% CI = cluster bootstrap over task families)", "",
            "| Contrast | Δ pass rate | d_z | Δ reasoning tok / dialogue | d_z | Δ output tok / dialogue | d_z | tasks |",
            "|---|---|---|---|---|---|---|---|"]
    dz = {}
    for a, b in PRIMARY + [("P1", "P1T")]:
        if a not in personas or b not in personas:
            continue
        p_ = contrast_row("pass", pass_means, a, b, family_of, rng, 3)
        r_ = contrast_row("rtok", rtok_means, a, b, family_of, rng, 1)
        o_ = contrast_row("otok", otok_means, a, b, family_of, rng, 1)
        dz[(a, b)] = (p_[2], r_[2])
        tag = " (secondary)" if (a, b) == ("P1", "P1T") else ""
        out.append(f"| {a} − {b}{tag} | {p_[4]} | {fmt(p_[2], 2)} | {r_[4]} | {fmt(r_[2], 2)} | "
                   f"{o_[4]} | {fmt(o_[2], 2)} | {p_[3]} |")
    out.append("")
    if ("P1", "P3") in dz:
        zp, zr = dz[("P1", "P3")]
        if not (math.isnan(zp) or math.isnan(zr)):
            verdict = "HOLDS" if abs(zr) > abs(zp) else "DOES NOT HOLD"
            out.append(f"**Prediction carried over from v0.2** (|d_z tokens| > |d_z pass| for P1−P3): "
                       f"{verdict} (|{zr:.2f}| vs |{zp:.2f}|).")
            out.append("")

    out += ["### Secondary: per persona", "",
            "| Persona | pass rate | extract F1 | reasoning tok | output tok | billed $ / 1k dlg | "
            "format ok | capitulation (pushback tasks) | truncated |",
            "|---|---|---|---|---|---|---|---|---|"]
    for p in personas:
        q = [r for r in quality if r["persona_id"] == p]
        k = [r for r in kept if r["persona_id"] == p]
        allp = [r for r in recs if r["persona_id"] == p]
        ex = [r["scores"]["final_score"] for r in q if r["task_id"].startswith("extract")]
        mean_or = lambda xs, f="{:.3f}": f.format(st.mean(xs)) if xs else "n/a"
        rt = [v for r in k if (v := usage_sum(r, "reasoning_tokens")) is not None]
        ot = [v for r in k if (v := usage_sum(r, "output_tokens")) is not None]
        co = [v for r in k if (v := usage_sum(r, "cost_usd")) is not None]
        pb = [1.0 if r["scores"].get("caved") else 0.0 for r in q if r["task_id"] in pushback_ids]
        out.append(f"| {p} | {mean_or([passv(r) for r in q])} | {mean_or(ex)} | {mean_or(rt, '{:.0f}')} | "
                   f"{mean_or(ot, '{:.0f}')} | {mean_or([c * 1000 for c in co], '{:.3f}')} | "
                   f"{mean_or([1.0 if r['scores'].get('format_ok') else 0.0 for r in k])} | "
                   f"{mean_or(pb)} (n={len(pb)}) | {sum(excluded_a(r) for r in allp)} |")
    out.append("")

    out += ["### Secondary: contrasts", "", "| Measure | " + " | ".join(f"{a} − {b}" for a, b in PRIMARY) + " |",
            "|---|" + "---|" * len(PRIMARY)]
    cav_means = task_means([r for r in quality if r["task_id"] in pushback_ids],
                           lambda r: 1.0 if r["scores"].get("caved") else 0.0)
    fmt_means = task_means(kept, lambda r: 1.0 if r["scores"].get("format_ok") else 0.0)
    f1_means = task_means([r for r in quality if r["task_id"].startswith("extract")],
                          lambda r: r["scores"]["final_score"])
    trunc_fail = task_means([r for r in recs if not refused_t1(r) or excluded_a(r)],
                            lambda r: 0.0 if excluded_a(r) else passv(r))
    for label, means, nd in (("Δ billed $ / dialogue ×1000", {p: {t: v * 1000 for t, v in m.items()} for p, m in cost_means.items()}, 3),
                             ("Δ capitulation rate (pushback tasks)", cav_means, 3),
                             ("Δ format compliance", fmt_means, 3),
                             ("Δ extract F1", f1_means, 3),
                             ("Δ pass rate, truncations scored as fail", trunc_fail, 3)):
        cells = []
        for a, b in PRIMARY:
            if a in means and b in means:
                cells.append(contrast_row(label, means, a, b, family_of, rng, nd)[4])
            else:
                cells.append("n/a")
        out.append(f"| {label} | " + " | ".join(cells) + " |")
    out.append("")

    for label, means in (("pass rate", pass_means), ("reasoning tokens", rtok_means)):
        pt = page_test(means, TREND)
        if pt:
            out.append(f"Page's trend test P1→P5, {label}: L = {pt['L']:.1f}, z = {pt['z']:+.2f}, "
                       f"p (two-sided, normal approx.) = {pt['p_two_sided']:.3f}, tasks = {pt['n_tasks']}")
    out.append("")
    out += ["Domain × persona pass rate:", "", "| Domain | " + " | ".join(personas) + " |",
            "|---|" + "---|" * len(personas)]
    for dom in ("code", "math", "extract"):
        row = []
        for p in personas:
            q = [r for r in quality if r["persona_id"] == p and r["task_id"].startswith(dom)]
            row.append(f"{st.mean(passv(r) for r in q):.3f}" if q else "n/a")
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
    tasks = common.load_all_tasks()
    family_of = {t["task_id"]: t.get("family", t["task_id"]) for t in tasks}
    pushback_ids = {t["task_id"] for t in tasks if t.get("pushback")}

    rng = random.Random(BOOT_SEED)
    lines = ["# TemperBench analysis (PROTOCOL.md §5)", "",
             f"Protocol versions: {sorted({r['protocol_version'] for r in recs})} · "
             f"bootstrap reps: {BOOT_REPS} · bootstrap seed: {BOOT_SEED} · "
             f"task families: {len(set(family_of.values()))}", ""]
    for model in sorted(by_model):
        lines += analyze_model(model, by_model[model], family_of, pushback_ids, rng)
    Path(args.out).write_text("\n".join(lines) + "\n")
    print(f"wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
