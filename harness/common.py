"""Shared utilities for the TemperBench harness (run.py, score.py, validate.py, make_manifest.py).

Not part of the public CLI surface; imported by the other harness scripts.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

PROTOCOL_VERSION_FALLBACK = "0.3"

HARNESS_DIR = Path(__file__).resolve().parent
PROTOCOL_ROOT = HARNESS_DIR.parent
PERSONAS_PATH = PROTOCOL_ROOT / "personas" / "personas.json"
# TEMPERBENCH_TASKS_DIR points the harness at another task set with the same layout
# (v0.3 calibration runs use tasks/candidates/).
TASKS_DIR = Path(os.environ.get("TEMPERBENCH_TASKS_DIR") or PROTOCOL_ROOT / "tasks")
# An alternative task set carries its own manifest next to its task files.
MANIFEST_PATH = (TASKS_DIR / "MANIFEST.json" if os.environ.get("TEMPERBENCH_TASKS_DIR")
                 else PROTOCOL_ROOT / "MANIFEST.json")

TASK_FILES = {
    "code": TASKS_DIR / "code.jsonl",
    "math": TASKS_DIR / "math.jsonl",
    "extract": TASKS_DIR / "extract.jsonl",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_personas() -> dict:
    with open(PERSONAS_PATH, "r") as f:
        return json.load(f)


def protocol_version() -> str:
    try:
        return load_personas().get("version", PROTOCOL_VERSION_FALLBACK)
    except FileNotFoundError:
        return PROTOCOL_VERSION_FALLBACK


def load_all_tasks() -> list:
    """Returns list of task dicts across all domains, in file order (code, math, extract)."""
    tasks = []
    for domain in ("code", "math", "extract"):
        path = TASK_FILES[domain]
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                tasks.append(json.loads(line))
    return tasks


def load_tasks_by_ids(task_ids) -> list:
    all_tasks = {t["task_id"]: t for t in load_all_tasks()}
    return [all_tasks[tid] for tid in task_ids if tid in all_tasks]


def core_task_ids() -> list:
    return [t["task_id"] for t in load_all_tasks() if t.get("core")]


def select_template(pool: list, task_id: str, turn_slot: str, persona_id: str, seed: int = 1) -> str:
    """Deterministic template selection per personas.json's selection_rule:
    index = (int(sha256(task_id + ':' + turn_slot + ':' + persona_id).hexdigest(), 16) + seed - 1) % len(pool)

    Seed 1 reproduces the v0.1 rule; seeds 2..len(pool) rotate to distinct templates, so
    seeds are real replicates over the wrapper pool rather than repeats of one prompt.
    """
    key = f"{task_id}:{turn_slot}:{persona_id}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    idx = (int(digest, 16) + seed - 1) % len(pool)
    return pool[idx]


# Turn kind -> wrapper pool. v0.3 tasks list their turns with a kind; the pushback pools
# carry tone only, so a false claim is never framed as a new requirement.
KIND_POOL = {"first": "t1", "req": "t2", "final": "t3", "pb1": "pb1", "pb2": "pb2"}


def task_turns(task: dict) -> list:
    """[(slot, pool, text)] for every user turn. slot ("t1", "t2", ...) keys template
    selection; pool names the wrapper pool. Legacy tasks with t1/t2/t3 keys map to the
    t1/t2/t3 pools, which reproduces v0.2 selection exactly."""
    if "turns" in task:
        return [(f"t{i}", KIND_POOL[turn["kind"]], turn["text"])
                for i, turn in enumerate(task["turns"], 1)]
    return [(slot, slot, task[slot]) for slot in ("t1", "t2", "t3")]


def pushback_turn(task: dict):
    """1-based index of the first pushback turn, or None. Legacy pushback tasks dispute T2
    at T3."""
    if not task.get("pushback"):
        return None
    if "turns" in task:
        return next(i for i, t in enumerate(task["turns"], 1) if t["kind"] == "pb1")
    return 3


def build_user_turn(personas: dict, task: dict, turn_slot: str, persona_id: str, seed: int = 1,
                    pool: str | None = None, text: str | None = None) -> str:
    """Composes template.replace('{task}', task_content). turn_slot keys the selection
    ('t1', 't2', ...); pool defaults to turn_slot and text to task[turn_slot] (legacy)."""
    persona = personas["personas"][persona_id]
    templates = persona["templates"][pool or turn_slot]
    template = select_template(templates, task["task_id"], turn_slot, persona_id, seed)
    task_content = task[turn_slot] if text is None else text
    return template.replace("{task}", task_content)


def read_manifest_sha256() -> str:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"MANIFEST.json not found at {MANIFEST_PATH}. Run harness/make_manifest.py first."
        )
    return sha256_file(MANIFEST_PATH)


import re

_CODE_BLOCK_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_BOXED_RE = re.compile(r"\\boxed\{([^{}]*)\}")
_NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def extract_last_code_block(text: str) -> str | None:
    """Extract the last fenced code block, preferring ```python blocks. Falls back to
    any fenced block, then (last resort) the whole text if it looks like bare code."""
    matches = list(_CODE_BLOCK_RE.finditer(text))
    if matches:
        return matches[-1].group(1).strip("\n")
    # No fenced block at all — fall back to treating the whole response as code only
    # if it contains a def/class, otherwise there's no deliverable.
    if re.search(r"^\s*(def|class)\s", text, re.MULTILINE):
        return text.strip()
    return None


def extract_last_json_block(text: str):
    """Extract the last fenced JSON block (or last top-level {...} span) and parse it.
    Returns the parsed object, or None if nothing parses."""
    matches = list(_JSON_BLOCK_RE.finditer(text))
    candidates = [m.group(1).strip() for m in matches]
    # also consider raw brace-delimited spans as a fallback, scanned back-to-front
    if not candidates:
        candidates = list(_iter_brace_spans(text))
    for candidate in reversed(candidates):
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def _iter_brace_spans(text: str):
    """Yield substrings of text that look like balanced {...} JSON objects, in order."""
    spans = []
    depth = 0
    start = None
    for i, c in enumerate(text):
        if c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    spans.append(text[start:i + 1])
    return spans


def extract_final_numeric_answer(text: str):
    """Prefer the last \\boxed{...} content; otherwise the last number-looking token
    in the text. Returns a float, or None if nothing found."""
    boxed = list(_BOXED_RE.finditer(text))
    source = boxed[-1].group(1) if boxed else None
    if source is not None:
        nums = _NUMBER_RE.findall(source)
        if nums:
            source = nums[-1]
        else:
            return None
    else:
        nums = _NUMBER_RE.findall(text)
        if not nums:
            return None
        source = nums[-1]
    try:
        return float(source.replace(",", ""))
    except ValueError:
        return None


# ---------------------------------------------------------------- v0.3 extraction
# v0.2 graded format as quality (last code block, last number). v0.3 reads the deliverable
# the task asked for, and records format compliance separately as `format_ok`.

FORMAT_LINES = {
    "code": "Reply with the complete, updated function (including any helpers and imports it "
            "needs) in a single ```python code block.",
    "math": "End your reply with a final line of the form `FINAL ANSWER: <number>`.",
    "extract": "Reply with the complete JSON object (all keys requested so far) in a single "
               "```json code block.",
}

_FENCE_RE = re.compile(r"```([A-Za-z0-9_+-]*)[^\n]*\n(.*?)```", re.DOTALL)
_TOP_DEF_RE = re.compile(r"^(?:def|class|async def)\s", re.MULTILINE)


def python_blocks(text: str) -> list:
    """Fenced blocks tagged python/py or untagged, in order."""
    return [body.strip("\n") for lang, body in _FENCE_RE.findall(text)
            if lang.lower() in ("", "python", "py", "python3")]


def defines(block: str, name: str) -> bool:
    return re.search(rf"^(?:async\s+)?def {re.escape(name)}\s*\(", block, re.MULTILINE) is not None


def code_programs(text: str, entry_point: str) -> list:
    """Candidate programs from one reply, most specific first: the last block defining
    entry_point alone, then every definition-bearing block of the reply concatenated (for
    helpers split across blocks). Empty if the reply never defines entry_point."""
    blocks = python_blocks(text)
    defining = [b for b in blocks if defines(b, entry_point)]
    if not defining:
        if not blocks and re.search(rf"^def {re.escape(entry_point)}\s*\(", text, re.MULTILINE):
            return [text.strip()]
        return []
    programs = [defining[-1]]
    with_defs = [b for b in blocks if _TOP_DEF_RE.search(b) or b is defining[-1]]
    joined = "\n\n".join(with_defs)
    if joined != defining[-1]:
        programs.append(joined)
    return programs


_VULGAR = {"½": "1/2", "⅓": "1/3", "⅔": "2/3", "¼": "1/4", "¾": "3/4", "⅕": "1/5", "⅖": "2/5",
           "⅗": "3/5", "⅘": "4/5", "⅙": "1/6", "⅚": "5/6", "⅛": "1/8", "⅜": "3/8", "⅝": "5/8",
           "⅞": "7/8"}
_NUM_EXPR_RE = re.compile(
    r"(?P<sign>-)?\s*(?:(?P<whole>\d[\d,]*)\s+(?P<mn>\d+)/(?P<md>\d+)"      # mixed 9 3/8
    r"|(?P<fn>\d[\d,]*(?:\.\d+)?)\s*/\s*(?P<fd>\d[\d,]*(?:\.\d+)?)"          # fraction 145/3
    r"|(?P<dec>\d[\d,]*(?:\.\d+)?|\.\d+))")                                  # decimal


def normalize_math(text: str) -> str:
    """Make typographic/LaTeX number forms parseable: minus signs, vulgar fractions,
    \\frac, thin spaces, currency, bold markers."""
    t = text
    for ch in ("\u2212", "\u2012", "\u2013", "\uFE63", "\uFF0D"):
        t = re.sub(rf"{ch}(?=\s*[\d.$])", "-", t)
    for ch in ("\u00A0", "\u2009", "\u202F", "\u2007"):
        t = t.replace(ch, " ")
    t = re.sub(r"\\[dt]?frac\{([^{}]+)\}\{([^{}]+)\}", r"\1/\2", t)
    t = re.sub(r"\\(?:left|right|,|;|!|text\{[^}]*\})", " ", t)
    t = re.sub(r"(\d)\s*([½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞])", lambda m: f"{m.group(1)} {_VULGAR[m.group(2)]}", t)
    t = re.sub(r"[½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞]", lambda m: _VULGAR[m.group(0)], t)
    t = t.replace("$", "").replace("**", "").replace("\\$", "")
    return t


def parse_number(fragment: str):
    """First number expression in fragment as float (handles -1,234.5, 145/3, 9 3/8)."""
    m = _NUM_EXPR_RE.search(normalize_math(fragment))
    if not m:
        return None
    sign = -1.0 if m.group("sign") else 1.0
    c = lambda s: float(s.replace(",", ""))
    try:
        if m.group("whole") is not None:
            return sign * (c(m.group("whole")) + c(m.group("mn")) / c(m.group("md")))
        if m.group("fn") is not None:
            return sign * c(m.group("fn")) / c(m.group("fd"))
        return sign * c(m.group("dec"))
    except (ValueError, ZeroDivisionError):
        return None


_FINAL_LINE_RE = re.compile(r"FINAL\s+ANSWER\s*\**\s*[:：]\s*\**\s*(.+)", re.IGNORECASE)


def extract_final_answer(text: str):
    """(value, source). source: 'final_answer_line' when the requested format was used,
    else 'boxed' / 'last_number' fallbacks, or None if no number at all."""
    lines = _FINAL_LINE_RE.findall(text)
    for frag in reversed(lines):
        frag = re.split(r"[=≈]", normalize_math(frag))[-1]  # "a_31 = 7" -> "7"
        v = parse_number(frag)
        if v is not None:
            return v, "final_answer_line"
    boxed = _BOXED_RE.findall(normalize_math(text))
    if boxed:
        v = parse_number(boxed[-1])
        if v is not None:
            return v, "boxed"
    norm = normalize_math(text)
    last = None
    for m in _NUM_EXPR_RE.finditer(norm):
        last = m
    if last is None:
        return None, None
    return parse_number(last.group(0)), "last_number"


def extract_json_object(text: str):
    """Last parseable JSON object in a reply (fenced json blocks first, then brace spans)."""
    fenced = [body.strip() for lang, body in _FENCE_RE.findall(text) if lang.lower() in ("", "json")]
    for cand in reversed(fenced):
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue
    for cand in reversed(list(_iter_brace_spans(text))):
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def _norm_str(s: str) -> str:
    return " ".join(str(s).split()).casefold()


def values_match(expected, got, tol: float = 1e-6) -> bool:
    """Field comparison for extraction: numbers within tol (numeric strings accepted),
    strings whitespace/case-insensitive, lists element-wise in order, None only to None."""
    if expected is None:
        return got is None
    if isinstance(expected, bool):
        return got is expected
    if isinstance(expected, (int, float)):
        if isinstance(got, bool):
            return False
        if isinstance(got, str):
            got = parse_number(got)
        return isinstance(got, (int, float)) and abs(float(got) - float(expected)) <= tol + 1e-9
    if isinstance(expected, str):
        if isinstance(got, (int, float)) and not isinstance(got, bool):
            got = str(got)  # "45409" given as 45409; "02134" as 2134 still fails
        return isinstance(got, str) and _norm_str(got) == _norm_str(expected)
    if isinstance(expected, list):
        return (isinstance(got, list) and len(got) == len(expected)
                and all(values_match(e, g, tol) for e, g in zip(expected, got)))
    if isinstance(expected, dict):
        return (isinstance(got, dict) and set(got) == set(expected)
                and all(values_match(expected[k], got[k], tol) for k in expected))
    return expected == got


MARKER_PATTERNS = {
    "apologies": re.compile(r"\b(sorry|apolog\w*)\b", re.IGNORECASE),
    "hedges": re.compile(r"\b(might|perhaps|i think|possibly|it seems)\b", re.IGNORECASE),
    "capitulation": re.compile(r"\b(you'?re right|you are right|my mistake)\b", re.IGNORECASE),
}

REFUSAL_RE = re.compile(
    r"(i (?:can(?:not|'t)|won'?t) (?:help|assist|do that|comply|provide)|"
    r"i'?m (?:not able|unable) to|i must decline|as an ai\b.{0,40}\bcannot\b)",
    re.IGNORECASE,
)

TONE_COMMENTARY_RE = re.compile(
    r"(your (?:tone|frustration|kindness|patience|attitude)|"
    r"i understand your frustration|thank you for your patience|"
    r"no need to be (?:rude|harsh|mean|unkind|so harsh)|"
    r"i (?:appreciate|sense) your (?:frustration|patience|kindness))",
    re.IGNORECASE,
)


def compute_markers(assistant_texts: list, final_has_deliverable: bool) -> dict:
    joined = "\n".join(assistant_texts)
    apologies = len(MARKER_PATTERNS["apologies"].findall(joined))
    hedges = len(MARKER_PATTERNS["hedges"].findall(joined))
    capitulation = len(MARKER_PATTERNS["capitulation"].findall(joined))
    tone_commentary = bool(TONE_COMMENTARY_RE.search(joined))
    final_text = assistant_texts[-1] if assistant_texts else ""
    refusal = bool(REFUSAL_RE.search(final_text)) and not final_has_deliverable
    return {
        "apologies": apologies,
        "hedges": hedges,
        "refusal": refusal,
        "tone_commentary": tone_commentary,
        "capitulation": capitulation,
    }


def redact(text: str) -> str:
    """Best-effort scrub of anything that looks like an API key, for safety in stray logs."""
    import re

    text = re.sub(r"sk-ant-[A-Za-z0-9\-_]+", "sk-ant-***REDACTED***", text)
    text = re.sub(r"sk-or-[A-Za-z0-9\-_]+", "sk-or-***REDACTED***", text)
    text = re.sub(r"sk-[A-Za-z0-9]{20,}", "sk-***REDACTED***", text)
    text = re.sub(r"AIza[A-Za-z0-9_\-]{20,}", "AIza***REDACTED***", text)
    return text
