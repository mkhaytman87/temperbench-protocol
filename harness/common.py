"""Shared utilities for the TemperBench harness (run.py, score.py, validate.py, make_manifest.py).

Not part of the public CLI surface; imported by the other harness scripts.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

PROTOCOL_VERSION_FALLBACK = "0.2"

HARNESS_DIR = Path(__file__).resolve().parent
PROTOCOL_ROOT = HARNESS_DIR.parent
PERSONAS_PATH = PROTOCOL_ROOT / "personas" / "personas.json"
TASKS_DIR = PROTOCOL_ROOT / "tasks"
MANIFEST_PATH = PROTOCOL_ROOT / "MANIFEST.json"

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


def build_user_turn(personas: dict, task: dict, turn_slot: str, persona_id: str, seed: int = 1) -> str:
    """turn_slot in {'t1','t2','t3'}. Composes template.replace('{task}', task_content)."""
    persona = personas["personas"][persona_id]
    pool = persona["templates"][turn_slot]
    template = select_template(pool, task["task_id"], turn_slot, persona_id, seed)
    task_content = task[turn_slot]
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
