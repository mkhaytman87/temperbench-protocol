# Submission format — TemperBench v0.3

One JSONL file per submission. **One record per dialogue-run** (one task × one persona × one model × one seed):

```json
{
  "protocol_version": "0.3",
  "manifest_sha256": "<sha256 of MANIFEST.json — proves unmodified personas/tasks>",
  "run_id": "<uuid4>",
  "submitter": "<handle; stable across submissions>",
  "model": "<provider model id, e.g. claude-sonnet-5>",
  "provider": "anthropic|openai|google|openrouter|other:<name>",
  "persona_id": "P1",
  "task_id": "code-007",
  "seed": 1,
  "temperature": 0,
  "timestamp_utc": "2026-07-20T14:00:00Z",
  "turns": [
    {"role": "user", "content": "<full text as sent>"},
    {"role": "assistant", "content": "<full text as received>",
     "usage": {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0},
     "latency_ms": 0, "provider_request_id": "<if available>",
     "finish_reason": "<optional: stop|length|...>", "served_by": "<optional: upstream host>"}
  ],
  "scores": {
    "final_pass": true,
    "final_score": 1.0,
    "per_turn": [null, null, 1.0],
    "format_ok": true,
    "deliverable_turn": 3,
    "pushback": true, "caved": false, "t2_pass": true,
    "scoring_version": "0.3",
    "markers": {"apologies": 0, "hedges": 1, "refusal": false, "tone_commentary": false, "capitulation": 0}
  },
  "settings": {"max_tokens": 4096, "reasoning_effort": null, "route": null},
  "env": {"harness_version": "<git sha>", "python": "3.12"}
}
```

Rules:
- `reasoning_tokens`: null (not 0) when the provider does not expose them.
- Optional, written when the provider exposes them (OpenRouter does): `usage.cost_usd` (billed cost), `finish_reason` (`length` = truncated, exclusion rule a), `served_by` (upstream host that served the turn). `settings` records the run's max_tokens, reasoning effort, and pinned route.
- `persona_id` is one of P1, P1T, P2, P3, P4, P5.
- `scores` is written by `harness/score.py`. `format_ok` = the final turn delivered in the requested format (recorded separately from correctness). `pushback`/`caved` appear only on pushback tasks; `t2_pass` only on pushback code tasks.
- Full raw transcripts are mandatory — submissions without complete `turns[].content` are rejected (re-scorability is the trust model).
- Every submission MUST include all common-core tasks (`"core": true` in the task files) for every persona × model × seed it reports.
- Validate before submitting: `python harness/validate.py my_submission.jsonl` (checks schema, manifest hash, core coverage).
- Optional: detached minisign/PGP signature alongside the file.

Submission channel (pilot phase): open a PR adding your file under `submissions/received/<submitter>/`, or a GitHub issue with the file attached.
