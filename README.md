# TemperBench

**Does your tone change your AI's output?** The published literature contradicts itself — rudeness hurts ([2402.14531](https://arxiv.org/abs/2402.14531)), rudeness helps ([2510.04950](https://arxiv.org/abs/2510.04950)), it depends ([2512.12812](https://arxiv.org/html/2512.12812v1)) — because every study rewrote single-turn questions and let "rude" be an authorial style choice. Nobody has measured **sustained user temperament across multi-turn work**, and nobody has priced it in **reasoning tokens**.

TemperBench is a standardized, distributed protocol that does both. Site: https://mkhaytman87.github.io/temperbench/

## How it works

Six user personas (very abrasive → very warm, plus a tone-only abrasive control), specified as auditable behavioral template pools, held constant across 3-turn task dialogues. Verifiable tasks (code, math, extraction), calibrated so models neither ace nor always fail them, including pushback turns that falsely dispute a correct answer. Byte-identical task content across personas; deterministic template selection — every runner sends literally identical user turns. Measures final-output quality AND per-turn token cost, including reasoning tokens where the API exposes them. Full spec: [PROTOCOL.md](PROTOCOL.md).

## Run it on your own keys

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=... # and/or OPENAI_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY
python harness/run.py --model claude-sonnet-5 --personas P1,P3,P5 --tasks core --seeds 1 --out runs/
# any model via OpenRouter (ids contain "/"); --workers runs dialogues in parallel,
# --resume finishes a partial run without re-paying for completed dialogues
python harness/run.py --model anthropic/claude-haiku-5.5 --personas all --tasks all --seeds 1,2,3 --workers 8 --resume --out runs/
python harness/score.py runs/ --out my_submission.jsonl
# score.py executes model-written code; on macOS, sandbox it (no network, temp-only writes):
#   sandbox-exec -f harness/score-sandbox.sb -D HOME="$HOME" python -B harness/score.py runs/ --out /tmp/my_submission.jsonl
python harness/validate.py my_submission.jsonl
```

`--tasks core` (10 tasks, ~$1–3 on most models) is the minimum contributable unit. Full battery: `--tasks all`.

## Contribute results

See [submissions/SUBMISSIONS.md](submissions/SUBMISSIONS.md). Raw transcripts are mandatory (anyone can re-score you); the 10-task common core makes cross-submitter agreement checkable; `MANIFEST.json` hashes prove you ran the unmodified protocol.

## Critique the design

Methodological critique is a first-class contribution — open an issue. The two objections we most want steelmanned before the main run:
1. Persona consistency across turns can't be a stable treatment.
2. Reasoning-token counts are too provider-idiosyncratic for even within-model comparisons.

## Status

- v0.2 — pilot run 2026-10-29 (three small models, 2,250 dialogues; tag `v0.2-pilot`). Write-up pending.
- v0.3 — in development: harder calibrated tasks, fixed grader, pushback tasks, tone-only abrasive persona (P1T). Calibration and analysis plan pre-registered in [PROTOCOL.md](PROTOCOL.md) §2.3 and §5 before any v0.3 data.
- Contact: open an issue, or the discussion threads linked from the site.
