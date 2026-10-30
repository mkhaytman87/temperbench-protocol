#!/usr/bin/env python3
"""TemperBench v0.3 task authoring: gen_extract.py

Generates candidate multi-turn extraction tasks over realistic, messy documents (email
threads, OCR-ish invoices, manifests, clinic notes, registration logs). Each document
contains corrections, distractors, unit/format conversions and computed fields. Every
expected value is computed by code from the same parameters that render the document, so
keys can't drift from the wording. Deterministic: random.Random(f"{family}-{i}").

6 families x 8 instances. Within a family, which traps fire is driven by the instance index
(so every trap branch is covered), and everything else (names, numbers, dates, orderings)
by the seeded RNG.

Usage:
    python3 tasks/src/gen_extract.py --out tasks/src/extract_candidates.jsonl
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import re
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal, getcontext

getcontext().prec = 50

INSTANCES = 8
LB_KG = Decimal("0.45359237")
OZ_KG = Decimal("0.028349523125")
IN_M = Decimal("0.0254")

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
MON3 = [m[:3] for m in MONTHS]
WDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WD3 = [w[:3] for w in WDAYS]

FIRST = ["Dana", "Marcus", "Priya", "Tomas", "Aisha", "Kenji", "Lucia", "Owen", "Fatima",
         "Elliot", "Nadia", "Rafael", "Grace", "Samuel", "Ingrid", "Mateo", "Hana", "Jonah",
         "Leila", "Victor", "Chloe", "Andre", "Mira", "Felix", "Zara", "Desmond", "Yuki",
         "Carmen", "Idris", "Paula", "Henrik", "Ruth", "Omar", "Beatriz", "Callum", "Esther",
         "Nikhil", "Sofia", "Gideon", "Talia"]
LAST = ["Whitfield", "Okafor", "Raman", "Novak", "Haddad", "Tanaka", "Ferreira", "Brennan",
        "Qureshi", "Lindqvist", "Petrov", "Alvarez", "Mensah", "Kowalski", "Abernathy",
        "Delgado", "Sato", "Fischer", "Nakamura", "Osei", "Castellanos", "Moreau", "Iyer",
        "Bergstrom", "Kiplagat", "Duarte", "Halloran", "Szabo", "Achebe", "Lindgren", "Varga",
        "Pham", "Rosales", "Eriksen", "Mbeki", "Calloway", "Yilmaz", "Thornton", "Banerjee",
        "Aguilar"]
STREETS = ["Larch St", "Willow Ave", "Harbor Rd", "Maple Ct", "Juniper Ln", "Orchard Way",
           "Granite St", "Bayview Dr", "Elm St", "Foundry Rd", "Linden Pl", "Cedar Ave"]


# --------------------------------------------------------------------------- helpers

def rnd(x: Decimal, dp: int) -> Decimal:
    return x.quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP)


def clear_of_midpoint(x: Decimal, dp: int, margin: str = "0.15") -> bool:
    """True if x is not within `margin` (in units of the last kept digit) of a rounding
    midpoint, so half-up vs half-even or float noise can't change the rounded answer."""
    s = x.scaleb(dp)
    frac = s - s.to_integral_value(rounding=ROUND_FLOOR)
    return abs(frac - Decimal("0.5")) >= Decimal(margin)


def money(x: Decimal) -> str:
    return f"${x:,.2f}"


def as_num(x: Decimal, dp: int) -> float:
    return float(rnd(x, dp))


def pick_people(rng, n, exclude_last=()):
    firsts = rng.sample(FIRST, n)
    lasts = rng.sample([s for s in LAST if s not in exclude_last], n)
    return list(zip(firsts, lasts))


def t24(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def t12(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def fmt_offset(mins: int) -> str:
    a = abs(mins)
    return f"UTC{'+' if mins >= 0 else '-'}{a // 60:02d}:{a % 60:02d}"


def fmt_numeric_date(d: dt.date, order: str, sep: str) -> str:
    if order == "DMY":
        return f"{d.day:02d}{sep}{d.month:02d}{sep}{d.year}"
    return f"{d.month:02d}{sep}{d.day:02d}{sep}{d.year}"


def numeric_date_label(order: str, sep: str) -> str:
    return sep.join(["DD", "MM", "YYYY"] if order == "DMY" else ["MM", "DD", "YYYY"])


def ambiguous_day(rng, year, months=range(1, 13)):
    """A date whose day and month are both <= 12 and differ, so DD/MM vs MM/DD matters."""
    while True:
        m = rng.choice(list(months))
        d = rng.randrange(1, 13)
        if d != m:
            return dt.date(year, m, d)


def email_stamp(t: dt.datetime) -> str:
    return f"{WD3[t.weekday()]}, {t.day} {MON3[t.month - 1]} {t.year} {t.hour:02d}:{t.minute:02d}"


def wrap_t1(kind: str, doc: str, schema: str) -> str:
    return (f"Extract the following from this {kind}:\n\n\"\"\"\n{doc}\n\"\"\"\n\n"
            f"Return JSON with exactly these keys: {schema}")


# --------------------------------------------------------------------------- 1. order

SHOPS = [
    ("Ridgeway Coffee Supply", "ridgewaycoffee.com", "RC", [
        ("Ceramic Pour-Over Dripper", "24.00"), ("Gooseneck Kettle 1L", "58.50"),
        ("Burr Grinder Mini", "89.00"), ("Paper Filters (100-pack)", "7.25"),
        ("Glass Carafe 600 ml", "31.40"), ("Guji Whole Beans 340 g", "18.75"),
        ("Digital Brew Scale", "42.00")]),
    ("Lantern & Quill Art Supply", "lanternquill.com", "LQ", [
        ("Cold-Press Watercolor Pad", "21.60"), ("Sable Round Brush No. 8", "34.25"),
        ("Gouache Set (12 tubes)", "46.00"), ("Masking Fluid 50 ml", "9.80"),
        ("Kneaded Eraser", "2.35"), ("Graphite Pencil Set", "15.90"),
        ("Tabletop Easel", "27.50")]),
    ("Switchback Outfitters", "switchbackoutfitters.com", "SB", [
        ("Merino Hiking Socks", "19.95"), ("Trekking Pole", "64.00"),
        ("Collapsible Bowl", "12.40"), ("Headlamp 350 lm", "38.00"), ("Dry Bag 20 L", "26.75"),
        ("Water Filter Straw", "22.50"), ("Titanium Camp Mug", "29.90")]),
    ("Copper Hen Kitchenware", "copperhen.com", "CH", [
        ("Cast Iron Skillet 10 in", "44.00"), ("Bench Scraper", "11.25"),
        ("Silicone Spatula Set", "16.80"), ("Proofing Basket", "23.40"),
        ("Chef's Knife 8 in", "79.00"), ("Linen Tea Towels (pair)", "14.60"),
        ("Instant-Read Thermometer", "27.95")]),
    ("Barkley & Finch Pet Goods", "barkleyfinch.com", "BF", [
        ("Slow-Feeder Bowl", "17.45"), ("Rope Tug Toy", "8.90"),
        ("Orthopedic Dog Bed (M)", "72.00"), ("Grain-Free Treats 400 g", "12.30"),
        ("Reflective Leash 6 ft", "21.00"), ("Grooming Brush", "15.75"),
        ("Cat Scratching Post", "36.50")]),
    ("Paper Lantern Stationers", "paperlantern.co", "PL", [
        ("A5 Dot-Grid Notebook", "16.50"), ("Fountain Pen (EF nib)", "48.00"),
        ("Ink Bottle 50 ml", "13.20"), ("Brass Bookmark", "6.85"),
        ("Leather Desk Pad", "39.00"), ("Washi Tape Set", "9.40"),
        ("Canvas Pencil Case", "18.25")]),
]
CITIES = [("Cambridge", "MA", "02139"), ("Providence", "RI", "02906"), ("Hartford", "CT", "06106"),
          ("Burlington", "VT", "05401"), ("Portland", "ME", "04101"), ("Hoboken", "NJ", "07030"),
          ("Madison", "WI", "53703"), ("Boulder", "CO", "80302"), ("Asheville", "NC", "28801"),
          ("Tucson", "AZ", "85719"), ("Eugene", "OR", "97401"), ("Ann Arbor", "MI", "48104"),
          ("Savannah", "GA", "31401"), ("Spokane", "WA", "99201"), ("Lawrence", "KS", "66044"),
          ("Durham", "NC", "27701")]
PROMO_WORDS = ["SPRING", "WELCOME", "THANKS", "HELLO", "CRAFT", "FRIENDS"]


def bad_zip(rng, z):
    for _ in range(20):
        k = rng.randrange(2, 4)
        s = list(z)
        s[k], s[k + 1] = s[k + 1], s[k]
        if "".join(s) != z:
            return "".join(s)
    return z[:4] + str((int(z[4]) + 3) % 10)


def fam_order(rng, i):
    shop, domain, pfx, catalog = SHOPS[i % len(SHOPS)]
    met = i in (0, 2, 4, 5, 6)            # promo rule satisfied by the FINAL order
    flip = i in (0, 1, 3, 6)              # original order is on the other side of the threshold
    inclusive = i % 2 == 0                # "$T or more" vs "more than $T"
    double = i in (1, 2, 5, 7)            # the changed quantity is changed a second time later
    newest_first = i in (1, 3, 4, 6)      # thread rendered newest message first
    zip_early = i in (0, 3, 6)            # ZIP fix in the first customer reply vs a later one
    n_items = 3 + (i % 2)
    (cf, cl), (sf, sl) = pick_people(rng, 2)
    city, st, zip_ok = rng.choice(CITIES)
    bcity, bst, bzip = rng.choice([c for c in CITIES if c[0] != city])
    zip_bad = bad_zip(rng, zip_ok)
    qualifies = (lambda s, T: s >= T) if inclusive else (lambda s, T: s > T)
    while True:
        picks = rng.sample(catalog, n_items)
        prices = [Decimal(p) for _, p in picks]
        qty = [rng.randrange(1, 5) for _ in picks]
        a, b = rng.sample(range(n_items), 2)
        q_new = rng.choice([q for q in range(1, 7) if q != qty[a]])
        q_new2 = rng.choice([q for q in range(1, 7) if q not in (qty[a], q_new)])
        final_q = list(qty)
        final_q[a] = q_new2 if double else q_new
        final_q[b] = 0
        orig = sum(q * p for q, p in zip(qty, prices))
        final = sum(q * p for q, p in zip(final_q, prices))
        if final < 40:
            continue
        pct = rng.choice([10, 15, 20])
        if met:
            cands = [T for T in range(50, 301, 25) if qualifies(final, T)]
            T = max(cands) if cands else None
        else:
            cands = [T for T in range(50, 301, 25) if not qualifies(final, T)]
            T = min(cands) if cands else None
        if T is None:
            continue
        if (qualifies(orig, T) != qualifies(final, T)) != flip:
            continue
        disc = final * pct / 100 if met else Decimal(0)
        if disc != disc.quantize(Decimal("0.01")):
            continue
        break
    total = final - disc
    order_no = f"{pfx}-{rng.randrange(40000, 60000)}"
    prev_no = f"{pfx}-{rng.randrange(20000, 39000)}"
    pitem, pprice = rng.choice(catalog)
    pq = rng.randrange(2, 7)
    ptotal = rnd(pq * Decimal(pprice) * Decimal("0.9"), 2)
    other = rng.choice([c for c in catalog if c not in picks and c[0] != pitem])[0]
    code = f"{rng.choice(PROMO_WORDS)}{pct}"
    street, bstreet = (f"{rng.randrange(12, 980)} {s}" for s in rng.sample(STREETS, 2))
    A, B = picks[a][0], picks[b][0]
    cust_from = f"{cf} {cl} <{cf.lower()}.{cl.lower()}@example.net>"
    shop_from = f"{shop} <orders@{domain}>"

    lines = "\n".join(f"  {q} x {n} @ ${Decimal(p):.2f} each" for q, (n, p) in zip(qty, picks))
    change = rng.choice([
        f"please change the {A} from {qty[a]} to {q_new}",
        f"can you make it {q_new} x {A} instead of {qty[a]}?",
        f"{'bump' if q_new > qty[a] else 'cut'} the {A} {'up' if q_new > qty[a] else 'down'} to {q_new}"])
    drop = rng.choice([f"take the {B} off the order entirely",
                       f"please drop the {B}, I found one locally",
                       f"cancel the {B} line, I don't need it after all"])
    zip_fix = (f"the ZIP on the shipping address is wrong: it should be {zip_ok}, not "
               f"{zip_bad}. Street and city are correct.")
    if inclusive:
        rule = f"it takes {pct}% off when the order subtotal before the discount is ${T}.00 or more"
    else:
        rule = (f"it takes {pct}% off when the order subtotal before the discount is more than "
                f"${T}.00 (a subtotal of exactly ${T}.00 doesn't qualify)")

    t0 = dt.datetime(2027, rng.randrange(1, 12), rng.randrange(1, 28), rng.randrange(8, 12),
                     rng.randrange(0, 60))
    stamps = [t0]
    for _ in range(4):
        stamps.append(stamps[-1] + dt.timedelta(minutes=rng.randrange(40, 1300)))
    subj = f"Order #{order_no} confirmed"
    msgs = [
        (shop_from, subj,
         f"Hi {cf},\n\nThanks for your order! Order #{order_no} is confirmed:\n\n{lines}\n\n"
         f"Ship to: {cf} {cl}, {street}, {city}, {st} {zip_bad}\n"
         f"Bill to: {bstreet}, {bcity}, {bst} {bzip}\n\n"
         f"Shipping is free on all orders. Just reply if anything needs to change before it "
         f"ships.\n\n{sf} | {shop} order desk"),
        (cust_from, "Re: " + subj,
         f"Hi {sf},\n\nA few changes before this ships:\n- {change}\n- {drop}\n"
         + (f"- also, {zip_fix}\n" if zip_early else "")
         + f"\nI also have a promo code, {code}. My last order with you (#{prev_no}) was {pq} x "
         f"{pitem} and came to ${ptotal} with a code, so hopefully this one works too.\n\n"
         f"Thanks!\n{cf}"),
        (shop_from, "Re: " + subj,
         f"Hi {cf}, done: the {A} is now {q_new} and the {B} is off the order. About {code}: "
         f"{rule}. If the final order qualifies we apply it when we invoice; if not, the order "
         f"is billed at full price.\n\n{sf}"),
    ]
    late = []
    if not zip_early:
        late.append(f"Sorry, one more fix: {zip_fix}")
    if double:
        late.append(f"And apologies for flip-flopping, but please make the {A} {q_new2} after all.")
    late.append(f"Unrelated: do you ever restock the {other}? Not for this order, just curious.")
    msgs.append((cust_from, "Re: " + subj, "Hi again,\n\n" + "\n".join(late) + f"\n\n{cf}"))
    msgs.append((shop_from, "Re: " + subj,
                 f"Noted, everything is updated on our side. We'll have it out within two "
                 f"business days.\n\n{sf}"))
    rendered = [f"From: {fr}\nDate: {email_stamp(ts)}\nSubject: {su}\n\n{body}"
                for (fr, su, body), ts in zip(msgs, stamps)]
    if newest_first:
        rendered.reverse()
    doc = "\n\n-----\n\n".join(rendered)

    schema = ('{"customer_name": string (the customer\'s full name, first and last), '
              '"order_number": string (the current order\'s number, without the leading "#"), '
              '"shipping_city": string (city name only), '
              '"total_units": integer (total number of units across all items in the order '
              'after every change in the thread)}')
    return dict(
        kind="customer email thread",
        doc=doc,
        t1=wrap_t1("customer email thread", doc, schema),
        t2='Also add the key "shipping_zip": string, the 5-digit ZIP code of the shipping '
           'address after any corrections in the thread.',
        t3='Also add the key "order_total": number with 2 decimal places: the sum of quantity '
           '× unit price over the items in the final order (after every change), minus the '
           'promo-code discount if and only if the final order meets the shop\'s stated rule '
           'for that code. Shipping is free and there is no tax.',
        expected={"customer_name": f"{cf} {cl}", "order_number": order_no,
                  "shipping_city": city, "total_units": sum(final_q),
                  "shipping_zip": zip_ok, "order_total": as_num(total, 2)},
        tol=0.005)


# --------------------------------------------------------------------------- 2. meeting

# UTC offsets that are correct for these cities between 2027-01-11 and 2027-03-12 (no DST
# transition in that window for any of them).
ZONES = [("Bengaluru", 330), ("Mumbai", 330), ("Kathmandu", 345), ("Tehran", 210),
         ("Kabul", 270), ("Yangon", 390), ("Darwin", 570), ("Tokyo", 540), ("Singapore", 480),
         ("Brisbane", 600), ("Dubai", 240), ("Nairobi", 180), ("Berlin", 60), ("Lagos", 60),
         ("London", 0), ("Sao Paulo", -180), ("St. John's", -210), ("New York", -300),
         ("Bogota", -300), ("Chicago", -360), ("Mexico City", -360), ("Denver", -420),
         ("Phoenix", -420), ("Los Angeles", -480), ("Anchorage", -540), ("Honolulu", -600)]
TITLES = ["Program Manager", "Account Director", "Data Engineer", "Legal Counsel",
          "Finance Lead", "Product Manager", "Security Analyst", "Ops Coordinator",
          "UX Researcher", "Solutions Architect", "Partner Manager", "QA Lead"]
TOPICS = ["vendor review", "data-retention sign-off", "launch readiness check",
          "API deprecation plan", "budget reforecast", "incident postmortem",
          "partner onboarding", "localization roadmap"]
DEPTS = ["legal", "finance", "security", "procurement", "ops", "design"]
COMPANIES = ["Halcyon Labs", "Brightwater Analytics", "Quillfeather", "Northstar Freight",
             "Tidewell Health", "Aperture Mills", "Copperleaf Systems", "Lumen & Vale"]

# (mode, organizer offset must be half/quarter-hour?, organizer offset must be negative?)
MEETING_PLAN = [("back", True, False), ("fwd", False, True), ("none", True, False),
                ("end", None, None), ("back", False, False), ("none", True, True),
                ("fwd", True, True), ("none", False, None)]


def fam_meeting(rng, i):
    mode, need_half, need_neg = MEETING_PLAN[i]
    pool = [z for z in ZONES
            if (need_half is None or (z[1] % 60 != 0) == need_half)
            and (need_neg is None or (z[1] < 0) == need_neg)]
    first_day = dt.date(2027, 1, 18)
    while True:
        oz = rng.choice(pool)
        d = first_day + dt.timedelta(days=rng.randrange(0, 46))
        if d.weekday() >= 5:
            continue
        start_min = rng.randrange(7 * 4, 21 * 4 + 1) * 15
        D0 = rng.choice([60, 75, 90, 120])
        D1 = D0 - rng.choice([15, 30, 45])
        if D1 < 30:
            continue
        local = dt.datetime(d.year, d.month, d.day) + dt.timedelta(minutes=start_min)
        su = local - dt.timedelta(minutes=oz[1])
        eu = su + dt.timedelta(minutes=D1)
        got = ("back" if su.date() < d else "fwd" if su.date() > d
               else "end" if eu.date() > su.date() else "none")
        if got == mode and start_min + D0 < 24 * 60:
            break
    n_inv = 3 + (i % 3)
    k_extra = 2 if i in (2, 6) else 1
    fyi = i in (1, 4, 7)
    people = pick_people(rng, 1 + n_inv + 1 + k_extra + 1)
    full = lambda p: f"{p[0]} {p[1]}"
    org, invitees = people[0], people[1:1 + n_inv]
    sub = people[1 + n_inv]
    extras = people[2 + n_inv:2 + n_inv + k_extra]
    fyi_p = people[-1]
    company = rng.choice(COMPANIES)
    titles = rng.sample(TITLES, 1 + n_inv)
    zones = {full(org): oz}
    for p in invitees:
        zones[full(p)] = rng.choice([z for z in ZONES if z != oz])
    sig = {full(p): f"{full(p)} | {t}, {company} | {zones[full(p)][0]} "
                    f"({fmt_offset(zones[full(p)][1])})"
           for p, t in zip([org] + invitees, titles)}
    roles = rng.sample(range(n_inv), 3)
    decl, subst, extra_by = (invitees[r] for r in roles)
    proposer = rng.choice([p for p in invitees if p != decl])
    objector = rng.choice([p for p in invitees if p != proposer])
    topic = rng.choice(TOPICS)
    use12 = rng.random() < 0.5
    tf = t12 if use12 else t24

    p1 = d - dt.timedelta(days=rng.choice([1, 2, 3]))
    while p1.weekday() >= 5:
        p1 -= dt.timedelta(days=1)
    p2 = d + dt.timedelta(days=rng.choice([1, 2]))
    while p2.weekday() >= 5:
        p2 += dt.timedelta(days=1)
    p1_min = rng.randrange(8 * 4, 18 * 4) * 15
    p2_min = rng.randrange(8 * 4, 18 * 4) * 15
    sent0 = d - dt.timedelta(days=rng.randrange(8, 12))
    sent = [sent0 + dt.timedelta(days=k // 2) for k in range(12)]
    fmt_day = lambda x: f"{WD3[x.weekday()]} {x.day} {MON3[x.month - 1]} {x.year}"
    if rng.random() < 0.5:
        confirm = f"{WDAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]} {d.year} at {tf(start_min)}"
    else:
        confirm = f"{WD3[d.weekday()]}, {MON3[d.month - 1]} {d.day}, {d.year}, {tf(start_min)}"

    msgs = []
    to_line = "; ".join(full(p) for p in invitees)
    msgs.append((org, f"To: {to_line}",
                 f"Hi all, I'd like to get {D0} minutes on the calendar for the {topic}. Could "
                 f"we do {WDAYS[p1.weekday()]} {p1.day} {MONTHS[p1.month - 1]} at {tf(p1_min)} my "
                 f"time?"))
    msgs.append((proposer, None,
                 f"{WDAYS[p1.weekday()]} is out for me, I'm on a site visit all day. Would "
                 f"{WDAYS[p2.weekday()]} {p2.day} {MONTHS[p2.month - 1]} at {tf(p2_min)} my time "
                 f"work instead?"))
    msgs.append((objector, None,
                 "That slot doesn't work for me, I have a board review then. Can we find something else?"))
    cc = f"Cc: {full(fyi_p)}" if fyi else None
    msgs.append((org, cc,
                 f"Thanks all. Confirmed: {confirm} my time, {D0} minutes. Invite to follow."
                 + (f" (Cc'ing {fyi_p[0]} for visibility only; they won't be joining.)" if fyi else "")))
    replies = [
        (decl, None, rng.choice([
            "Unfortunately I'm out on leave that day, so I'll have to decline. Please send notes!",
            "I can't make that one after all, so count me out. I'll catch up from the notes."])),
        (subst, None, f"I'm double-booked then, so {full(sub)} from my team will attend in my "
                      f"place."),
        (extra_by, None,
         "Works for me. I'll bring "
         + (f"{full(extras[0])} from {rng.choice(DEPTS)}" if k_extra == 1 else
            f"{full(extras[0])} and {full(extras[1])} from {rng.choice(DEPTS)}")
         + " along, since they own the numbers."),
    ]
    others = [p for p in invitees if p not in (decl, subst, extra_by)]
    for p in others:
        replies.append((p, None, rng.choice(["Works for me, see you then.",
                                             "Accepted, thanks.", "Fine by me."])))
    rng.shuffle(replies)
    msgs.extend(replies)
    shorten = rng.randrange(3)
    if shorten == 0:
        change = f"let's keep it to {D1} minutes instead of {D0}. Same start time."
    elif shorten == 1:
        change = f"we can trim {D0 - D1} minutes off the end. Same start time."
    else:
        change = (f"we'll wrap up at {tf(start_min + D1)} my time instead, same start, so a "
                  f"shorter call.")
    msgs.append((org, None, f"Quick update on the {topic}: {change}"))
    blocks = []
    for k, (who, extra_hdr, body) in enumerate(msgs):
        hdr = f"From: {full(who)}\nSent: {fmt_day(sent[k])}"
        if extra_hdr:
            hdr += "\n" + extra_hdr
        blocks.append(f"{hdr}\n\n{body}\n\n{sig[full(who)]}")
    doc = f"Subject: {topic.capitalize()} call\n\n" + "\n\n-----\n\n".join(blocks)

    schema = ('{"organizer": string (full name of the person who organized the meeting), '
              '"meeting_date": string (YYYY-MM-DD, the confirmed meeting date in the '
              'organizer\'s local time), '
              '"attendee_count": integer (number of people expected to attend the confirmed '
              'meeting after all replies in the thread, including the organizer; people who are '
              'only cc\'d for information do not count)}')
    return dict(
        kind="email thread",
        doc=doc,
        t1=wrap_t1("email thread", doc, schema),
        t2='Also add the key "start_utc": string in the format "YYYY-MM-DDTHH:MM" (24-hour '
           'clock), the confirmed start time converted to UTC using the UTC offset given in the '
           'organizer\'s signature.',
        t3='Also add the key "end_utc": string in the same format, the meeting\'s end time in '
           'UTC based on its final duration.',
        expected={"organizer": full(org), "meeting_date": d.isoformat(),
                  "attendee_count": 1 + n_inv - 1 + k_extra,
                  "start_utc": su.strftime("%Y-%m-%dT%H:%M"),
                  "end_utc": eu.strftime("%Y-%m-%dT%H:%M")},
        tol=0.0)


# --------------------------------------------------------------------------- 3. invoice

VENDORS = [
    ("Harborline Office Supply Co.", "1180 Dockside Ave, Tacoma WA 98402", "HOS", [
        ("Toner cartridge TN-760", 52, 89), ("Copy paper, 10-ream case", 38, 52),
        ("Desk organizer, mesh", 12, 24), ("Gel pens, box of 12", 9, 16),
        ("Label tape 12 mm", 14, 22), ("Stapler, heavy duty", 25, 45)]),
    ("Bright Anvil Industrial Supply", "44 Foundry Rd, Dayton OH 45402", "BAI", [
        ("Nitrile gloves, case of 1000", 48, 70), ("Safety glasses, clear", 4, 9),
        ("Hex bolts M10, box of 50", 11, 19), ("Shop rags, 25 lb bale", 30, 44),
        ("Cutting discs 4.5 in, 10-pack", 16, 27), ("Wire brush set", 8, 15)]),
    ("Kestrel Lab Consumables Inc.", "9 Innovation Pkwy, Durham NC 27703", "KLC", [
        ("Pipette tips 200 uL, rack of 96", 9, 15), ("Petri dishes 90 mm, sleeve of 20", 6, 11),
        ("Ethanol 70%, 4 L", 21, 34), ("Cryo labels, roll", 17, 29),
        ("Centrifuge tubes 50 mL, pack of 25", 12, 20), ("Nitrile gloves M, box", 9, 14)]),
    ("Cedar & Pine Janitorial Supply", "301 Mill St, Burlington VT 05401", "CPJ", [
        ("Floor cleaner concentrate, 5 gal", 46, 72), ("Paper towel rolls, case", 33, 49),
        ("Trash liners 55 gal, box of 100", 27, 41), ("Microfiber mops", 7, 13),
        ("Hand soap refill 1 L", 5, 10), ("Disinfectant wipes, tub", 6, 11)]),
    ("Northgate Print & Sign LLC", "77 Ferry St, Albany NY 12207", "NPS", [
        ("Vinyl banner 3x8 ft", 64, 98), ("Foam board signs 18x24", 14, 26),
        ("Business cards, 500", 29, 45), ("Tri-fold brochures, 250", 88, 130),
        ("Window decals", 11, 19), ("A-frame sign insert", 35, 55)]),
    ("Bluewater Marine Parts Co.", "15 Wharf Rd, Portland ME 04101", "BMP", [
        ("Bilge pump 1100 GPH", 58, 84), ("Stainless shackle 3/8 in", 7, 12),
        ("Marine grease, tube", 9, 15), ("Fuel filter element", 18, 31),
        ("Dock line 5/8 in x 25 ft", 26, 39), ("Navigation bulb 12V", 4, 8)]),
]
CUSTOMERS = ["Fernway Dental Group", "Oakridge Montessori School", "Pinecrest Veterinary Clinic",
             "Lakeshore Brewing Co.", "Summit Ridge Physical Therapy",
             "Maple Hollow Library District", "Granite Peak Builders",
             "Riverside Community Theatre"]
OCR_NOISE = ["~~ scan_0{n}.tif ~~ pg 1/1 ~~ |l|l| .:;", "%%RCVD {n} %% ' ` ~ ' [fax hdr]",
             "### AP INBOX / scanned {n} ### ;:'l|", "[[ page 1 of 1 ]]  ~ i|l ~ ref {n}"]
TAX_RATES = ["6.25", "7.25", "8.875", "9.5", "5.3", "10.1", "6.85", "7.75"]


def garble(s: str, rng) -> str:
    chars = list(s)
    digit_pos = [k for k, c in enumerate(chars) if c.isdigit()]
    for k in rng.sample(digit_pos, min(3, len(digit_pos))):
        chars[k] = rng.choice("#?%_")
    return "".join(chars)


def fam_invoice(rng, i):
    vendor, addr, pfx, catalog = VENDORS[i % len(VENDORS)]
    order = "DMY" if i % 2 == 0 else "MDY"
    sep = ["/", "-", ".", "/"][i % 4]
    note_in_footer = i in (1, 4, 6)
    tax_rule = ["after_credit", "before_credit", "with_freight"][i % 3]
    has_freight = tax_rule == "with_freight" or i in (1, 3, 6)
    backorder = i in (1, 4, 6)
    extended = i in (2, 5)
    customer = CUSTOMERS[i]
    if i in (2, 5):
        inv_date = dt.date(2028, 2, rng.choice([1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]))
        N = rng.choice([45, 60])
    else:
        inv_date = ambiguous_day(rng, 2027)
        N = rng.choice([10, 15, 30, 45, 60])
    due = inv_date + dt.timedelta(days=N)
    while True:
        items = rng.sample(catalog, rng.choice([3, 4]))
        lines = [(rng.randrange(1, 13), desc, Decimal(rng.randrange(lo * 100, hi * 100)) / 100)
                 for desc, lo, hi in items]
        merch = sum(q * p for q, _, p in lines)
        if rng.random() < 0.6:
            k = rng.randrange(len(lines))
            cq = rng.randrange(1, lines[k][0] + 1)
            credit = cq * lines[k][2]
            reason = f"returned {cq} x {lines[k][1]}"
        else:
            k = rng.randrange(len(lines))
            credit = Decimal(rng.randrange(500, 4000)) / 100
            reason = f"price adjustment on {lines[k][1]}"
        freight = Decimal(rng.randrange(1500, 6000)) / 100 if has_freight else Decimal(0)
        rate = Decimal(rng.choice(TAX_RATES))
        base = {"after_credit": merch - credit, "before_credit": merch,
                "with_freight": merch - credit + freight}[tax_rule]
        tax = base * rate / 100
        if credit < merch and clear_of_midpoint(tax, 2):
            break
    amount_due = merch - credit + freight + rnd(tax, 2)
    inv_no = f"{pfx}-{inv_date.year % 100}-{rng.randrange(300, 999):04d}"
    prev_no = f"{pfx}-{inv_date.year % 100}-{rng.randrange(100, 299):04d}"
    D = lambda x: fmt_numeric_date(x, order, sep)
    order_d = inv_date - dt.timedelta(days=rng.randrange(5, 15))
    ship_d = inv_date - dt.timedelta(days=rng.randrange(1, 4))
    prev_d = inv_date - dt.timedelta(days=rng.randrange(30, 50))
    paid_d = prev_d + dt.timedelta(days=rng.randrange(8, 20))
    prev_amt = Decimal(rng.randrange(8000, 90000)) / 100
    smudge = rng.randrange(len(lines))
    date_note = f"NOTE: all dates on this document are written {numeric_date_label(order, sep)}."

    out = [OCR_NOISE[i % 4].format(n=rng.randrange(100, 999)),
           f"Vendor: {vendor}", f"{addr} | Tel 555-01{rng.randrange(10, 99)}",
           f"INV0ICE No.: {inv_no}        Invoice date: {D(inv_date)}",
           f"Customer PO: {rng.randrange(10000, 99999)}   Order date: {D(order_d)}   Ship date: {D(ship_d)}",
           f"Bill to: {customer}, Attn: Accounts Payable    Acct #: {rng.randrange(10000, 99999)}",
           f"Ship to: {customer}, {rng.choice(['Receiving Dock B', 'Suite 200', 'Rear entrance', 'Main office'])}   "
           f"Sales rep: {' '.join(pick_people(rng, 1)[0])}   Ship via: {rng.choice(['UPS Ground', 'our truck', 'FedEx Freight', 'customer pickup'])}"]
    if not note_in_footer:
        out.append(date_note)
    out.append("-" * 58)
    out.append(f"{'QTY':<5}{'DESCRlPTION':<36}{'UNIT':>8}  AMOUNT")
    for k, (q, desc, p) in enumerate(lines):
        amt = "[smudged]" if k == smudge else f"{q * p:,.2f}"
        out.append(f"{q:<5}{desc:<36}{p:>8.2f}  {amt}")
    if backorder:
        bdesc, blo, bhi = rng.choice([c for c in catalog if c not in items])
        out.append(f"{'0':<5}{bdesc + ' (BACKORDERED)':<36}{Decimal(rng.randrange(blo * 100, bhi * 100)) / 100:>8.2f}  0.00")
        out.append(f"     ^ {rng.randrange(2, 9)} on backorder, not billed on this invoice")
    out.append("-" * 58)
    out.append(f"Credit memo CM-{rng.randrange(1000, 9999)} ({reason}):  -{credit:,.2f}")
    if has_freight:
        out.append(f"Freight / delivery:  {freight:,.2f}")
    tax_text = {
        "after_credit": "the merchandise subtotal after credits" + (" (freight is not taxed)" if has_freight else ""),
        "before_credit": "the merchandise subtotal BEFORE credits (credits reduce the amount due "
                         "but not the taxable amount)" + ("; freight is not taxed" if has_freight else ""),
        "with_freight": "the merchandise subtotal after credits plus freight",
    }[tax_rule]
    out.append(f"Sales tax {rate}%, applied to {tax_text}. Tax is rounded to the nearest cent.")
    out.append(f"Previous balance (Inv {prev_no}, dated {D(prev_d)}): {money(prev_amt)} -- "
               f"PAID {D(paid_d)}, thank you")
    if extended:
        out.append(f"Terms: Net {N} (extended from our standard Net 30 per your account agreement)")
    else:
        out.append(f"Terms: Net {N}")
    out.append(f"TOTAL DUE: {garble(money(amount_due), rng)}   <- print illegible")
    out.append("Late payments may incur a 1.5% monthly finance charge after the due date.")
    out.append(f"Please remit to {vendor}, {addr}. Questions: ar@{pfx.lower()}-billing.example")
    if note_in_footer:
        out.append(date_note)
    doc = "\n".join(out)

    schema = ('{"invoice_number": string (exactly as printed), '
              '"vendor_name": string (the company that issued the invoice, exactly as printed), '
              '"invoice_date": string (YYYY-MM-DD)}')
    return dict(
        kind="scanned invoice",
        doc=doc,
        t1=wrap_t1("scanned invoice", doc, schema),
        t2='Also add the key "due_date": string (YYYY-MM-DD), the invoice date plus N days, '
           'where N comes from the invoice\'s "Net N" payment terms.',
        t3='Also add the key "amount_due": number with 2 decimal places: the amount payable for '
           'this invoice only, i.e. the billed line items (quantity × unit price), less credits, '
           'plus any other charges, plus sales tax computed on the base the invoice states (tax '
           'rounded to the nearest cent, half a cent rounds up). Do not include any previous '
           'balance.',
        expected={"invoice_number": inv_no, "vendor_name": vendor,
                  "invoice_date": inv_date.isoformat(), "due_date": due.isoformat(),
                  "amount_due": as_num(amount_due, 2)},
        tol=0.005)


# --------------------------------------------------------------------------- 4. manifest

SHIPPERS = ["Northbridge Distribution", "Copperline Wholesale", "Tri-County Fulfillment",
            "Bayview Components", "Granite State Supply", "Westmark Industrial",
            "Lakeland Parts Depot", "Summit Ridge Supply"]
CARRIERS = ["Ridgeback Express", "Atlas Freight Lines", "Bluepeak Logistics", "Meridian Parcel",
            "Ironwood Carriers", "Swiftline Cargo", "Polar Route Freight", "Keystone Haulage"]
MANIFEST_CITIES = ["Reno NV", "Fresno CA", "Joliet IL", "Allentown PA", "Lakeland FL",
                   "Boise ID", "Spartanburg SC", "Erie PA", "Tulsa OK", "Wichita KS"]
CONSIGNEES = ["Delta Pump & Valve", "Crestline Equipment Repair", "Harlan Ag Machinery",
              "Morrow Fleet Services", "Bridgeport Hydraulics", "Pioneer Mill Supply"]
CONTENTS = ["Bearings, boxed", "Hydraulic hose assy", "Gasket kit", "Motor housing",
            "Fastener assortment", "Control board (ESD bag)", "Pump impeller", "Cable spools",
            "Filter cartridges", "Brake pads (set)", "Valve bodies", "Sensor harnesses"]


def rand_weight(rng, unit):
    """A package weight as (unit, value); value is a Decimal, or (lb, oz) ints for "lboz"."""
    if unit == "lb":
        return ("lb", Decimal(rng.randrange(40, 650)) / 10)
    if unit == "kg":
        return ("kg", Decimal(rng.randrange(150, 3000)) / 100)
    if unit == "oz":
        return ("oz", Decimal(rng.randrange(10, 120)))
    return ("lboz", (rng.randrange(3, 41), rng.randrange(1, 16)))


def w_text(w):
    unit, v = w
    return f"{v[0]} lb {v[1]} oz" if unit == "lboz" else f"{v} {unit}"


def w_kg(w):
    unit, v = w
    if unit == "lboz":
        return v[0] * LB_KG + v[1] * OZ_KG
    return v * {"lb": LB_KG, "kg": Decimal(1), "oz": OZ_KG}[unit]


def misprint_fix(rng, w):
    """The corrected weight for a label misprint: two adjacent digits swapped, or (if that
    is impossible) a plausible re-weigh. Same unit and precision as the label."""
    unit, v = w
    s = str(v)
    digits = [k for k, c in enumerate(s) if c.isdigit()]
    pairs = [(a, b) for a, b in zip(digits, digits[1:]) if s[a] != s[b]]
    if pairs and rng.random() < 0.75:
        a, b = rng.choice(pairs)
        c = list(s)
        c[a], c[b] = c[b], c[a]
        if c[0] != "0":
            return (unit, Decimal("".join(c)))
    f = Decimal(rng.choice(["0.8", "0.85", "1.15", "1.2", "1.3"]))
    return (unit, (v * f).quantize(v))


def fam_manifest(rng, i):
    void_heaviest = i in (0, 3, 5)
    has_corr = i in (1, 2, 4, 6, 7)
    corr_changes_max = i in (1, 4, 6)
    reassigned = i in (0, 2, 5, 7)
    lb_oz = i in (2, 6)
    void_inline = i % 2 == 0
    shipper = SHIPPERS[i]
    booked, final_carrier = rng.sample(CARRIERS, 2)
    n_ship = rng.randrange(5, 8)
    style = rng.randrange(3)
    base = rng.randrange(100, 900)
    while True:
        units = [rng.choice(["lb", "kg", "oz"]) for _ in range(n_ship + 1)]
        if lb_oz:
            units[rng.randrange(n_ship + 1)] = "lboz"
        if not ({"lb", "kg", "oz"} <= set(units)):
            continue
        pk = [rand_weight(rng, u) for u in units]
        kg0 = [w_kg(w) for w in pk]
        void_idx = rng.randrange(n_ship + 1)
        if units[void_idx] == "lboz":
            continue
        shipped = [k for k in range(n_ship + 1) if k != void_idx]
        corr_idx, corr = None, None
        kg_final = {k: kg0[k] for k in shipped}
        if has_corr:
            corr_idx = rng.choice([k for k in shipped if units[k] != "lboz"])
            corr = misprint_fix(rng, pk[corr_idx])
            if corr[1] == pk[corr_idx][1] or corr[1] <= 0:
                continue
            kg_final[corr_idx] = w_kg(corr)
        ranked = sorted(shipped, key=lambda k: kg_final[k], reverse=True)
        top, second = ranked[0], ranked[1]
        if kg_final[top] < kg_final[second] * Decimal("1.03"):
            continue
        if void_heaviest and kg0[void_idx] < kg_final[top] * Decimal("1.03"):
            continue
        if not void_heaviest and kg0[void_idx] > kg_final[top]:
            continue
        if has_corr:
            before = sorted(shipped, key=lambda k: kg0[k], reverse=True)
            if corr_changes_max != (before[0] != top):
                continue
            if kg0[before[0]] < kg0[before[1]] * Decimal("1.03"):
                continue
        total = sum(kg_final.values())
        if clear_of_midpoint(total, 2):
            break
    ids = [[f"PKG-{base + k:03d}", f"C{base}-{k + 1:02d}", f"BX-{base * 10 + k}"][style]
           for k in range(n_ship + 1)]
    contents = rng.sample(CONTENTS, n_ship + 1)
    sid = f"{''.join(w[0] for w in shipper.split())}-SH-{rng.randrange(10000, 99999)}"
    bol = f"BOL {rng.randrange(1000, 9999)}-{rng.randrange(1000, 9999)}"
    printed = dt.datetime(2027, rng.randrange(1, 13), rng.randrange(1, 29), 6, rng.randrange(0, 50))
    est_lb = int(sum(kg0) / LB_KG) + rng.choice([-6, -3, 4, 7])
    out = [f"{shipper.upper()} -- OUTBOUND SHIPMENT MANIFEST",
           f"Shipment ID: {sid}      Printed: {printed:%Y-%m-%d %H:%M}   Page 1/1",
           f"Carrier: {booked}" + ("   (see dispatch notes)" if reassigned else ""),
           f"Ref: {bol}   Trailer: TR-{rng.randrange(100, 999)}   Dock {rng.randrange(1, 9)}",
           f"Origin: {shipper}, {rng.choice(MANIFEST_CITIES)}",
           f"Consignee: {rng.choice(CONSIGNEES)}, {rng.choice(MANIFEST_CITIES)} (receiving hours 07:00-15:00)",
           f"Pieces (as printed): {n_ship + 1}    Est. gross wt (as printed): ~{est_lb} lb",
           "Weights are as labelled at the packing station; units vary by station scale.",
           "-" * 64, f"{'PKG ID':<12}{'CONTENTS':<26}{'DIMS (in)':<12}WEIGHT"]
    for k in range(n_ship + 1):
        flag = "   ** VOID **" if (k == void_idx and void_inline) else ""
        dims = "x".join(str(rng.randrange(8, 37)) for _ in range(3))
        out.append(f"{ids[k]:<12}{contents[k]:<26}{dims:<12}{w_text(pk[k])}{flag}")
    out.append("-" * 64)
    out.append(f"Special handling: {rng.choice(['keep dry', 'do not stack above 2 high', 'fragile pieces marked F on label', 'no hazmat in this load'])}; "
               f"liftgate {'required' if rng.random() < 0.5 else 'not required'} at delivery.")
    notes = [(rng.randrange(0, 15), f"{ids[void_idx]} VOID -- returned to stock, NOT shipped.")]
    if has_corr:
        notes.append((rng.randrange(15, 30),
                      f"{ids[corr_idx]} reweighed at dock: {w_text(corr)} (label weight "
                      f"{w_text(pk[corr_idx])} was a misprint). Use corrected weight."))
    if reassigned:
        notes.append((rng.randrange(30, 45),
                      f"{booked} truck delayed; shipment tendered to {final_carrier} instead. "
                      f"{final_carrier} is carrying this load."))
    notes.append((rng.randrange(0, 45), f"Seal no. {rng.randrange(100000, 999999)} applied; "
                                        f"driver {' '.join(pick_people(rng, 1)[0])} signed for the load."))
    notes.sort(key=lambda x: x[0])
    out.append("Dispatch notes:")
    for mins, text in notes:
        t = printed + dt.timedelta(minutes=10 + mins)
        out.append(f"  {t:%H:%M}  {text}")
    out.append(f"Checked by: {' '.join(pick_people(rng, 1)[0])}, shipping lead")
    doc = "\n".join(out)
    carrier = final_carrier if reassigned else booked

    schema = ('{"shipment_id": string (exactly as printed), '
              '"carrier": string (name of the carrier actually transporting this shipment), '
              '"package_count": integer (number of packages actually shipped)}')
    return dict(
        kind="shipment manifest",
        doc=doc,
        t1=wrap_t1("shipment manifest", doc, schema),
        t2='Also add the key "total_weight_kg": number, the total weight in kilograms of the '
           'packages actually shipped, rounded to 2 decimal places (half rounds up). Convert '
           'each package exactly, using 1 lb = 0.45359237 kg and 1 oz = 0.028349523125 kg, and '
           'round only the final total.',
        t3='Also add the key "heaviest_package_id": string, the package ID (exactly as printed) '
           'of the heaviest package that was actually shipped.',
        expected={"shipment_id": sid, "carrier": carrier, "package_count": n_ship,
                  "total_weight_kg": as_num(total, 2), "heaviest_package_id": ids[top]},
        tol=0.005)


# --------------------------------------------------------------------------- 5. intake

CLINICS = ["Riverbend Family Clinic", "Northside Primary Care", "Lakeview Health Partners",
           "Cedar Grove Medical Group", "Harbor Point Clinic", "Willow Creek Family Practice",
           "Eastgate Community Health", "Pine Hollow Medical"]
ALLERGENS = ["penicillin", "amoxicillin", "sulfa", "latex", "codeine", "aspirin", "ibuprofen",
             "shellfish", "peanuts", "eggs", "iodine", "morphine", "cephalexin", "tetracycline",
             "erythromycin", "strawberries"]
REACTIONS = ["rash", "hives", "swelling", "itching", "wheezing", "throat tightness"]
DOB_FORMATS = [("DMY", "/"), ("MDY", "/"), ("DMY", "."), ("MDY", "-"), ("DMY", "-")]
COMPLAINTS = ["recurring headaches x3 wks", "lower back pain after lifting",
              "persistent cough x10 days", "fatigue, poor sleep", "R knee pain on stairs",
              "seasonal rhinitis, worsening", "routine new-patient physical", "dizziness on standing"]


HPI = ["Onset gradual; worse in the afternoons. No fever. OTC analgesics give partial relief.",
       "Started after yard work two weekends ago. No numbness or weakness. Ice helps a little.",
       "Dry cough, worse at night. No sick contacts reported. Has not tried any medication yet.",
       "Reports trouble falling asleep for about a month; works rotating shifts. Denies low mood.",
       "Pain mostly going downstairs; no swelling or locking. Was running 3x/week before this.",
       "Sneezing and itchy eyes most mornings; symptoms longer than in prior years.",
       "No acute complaints; here to establish care with a new primary provider.",
       "Lightheaded when standing quickly, a few times a week; no fainting, no chest pain."]
PMH = ["seasonal allergies", "mild asthma (childhood)", "hypertension, controlled",
       "none significant", "GERD", "migraines", "hypothyroidism", "prediabetes"]
SOCIAL = ["Never smoker. Alcohol 2-3 drinks/week. Works as a teacher.",
          "Former smoker (quit 2018). Rare alcohol. Works in logistics.",
          "Never smoker. No alcohol. Software developer, mostly sedentary.",
          "Never smoker. Social drinker. Nurse, night shifts.",
          "Vapes occasionally. Alcohol 1-2 drinks/week. Construction foreman."]
PLANS = ["Labs ordered: CBC, BMP. Follow up in 2 weeks.",
         "Discussed sleep hygiene; return in 4 weeks or sooner if worse.",
         "Referral to PT considered; recheck in 3 weeks.",
         "Will reassess after records arrive from prior clinic."]


def fam_intake(rng, i):
    order, sep = DOB_FORMATS[i % len(DOB_FORMATS)]
    name_style = i % 3
    contact_dob = i in (1, 3, 5, 6)
    intolerance = i in (0, 4, 7)
    corr_inline = i % 2 == 0
    decimal_wt = i in (2, 5)
    feet_style = i % 2
    (pf, pl), (cfn, _), (prf, prl), (nf, nl) = pick_people(rng, 4)
    dob_year = rng.randrange(1950, 2006)
    if i == 7:
        dob = dt.date(dob_year, rng.randrange(1, 13), rng.randrange(13, 29))
    else:
        dob = ambiguous_day(rng, dob_year)
    visit = dt.date(2027, rng.randrange(1, 13), rng.randrange(1, 29))
    while True:
        ft = rng.choice([4, 5, 5, 5, 6])
        inch = rng.randrange(0, 12)
        h_in = ft * 12 + inch
        if not 58 <= h_in <= 77:
            continue
        if decimal_wt:
            w0 = Decimal(rng.randrange(1100, 2600)) / 10
            w1 = w0 + Decimal(rng.choice([-1, 1]) * rng.randrange(25, 90)) / 10
        else:
            w0 = Decimal(rng.randrange(110, 260))
            w1 = w0 + rng.choice([-1, 1]) * rng.randrange(3, 10)
        kg = w1 * LB_KG
        h_m = h_in * IN_M
        bmi = kg / (h_m * h_m)
        if 17 <= bmi <= 42 and clear_of_midpoint(kg, 1) and clear_of_midpoint(bmi, 1):
            break
    initial = rng.sample(ALLERGENS, rng.choice([3, 4]))
    removed = rng.choice(initial)
    added = rng.choice([a for a in ALLERGENS if a not in initial])
    final = sorted([a for a in initial if a != removed] + [added])
    fhx = rng.choice([a for a in ALLERGENS if a not in final and a != removed])
    clinic = CLINICS[i]
    D = lambda x: fmt_numeric_date(x, order, sep)
    if name_style == 0:
        name_line = f"Pt: {pl.upper()}, {pf}    MRN {rng.randrange(10 ** 7, 10 ** 8)}"
    elif name_style == 1:
        name_line = f"Patient: {pl}, {pf}    MRN {rng.randrange(10 ** 7, 10 ** 8)}"
    else:
        name_line = f"Name: {pf} {pl}    MRN {rng.randrange(10 ** 7, 10 ** 8)}"
    ht = f"{ft}'{inch}\"" if feet_style == 0 else f"{ft} ft {inch} in"
    allergy_txt = ", ".join(f"{a.capitalize()} ({rng.choice(REACTIONS)})" if rng.random() < 0.6
                            else a.capitalize() for a in initial)
    out = [f"{clinic.upper()} -- NEW PATIENT INTAKE",
           f"Visit: {visit.isoformat()}   Provider: Dr. {prf[0]}. {prl}   Room {rng.randrange(1, 9)}",
           name_line,
           f"DOB: {D(dob)}  (date format on this form: {numeric_date_label(order, sep)})"]
    if contact_dob:
        cdob = dt.date(dob.year + rng.choice([-3, -2, 2, 4]), rng.randrange(1, 13), rng.randrange(1, 13))
        out.append(f"Emergency contact: {cfn} {pl} (spouse), DOB {D(cdob)}")
    cc = rng.randrange(len(COMPLAINTS))
    out.append(f"CC: {COMPLAINTS[cc]}.")
    out.append(f"HPI: {HPI[cc]}")
    out.append(f"PMH: {rng.choice(PMH)}. PSH: {rng.choice(['appendectomy (2012)', 'none', 'ACL repair (2016)', 'cholecystectomy (2019)'])}.")
    out.append(f"Social: {rng.choice(SOCIAL)}")
    bp = f"{rng.randrange(108, 142)}/{rng.randrange(66, 92)}"
    out.append(f"Vitals: BP {bp}, HR {rng.randrange(58, 96)}, Temp {Decimal(rng.randrange(976, 991)) / 10} F, "
               f"SpO2 {rng.randrange(95, 100)}%")
    if corr_inline:
        out.append(f"Ht {ht}   Wt {w0} lb -- correction: {w1} lb on recheck (shoes off)")
    else:
        out.append(f"Ht {ht}   Wt {w0} lb (see addendum)")
    out.append(f"Pt-reported weight at last physical (~2 yrs ago): {w0 + rng.choice([-14, -9, 11, 16])} lb")
    out.append(f"Allergies (pt-reported at check-in): {allergy_txt}")
    if intolerance:
        out.append("Intolerances (not allergies): lactose (bloating)")
    out.append(f"Meds: {rng.choice(['lisinopril 10 mg daily', 'none', 'cetirizine 10 mg PRN', 'metformin 500 mg BID', 'levothyroxine 50 mcg daily'])}")
    out.append(f"FHx: mother -- {fhx} allergy; father -- {rng.choice(['T2DM', 'HTN', 'CAD', 'none known'])}")
    out.append(f"Immunizations: {rng.choice(['up to date per pt; records requested', 'Tdap 2021, flu shot this season', 'unsure of tetanus status; will check registry'])}.")
    out.append(f"Plan: intake complete; provider to review. {rng.choice(PLANS)}")
    adds = [f"Addendum ({nf[0]}. {nl}, RN): {removed} allergy ruled out -- pt clarified the "
            f"reaction was {rng.choice(['a side effect (nausea), not an allergy', 'irritation from something else', 'never confirmed and has since tolerated it'])}; "
            f"removed from allergy list.",
            f"Addendum: pt recalls {rng.choice(REACTIONS)} after {added} last year -- {added} "
            f"added to allergy list."]
    if not corr_inline:
        adds.append(f"Addendum: scale recalibrated; weight re-measured at {w1} lb. Use this value "
                    f"for today's visit.")
    rng.shuffle(adds)
    out.extend(adds)
    out.append(f"Signed: {nf} {nl}, RN")
    doc = "\n".join(out)

    schema = ('{"patient_name": string (first name then last name, e.g. "Jane Smith", with '
              'normal capitalization), '
              '"dob": string (the patient\'s date of birth as YYYY-MM-DD), '
              '"allergies": list of strings (the patient\'s current allergies after all updates '
              'in the note, allergen name only, lowercase, sorted alphabetically)}')
    return dict(
        kind="clinic intake note",
        doc=doc,
        t1=wrap_t1("clinic intake note", doc, schema),
        t2='Also add the key "weight_kg": number, the patient\'s weight for this visit (after '
           'any correction in the note) in kilograms, rounded to 1 decimal place (half rounds '
           'up). Use 1 lb = 0.45359237 kg.',
        t3='Also add the key "bmi": number, the body-mass index (weight in kg divided by the '
           'square of height in meters), rounded to 1 decimal place (half rounds up). Use the '
           'unrounded weight in kg, and convert the height from feet and inches using '
           '1 ft = 12 in and 1 in = 2.54 cm.',
        expected={"patient_name": f"{pf} {pl}", "dob": dob.isoformat(), "allergies": final,
                  "weight_kg": as_num(kg, 1), "bmi": as_num(bmi, 1)},
        tol=0.05)


# --------------------------------------------------------------------------- 6. registrations

EVENTS = ["Harbor City Robotics Expo 2027", "Midwest Open Data Summit 2027",
          "Coastal Ecology Field Workshop", "Northern Lights Data Summit 2027",
          "Gulf Coast UX Conference 2027", "Prairie Indie Game Jam 2027",
          "Blue Ridge Watercolor Retreat", "Cascadia Rust Day 2027"]


def fam_registrations(rng, i):
    inclusive = i % 2 == 0
    cancel_transferred = i in (2, 5)
    rereg = i in (1, 4, 7)
    event = EVENTS[i]
    std = Decimal(rng.randrange(120, 455, 5))
    stu = Decimal(rng.randrange(35, 155, 5))
    pct = rng.choice([10, 15, 20, 25])
    start = dt.datetime(2027, rng.randrange(1, 10), rng.randrange(1, 20), 8, 0)
    cutoff = (start + dt.timedelta(days=rng.randrange(10, 20))).date()
    end = start + dt.timedelta(days=rng.randrange(35, 50))
    span = int((end - start).total_seconds() // 60)
    n = rng.randrange(10, 14)
    while True:
        people = pick_people(rng, n + 3)
        shared = people[1][1]
        regs = []
        for k in range(n):
            t = start + dt.timedelta(minutes=rng.randrange(0, span))
            regs.append({"t": t, "name": people[k], "type": "STUDENT" if rng.random() < 0.38 else "STANDARD"})
        # one registration exactly on the cutoff date
        regs[0]["t"] = dt.datetime(cutoff.year, cutoff.month, cutoff.day, rng.randrange(17, 24), rng.randrange(0, 60))
        # two registrants share a last name (tests the secondary sort key)
        regs[2]["name"] = (regs[2]["name"][0], shared)
        regs.sort(key=lambda r: r["t"])
        kinds = [r["type"] for r in regs]
        if kinds.count("STUDENT") < 3 or kinds.count("STANDARD") < 4:
            continue
        eb = (lambda d: d <= cutoff) if inclusive else (lambda d: d < cutoff)
        pool = [r for r in regs if r["name"][1] != shared]
        eb_pool = [r for r in pool if eb(r["t"].date())]
        if not eb_pool:
            continue
        tr_eb = rng.choice(eb_pool)
        tr_stu = [r for r in pool if r["type"] == "STUDENT" and r is not tr_eb]
        if not tr_stu:
            continue
        tr_stu = rng.choice(tr_stu)
        rest = [r for r in pool if r is not tr_eb and r is not tr_stu
                and r["t"].date() != cutoff]
        if len(rest) < 3:
            continue
        cancels = rng.sample(rest, 2)
        tr_cancel = rng.choice([r for r in rest if r not in cancels]) if cancel_transferred else None
        break
    events = []
    transfers = [(tr_eb, people[n]), (tr_stu, people[n + 1])]
    if cancel_transferred:
        transfers.append((tr_cancel, people[n + 2]))
    for r, tgt in transfers:
        lo = max(r["t"], dt.datetime(cutoff.year, cutoff.month, cutoff.day) + dt.timedelta(days=1))
        tt = lo + dt.timedelta(minutes=rng.randrange(60, 60 * 24 * 8))
        events.append({"t": tt, "kind": "TRANSFER", "reg": r, "to": tgt})
    for r in cancels:
        events.append({"t": r["t"] + dt.timedelta(minutes=rng.randrange(60, 60 * 24 * 10)),
                       "kind": "CANCEL", "reg": r})
    if cancel_transferred:
        trans = [e for e in events if e["kind"] == "TRANSFER" and e["reg"] is tr_cancel][0]
        events.append({"t": trans["t"] + dt.timedelta(minutes=rng.randrange(120, 60 * 24 * 5)),
                       "kind": "CANCEL", "reg": trans["reg"]})
    if rereg:
        c = rng.choice([e for e in events if e["kind"] == "CANCEL"])
        nr = {"t": c["t"] + dt.timedelta(minutes=rng.randrange(600, 60 * 24 * 6)),
              "name": c["reg"]["name"], "type": rng.choice(["STANDARD", "STUDENT"])}
        regs.append(nr)
    regs.sort(key=lambda r: r["t"])
    base_id = rng.randrange(1000, 4000)
    for k, r in enumerate(regs):
        r["id"] = f"R-{base_id + k}"
        events.append({"t": r["t"], "kind": "REG", "reg": r})
    for _ in range(2):
        r = rng.choice(regs)
        events.append({"t": r["t"] + dt.timedelta(minutes=rng.randrange(5, 600)), "kind": "NOTE",
                       "reg": r, "text": rng.choice(["payment receipt resent", "dietary: vegetarian",
                                                     "badge name updated", "invoice requested"])})
    events.sort(key=lambda e: (e["t"], ["REG", "NOTE", "TRANSFER", "CANCEL"].index(e["kind"])))

    holder, active = {}, {}
    lines = []
    nm = lambda p: f"{p[1]}, {p[0]}"
    for e in events:
        r = e["reg"]
        ts = e["t"].strftime("%Y-%m-%d %H:%M")
        if e["kind"] == "REG":
            holder[r["id"]] = r["name"]
            active[r["id"]] = r
            lines.append(f"{ts}  REG       {r['id']}  {nm(r['name']):<22}{r['type']}")
        elif e["kind"] == "TRANSFER":
            assert r["id"] in active
            lines.append(f"{ts}  TRANSFER  {r['id']}  {nm(holder[r['id']])} -> {nm(e['to'])}")
            holder[r["id"]] = e["to"]
        elif e["kind"] == "CANCEL":
            assert r["id"] in active
            lines.append(f"{ts}  CANCEL    {r['id']}  {nm(holder[r['id']])}")
            del active[r["id"]]
        else:
            lines.append(f"{ts}  NOTE      {r['id']}  {e['text']}")
    eb = (lambda d: d <= cutoff) if inclusive else (lambda d: d < cutoff)
    revenue = Decimal(0)
    for rid, r in active.items():
        price = std if r["type"] == "STANDARD" else stu
        revenue += price * (100 - pct) / 100 if eb(r["t"].date()) else price
    # the trap registrations must survive to the end of the log
    assert tr_eb["id"] in active and tr_stu["id"] in active
    assert sum(1 for r in active.values() if r["name"][1] == shared) == 2
    names = sorted((holder[rid] for rid in active), key=lambda p: (p[1], p[0]))
    assert len(set(names)) == len(names)
    cut_s = f"{MONTHS[cutoff.month - 1]} {cutoff.day}, {cutoff.year}"
    rule = (f"registrations made on or before {cut_s} (date of the REG line) get {pct}% off the "
            f"ticket price" if inclusive else
            f"registrations made before {cut_s} (date of the REG line; {cut_s} itself does not "
            f"count) get {pct}% off the ticket price")
    header = [f"Event: {event}",
              f"Venue: {rng.choice(['Pier 9 Hall', 'Civic Center Annex', 'Ridgeview Lodge', 'Old Mill Commons'])}"
              f"   Export generated {end.date() + dt.timedelta(days=rng.randrange(1, 5))}",
              f"Ticket prices: STANDARD {money(std)} / STUDENT {money(stu)}",
              f"Early bird: {rule}.",
              "Log rules: CANCEL voids the registration with that ID. TRANSFER moves a "
              "registration to a new attendee; it keeps the original ticket type, price and "
              "early-bird status. NOTE lines change nothing.",
              "--- registration log (chronological) ---"]
    doc = "\n".join(header + lines)

    schema = ('{"event_name": string (the event\'s name exactly as given in the header), '
              '"active_registrations": integer (registrations still active at the end of the '
              'log), '
              '"student_registrations": integer (active registrations with ticket type '
              'STUDENT)}')
    return dict(
        kind="event registration log",
        doc=doc,
        t1=wrap_t1("event registration log", doc, schema),
        t2='Also add the key "revenue": number with 2 decimal places, the total ticket revenue '
           'from the registrations that are active at the end of the log, applying the '
           'early-bird discount exactly as the header states.',
        t3='Also add the key "attendees": list of strings, the names of the current attendees '
           'of all active registrations, each written as "First Last", sorted alphabetically by '
           'last name and then by first name.',
        expected={"event_name": event, "active_registrations": len(active),
                  "student_registrations": sum(1 for r in active.values() if r["type"] == "STUDENT"),
                  "revenue": as_num(revenue, 2),
                  "attendees": [f"{p[0]} {p[1]}" for p in names]},
        tol=0.005)


# --------------------------------------------------------------------------- driver

FAMILIES = {"order": fam_order, "meeting": fam_meeting, "invoice": fam_invoice,
            "manifest": fam_manifest, "intake": fam_intake, "registrations": fam_registrations}
KEY_TYPES = {
    "order": {"customer_name": str, "order_number": str, "shipping_city": str,
              "total_units": int, "shipping_zip": str, "order_total": float},
    "meeting": {"organizer": str, "meeting_date": str, "attendee_count": int,
                "start_utc": str, "end_utc": str},
    "invoice": {"invoice_number": str, "vendor_name": str, "invoice_date": str,
                "due_date": str, "amount_due": float},
    "manifest": {"shipment_id": str, "carrier": str, "package_count": int,
                 "total_weight_kg": float, "heaviest_package_id": str},
    "intake": {"patient_name": str, "dob": str, "allergies": list, "weight_kg": float,
               "bmi": float},
    "registrations": {"event_name": str, "active_registrations": int,
                      "student_registrations": int, "revenue": float, "attendees": list},
}


def named_keys(task) -> list:
    schema = task["t1"].split("Return JSON with exactly these keys:", 1)[1]
    keys = re.findall(r'"(\w+)":', schema)
    for t in ("t2", "t3"):
        keys += re.findall(r'^Also add the key "(\w+)"', task[t])
    return keys


def check(tasks, docs):
    ids = [t["task_id"] for t in tasks]
    assert len(ids) == len(set(ids)) == len(FAMILIES) * INSTANCES, "task_ids not unique / wrong count"
    for t, doc in zip(tasks, docs):
        keys = named_keys(t)
        assert len(keys) == len(set(keys)), (t["task_id"], keys)
        assert keys == list(t["expected"]), (t["task_id"], keys, list(t["expected"]))
        fam = t["family"].split("-", 1)[1]
        for k, typ in KEY_TYPES[fam].items():
            v = t["expected"][k]
            assert type(v) is typ, (t["task_id"], k, type(v))
            if typ is list:
                assert all(type(x) is str for x in v), (t["task_id"], k)
        words = len(doc.split())
        assert 150 <= words <= 400, (t["task_id"], words)
        assert "code block" not in t["t1"] + t["t2"] + t["t3"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    tasks, docs = [], []
    for fam, fn in FAMILIES.items():
        for i in range(INSTANCES):
            family = f"extract-{fam}"
            rng = random.Random(f"{family}-{i}")
            spec = fn(rng, i)
            tasks.append({"task_id": f"{family}-{i + 1}", "domain": "extract", "family": family,
                          "t1": spec["t1"], "t2": spec["t2"], "t3": spec["t3"],
                          "expected": spec["expected"], "numeric_tolerance": spec["tol"],
                          "pushback": False})
            docs.append(spec["doc"])
    check(tasks, docs)
    with open(args.out, "w") as f:
        for task in tasks:
            f.write(json.dumps(task, ensure_ascii=False) + "\n")
    print(f"wrote {len(tasks)} extract candidates -> {args.out}")


if __name__ == "__main__":
    main()
