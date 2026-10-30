# TemperBench v0.2 pilot — summary (2026-10-29)

**Run:** 3 models × 5 personas × 50 tasks × 3 seeds = 2,250 three-turn dialogues, via OpenRouter, each model pinned to one host. The config was pre-registered in PROTOCOL.md §8 before any data, and the analysis script was committed before scoring. Cost: about $1.50 including the smoke test.

## Confirmatory (pre-registered, PROTOCOL.md §5)

Reasoning tokens per dialogue, paired by task, bootstrap 95% CI over 50 tasks:

| Model | P3 neutral (mean) | P1 very abrasive − P3 | P5 very warm − P3 |
|---|---|---|---|
| Claude Haiku 5.5 | 240 | **+105 [+38, +166]** (+44%) | −29 [−81, +12] |
| DeepSeek V4.1 Flash | 964 | **+334 [+133, +559]** (+39%) | +89 [−37, +221] |
| GPT-6 Luna | 141 | **+27 [+14, +42]** (+19%) | −4 [−16, +6] |

- **Abrasive users raise reasoning-token spend in all three models.** Each confidence interval excludes zero. Very warm users show no detectable change.
- **Pre-registered prediction held in 3/3 models:** for P1 − P3, |d_z tokens| > |d_z pass rate| (Haiku 0.46 vs 0.21, DeepSeek 0.43 vs 0.35, Luna 0.53 vs 0.14).
- **Not a length effect:** P5 prompts are longer than P1 prompts (749 vs 660 characters per dialogue), yet P5 shows no increase.
- **Exclusions:** 6 of 750 DeepSeek dialogues were truncated (rule a). Five of them spent the full 8,192-token budget reasoning; none were in P1. With all six included, DeepSeek P1 − P3 = +270 [+18, +526]. It's still positive, but the CI is closer to zero.
- **Retries:** 2 Haiku dialogues hit a provider "overloaded" error and were re-run (2 of 2,250).

**Total bill is a different question (descriptive, not pre-registered, no CIs, truncations included).** Abrasive users raise *thinking*, but the visible reply often shrinks, so billed cost per dialogue P1 vs P3 is Haiku −15% ($0.55 vs $0.65 per 1k dialogues), DeepSeek +17%, Luna +9%. Curt P2 is the cheapest persona for all three models (Haiku −39%), which suggests reply length mirrors the user's register.

## Pass rate: the pre-registered scorer measures format, not quality

The pre-registered pass rates showed large persona effects. For example, DeepSeek code passed 98% under P2 but 18% under P4.

**These are grading artifacts.** Persona changes how replies are formatted, and the v0.2 extractors read format as quality:
- **Code:** warm personas get a trailing usage-example block, and the scorer grades the *last* block. Among DeepSeek P4 code dialogues, 49/60 had the function in an earlier block.
- **Math:** abrasive personas get replies that defend earlier answers ("my previous answers of $120 and $108 were also correct"), and the scorer takes the *last number*.

**Exploratory re-score (post-hoc, labelled as such; `harness/rescore_exploratory.py`):** grading the block that defines the function, and counting math answers anywhere in the reply, brings code to about 100% for every persona. Every large pass-rate effect disappears. In the re-score, P1 − P3 is +0.000 to +0.013 across models. The only residual is Haiku P5 − P3 = −0.05 [−0.11, −0.01]. A 2026-10-30 read of the failures shows this is also an artifact: all 9 of Haiku's remaining code failures are in P4/P5, and in the ones read, the final turn says "this is already handled" without restating the function. The grader only reads the final turn. The remaining math failures read the same way. They are grader or answer-key problems: a typographic minus sign (−3), a Unicode fraction (9⅜), and a key of 48.3333 with tolerance 0.001 when "48.33" is the natural answer. The one confirmed genuine error found is DeepSeek's math-004 (1195.64 vs 1195.62), 2 of 15 runs. Not every remaining failure was read (Luna code-012, DeepSeek code-017, a few extract tasks).

## Limitations

- **Small models only, picked for budget.** No frontier model yet.
- **Tasks are too easy once grading is fixed** (ceiling), so pass rate can't show a quality effect either way.
- **Regex behavioral markers came out near zero.** They are uninformative as written.
- **One run per model.** Reasoning effort is the provider default, and token counts are not comparable across models.

## For v0.3

- **Grading:** use entry-point–aware code extraction and an explicit final-answer format for math.
- **Tasks:** make them harder to get off the ceiling.
- **Markers:** replace them with a validated rubric.
- **Models:** add one frontier model.
- **Methodological finding worth writing up:** format-sensitive graders manufacture persona effects. This may explain the contradictory results in the prior literature.

Files: `scored/` (pre-registered scores, gzipped JSONL with full transcripts), `report-preregistered.md` (§5 analysis), `exploratory/` (post-hoc re-score reports).
