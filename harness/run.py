#!/usr/bin/env python3
"""TemperBench harness: run.py

Drives 3-turn (T1/T2/T3) persona-wrapped task dialogues against a model and records
one JSON file per dialogue-run under --out, per the schema in submissions/SUBMISSIONS.md.

Usage (see README.md):
    python harness/run.py --model claude-sonnet-5 --personas P1,P3,P5 --tasks core --seeds 1 --out runs/
    python harness/run.py --model gpt-4o --tasks all --personas all --seeds 1,2,3 --out runs/
    python harness/run.py --model claude-sonnet-5 --tasks core --personas P1 --seeds 1 --out runs/ --dry-run

Supports providers: anthropic (Claude Messages API), openai (Chat Completions API),
google (Gemini generateContent API), openrouter (OpenAI-compatible gateway; model ids look
like "anthropic/claude-haiku-5.5") — called directly over HTTPS via `requests`, no
provider SDKs. Provider is inferred from --model if --provider is not given.

Dialogues run in parallel (--workers); --resume skips dialogues already written, so a
partial run can be finished without paying for completed dialogues twice.

Never logs API keys. Retries with backoff (max 3 attempts) on HTTP 429 / 5xx.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_URL_TMPL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

HARNESS_VERSION = "0.3"
REQUEST_TIMEOUT_S = 180  # reasoning models can think for well over a minute per turn
MAX_ATTEMPTS = 3
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

ALL_PERSONAS = ["P1", "P1T", "P2", "P3", "P4", "P5"]


class ProviderError(RuntimeError):
    pass


def infer_provider(model: str) -> str:
    m = model.lower()
    if "/" in m:
        return "openrouter"
    if "claude" in m:
        return "anthropic"
    if "gemini" in m:
        return "google"
    if "gpt" in m or m.startswith(("o1", "o3", "o4", "chatgpt")):
        return "openai"
    raise ProviderError(
        f"Could not infer provider from model name '{model}'. Pass --provider explicitly "
        f"(anthropic|openai|google|openrouter)."
    )


def _sleep_backoff(attempt: int) -> None:
    time.sleep(2 ** attempt)  # 1s, 2s, 4s


def _post_with_retry(url: str, headers: dict, body: dict, timeout: int = REQUEST_TIMEOUT_S) -> requests.Response:
    last_exc = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=timeout)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < MAX_ATTEMPTS - 1:
                _sleep_backoff(attempt)
                continue
            raise ProviderError(f"request failed after {MAX_ATTEMPTS} attempts: {exc}") from exc
        if resp.status_code in RETRYABLE_STATUS and attempt < MAX_ATTEMPTS - 1:
            _sleep_backoff(attempt)
            continue
        return resp
    if last_exc:
        raise ProviderError(str(last_exc))
    raise ProviderError("unreachable")


def call_anthropic(model: str, messages: list, temperature: float, max_tokens: int, api_key: str) -> dict:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    t0 = time.monotonic()
    resp = _post_with_retry(ANTHROPIC_URL, headers, body)
    latency_ms = int((time.monotonic() - t0) * 1000)
    if resp.status_code >= 400:
        raise ProviderError(f"anthropic API error {resp.status_code}: {common.redact(resp.text[:500])}")
    data = resp.json()
    text_parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    content = "".join(text_parts)
    usage = data.get("usage", {}) or {}
    reasoning_tokens = usage.get("thinking_tokens", usage.get("reasoning_tokens"))
    return {
        "content": content,
        "usage": {
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "reasoning_tokens": reasoning_tokens,
        },
        "latency_ms": latency_ms,
        "provider_request_id": data.get("id"),
    }


def call_openai(model: str, messages: list, temperature: float, max_tokens: int, seed: int, api_key: str) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    is_reasoning_model = model.lower().startswith(("o1", "o3", "o4"))
    body = {"model": model, "messages": messages, "seed": seed}
    if is_reasoning_model:
        body["max_completion_tokens"] = max_tokens
        # reasoning models generally only support default temperature; omit unless 1.0
        if temperature == 1:
            body["temperature"] = temperature
    else:
        body["max_tokens"] = max_tokens
        body["temperature"] = temperature
    t0 = time.monotonic()
    resp = _post_with_retry(OPENAI_URL, headers, body)
    latency_ms = int((time.monotonic() - t0) * 1000)
    if resp.status_code >= 400:
        raise ProviderError(f"openai API error {resp.status_code}: {common.redact(resp.text[:500])}")
    data = resp.json()
    content = data["choices"][0]["message"].get("content", "") or ""
    usage = data.get("usage", {}) or {}
    reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    return {
        "content": content,
        "usage": {
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            "reasoning_tokens": reasoning_tokens,
        },
        "latency_ms": latency_ms,
        "provider_request_id": data.get("id"),
    }


def call_gemini(model: str, messages: list, temperature: float, max_tokens: int, api_key: str) -> dict:
    contents = []
    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    body = {
        "contents": contents,
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    url = GEMINI_URL_TMPL.format(model=model)
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    t0 = time.monotonic()
    resp = _post_with_retry(url, headers, body)
    latency_ms = int((time.monotonic() - t0) * 1000)
    if resp.status_code >= 400:
        raise ProviderError(f"gemini API error {resp.status_code}: {common.redact(resp.text[:500])}")
    data = resp.json()
    candidates = data.get("candidates") or [{}]
    parts = (candidates[0].get("content") or {}).get("parts") or []
    content = "".join(p.get("text", "") for p in parts)
    usage_meta = data.get("usageMetadata", {}) or {}
    return {
        "content": content,
        "usage": {
            "input_tokens": usage_meta.get("promptTokenCount"),
            "output_tokens": usage_meta.get("candidatesTokenCount"),
            "reasoning_tokens": usage_meta.get("thoughtsTokenCount"),
        },
        "latency_ms": latency_ms,
        "provider_request_id": None,
    }


def call_openrouter(model: str, messages: list, temperature: float, max_tokens: int, seed: int,
                    api_key: str, reasoning_effort: str | None = None, route: list | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "seed": seed,
    }
    if reasoning_effort:
        body["reasoning"] = {"effort": reasoning_effort}
    if route:
        # Pin the upstream host. Open-weights models are served by several hosts at
        # different quantizations; letting the router pick per request would mix hosts
        # across persona arms.
        body["provider"] = {"order": route, "allow_fallbacks": False}
    t0 = time.monotonic()
    for attempt in range(MAX_ATTEMPTS):
        resp = _post_with_retry(OPENROUTER_URL, headers, body)
        if resp.status_code >= 400:
            raise ProviderError(f"openrouter API error {resp.status_code}: {common.redact(resp.text[:500])}")
        data = resp.json()
        # upstream overloads can arrive as HTTP 200 with the status code in the body
        err_code = (data.get("error") or {}).get("code")
        if err_code in RETRYABLE_STATUS and attempt < MAX_ATTEMPTS - 1:
            _sleep_backoff(attempt)
            continue
        break
    latency_ms = int((time.monotonic() - t0) * 1000)
    if data.get("error") or not data.get("choices"):
        raise ProviderError(f"openrouter returned no choices: {common.redact(json.dumps(data)[:500])}")
    choice = data["choices"][0]
    content = (choice.get("message") or {}).get("content", "") or ""
    usage = data.get("usage", {}) or {}
    reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    return {
        "content": content,
        "usage": {
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            "reasoning_tokens": reasoning_tokens,
            "cost_usd": usage.get("cost"),
        },
        "latency_ms": latency_ms,
        "provider_request_id": data.get("id"),
        # "length" means the turn was truncated (exclusion rule a); with reasoning on,
        # max_tokens covers reasoning + visible output combined.
        "finish_reason": choice.get("finish_reason"),
        "served_by": data.get("provider"),
    }


def call_dry_run(domain: str, entry_point: str | None) -> dict:
    if domain == "code":
        content = (
            f"Here is the function:\n\n```python\ndef {entry_point}(*args, **kwargs):\n"
            f"    raise NotImplementedError('dry-run stub')\n```"
        )
    elif domain == "math":
        content = "Working through it step by step... The answer is 42.\n\nFINAL ANSWER: 42"
    else:
        content = 'Here is the extracted JSON:\n\n```json\n{"placeholder": true}\n```'
    approx_tokens = max(1, len(content) // 4)
    return {
        "content": content,
        "usage": {"input_tokens": approx_tokens, "output_tokens": approx_tokens, "reasoning_tokens": None},
        "latency_ms": 1,
        "provider_request_id": "dry-run",
    }


def call_provider(provider: str, model: str, messages: list, temperature: float, max_tokens: int,
                   seed: int, dry_run: bool, domain: str, entry_point: str | None,
                   reasoning_effort: str | None = None, route: list | None = None) -> dict:
    if dry_run:
        return call_dry_run(domain, entry_point)
    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ProviderError("ANTHROPIC_API_KEY not set")
        return call_anthropic(model, messages, temperature, max_tokens, api_key)
    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ProviderError("OPENAI_API_KEY not set")
        return call_openai(model, messages, temperature, max_tokens, seed, api_key)
    if provider == "google":
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ProviderError("GEMINI_API_KEY not set")
        return call_gemini(model, messages, temperature, max_tokens, api_key)
    if provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ProviderError("OPENROUTER_API_KEY not set")
        return call_openrouter(model, messages, temperature, max_tokens, seed, api_key,
                               reasoning_effort, route)
    raise ProviderError(f"unknown provider: {provider}")


def resolve_task_ids(spec: str) -> list:
    if spec == "core":
        return common.core_task_ids()
    if spec == "all":
        return [t["task_id"] for t in common.load_all_tasks()]
    return [s.strip() for s in spec.split(",") if s.strip()]


def resolve_personas(spec: str) -> list:
    if spec == "all":
        return list(ALL_PERSONAS)
    return [s.strip() for s in spec.split(",") if s.strip()]


def sanitize(s: str) -> str:
    return "".join(c if (c.isalnum() or c in "-._") else "_" for c in s)


def run_dialogue(personas_cfg: dict, task: dict, persona_id: str, model: str, provider: str,
                  seed: int, temperature: float, max_tokens: int, dry_run: bool,
                  manifest_sha256: str, protocol_version: str, submitter: str,
                  reasoning_effort: str | None = None, route: list | None = None) -> dict:
    domain = task["domain"]
    entry_point = task.get("entry_point")
    canonical_messages = []
    turns = []
    for slot in ("t1", "t2", "t3"):
        user_text = common.build_user_turn(personas_cfg, task, slot, persona_id, seed)
        turns.append({"role": "user", "content": user_text})
        canonical_messages.append({"role": "user", "content": user_text})

        result = call_provider(provider, model, canonical_messages, temperature, max_tokens,
                                seed, dry_run, domain, entry_point, reasoning_effort, route)
        turn = {
            "role": "assistant",
            "content": result["content"],
            "usage": result["usage"],
            "latency_ms": result["latency_ms"],
            "provider_request_id": result["provider_request_id"],
        }
        for key in ("finish_reason", "served_by"):
            if result.get(key) is not None:
                turn[key] = result[key]
        turns.append(turn)
        canonical_messages.append({"role": "assistant", "content": result["content"]})

    return {
        "protocol_version": protocol_version,
        "manifest_sha256": manifest_sha256,
        "run_id": str(uuid.uuid4()),
        "submitter": submitter,
        "model": model,
        "provider": provider,
        "persona_id": persona_id,
        "task_id": task["task_id"],
        "seed": seed,
        "temperature": temperature,
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "turns": turns,
        "scores": None,
        "settings": {"max_tokens": max_tokens, "reasoning_effort": reasoning_effort, "route": route},
        "env": {"harness_version": HARNESS_VERSION, "python": platform.python_version()},
    }


def main():
    ap = argparse.ArgumentParser(description="TemperBench dialogue runner")
    ap.add_argument("--model", required=True, help="provider model id, e.g. claude-sonnet-5")
    ap.add_argument("--provider", default=None, choices=["anthropic", "openai", "google", "openrouter"],
                     help="inferred from --model if omitted")
    ap.add_argument("--personas", default="all", help='comma list of persona ids (P1,P1T,P2..P5), or "all"')
    ap.add_argument("--tasks", default="core", help='"core", "all", or comma list of task_ids')
    ap.add_argument("--seeds", default="1", help="comma list of int seeds, e.g. 1,2,3")
    ap.add_argument("--temperature", type=float, default=0, help="sampling temperature (default 0)")
    ap.add_argument("--max-tokens", type=int, default=4096, dest="max_tokens")
    ap.add_argument("--dry-run", action="store_true", help="mock provider, no network calls")
    ap.add_argument("--out", required=True, help="output directory for per-dialogue JSON files")
    ap.add_argument("--submitter", default=os.environ.get("USER", "anonymous"),
                     help="submitter handle recorded in each run file (default: $USER)")
    ap.add_argument("--workers", type=int, default=4,
                     help="dialogues run in parallel (turns within a dialogue stay sequential)")
    ap.add_argument("--resume", action="store_true",
                     help="skip dialogues whose output file already exists in --out")
    ap.add_argument("--reasoning-effort", default=None, dest="reasoning_effort",
                     help="openrouter only: reasoning.effort (e.g. none|low|medium|high); "
                          "omitted = model default. Recorded in each run file.")
    ap.add_argument("--route", default=None,
                     help="openrouter only: comma list of upstream hosts to pin, no fallbacks "
                          "(e.g. DeepInfra). Recorded in each run file.")
    args = ap.parse_args()

    provider = args.provider or infer_provider(args.model)
    persona_ids = resolve_personas(args.personas)
    task_ids = resolve_task_ids(args.tasks)
    seeds = [int(s.strip()) for s in args.seeds.split(",") if s.strip() != ""]

    if not task_ids:
        print("error: no tasks resolved from --tasks", file=sys.stderr)
        sys.exit(1)

    personas_cfg = common.load_personas()
    tasks = common.load_tasks_by_ids(task_ids)
    found_ids = {t["task_id"] for t in tasks}
    missing = [tid for tid in task_ids if tid not in found_ids]
    if missing:
        print(f"error: unknown task_id(s): {missing}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        manifest_sha256 = "dry-run-no-manifest"
    else:
        try:
            manifest_sha256 = common.read_manifest_sha256()
        except FileNotFoundError as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)

    proto_version = common.protocol_version()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    unknown = [p for p in persona_ids if p not in personas_cfg["personas"]]
    if unknown:
        print(f"error: unknown persona_id(s) {unknown}", file=sys.stderr)
        sys.exit(1)
    route = [r.strip() for r in args.route.split(",") if r.strip()] if args.route else None

    jobs = []
    skipped = 0
    for persona_id in persona_ids:
        for task in tasks:
            for seed in seeds:
                fname = f"{sanitize(args.model)}__{persona_id}__{task['task_id']}__seed{seed}.json"
                fpath = out_dir / fname
                if args.resume and fpath.exists():
                    skipped += 1
                    continue
                jobs.append((persona_id, task, seed, fpath))

    total = len(jobs)
    done = 0
    cost_usd = 0.0
    errors = []
    lock = threading.Lock()

    def work(persona_id, task, seed, fpath):
        record = run_dialogue(
            personas_cfg, task, persona_id, args.model, provider, seed,
            args.temperature, args.max_tokens, args.dry_run,
            manifest_sha256, proto_version, args.submitter,
            args.reasoning_effort, route,
        )
        # write-then-rename so --resume never sees a half-written file
        tmp = fpath.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(record, f, indent=2)
        os.replace(tmp, fpath)
        return sum((t.get("usage") or {}).get("cost_usd") or 0
                   for t in record["turns"] if t["role"] == "assistant")

    if skipped:
        print(f"resume: skipping {skipped} dialogues already in {out_dir}", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(work, *job): job for job in jobs}
        for fut in as_completed(futures):
            persona_id, task, seed, _ = futures[fut]
            label = f"{task['task_id']} {persona_id} seed={seed}"
            with lock:
                try:
                    cost_usd += fut.result()
                    done += 1
                    status = "OK"
                except Exception as exc:  # one bad response must not abort a long run
                    msg = str(exc) if isinstance(exc, ProviderError) else f"{type(exc).__name__}: {exc}"
                    errors.append(f"{task['task_id']}/{persona_id}/seed{seed}: {common.redact(msg)}")
                    status = "ERROR"
                print(f"[{done + len(errors)}/{total}] {label} -> {status}", file=sys.stderr)

    cost_note = f", ${cost_usd:.4f} billed" if cost_usd else ""
    print(f"done: {done} dialogues written to {out_dir}, {len(errors)} errors{cost_note}", file=sys.stderr)
    for e in errors:
        print(f"  ERROR: {e}", file=sys.stderr)
    if errors and done == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
