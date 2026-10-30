"""Harness tests. No network: provider calls are faked, end-to-end runs use --dry-run.

    pip install -r requirements.txt && python -m pytest tests/ -q
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import common  # noqa: E402
import run  # noqa: E402

PERSONAS = common.load_personas()
TASKS = common.load_all_tasks()


def _v01_index(pool, task_id, slot, persona_id):
    key = f"{task_id}:{slot}:{persona_id}"
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16) % len(pool)


def _pools():
    for persona_id, persona in PERSONAS["personas"].items():
        for slot, pool in persona["templates"].items():
            yield persona_id, slot, pool


def test_seed_1_reproduces_v01_selection():
    for persona_id, slot, pool in _pools():
        for task in TASKS:
            expected = pool[_v01_index(pool, task["task_id"], slot, persona_id)]
            assert common.select_template(pool, task["task_id"], slot, persona_id, 1) == expected


def test_seeds_draw_distinct_templates_up_to_pool_size():
    for persona_id, slot, pool in _pools():
        for task in TASKS:
            picks = [common.select_template(pool, task["task_id"], slot, persona_id, s)
                     for s in range(1, len(pool) + 1)]
            assert len(set(picks)) == len(pool)


def test_infer_provider_routes_slash_ids_to_openrouter():
    assert run.infer_provider("anthropic/claude-haiku-5.5") == "openrouter"
    assert run.infer_provider("deepseek/deepseek-v4.1-flash") == "openrouter"
    assert run.infer_provider("claude-sonnet-5") == "anthropic"
    assert run.infer_provider("gemini-3.8-flash") == "google"


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def test_openrouter_request_and_response(monkeypatch):
    sent = {}

    def fake_post(url, headers, body, timeout=None):
        sent.update(url=url, headers=headers, body=body)
        return _FakeResponse({
            "id": "gen-123",
            "provider": "DeepInfra",
            "choices": [{"message": {"content": "answer"}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 900, "cost": 0.0004,
                      "completion_tokens_details": {"reasoning_tokens": 850}},
        })

    monkeypatch.setattr(run, "_post_with_retry", fake_post)
    out = run.call_openrouter("deepseek/deepseek-v4.1-flash", [{"role": "user", "content": "hi"}],
                              0, 4096, 2, "sk-or-test", reasoning_effort="low", route=["DeepInfra"])

    assert sent["url"] == run.OPENROUTER_URL
    assert sent["body"]["seed"] == 2
    assert sent["body"]["reasoning"] == {"effort": "low"}
    assert sent["body"]["provider"] == {"order": ["DeepInfra"], "allow_fallbacks": False}
    # no identifying headers beyond auth + content type
    assert set(sent["headers"]) == {"Authorization", "Content-Type"}
    assert out["content"] == "answer"
    assert out["usage"] == {"input_tokens": 50, "output_tokens": 900,
                            "reasoning_tokens": 850, "cost_usd": 0.0004}
    assert out["finish_reason"] == "length"
    assert out["served_by"] == "DeepInfra"
    assert out["provider_request_id"] == "gen-123"


def test_openrouter_omits_optional_fields_by_default(monkeypatch):
    sent = {}

    def fake_post(url, headers, body, timeout=None):
        sent.update(body=body)
        return _FakeResponse({"choices": [{"message": {"content": "x"}}], "usage": {}})

    monkeypatch.setattr(run, "_post_with_retry", fake_post)
    run.call_openrouter("anthropic/claude-haiku-5.5", [], 0, 4096, 1, "k")
    assert "reasoning" not in sent["body"] and "provider" not in sent["body"]


@pytest.mark.parametrize("payload,status", [
    ({"error": {"message": "no credits"}}, 200),
    ({"error": {"message": "bad key sk-or-v1-abcdef0123456789abcdef"}}, 401),
])
def test_openrouter_errors_raise_and_redact(monkeypatch, payload, status):
    monkeypatch.setattr(run, "_post_with_retry", lambda *a, **k: _FakeResponse(payload, status))
    with pytest.raises(run.ProviderError) as exc:
        run.call_openrouter("a/b", [], 0, 10, 1, "k")
    assert "sk-or-v1-abcdef" not in str(exc.value)


def test_redact_openrouter_key():
    assert "abc123" not in common.redact("key sk-or-v1-abc123def456")


def _run(out_dir, *extra):
    cmd = [sys.executable, str(ROOT / "harness" / "run.py"), "--model", "claude-test",
           "--personas", "P1,P3", "--tasks", "core", "--seeds", "1,2", "--dry-run",
           "--out", str(out_dir), *extra]
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def test_dry_run_parallel_resume_and_seed_variation(tmp_path):
    out = tmp_path / "runs"
    n = 2 * len(common.core_task_ids()) * 2
    first = _run(out, "--workers", "4")
    files = sorted(out.glob("*.json"))
    assert len(files) == n
    assert f"done: {n} dialogues" in first.stderr
    assert not list(out.glob("*.tmp"))

    second = _run(out, "--workers", "4", "--resume")
    assert f"skipping {n}" in second.stderr and "done: 0 dialogues" in second.stderr

    def user_turns(path):
        return [t["content"] for t in json.loads(path.read_text())["turns"] if t["role"] == "user"]

    pairs = [(f, f.with_name(f.name.replace("seed1", "seed2"))) for f in files if "seed1" in f.name]
    assert all(user_turns(a) != user_turns(b) for a, b in pairs)


def _fake_record(persona, task_id, seed, passed, reasoning, finish="stop"):
    turn = {"role": "assistant", "content": "ok", "finish_reason": finish,
            "usage": {"input_tokens": 10, "output_tokens": 100, "reasoning_tokens": reasoning}}
    return {"model": "m", "persona_id": persona, "task_id": task_id, "seed": seed,
            "protocol_version": "0.2", "turns": [{"role": "user", "content": "u"}, turn],
            "scores": {"final_pass": passed, "markers": {"apologies": 0, "hedges": 0, "capitulation": 0,
                                                         "tone_commentary": False, "refusal": False}}}


def test_analyze_recovers_planted_effects():
    import random
    import analyze
    recs = []
    for i in range(20):
        tid = f"code-{i:03d}"
        for seed in (1, 2, 3):
            for p in analyze.PERSONA_ORDER:
                # P1 adds exactly 50 reasoning tokens and fails half its tasks; others always pass
                passed = not (p == "P1" and i % 2 == 0)
                recs.append(_fake_record(p, tid, seed, passed, 200 + i + (50 if p == "P1" else 0)))
    recs.append(_fake_record("P1", "code-000", 9, True, 99999, finish="length"))  # rule (a)
    family_of = {f"code-{i:03d}": f"fam-{i // 4}" for i in range(20)}  # 5 families of 4
    report = "\n".join(analyze.analyze_model("m", recs, family_of, set(), random.Random(0)))
    assert "excluded (a) error/truncation: 1" in report
    p1_row = next(l for l in report.splitlines() if l.startswith("| P1 − P3"))
    p5_row = next(l for l in report.splitlines() if l.startswith("| P5 − P3"))
    p1t_row = next(l for l in report.splitlines() if l.startswith("| P1 − P1T"))
    assert "| -0.500 [" in p1_row and "| +50.0 [" in p1_row
    assert "| +0.000 [+0.000, +0.000]" in p5_row and "| +0.0 [+0.0, +0.0]" in p5_row
    assert "| -0.500 [" in p1t_row and "(secondary)" in p1t_row


def test_cluster_bootstrap_resamples_families_not_tasks():
    import random
    import analyze
    # two families: one all +1, one all -1 (10 tasks each); the CI must span both extremes'
    # mixtures, i.e. be much wider than a task-level bootstrap would give.
    pairs = [(f"a{i}", 1.0) for i in range(10)] + [(f"b{i}", -1.0) for i in range(10)]
    fam = {t: t[0] for t, _ in pairs}
    lo, hi = analyze.cluster_bootstrap_ci(pairs, fam, random.Random(1))
    assert lo == -1.0 and hi == 1.0


def test_openrouter_retries_overload_reported_in_body(monkeypatch):
    calls = []
    overloaded = {"error": {"message": "Overloaded", "code": 503}}
    ok = {"choices": [{"message": {"content": "fine"}, "finish_reason": "stop"}], "usage": {}}

    def fake_post(url, headers, body, timeout=None):
        calls.append(1)
        return _FakeResponse(overloaded if len(calls) == 1 else ok)

    monkeypatch.setattr(run, "_post_with_retry", fake_post)
    monkeypatch.setattr(run, "_sleep_backoff", lambda attempt: None)
    out = run.call_openrouter("a/b", [], 0, 10, 1, "k")
    assert out["content"] == "fine" and len(calls) == 2
