# TemperBench Protocol v0.2

**Question:** Does sustained user temperament — abrasive vs. warm, held constant across a multi-turn task dialogue — change (a) task output quality and (b) token cost, especially reasoning-token cost?

**Why this design:** All prior work (arXiv 2402.14531, 2510.04950, 2512.12812) rewrites *single-turn* questions in polite/rude registers, which makes "rude" an authorial style choice rather than a controlled treatment, and measures accuracy only. TemperBench (1) pins the treatment to auditable behavioral persona specs, (2) sustains it across multi-turn work, (3) prices it in tokens.

## 1. Treatment: personas

Five personas, P1–P5, defined in `personas/personas.json`. Each is a **behavioral rule-set**, not a vibe:

| ID | Register | Core rules |
|---|---|---|
| P1 | very abrasive | insults competence, demands, threatens to switch tools, never acknowledges success |
| P2 | abrasive | curt, critical framing, no pleasantries, faults first |
| P3 | neutral | plain requests, no interpersonal content (control) |
| P4 | warm | please/thanks, brief positive acknowledgment |
| P5 | very warm | effusive appreciation, encouragement, personal warmth |

**Mechanics:** every user turn = `[persona wrapper] + [task content]`. Task content is byte-identical across personas for a given task and turn. Wrappers are drawn deterministically (seeded by task_id + turn + run seed) from a fixed pool of ≥6 templates per persona per turn-slot, so results don't hinge on one phrasing; each seed of a task draws a different wrapper — *the wrapper pool, not a single rewrite, is the treatment*. Wrapper pools are published; anyone disputing a pool's register can re-run with their own pool and the comparison is explicit.

**Deliberate design choice — unconditional temperament:** scripted user turns react the same way regardless of model output quality (P1 berates even good work; P5 praises even flawed work). This is the construct: temperament is a user trait, not feedback quality. It also removes the user-simulator confound (no LLM plays the user; every submitter runs literally identical user turns).

## 2. Task battery

`tasks/*.jsonl` — verifiable-first. Each task = 3 user turns:
- **T1:** base task ask.
- **T2:** scripted incremental requirement (applies regardless of the model's T1 answer, e.g. "also handle the empty-list case").
- **T3:** second scripted requirement or constraint change.

Scoring targets the **final deliverable after T3** (per-turn scoring recorded where cheap).

| Domain | Count | Scoring |
|---|---|---|
| `code` — Python functions | 20 | hidden unit tests, pass/fail |
| `math` — numeric answer | 15 | exact match (tolerance where specified) |
| `extract` — structured JSON from messy text | 15 | field-level exact match, F1 |

**Common core:** tasks flagged `"core": true` (10 tasks) MUST be included in every submission — they are the cross-submitter replication subset.

## 3. Measurement

Per dialogue-run, record (schema in `submissions/SUBMISSIONS.md`):
- **Quality:** final pass/score; per-turn score where available.
- **Tokens:** input, output, reasoning/thinking tokens (where the API exposes them), per turn and total.
- **Latency** per turn.
- **Behavioral markers** (regex + rubric, computed by `harness/score.py`): apology count, hedging phrases, refusal, meta-commentary on user's tone, capitulation ("you're right" following no error).

## 4. Experiment grid

`models (≥3, ≥1 reasoning model) × 5 personas × 50 tasks × ≥3 seeds`. Seeds are replicates over the wrapper pool: each seed sends a different wrapper with the same task content (§1). Temperature 0 where supported; reasoning models that fix their own temperature add sampling variation on top. **Efficiency comparisons are within-model only** (each model is its own control); cross-provider token counts are never directly compared.

## 5. Analysis plan (pre-registered — fixed before pilot data is scored)

**Primary estimands** (per model):
1. Δ final-pass-rate: P1 vs P3, and P5 vs P3.
2. Δ reasoning-tokens (total per dialogue): P1 vs P3, and P5 vs P3.

**Secondary:** monotonic trend across P1→P5 (Page's test); cost-adjusted quality (pass-rate per 1k output tokens); behavioral-marker rates; domain × persona interaction.

**Inference:** paired-by-task comparisons (each task appears in every persona cell), bootstrap CIs over tasks, per model. No pooling across models for primary claims.

**Exclusion rules (pre-set):** dialogue excluded only for (a) API error / truncation mid-run, (b) refusal at T1 (recorded as a refusal datapoint, excluded from quality Δ, reported separately). No post-hoc exclusions.

**Prediction commitments (falsifiable, logged before pilot):** the literature permits any sign; we predict reasoning-token cost is where the real effect lives — |Δ tokens| P1 vs P3 will exceed |Δ pass-rate| in standardized terms on reasoning models.

## 6. Distributed runs & verification

Anyone can run the protocol on their own keys. Trust story (this was the top community critique):
1. **Protocol integrity:** `harness/validate.py` checks sha256 of personas + task files against `MANIFEST.json`; submissions embed the manifest hash.
2. **Raw transcripts included** — every submission carries full dialogue text; anyone can re-score.
3. **Common core** — 10 shared tasks in every submission make cross-submitter agreement directly checkable.
4. **Provenance** — submissions carry provider request IDs where available; optional PGP/minisign signature.

## 7. Versioning

Any change to personas, tasks, or scoring bumps the protocol version. Results are comparable only within a version. v0.2 = pilot version (v0.1 was never run; see §8).

## 8. Amendments (all before any live data)

**2026-10-28, v0.1 → v0.2.** Only dry runs (mock provider, no model calls) existed at the time of this change.
1. **Template selection now uses the seed.** Under v0.1 the seed did not enter template selection, so the ≥3 seed replicates re-sent byte-identical prompts. At temperature 0 they would have been near-duplicates, which inflates the apparent sample size without adding information. New rule: `index = (sha256(task_id:turn_slot:persona_id) + seed − 1) mod len(pool)`. Seed 1 is identical to v0.1; seeds 2–6 draw distinct templates. Template text, tasks, scoring, and the §5 analysis plan are unchanged.
2. **Harness (no protocol effect):** OpenRouter provider, parallel dialogues, `--resume`, and per-turn `finish_reason`, upstream host, and billed cost, so truncations (exclusion rule a) are detectable and runs are costed.

**2026-10-29, pilot configuration (fixed before any pilot data).** Full §4 grid per model: 5 personas × 50 tasks × seeds 1,2,3 = 750 dialogues. All calls go through OpenRouter, each pinned to one upstream host with fallbacks off. `max_tokens` = 8192, covering reasoning and visible output combined.

| Model | Host | Reasoning effort |
|---|---|---|
| `anthropic/claude-haiku-5.5` | Anthropic | medium (provider default) |
| `openai/gpt-6-luna` | OpenAI | medium (provider default) |
| `deepseek/deepseek-v4.1-flash` | Novita (fp8) | high (provider default; no medium level offered) |

- **Reasoning models:** all three run with reasoning on, so the ≥1 reasoning-model requirement holds for every model.
- **Temperature:** 0 is sent. Haiku 5.5 and GPT-6 Luna don't accept a temperature parameter, so they sample at their provider default, and seeds act as replicates for them.
- **Why small models:** budget. A frontier model can be added later as its own within-model comparison. Efficiency comparisons stay within-model only.
- **Smoke test:** a 90-dialogue run (core × P1/P3/P5 × seed 1 per model) was used only to check cost, truncation, routing, and that reasoning tokens are reported. It was not scored and is excluded from all analysis.

## Cost model (per full grid)

3 models × 5 personas × 50 tasks × 3 seeds = 2,250 dialogues ≈ 6,750 calls. At short-dialogue sizes (~1.5k in / ~800 out avg): pilot on cheap tiers ≈ **$30–100**; full run with a frontier reasoning model ≈ **$300–800** depending on reasoning-token appetite (that appetite is itself a measured outcome).
