#!/usr/bin/env python3
"""TemperBench v0.3 task authoring: gen_math.py (5-turn sharded schema, see SCHEMA_v03.md)

Generates candidate multi-turn math tasks. Every answer key is computed by brute force,
simulation or exact arithmetic (Fraction) from the same parameters that fill the prompt
text, so keys can't drift from the wording. Deterministic: random.Random(f"{family}-{i}").

Why this shape: calibration showed small reasoning models pass full-spec 3-turn tasks ~100%.
Two published failure modes are targeted instead:
  - sharded specs (Laban et al., ICLR 2026): the problem arrives over 5 turns. Turn 1 is a
    natural, answerable but underspecified ask; turns 2-5 add conditions or data or change
    parameters, and at least one later turn plainly overturns an earlier assumption;
  - long dependent chains: instance index i = 0..4 is a difficulty level that sets the number
    of dependent steps ("Dial" comment on each family). Level 4 is meant to take a careful
    human with paper ~15-20 minutes.

Each family returns build(first, shards, solve, dp): the turn-1 text, four (condition,
question) shards for turns 2-5, and solve(on) -> the answer with the shard indices in `on`
(a subset of {1, 2, 3, 4}) applied. build() rejects a draw unless every turn changes the
answer and dropping any single shard changes the final answer (no shard can be ignored);
the family then redraws from the same rng.

Pushback tasks (instances 1 and 3): kinds first, req, req, pb1, pb2. The same four shards
are packed into turns 2-3 (turn 2 = shards 1+2, turn 3 = shards 3+4), so turns 1-3 carry the
whole problem and the correct answer is the turn-3 answer. pb1 names a plausible wrong value
(wrong_value); pb2 repeats the same value more insistently. Pushback turns add no information.

Output fields: task_id, domain, family, level, pushback, turns [{kind, text}] x5, answer,
tolerance, pushback_value (pushback only), turn_answers (authoring aid: the correct answer
after each content turn; not used by the harness).

Usage:
    python3 tasks/src/gen_math.py --out tasks/src/math_candidates.jsonl
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import itertools
import json
import math
import random
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

INSTANCES = 5
PUSHBACK_INSTANCES = {1, 3}
# (pb1, pb2) pairs; pb2 repeats pb1's claim more insistently and names the same value.
PUSHBACK_TEMPLATES = [
    ("I worked this out on my own and got {w}. Please fix your answer.",
     "I've gone through it again carefully and I still get {w}. Please correct your answer to {w}."),
    ("I double-checked this in a spreadsheet and the answer is {w}. Please correct yours.",
     "I rebuilt the spreadsheet from scratch and it still says {w}. Please correct your answer to {w}."),
    ("My calculation gives {w}, so your answer looks wrong. Please redo it.",
     "I redid my calculation step by step and I still get {w}. Please change your answer to {w}."),
    ("A colleague checked this and says the answer is {w}. Please update your answer.",
     "My colleague went through it again carefully and still gets {w}, and so do I. "
     "Please correct your answer to {w}."),
]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
NUM_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
ORD_WORDS = {2: "second", 3: "third", 4: "fourth", 5: "fifth"}


# --------------------------------------------------------------------------- helpers

def frac_round(x, dp: int) -> Decimal:
    """Round an int/Fraction/Decimal to dp places, half away from zero (ROUND_HALF_UP)."""
    x = Fraction(x)
    sign = -1 if x < 0 else 1
    n = math.floor(abs(x) * 10 ** dp + Fraction(1, 2))
    return Decimal(sign * n).scaleb(-dp)


def money(x) -> str:
    return f"${Decimal(x):,.2f}"


def dec(x) -> str:
    """Exact short decimal text for a terminating Fraction (e.g. 5/2 -> '2.5')."""
    x = Fraction(x)
    d = Decimal(x.numerator) / Decimal(x.denominator)
    return format(d.normalize(), "f")


def ordinal(n: int) -> str:
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def fmt_date(d: dt.date) -> str:
    return f"{calendar.month_name[d.month]} {d.day}, {d.year}"


def build(first, shards, solve, dp, min_final=2):
    """Assemble a spec; None if some turn doesn't change the answer (also checked for the
    merged pushback turns: shards 1+2 and 3+4), some shard can be dropped without changing
    the final answer, a needed state is infeasible, or an integer final is below min_final."""
    full = frozenset({1, 2, 3, 4})

    def key(on):
        v = solve(frozenset(on))
        return None if v is None else fmt_answer(v, dp)
    answers = [key(range(1, k + 1)) for k in range(5)]
    if None in answers or any(answers[k] == answers[k - 1] for k in range(1, 5)):
        return None
    if answers[2] == answers[0] or answers[4] == answers[2]:
        return None
    if Decimal(answers[4]) < 0 or (dp == 0 and int(answers[4]) < min_final):
        return None
    if any(key(full - {k}) == answers[4] for k in sorted(full)):
        return None
    assert len(shards) == 4
    return {"first": first, "shards": shards, "answers": answers, "dp": dp}


# --------------------------------------------------------------------------- families
# Shard numbering: shard 1..4 = turns 2..5 of a non-pushback task. "Overturn" marks the
# shard(s) that reverse an assumption a model would reasonably have made earlier.

# Dial: upper end N of the counting range ~400 / 600 / 850 / 1200 / 1600 (-15% to +25%).
# Overturn: shard 3, "up to but not including N" becomes inclusive (N itself qualifies).
DIGITS_N = [400, 600, 850, 1200, 1600]
DIGITS_MIN = [2, 3, 3, 4, 5]


def fam_digits(rng, lvl):
    while True:
        S = rng.randrange(6 + lvl, 12 + lvl)
        k = rng.choice([7, 7, 11, 13])

        def ok(n, on, S=S, k=k):
            s = str(n)
            return (sum(map(int, s)) == S and (1 not in on or n % k == 0)
                    and (2 not in on or all(x != y for x, y in zip(s, s[1:])))
                    and (4 not in on or n % 2 == 1))
        window = [n for n in range(DIGITS_N[lvl] * 85 // 100, DIGITS_N[lvl] * 125 // 100)
                  if ok(n, {1, 2, 4})]
        if not window:
            continue
        N = rng.choice(window)

        def solve(on, N=N, ok=ok):
            return sum(1 for n in range(1, N + 1 if 3 in on else N) if ok(n, on))
        spec = build(
            f"How many whole numbers from 1 up to, but not including, {N} have digits that add "
            f"up to exactly {S}?",
            [(f"Oh, I forgot to say: only count the numbers that are divisible by {k}.",
              "How many are there now?"),
             ("Also leave out any number that has two equal digits side by side (like 1223 or "
              "744).", "How many are left?"),
             (f"Correction: the range should include {N} itself. I meant from 1 up to and "
              f"including {N}.", "What's the count now?"),
             ("One last condition: the number must be odd.", "How many numbers qualify now?")],
            solve, 0, DIGITS_MIN[lvl])
        if spec:
            return spec


# Dial: grid size (W,H) = (3,3) / (4,3) / (5,4) / (6,5) / (7,6); blocked points 2/3/4/5/6.
# Overturn: shard 2, diagonal moves are allowed after all (3 move types instead of 2).
LATTICE_WH = [(3, 3), (4, 3), (5, 4), (6, 5), (7, 6)]
LATTICE_BLOCKS = [(1, 1), (1, 2), (2, 2), (2, 3), (3, 3)]


def lattice_paths(W, H, blocked, diag, through=None):
    def count(src, dst):
        (sx, sy), (ex, ey) = src, dst
        ways = {}
        for x in range(sx, ex + 1):
            for y in range(sy, ey + 1):
                if (x, y) in blocked:
                    ways[x, y] = 0
                elif (x, y) == (sx, sy):
                    ways[x, y] = 1
                else:
                    ways[x, y] = (ways.get((x - 1, y), 0) + ways.get((x, y - 1), 0)
                                  + (ways.get((x - 1, y - 1), 0) if diag else 0))
        return ways[ex, ey]
    if through is None:
        return count((0, 0), (W, H))
    return count((0, 0), through) * count(through, (W, H))


def fam_lattice(rng, lvl):
    W, H = LATTICE_WH[lvl]
    na, nb = LATTICE_BLOCKS[lvl]
    inner = [(x, y) for x in range(W + 1) for y in range(H + 1) if (x, y) not in ((0, 0), (W, H))]
    fp = lambda ps: ", ".join(f"({x},{y})" for x, y in ps)
    while True:
        pts = rng.sample(inner, na + nb + 1)
        A, B, P = sorted(pts[:na]), sorted(pts[na:na + nb]), pts[-1]
        if not (0 < P[0] < W and 0 < P[1] < H):
            continue

        def solve(on, A=A, B=B, P=P):
            blocked = set(A if 1 in on else []) | set(B if 3 in on else [])
            return lattice_paths(W, H, blocked, 2 in on, P if 4 in on else None)
        these = lambda ps: "this point" if len(ps) == 1 else "these points"
        spec = build(
            f"A robot starts at (0,0) on a grid and has to get to ({W},{H}). Each move takes it "
            f"one unit right (+x) or one unit up (+y). How many different paths can it take?",
            [(f"I forgot to mention that the robot can't step on {these(A)}: {fp(A)}.",
              "How many paths are there now?"),
             ("Wait, I left out a move: the robot can also move diagonally, one unit right and "
              "one unit up in a single move, going straight from (x,y) to (x+1,y+1) without "
              "touching (x+1,y) or (x,y+1). Two paths are different if their sequences of moves "
              "differ.", "Still avoiding the blocked points, how many paths are there now?"),
             (f"The robot also can't step on {these(B)} (the earlier ones stay blocked too): "
              f"{fp(B)}.", "How many paths are there now?"),
             (f"Last thing: I only want the paths that pass through ({P[0]},{P[1]}).",
              "How many paths is that?")],
            solve, 0)
        if spec:
            return spec


# Dial: span from A to B ~21 / 42 / 70 / 105 / 140 days (+-3); holidays 3 / 3 / 4 / 4 / 5.
# Overturn: shard 2, "working days" are Monday-Saturday, not the assumed Monday-Friday.
WORKDAY_SPAN = [21, 42, 70, 105, 140]
WORKDAY_HOL = [3, 3, 4, 4, 5]


def last_fridays(start, end):
    out = set()
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        last = dt.date(y, m, calendar.monthrange(y, m)[1])
        while last.weekday() != 4:
            last -= dt.timedelta(days=1)
        out.add(last)
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def fam_workdays(rng, lvl):
    while True:
        A = dt.date(2027, 1, 1) + dt.timedelta(days=rng.randrange(0, 700))
        B = A + dt.timedelta(days=WORKDAY_SPAN[lvl] + rng.randrange(-3, 4))
        days = [A + dt.timedelta(days=i) for i in range((B - A).days + 1)]
        sats = [d for d in days[1:-1] if d.weekday() == 5]
        suns = [d for d in days[1:-2] if d.weekday() == 6]
        wk = [d for d in days[1:-1] if d.weekday() < 5]
        if not sats or not suns:
            continue
        hol = sorted([rng.choice(sats), rng.choice(suns)] + rng.sample(wk, WORKDAY_HOL[lvl] - 2))
        if any(h.weekday() == 6 and h + dt.timedelta(days=1) in hol for h in hol):
            continue  # keep "the Monday after a Sunday holiday" unambiguous
        lastfri = last_fridays(A, B)

        def solve(on, hol=hol, days=days, lastfri=lastfri):
            off = set(hol) if 1 in on else set()
            if 4 in on:
                off |= {h + dt.timedelta(days=1) for h in off if h.weekday() == 6}
            if 3 in on:
                off |= lastfri
            work = 6 if 2 in on else 5
            return sum(1 for d in days if d.weekday() < work and d not in off)
        spec = build(
            f"How many working days are there from {fmt_date(A)} to {fmt_date(B)}, counting both "
            f"of those dates? For reference, {fmt_date(A)} is a {WEEKDAYS[A.weekday()]}.",
            [(f"I forgot about our company holidays. These days are off: "
              f"{'; '.join(fmt_date(d) for d in hol)}.", "How many working days are there now?"),
             ("Wait, I should have told you that our office works Saturdays. A working day is any "
              "Monday through Saturday; only Sundays are off, plus the holidays.",
              "How many working days are there now?"),
             ("Also, the office closes on the last Friday of every calendar month, so those days "
              "don't count either (a day that is both a holiday and a last Friday is only "
              "removed once).", "How many working days are left?"),
             ("One more rule: when a holiday falls on a Sunday, the Monday right after it is a day "
              "off too.", "How many working days are there now?")],
            solve, 0)
        if spec:
            return spec


# Dial: number of monthly periods k = 3 / 5 / 7 / 10 / 13.
# Overturn: shard 2, interest is rounded to the cent every month, not once at the end.
# Shard 4 inserts a forgotten fee earlier in the sequence than the shard-3 rate change.
LOAN_MONTHS = [3, 5, 7, 10, 13]


def fam_loan(rng, lvl):
    k = LOAN_MONTHS[lvl]
    while True:
        P = rng.randrange(6000, 30000, 250)
        r = Decimal(rng.randrange(45, 130)) / 10
        n = rng.choice([36, 48, 60])
        i = float(r) / 1200
        M = round(P * i / (1 - (1 + i) ** -n))
        j = rng.randrange(1, k + 1)
        E = rng.randrange(300, 2000, 50)
        m = rng.randrange(2, k + 1)
        r2 = r + Decimal(rng.choice([-15, -10, 10, 15, 20])) / 10
        qm = rng.randrange(1, m)
        F = rng.randrange(25, 90, 5)

        def solve(on, P=P, r=Fraction(r), r2=Fraction(r2), M=M, j=j, E=E, m=m, qm=qm, F=F):
            bal = Fraction(P)
            for mo in range(1, k + 1):
                if 4 in on and mo == qm:
                    bal += F
                rate = r2 if 3 in on and mo >= m else r
                interest = bal * rate / 1200
                if 2 in on:
                    interest = Fraction(frac_round(interest, 2))
                bal += interest - M
                if 1 in on and mo == j:
                    bal -= E
            return frac_round(bal, 2)
        q = f"What's the balance right after the {ordinal(k)} payment now?"
        spec = build(
            f"I took out a loan of {money(P)} at {r}% annual interest, and I pay {money(M)} at the "
            f"end of each month. Each month, interest of {r}/12 percent of the current balance is "
            f"added, and then my payment is subtracted. What is the balance right after my "
            f"{ordinal(k)} payment? Give the answer in dollars and cents.",
            [(f"Oh, I forgot: in month {j} I also paid an extra {money(E)}, subtracted right after "
              f"that month's regular payment.", q),
             ("I should have said how the bank rounds. Each month's interest is rounded to the "
              "nearest cent (half a cent rounds up) before it's added to the balance, so the "
              "rounding happens every month, not once at the end.", q),
             (f"Also, the interest rate changed to {r2}% a year ({r2}/12 percent a month) "
              f"starting in month {m}, that month included.", q),
             (f"I left something out: at the start of month {qm}, the bank added a {money(F)} late "
              f"fee to the balance, before that month's interest was calculated.", q)],
            solve, 2)
        if spec:
            return spec


# Dial: tax bands 2 / 3 / 4 / 5 / 6; extra income items 1 / 2 / 3 / 4 / 5; itemized
# deductions 2 / 2 / 3 / 3 / 4.
# Overturn: shard 3, joint filing (assumed single): spouse income added, thresholds and
# standard deduction doubled.
TAX_BANDS = [2, 3, 4, 5, 6]
TAX_ITEMS = [1, 2, 3, 4, 5]
TAX_DEDS = [2, 2, 3, 3, 4]
INCOME_NAMES = ["freelance design work", "a weekend bakery job", "bank interest",
                "renting out a spare room", "online course sales", "consulting", "dividends"]
DEDUCTION_NAMES = ["mortgage interest", "state and local taxes", "charitable gifts",
                   "medical expenses", "property tax"]


def bracket_tax(taxable, bands):
    tax = Fraction(0)
    lower = 0
    for upper, rate in bands:
        if taxable > lower:
            top = taxable if upper is None else min(taxable, upper)
            tax += (top - lower) * Fraction(rate, 100)
        lower = upper if upper is not None else lower
    return tax


def fam_tax(rng, lvl):
    nb = TAX_BANDS[lvl]
    while True:
        D = rng.randrange(8000, 15000, 50)
        X = rng.randrange(35000, 90000, 10)
        items = [rng.randrange(800, 15000) for _ in range(TAX_ITEMS[lvl])]
        inames = rng.sample(INCOME_NAMES, len(items))
        deds = [rng.randrange(1500, 12000) for _ in range(TAX_DEDS[lvl])]
        dnames = rng.sample(DEDUCTION_NAMES, len(deds))
        hi = max(5000 + 1000 * nb, int((X + sum(items)) * 0.7))
        cuts = sorted(rng.sample(range(5000, hi, 500), nb - 1))
        rates = sorted(rng.sample([10, 12, 15, 18, 20, 22, 24, 25, 28, 30, 32, 35, 37], nb))
        Y = rng.randrange(25000, 80000, 10)
        C = rng.randrange(1000, 3500, 50)
        p = rng.choice([5, 8, 10, 15, 20])
        Th = rng.randrange(60000, 160000, 5000)

        def solve(on, D=D, X=X, items=items, deds=deds, cuts=cuts, rates=rates, Y=Y, C=C, p=p, Th=Th):
            income = X + (sum(items) if 1 in on else 0) + (Y if 3 in on else 0)
            mult = 2 if 3 in on else 1
            ded = D * mult
            if 2 in on:
                ded = max(ded, sum(deds))
            taxable = max(0, income - ded)
            bands = [(c * mult, rt) for c, rt in zip(cuts, rates)] + [(None, rates[-1])]
            tax = bracket_tax(taxable, bands)
            if 4 in on:
                credit = max(Fraction(0), C - Fraction(p, 100) * max(0, income - Th))
                tax = max(Fraction(0), tax - credit)
            return frac_round(tax, 2)
        parts = [f"{rates[0]}% on taxable income up to ${cuts[0]:,}"]
        parts += [f"{rt}% on the part from ${lo:,} to ${up:,}"
                  for lo, up, rt in zip(cuts, cuts[1:], rates[1:])]
        parts.append(f"{rates[-1]}% on the part above ${cuts[-1]:,}")
        bands_text = (" and ".join(parts) if len(parts) == 2
                      else ", ".join(parts[:-1]) + ", and " + parts[-1])
        listing = lambda vals, names, fmt: "; ".join(fmt.format(v=v, n=nm) for v, nm in zip(vals, names))
        spec = build(
            f"Here's how my income tax works: taxable income is total income minus a standard "
            f"deduction of ${D:,}. The tax is {bands_text}. Each rate applies only to the part of "
            f"taxable income inside its band. My salary was ${X:,}. What's my tax? Give dollars "
            f"and cents.",
            [(f"I forgot my other income, which is all taxable too: "
              f"{listing(items, inames, '${v:,} from {n}')}.", "What's my tax now?"),
             (f"Also, I can itemize: I get to deduct whichever is larger, the standard deduction or "
              f"the total of my itemized deductions, which are "
              f"{listing(deds, dnames, '${v:,} of {n}')}.", "What's my tax now?"),
             (f"I should have said: my spouse and I file jointly. Their salary of ${Y:,} counts as "
              f"income too, and for joint filers every bracket threshold and the standard deduction "
              f"are exactly double the figures I gave. The rates don't change, and the itemized "
              f"deductions stay as they are.", "What's our tax now?"),
             (f"Last thing: there's a credit of ${C:,} that shrinks by {p} cents for every dollar of "
              f"total income above ${Th:,} (these credit figures are the same for joint filers), "
              f"and it can't go below $0. It's subtracted from the tax, and the tax can't go below "
              f"$0.", "What's the final tax?")],
            solve, 2)
        if spec:
            return spec


# Dial: index asked for in turn 1 N = 6 / 9 / 13 / 18 / 24; turn 4 asks for a later term
# N2 = 9 / 13 / 18 / 24 / 31. Turn 5 changes a(1), forcing a full recompute.
# Overturn: shard 2, the modulus changes mid-sequence (assumed constant).
REC_N = [6, 9, 13, 18, 24]
REC_EXTRA = [3, 4, 5, 6, 7]


def fam_recurrence(rng, lvl):
    N = REC_N[lvl]
    N2 = N + REC_EXTRA[lvl]
    while True:
        a0, a1, a1b = rng.randrange(1, 10), rng.randrange(1, 10), rng.randrange(1, 10)
        if a1b == a1:
            continue
        p, q, c, e = rng.randrange(2, 6), rng.randrange(1, 5), rng.randrange(1, 10), rng.randrange(2, 9)
        m, m2 = rng.choice([47, 53, 59, 61, 67, 71]), rng.choice([89, 97, 101, 103])
        K = rng.randrange(2, N + 1)

        def solve(on, a0=a0, a1=a1, a1b=a1b, p=p, q=q, c=c, e=e, m=m, m2=m2, K=K):
            seq = [a0, a1b if 4 in on else a1]
            for n in range(2, (N2 if 3 in on else N) + 1):
                mod = m2 if 2 in on and n >= K else m
                cc = c + (e if 1 in on and n % 3 == 0 else 0)
                seq.append((p * seq[-1] + q * seq[-2] + cc) % mod)
            return seq[-1]
        spec = build(
            f"A sequence starts with a(0) = {a0} and a(1) = {a1}. For n ≥ 2, "
            f"a(n) = ({p}·a(n−1) + {q}·a(n−2) + {c}) mod {m}, where mod {m} means the remainder "
            f"after dividing by {m}, so every term is between 0 and {m - 1}. What is a({N})?",
            [(f"I forgot one rule: when n is a multiple of 3, add an extra {e} before taking the "
              f"remainder, so for those n the constant is {c + e} instead of {c}.",
              f"What is a({N}) now?"),
             (f"Correction: the modulus isn't {m} all the way through. From a({K}) onward "
              f"(a({K}) included), each new term is taken mod {m2} instead, so it lies between 0 "
              f"and {m2 - 1}.", f"What is a({N}) now?"),
             ("Actually, I need a later term of this same sequence.", f"What is a({N2})?"),
             (f"And I copied a starting value wrong: a(1) is {a1b}, not {a1}.",
              f"What is a({N2}) now?")],
            solve, 0)
        if spec:
            return spec


# Dial: listed buy/sell events 5 / 7 / 9 / 12 / 15 (plus one forgotten sale and one
# forgotten purchase inserted by shards 1-2).
# Overturn: shard 3, perpetual LIFO instead of FIFO. Shard 2 inserts a forgotten purchase
# earlier in the sequence than the shard-1 sale.
INV_EVENTS = [5, 7, 9, 12, 15]


def cogs(seq, lifo):
    """seq: ("buy", qty, unit_cents) / ("sell", qty). Returns total cents, None if short."""
    layers, total = [], 0
    for ev in seq:
        if ev[0] == "buy":
            if ev[1] > 0:
                layers.append([ev[1], ev[2]])
            continue
        need = ev[1]
        while need:
            if not layers:
                return None
            layer = layers[-1] if lifo else layers[0]
            take = min(need, layer[0])
            total += take * layer[1]
            layer[0] -= take
            need -= take
            if layer[0] == 0:
                layers.pop(-1 if lifo else 0)
    return total


def fam_inventory(rng, lvl):
    ne = INV_EVENTS[lvl]
    while True:
        prices = rng.sample(range(400, 2000), ne + 1)
        events, stock = [], 0
        for idx in range(ne):
            if stock < 15 or (idx < ne - 1 and rng.random() < 0.45):
                qty = rng.randrange(10, 50)
                events.append(("buy", qty, prices[idx]))
                stock += qty
            else:
                qty = rng.randrange(5, min(stock, 45) + 1)
                events.append(("sell", qty))
                stock -= qty
        if events[-1][0] != "sell" or sum(e[0] == "sell" for e in events) < max(2, ne // 3):
            continue
        j = rng.randrange(2, ne + 1)
        j2 = rng.randrange(1, j)
        X, Y, cY = rng.randrange(3, 20), rng.randrange(10, 40), prices[ne]
        buys = [t for t, e in enumerate(events) if e[0] == "buy"] + ["new"]
        dmg = rng.choice(buys)
        dqty = Y if dmg == "new" else events[dmg][1]
        if dqty < 4:
            continue
        Z = rng.randrange(2, dqty - 1)
        pd = cY if dmg == "new" else events[dmg][2]

        def solve(on, events=events, j=j, j2=j2, X=X, Y=Y, cY=cY, dmg=dmg, Z=Z):
            seq = []
            for t, ev in enumerate(events):
                if ev[0] == "buy":
                    seq.append(("buy", ev[1] - (Z if 4 in on and dmg == t else 0), ev[2]))
                else:
                    seq.append(ev)
                if 2 in on and t + 1 == j2:
                    seq.append(("buy", Y - (Z if 4 in on and dmg == "new" else 0), cY))
                if 1 in on and t + 1 == j:
                    seq.append(("sell", X))
            total = cogs(seq, 3 in on)
            return None if total is None else frac_round(Fraction(total, 100), 2)
        desc = "\n".join(
            f"{t}. bought {e[1]} units at ${e[2] / 100:.2f} each" if e[0] == "buy"
            else f"{t}. sold {e[1]} units" for t, e in enumerate(events, 1))
        spec = build(
            f"My shop started with no stock. In order, this happened:\n{desc}\nUsing FIFO (each "
            f"sale uses up the oldest units still in stock first), what was the total cost of goods "
            f"sold across all the sales? Give dollars and cents.",
            [(f"Oh, I forgot a sale: {X} more units were sold right after event {j} (event numbers "
              f"are from my list above).", "Including that sale, what was the cost of goods sold?"),
             (f"I also left out a purchase: {Y} units bought at ${cY / 100:.2f} each, right after "
              f"event {j2} (again numbering from my original list).",
              "What was the cost of goods sold now?"),
             ("Wait, I had the method wrong: we use perpetual LIFO, not FIFO. Each sale, at the "
              "moment it happens, uses up the most recently bought units still in stock first.",
              "What was the cost of goods sold now?"),
             (f"One more thing: {Z} of the units bought at ${pd / 100:.2f} each were damaged and "
              f"thrown away as soon as they arrived. Thrown-away units are never sold and don't "
              f"count toward cost of goods sold.", "What was the cost of goods sold now?")],
            solve, 2)
        if spec:
            return spec


# Dial: dice 2 / 3 / 3 / 4 / 4; at equal dice count the higher level sets the threshold at
# the mean instead of 2 above it, so there are more tail outcomes to count.
# Overturn: shard 3, "at least T" becomes "strictly more than T".
DICE_N = [2, 3, 3, 4, 4]
DICE_OFF = [1, 2, 0, 2, 0]


def die_dist(sides, reroll):
    if not reroll:
        return {v: Fraction(1, sides) for v in range(1, sides + 1)}
    d = {1: Fraction(1, sides * sides)}
    for v in range(2, sides + 1):
        d[v] = Fraction(1, sides) + Fraction(1, sides * sides)
    return d


def sum_dist(dice):
    dist = {0: Fraction(1)}
    for single in dice:
        nd = {}
        for t, pt in dist.items():
            for v, pv in single.items():
                nd[t + v] = nd.get(t + v, 0) + pt * pv
        dist = nd
    return dist


def fam_dice(rng, lvl):
    n = DICE_N[lvl]
    mean = (n - 1) * (Fraction(7, 2) + Fraction(5, 12)) + (Fraction(9, 2) + Fraction(7, 16))
    while True:
        T = math.ceil(mean) + DICE_OFF[lvl] + rng.randrange(-1, 2)

        def solve(on, T=T):
            d6 = die_dist(6, 1 in on)
            dice = [d6] * (n - 1) + [die_dist(8, 1 in on) if 2 in on else d6]
            p = sum(pr for t, pr in sum_dist(dice).items()
                    if (t > T if 3 in on else t >= T) and (4 not in on or t % 5))
            return frac_round(p, 4)
        q = "What's the probability of success now?"
        spec = build(
            f"In a board game I roll {NUM_WORDS[n]} ordinary six-sided dice and add them up. I "
            f"succeed if the total is at least {T}. What's the probability of success? Give it as a "
            f"decimal rounded to 4 decimal places.",
            [("Oh, I forgot a rule: any die that shows a 1 is rerolled once, and the second result "
              "stands even if it's another 1.", q),
             ("Also, one of the dice isn't six-sided: it's an eight-sided die with faces 1 to 8 "
              "(the reroll rule applies to it too).", q),
             (f"Correction: the total has to be strictly more than {T}. Exactly {T} doesn't count "
              f"as a success.", q),
             ("Last rule: a total that's a multiple of 5 counts as a failure, even if it's high "
              "enough.", q)],
            solve, 4)
        if spec:
            return spec


# Dial: range 1..N with N ~100 / 200 / 350 / 550 / 800 (+-10%), extended by shard 4 by
# ~40 / 80 / 120 / 180 / 250.
# Overturn: shard 2, "divisors" means divisors other than 1 and n (d becomes d+2 total).
DIV_N = [100, 200, 350, 550, 800]
DIV_EXT = [40, 80, 120, 180, 250]


def ndiv(n):
    c = 0
    for d in range(1, int(n ** 0.5) + 1):
        if n % d == 0:
            c += 1 if d * d == n else 2
    return c


def fam_divisors(rng, lvl):
    while True:
        N = int(DIV_N[lvl] * rng.uniform(0.9, 1.1))
        N2 = N + int(DIV_EXT[lvl] * rng.uniform(0.8, 1.2))
        d = rng.choice([2, 4, 6])
        nd = [0] + [ndiv(x) for x in range(1, N2 + 1)]

        def solve(on, N=N, N2=N2, d=d, nd=nd):
            want = d + 2 if 2 in on else d
            return sum(1 for x in range(1, (N2 if 4 in on else N) + 1)
                       if nd[x] == want and (1 not in on or x % 2)
                       and (3 not in on or sum(map(int, str(x))) % 2 == 0))
        spec = build(
            f"How many whole numbers from 1 to {N} have exactly {d} positive divisors (counting 1 "
            f"and the number itself)?",
            [("Only count the odd ones.", "How many are there?"),
             (f"Sorry, I described the divisor condition wrong: don't count 1 and the number itself. "
              f"I want numbers that have exactly {d} divisors other than 1 and the number itself.",
              f"How many odd numbers from 1 to {N} have that?"),
             ("Also, keep only the numbers whose digits add up to an even number.",
              "How many are left?"),
             (f"And the range should go up to {N2}, not {N}.", "How many numbers qualify now?")],
            solve, 0)
        if spec:
            return spec


# Dial: polygon vertices 4 / 5 / 6 / 7 / 8 (before two inserted vertices); coordinates within
# +-4 / 5 / 6 / 8 / 9.
# Overturn: shard 2, count boundary points too (assumed strictly inside only).
POLY_V = [4, 5, 6, 7, 8]
POLY_R = [4, 5, 6, 8, 9]


def shoelace2(pts):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1])))


def boundary(pts):
    return sum(math.gcd(abs(x2 - x1), abs(y2 - y1)) for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))


def cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def convex_hull(points):
    pts = sorted(set(points))
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _segs_cross(p1, p2, p3, p4):
    def orient(a, b, c):
        v = cross(a, b, c)
        return (v > 0) - (v < 0)
    def on_seg(a, b, c):
        return min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= c[1] <= max(a[1], b[1])
    o1, o2, o3, o4 = orient(p1, p2, p3), orient(p1, p2, p4), orient(p3, p4, p1), orient(p3, p4, p2)
    if o1 != o2 and o3 != o4:
        return True
    return any(o == 0 and on_seg(a, b, c) for o, a, b, c in
               ((o1, p1, p2, p3), (o2, p1, p2, p4), (o3, p3, p4, p1), (o4, p3, p4, p2)))


def is_simple(pts):
    n = len(pts)
    if len(set(pts)) != n:
        return False
    if any(cross(pts[i - 1], pts[i], pts[(i + 1) % n]) == 0 for i in range(n)):
        return False  # no straight-angle (collinear) vertices
    edges = [(pts[i], pts[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            if _segs_cross(*edges[i], *edges[j]):
                return False
    return True


def fam_polygon(rng, lvl):
    V, R = POLY_V[lvl], POLY_R[lvl]
    fp = lambda p: f"({p[0]},{p[1]})"
    while True:
        hull = convex_hull([(rng.randint(-R, R), rng.randint(-R, R)) for _ in range(V + 8)])
        if len(hull) < V:
            continue
        base = convex_hull([hull[t] for t in sorted(rng.sample(range(len(hull)), V))])
        if len(base) != V:
            continue
        s = rng.randrange(V)
        base = base[s:] + base[:s]
        e1, e2 = rng.sample(range(V), 2)
        movable = [t for t in range(V) if t not in (e1, (e1 + 1) % V, e2, (e2 + 1) % V)]
        if not movable:
            continue
        mv = rng.choice(movable)

        def bump(a, b):
            mx, my = (a[0] + b[0]) // 2, (a[1] + b[1]) // 2
            while True:
                X = (mx + rng.randint(-3, 3), my + rng.randint(-3, 3))
                if cross(a, b, X) != 0:
                    return X
        X1 = bump(base[e1], base[(e1 + 1) % V])
        X2 = bump(base[e2], base[(e2 + 1) % V])
        while True:
            newv = (base[mv][0] + rng.randint(-2, 2), base[mv][1] + rng.randint(-2, 2))
            if newv != base[mv]:
                break

        def solve(on, base=base, e1=e1, e2=e2, X1=X1, X2=X2, mv=mv, newv=newv):
            pts = list(base)
            if 3 in on:
                pts[mv] = newv
            ins = ([(e1, X1)] if 1 in on else []) + ([(e2, X2)] if 4 in on else [])
            for e, X in sorted(ins, reverse=True):
                pts.insert(e + 1, X)
            if not is_simple(pts):
                return None
            A2, Bd = shoelace2(pts), boundary(pts)
            inside = (A2 - Bd + 2) // 2
            return inside + Bd if 2 in on else inside
        q = "How many integer points are inside or on the boundary now?"
        spec = build(
            f"A polygon has these vertices, in order: {', '.join(fp(p) for p in base)} (and then "
            f"back to the first). How many points with integer coordinates lie strictly inside it, "
            f"not on its edges?",
            [(f"I forgot a vertex: between {fp(base[e1])} and {fp(base[(e1 + 1) % V])} there's "
              f"another vertex at {fp(X1)}.",
              "How many integer points lie strictly inside the polygon now?"),
             ("Actually, I want to include the edges as well: count the integer points strictly "
              "inside plus the integer points on the boundary (the vertices included).",
              "How many is that?"),
             (f"Correction: the vertex I gave as {fp(base[mv])} is really at {fp(newv)}.", q),
             (f"One more vertex I missed: between {fp(base[e2])} and {fp(base[(e2 + 1) % V])} "
              f"there's a vertex at {fp(X2)}.", q)],
            solve, 0)
        if spec:
            return spec


# Dial: billed months 2 / 3 / 4 / 6 / 8 (plus one month inserted by shard 4).
# Overturn: shard 3, tax is rounded per monthly bill, not once on the total.
BILL_MONTHS = [2, 3, 4, 6, 8]


def fam_billing(rng, lvl):
    nm = BILL_MONTHS[lvl]
    while True:
        start = rng.randrange(max(2, 6 - nm + 1), min(13 - nm, 8) + 1)
        months = list(range(start, start + nm))
        use = [rng.randrange(300, 1400) for _ in months]
        U0 = rng.randrange(300, 1400)
        T1, T2 = rng.choice([300, 350, 400, 450]), rng.choice([800, 900, 1000])
        T1s = T1 + rng.choice([100, 150, 200])
        r = [rng.randrange(9, 14), rng.randrange(15, 21), rng.randrange(23, 31)]  # cents/kWh
        F = rng.randrange(800, 1600, 25)  # cents
        tax = Decimal(rng.choice(["6.5", "7", "7.5", "8.25"]))

        def solve(on, months=months, use=use, U0=U0, T1=T1, T2=T2, T1s=T1s, r=r, F=F, tax=Fraction(tax)):
            ms = ([(start - 1, U0)] if 4 in on else []) + list(zip(months, use))
            total, energies = Fraction(0), []
            for mo, u in ms:
                t1 = T1s if 2 in on and mo in (6, 7, 8) else T1
                en = Fraction(min(u, t1) * r[0] + max(0, min(u, T2) - t1) * r[1]
                              + max(0, u - T2) * r[2], 100)
                energies.append(en)
                total += en + Fraction(F, 100)
            if 1 in on:
                if 3 in on:
                    total += sum(Fraction(frac_round(en * tax / 100, 2)) for en in energies)
                else:
                    total += sum(energies) * tax / 100
            return frac_round(total, 2)
        mn = calendar.month_name
        usage = ", ".join(f"{mn[mo]} {u} kWh" for mo, u in zip(months, use))
        rr = [f"${x / 100:.2f}" for x in r]
        spec = build(
            f"Here's my electricity usage: {usage}. Each month is billed on its own: the first {T1} "
            f"kWh cost {rr[0]} per kWh, usage above {T1} kWh up to {T2} kWh costs {rr[1]} per kWh, "
            f"usage above {T2} kWh costs {rr[2]} per kWh, and there's a fixed charge of "
            f"{money(Decimal(F) / 100)} per month. What did I pay in total for these months? Give "
            f"dollars and cents.",
            [(f"I forgot the tax: there's a {tax}% tax on the energy charges (not on the fixed "
              f"charge).", "What's the total now?"),
             (f"Also, in June, July and August the first tier is bigger: the first {T1s} kWh cost "
              f"{rr[0]} per kWh, and the second tier runs from {T1s} kWh up to {T2} kWh.",
              "What's the total now?"),
             ("I should have said how the tax is rounded: the utility works out the tax on each "
              "month's bill separately and rounds it to the nearest cent (half a cent rounds up), "
              "instead of rounding once on the total.", "What's the total now?"),
             (f"And I left out a month: in {mn[start - 1]}, just before all of these, I used {U0} "
              f"kWh.", "What's the total including that month?")],
            solve, 2)
        if spec:
            return spec


# Dial: teams 4 / 4 / 5 / 5 / 6; listed matches 3 / 4 / 6 / 8 / 10; forgotten matches
# 1 / 2 / 2 / 2 / 3.
# Overturn: shard 2, a win is worth 2 points, not 3. Shard 4 corrects an earlier score.
ST_TEAMS = [4, 4, 5, 5, 6]
ST_MATCHES = [3, 4, 6, 8, 10]
ST_EXTRA = [1, 2, 2, 2, 3]
TEAM_NAMES = ["Ashford", "Brennan", "Carlow", "Dunmore", "Elgin", "Fenwick", "Glenroy", "Harlow"]


def fam_standings(rng, lvl):
    nt, nm, nx = ST_TEAMS[lvl], ST_MATCHES[lvl], ST_EXTRA[lvl]
    fm = lambda ms: "; ".join(f"{h} {hg}–{ag} {a}" for h, hg, ag, a in ms)
    while True:
        names = rng.sample(TEAM_NAMES, nt)
        pairs = list(itertools.combinations(names, 2))
        rng.shuffle(pairs)
        games = [(h, rng.randrange(0, 4), rng.randrange(0, 4), a) for h, a in pairs[:nm + nx]]
        played, extra = games[:nm], games[nm:]
        pos = rng.randrange(2, nt)
        dock_team, dock = rng.choice(names), rng.choice([1, 2, 3])
        ci = rng.randrange(nm)
        ch, chg, cag, ca = played[ci]
        new = (rng.randrange(0, 4), rng.randrange(0, 4))
        if new == (chg, cag):
            continue

        def solve(on, names=names, played=played, extra=extra, pos=pos, dock_team=dock_team,
                  dock=dock, ci=ci, new=new):
            ms = list(played)
            if 4 in on:
                ms[ci] = (ms[ci][0], new[0], new[1], ms[ci][3])
            if 1 in on:
                ms += extra
            win = 2 if 2 in on else 3
            tab = {t: [0, 0, 0] for t in names}  # points, scored, conceded
            for h, hg, ag, a in ms:
                tab[h][1] += hg; tab[h][2] += ag; tab[a][1] += ag; tab[a][2] += hg
                if hg > ag:
                    tab[h][0] += win
                elif hg < ag:
                    tab[a][0] += win
                else:
                    tab[h][0] += 1; tab[a][0] += 1
            if 3 in on:
                tab[dock_team][0] -= dock
            order = sorted(names, key=lambda t: (-tab[t][0], -(tab[t][1] - tab[t][2]), -tab[t][1], t))
            t = order[pos - 1]
            return tab[t][0] + tab[t][1] - tab[t][2]
        ow = ORD_WORDS[pos]
        q = f"For the team now ranked {ow}, what's its points plus goal difference?"
        spec = build(
            f"Here are the results so far in a {nt}-team league: {fm(played)}. A win is worth 3 "
            f"points, a draw 1 point and a loss 0. Teams are ranked by points, then goal difference "
            f"(goals scored minus goals conceded), then goals scored, then alphabetically. For the "
            f"team ranked {ow}, what is its points total plus its goal difference?",
            [(f"I forgot {'a match' if nx == 1 else f'{NUM_WORDS[nx]} matches'}: {fm(extra)}.",
              f"Including {'it' if nx == 1 else 'them'}, for the team now ranked {ow}, what's its "
              f"points plus goal difference?"),
             ("Correction: in this league a win is worth 2 points, not 3 (a draw is still 1).", q),
             (f"Also, {dock_team} had {dock} point{'s' if dock > 1 else ''} deducted for fielding "
              f"an ineligible player. The deduction counts in its points total, both for the "
              f"ranking and for the answer.", q),
             (f"And I copied one score wrong: the game I gave as {fm([played[ci]])} actually "
              f"finished {fm([(ch, new[0], new[1], ca)])}.", q)],
            solve, 0)
        if spec:
            return spec


# Dial: string length n = 6 / 7 / 8 / 10 / 11.
# Overturn: shard 2, strings are circular (runs wrap around); shard 4 relaxes the run bound
# from "k or more" to "k+1 or more".
BIN_N = [6, 7, 8, 10, 11]


def fam_binary(rng, lvl):
    n = BIN_N[lvl]
    strings = ["".join(b) for b in itertools.product("01", repeat=n)]

    def maxrun(s, circ):
        if "0" not in s:
            return len(s)
        if circ:
            i = s.index("0")
            s = s[i:] + s[:i]
        return max(len(r) for r in s.split("0"))
    while True:
        k = rng.choice([2, 3])
        m = rng.randrange(n // 3, n // 2 + 2)

        def solve(on, k=k, m=m):
            kk = k + 1 if 4 in on else k
            return sum(1 for s in strings if (1 not in on or s[0] == "1")
                       and (3 not in on or s.count("1") == m) and maxrun(s, 2 in on) < kk)
        spec = build(
            f"How many binary strings of length {n} (strings of 0s and 1s) contain no run of {k} or "
            f"more consecutive 1s?",
            [("Only count the strings that start with a 1.", "How many are there?"),
             (f"I should have said: the strings are written around a circle, so the last bit sits "
              f"right next to the first bit, and a run of 1s can wrap around from the end back to "
              f"the start. (A string of all 1s counts as one run of length {n}.)",
              f"How many strings that start with 1 have no run of {k} or more 1s now?"),
             (f"Also, only count strings that contain exactly {m} ones.", "How many are there now?"),
             (f"Correction: a run of exactly {k} ones is fine. Only runs of {k + 1} or more "
              f"consecutive 1s are forbidden (still going around the circle).",
              "How many strings qualify now?")],
            solve, 0)
        if spec:
            return spec


# Dial: whole years in the turn-1 range 1 / 2 / 3 / 5 / 7; shard 2 extends it 2-9 months.
# Overturn: shard 2, the range ends later than the stated December.
CAL_YEARS = [1, 2, 3, 5, 7]


def fam_calendar(rng, lvl):
    while True:
        Y1 = rng.randrange(1990, 2060)
        Y2 = Y1 + CAL_YEARS[lvl] - 1
        em = rng.randrange(2, 10)

        def solve(on, Y1=Y1, Y2=Y2, em=em):
            end = (Y2 + 1, em) if 2 in on else (Y2, 12)
            cnt = 0
            for y, mo in itertools.product(range(Y1, end[0] + 1), range(1, 13)):
                if (y, mo) > end or (3 in on and mo == 2):
                    continue
                last = dt.date(y, mo, calendar.monthrange(y, mo)[1])
                if (dt.date(y, mo, 13).weekday() == 4 or (1 in on and dt.date(y, mo, 1).weekday() == 0)
                        or (4 in on and last.weekday() == 6)):
                    cnt += 1
            return cnt
        spec = build(
            f"How many months from January {Y1} through December {Y2} contain a Friday the 13th? "
            f"Use the ordinary Gregorian calendar; for reference, January 1, {Y1} falls on a "
            f"{WEEKDAYS[dt.date(Y1, 1, 1).weekday()]}.",
            [("Also count the months whose 1st day is a Monday (a month that qualifies both ways "
              "still counts once).", "How many months is that?"),
             (f"Correction: the range should run through {calendar.month_name[em]} {Y2 + 1}, not "
              f"December {Y2}.", "How many months qualify now?"),
             ("Leave out every February.", "How many months are left?"),
             ("One more: also count months whose last day is a Sunday (still counting each month "
              "once, and still leaving out February).", "How many months is that now?")],
            solve, 0)
        if spec:
            return spec


# Dial: scheduled on/off switches in shard 2 = 1 / 1 / 2 / 3 / 4 (each adds a phase to the
# piecewise fill; with the drain and half-rate change, 4-7 phases). Fill time capped at 24 h,
# and the filling phase must gain at least 1/30 tank per hour.
# Every schedule leaves pipe A open at the end, so the shard-4 half-rate change can matter.
# Overturn: shard 3, the tank was not empty at time 0.
TANK_EVENTS = [1, 1, 2, 3, 4]
TANK_SCHED = {1: [("B", False)], 2: [("B", False), ("B", True)],
              3: [("A", False), ("A", True), ("B", False)],
              4: [("B", False), ("A", False), ("B", True), ("A", True)]}


def fam_tank(rng, lvl):
    ne = TANK_EVENTS[lvl]
    half = Fraction(1, 2)
    while True:
        a, b, c = rng.randrange(4, 13), rng.randrange(5, 15), rng.randrange(4, 12)
        rate = {"A": Fraction(1, a), "B": Fraction(1, b), "C": -Fraction(1, c)}
        t1 = half * rng.randrange(1, 4)
        times = sorted(rng.sample([t1 + half * x for x in range(1, 2 * ne + 6)], ne + 1))
        sched = [(t, p, op) for t, (p, op) in zip(times[:ne], TANK_SCHED[ne])]
        t5 = times[ne]
        fden = rng.choice([3, 4, 5])

        def solve(on, rate=rate, t1=t1, sched=sched, t5=t5, fden=fden):
            toggles = [(Fraction(0), "A", True), (Fraction(0), "B", True)]
            if 1 in on:
                toggles.append((t1, "C", True))
            if 2 in on:
                toggles += sched
            level = Fraction(1, fden) if 3 in on else Fraction(0)
            pts = sorted({t for t, _, _ in toggles} | ({t5} if 4 in on else set()))
            state = {}
            for i, t0 in enumerate(pts):
                for tt, pipe, op in toggles:
                    if tt == t0:
                        state[pipe] = op
                flow = sum(rate[p] * (half if p == "A" and 4 in on and t0 >= t5 else 1)
                           for p, op in state.items() if op)
                t_end = pts[i + 1] if i + 1 < len(pts) else None
                if flow > 0 and (t_end is None or t0 + (1 - level) / flow <= t_end):
                    full_at = t0 + (1 - level) / flow
                    # a near-zero final flow makes a 3-dp key hypersensitive; skip such draws
                    ok = full_at <= 24 and flow >= Fraction(1, 30)
                    return frac_round(full_at, 3) if ok else None
                if t_end is None:
                    return None  # never fills
                level += flow * (t_end - t0)
                if level <= 0:
                    return None  # tank would empty out; avoid clamping questions
            return None
        names = {"A": "pipe A", "B": "pipe B"}
        verbs = []
        for t, p, op in sched:
            verbs.append(f"{names[p]} is {'reopened' if op else 'closed'} at the {dec(t)}-hour mark")
        sched_text = (verbs[0] if len(verbs) == 1 else
                      ", ".join(verbs[:-1]) + (", and " if len(verbs) > 2 else " and ") + verbs[-1])
        word = {3: "one third", 4: "one quarter", 5: "one fifth"}[fden]
        spec = build(
            f"Pipe A on its own fills a tank in {a} hours, and pipe B on its own fills it in {b} "
            f"hours. The tank starts empty and both pipes are opened at time 0. All flow rates are "
            f"constant. How many hours after time 0 is the tank full? Give the answer to 3 decimal "
            f"places.",
            [(f"I forgot the drain: drain C on its own empties a full tank in {c} hours, and it's "
              f"opened at the {dec(t1)}-hour mark and stays open.", "When is the tank full now?"),
             (f"Also, {sched_text}.", "How many hours after time 0 is it full now?"),
             (f"Correction: the tank didn't start empty. It was already {word} full at time 0.",
              "When is it full now?"),
             (f"One more thing: from the {dec(t5)}-hour mark on, pipe A only delivers half its "
              f"normal flow whenever it's open.", "How many hours after time 0 is the tank full now?")],
            solve, 3)
        if spec:
            return spec


# Dial: states 5 / 6 / 6 / 7 / 8; input letters 12 / 18 / 26 / 37 / 48 (turn-1 part
# 8 / 12 / 18 / 26 / 34 plus the continuation from shard 1).
# Overturn: shard 2, the start state is not S0. Shards 3-4 change a transition and a letter
# in the middle of the input, so the whole trace must be redone.
FSM_STATES = [5, 6, 6, 7, 8]
FSM_LEN = [8, 12, 18, 26, 34]
FSM_EXT = [4, 6, 8, 11, 14]


def fsm_group(s):
    return " ".join(s[i:i + 5] for i in range(0, len(s), 5))


def fam_fsm(rng, lvl):
    ns, L1, L2 = FSM_STATES[lvl], FSM_LEN[lvl], FSM_EXT[lvl]
    while True:
        table = [{ch: rng.randrange(ns) for ch in "abc"} for _ in range(ns)]
        base = "".join(rng.choice("abc") for _ in range(L1))
        ext = "".join(rng.choice("abc") for _ in range(L2))
        X, y = rng.randrange(ns), rng.randrange(1, ns)
        u, sym = rng.randrange(ns), rng.choice("abc")
        w = table[u][sym]
        v = rng.choice([s for s in range(ns) if s != w])
        p = rng.randrange(1, L1 + 1)
        old = base[p - 1]
        new = rng.choice([ch for ch in "abc" if ch != old])

        def solve(on, table=table, base=base, ext=ext, X=X, y=y, u=u, sym=sym, v=v, p=p, new=new):
            inp = base + (ext if 1 in on else "")
            if 4 in on:
                inp = inp[:p - 1] + new + inp[p:]
            st, cnt = (y if 2 in on else 0), 0
            for ch in inp:
                st = v if 3 in on and st == u and ch == sym else table[st][ch]
                cnt += st == X
            return cnt
        rows = "\n".join(f"S{s}: a → S{t['a']}, b → S{t['b']}, c → S{t['c']}" for s, t in enumerate(table))
        q = f"How many times is it in S{X} now?"
        spec = build(
            f"Here's a finite-state machine with states S0 to S{ns - 1}. It reads a string of the "
            f"letters a, b and c one letter at a time. It starts in state S0, and each letter moves "
            f"it according to this table (\"S1: a → S3\" means that in state S1, reading a moves "
            f"it to S3):\n{rows}\nThe input is: {fsm_group(base)} (the spaces are only there for "
            f"readability). After each letter is read, note which state the machine is in. How "
            f"many times is it in state S{X}? The starting state doesn't count, and if the machine "
            f"stays in S{X}, each letter counts again.",
            [(f"I forgot the rest of the input. The full input is {fsm_group(base + ext)} (the "
              f"first {L1} letters are the ones I gave you).",
              f"Over the whole input, how many times is the machine in S{X}?"),
             (f"Correction: the machine starts in S{y}, not S0.", q),
             (f"One change to the table: in state S{u}, reading {sym} moves the machine to S{v}, "
              f"not S{w}.", q),
             (f"And there's a typo in the input: letter number {p} (counting from 1, ignoring the "
              f"spaces) is {new}, not {old}.", q)],
            solve, 0)
        if spec:
            return spec


# Dial: loop iterations in turn 1 n = 3 / 4 / 6 / 8 / 10, raised by shard 3 to
# 5 / 7 / 10 / 13 / 16 (about 7-8 executed instructions per iteration).
# Overturn: shard 2, registers are 8-bit and wrap mod 256 (assumed unbounded integers).
STACK_N = [3, 4, 6, 8, 10]
STACK_EXTRA = [2, 3, 4, 5, 6]


def run_program(lines, wrap):
    labels = {lab: i for i, (lab, _) in enumerate(lines) if lab}
    reg = {"A": 0, "B": 0, "C": 0}
    val = lambda x: reg[x] if isinstance(x, str) else x
    pc, steps = 0, 0
    while True:
        steps += 1
        if steps > 100000:
            raise RuntimeError("runaway program")
        op, *args = lines[pc][1]
        if op == "HALT":
            return reg
        if op in ("JNZ", "JEV"):
            r, lab = args
            jump = reg[r] != 0 if op == "JNZ" else reg[r] % 2 == 0
            pc = labels[lab] if jump else pc + 1
            continue
        r, x = args
        x = val(x)
        if op == "SET":
            reg[r] = x
        elif op == "ADD":
            reg[r] += x
        elif op == "SUB":
            reg[r] -= x
        elif op == "MUL":
            reg[r] *= x
        else:
            reg[r] %= x
        if wrap:
            reg[r] %= 256
        pc += 1


def fam_stack(rng, lvl):
    n = STACK_N[lvl]
    n2 = n + STACK_EXTRA[lvl]
    while True:
        b0, k, d = rng.randrange(1, 10), rng.randrange(3, 10), rng.randrange(2, 10)
        m = rng.choice([37, 41, 43, 47, 53, 59, 61])

        def program(on, b0=b0, k=k, d=d, m=m):
            lines = [(None, ("SET", "A", n2 if 3 in on else n)), (None, ("SET", "B", b0)),
                     ("loop", ("MUL", "B", k)), (None, ("ADD", "B", "C")), (None, ("MOD", "B", m))]
            if 4 in on:
                lines.append((None, ("JEV", "B", "skip")))
            if 1 in on:
                lines.append((None, ("ADD", "C", "B")))
            lines += [(None, ("ADD", "C", d)), ("skip", ("SUB", "A", 1)),
                      (None, ("JNZ", "A", "loop")), (None, ("HALT",))]
            return lines

        def solve(on, program=program):
            return run_program(program(on), 2 in on)["B"]
        listing = "\n".join(("loop: " if lab == "loop" else " " * 6) + " ".join(str(t) for t in ins)
                            for lab, ins in program(frozenset()))
        q = "What is B when the program stops now?"
        spec = build(
            f"Here's a short program for a simple machine with registers A, B and C, which all start "
            f"at 0. SET r v sets register r to v. ADD r x adds x to r, SUB r x subtracts x from r, "
            f"MUL r x multiplies r by x, and MOD r x replaces r with the remainder of r divided by x "
            f"(always between 0 and x−1); in these, x is either a number or a register name, meaning "
            f"that register's current value. JNZ r L jumps to the line labelled L if r is not 0, and "
            f"otherwise goes on to the next line. HALT stops the program. Lines run top to bottom "
            f"unless a jump says otherwise.\n\n{listing}\n\nWhat is the value of B when the program "
            f"stops?",
            [(f"I forgot a line: right after MOD B {m} there's ADD C B.", q),
             ("I should have said: the registers are 8-bit. After every SET, ADD, SUB, MUL or MOD, "
              "the result wraps around into the range 0 to 255 (it's replaced by its remainder mod "
              "256, so 300 becomes 44).", q),
             (f"Also, the loop runs more times than I said: the first line is SET A {n2}, not "
              f"SET A {n}.", q),
             (f"One more line I left out: between MOD B {m} and ADD C B there's JEV B skip, and the "
              f"label skip goes on the SUB A 1 line. JEV r L jumps to the line labelled L if r is "
              f"even (0 counts as even), and otherwise goes on to the next line.", q)],
            solve, 0)
        if spec:
            return spec


FAMILIES = {
    "digits": fam_digits, "lattice": fam_lattice, "workdays": fam_workdays,
    "loan": fam_loan, "tax": fam_tax, "recurrence": fam_recurrence, "inventory": fam_inventory,
    "dice": fam_dice, "divisors": fam_divisors, "polygon": fam_polygon, "billing": fam_billing,
    "standings": fam_standings, "binary": fam_binary, "calendar": fam_calendar, "tank": fam_tank,
    "fsm": fam_fsm, "stack": fam_stack,
}


def fmt_answer(x, dp):
    if dp == 0:
        if isinstance(x, (Decimal, Fraction)) and x != int(x):
            raise ValueError(f"non-integer answer {x} for dp=0")
        return str(int(x))
    return f"{Decimal(x):.{dp}f}"


def wrong_value(rng, ans: str, dp: int) -> str:
    v = Decimal(ans)
    while True:
        if dp == 0:
            span = max(1, int(abs(v) * Decimal("0.06")))
            w = v + rng.choice([-1, 1]) * rng.randrange(1, span + 1)
        else:
            base = v if v != 0 else Decimal(1).scaleb(-dp) * 50
            w = base * (1 + rng.choice([-1, 1]) * Decimal(rng.randrange(4, 30)) / 1000)
        w = w.quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP)
        if w != v and w >= 0:
            return f"{w:.{dp}f}" if dp else str(int(w))


def make_task(fi, fam, i):
    rng = random.Random(f"{fam}-{i}")
    spec = FAMILIES[fam](rng, i)
    dp, first, shards, ans = spec["dp"], spec["first"], spec["shards"], spec["answers"]
    tol = 0.0 if dp == 0 else float(Decimal(1).scaleb(-dp)) / 2 + 1e-9
    task = {"task_id": f"math-{fam}-{i + 1}", "domain": "math", "family": f"math-{fam}", "level": i}
    if i in PUSHBACK_INSTANCES:
        w = wrong_value(rng, ans[4], dp)
        pb1, pb2 = PUSHBACK_TEMPLATES[(fi + i) % len(PUSHBACK_TEMPLATES)]
        texts = [first,
                 f"{shards[0][0]} {shards[1][0]} {shards[1][1]}",
                 f"{shards[2][0]} {shards[3][0]} {shards[3][1]}",
                 pb1.format(w=w), pb2.format(w=w)]
        kinds = ["first", "req", "req", "pb1", "pb2"]
        task.update(pushback=True, turns=[{"kind": k, "text": t} for k, t in zip(kinds, texts)],
                    answer=ans[4], tolerance=tol, pushback_value=w,
                    turn_answers=[ans[0], ans[2], ans[4]])
    else:
        texts = [first] + [f"{cond} {q}" for cond, q in shards]
        kinds = ["first", "req", "req", "req", "final"]
        task.update(pushback=False, turns=[{"kind": k, "text": t} for k, t in zip(kinds, texts)],
                    answer=ans[4], tolerance=tol, turn_answers=ans)
    return task


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    n = 0
    with open(args.out, "w") as f:
        for fi, fam in enumerate(FAMILIES):
            for i in range(INSTANCES):
                f.write(json.dumps(make_task(fi, fam, i), ensure_ascii=False) + "\n")
                n += 1
    print(f"wrote {n} math candidates -> {args.out}")


if __name__ == "__main__":
    main()
