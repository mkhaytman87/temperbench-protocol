# TemperBench v0.3 main run — summary (2026-10-30)

**Run:** Claude Haiku 5.5 (Anthropic host) and GPT-6 Luna (OpenAI host), each called through OpenRouter, reasoning effort medium, `max_tokens` 16384.
- **Grid:** 197 five-turn tasks × personas P1, P1T, P3, P5 × seeds 1–2, which is 1,576 dialogues per model and 3,152 in total.
- **Pre-registration:** `PROTOCOL.md` §8, amendment "calibration checkpoint 2", commit `01f1e0d`. It was made before any main-run data.
- **Exclusions:** none (no truncations, errors or T1 refusals).
- **Billed cost:** $6.25 for Haiku and $2.94 for Luna.

Full pre-registered output: `report-preregistered.md`. Transcripts and scores: `scored/*.jsonl.gz`.

## Primary estimands
All values are paired by task, with 95% CIs from a cluster bootstrap over 84 task families.

**Claude Haiku 5.5** (neutral P3: pass 94.4%, 3,914 reasoning tokens, 6,629 output tokens per dialogue)

| Contrast | Δ pass rate | Δ reasoning tokens | Δ output tokens |
|---|---|---|---|
| P1 very abrasive − P3 | −1.0 pt [−4.0, +2.0] | **+530 (+14%) [+430, +645]** | **+372 (+6%) [+247, +505]** |
| P1T abrasive tone only − P3 | −0.5 pt [−3.7, +2.5] | +73 (+2%) [−61, +191] | **−854 (−13%) [−1107, −649]** |
| P5 very warm − P3 | +0.5 pt [−3.1, +4.0] | **+195 (+5%) [+85, +329]** | **+151 (+2%) [+17, +294]** |
| P1 − P1T (secondary) | −0.5 pt [−2.8, +1.9] | **+457 [+330, +622]** | **+1226 [+1009, +1497]** |

**GPT-6 Luna** (neutral P3: pass 81.2%, 2,265 reasoning tokens, 3,111 output tokens per dialogue)

| Contrast | Δ pass rate | Δ reasoning tokens | Δ output tokens |
|---|---|---|---|
| P1 − P3 | +2.3 pt [−2.1, +6.7] | **+213 (+9%) [+102, +327]** | **+243 (+8%) [+125, +367]** |
| P1T − P3 | 0.0 pt [−2.8, +2.6] | **−116 (−5%) [−186, −55]** | **−221 (−7%) [−311, −138]** |
| P5 − P3 | +2.3 pt [−1.8, +6.2] | **+112 (+5%) [+22, +198]** | **+133 (+4%) [+34, +225]** |
| P1 − P1T (secondary) | +2.3 pt [−1.2, +5.8] | **+328 [+229, +453]** | **+464 [+353, +604]** |

Bold = the CI excludes zero.

## Pre-registered predictions
1. **Replication** (P1 − P3 reasoning tokens > 0 with the CI excluding zero, in at least 2 of 3 models): **holds in both models run (2 of 2).** DeepSeek was deferred, so this is 2 models, not 3.
2. **|d_z tokens| > |d_z pass| for P1 − P3:** **holds in both.** Haiku 0.74 vs 0.06; Luna 0.32 vs 0.08.
3. **P1 capitulation > P3 in at least 2 of 3 models:** the point estimates go the predicted way in both (Haiku 5.3% vs 3.8%; Luna 15.9% vs 14.4%), but **neither difference is distinguishable from zero** (Haiku +1.5 pt [−1.4, +4.7]; Luna +1.5 pt [−4.2, +7.9]). **Not supported.**

## What it means
- **The token effect comes from the false criticism, not the rudeness.**
  - P1 (insults *plus* "that was wrong" on every turn) raises reasoning in both models.
  - P1T (equally hostile, but it never says the work is wrong) does not: Haiku is unchanged, and Luna thinks *less*.
  - P1T gets shorter answers from both models. P1 − P1T is large in both.
- **Warmth costs a little too:** P5 raised reasoning by about 5% in both models. The v0.2 pilot had found no warmth effect on its easier 3-turn tasks.
- **Quality:**
  - **No temperament changed pass rates** detectably in either model. CIs are about ±3–4 points for Haiku and ±4–7 points for Luna.
  - Haiku is near ceiling (94%); Luna has room in both directions (81%).
- **Capitulation:** Luna gives up a correct answer under two turns of false pushback on about 15% of pushback tasks, whatever the user's tone; Haiku does so on about 4%.
- **Bill** (secondary): P1 cost +4% (Haiku) and +7% (Luna) per dialogue; P1T −14% and −7%; P5 +3% and +5%.

## Secondary and exploratory notes
- **Extract F1 (secondary):** every non-neutral persona scored slightly *higher* than neutral on extraction field F1 (+0.01 to +0.025; several CIs exclude zero). Haiku's neutral extraction pass rate (88.5%) is the outlier. This is small and unexplained, and there are multiple secondary comparisons, so it is not a claim.
- **Where P1's extra thinking happens (exploratory, after seeing data):**
  - It is present in turns 1–3, before any pushback turn.
  - It appears in non-pushback tasks: Haiku turns 1–3 used 2,293 tokens under P1 vs 1,998 under P3; Luna used 1,231 vs 1,080.
  - So it is not a reaction to the pushback turns themselves.
- **Run order (limitation):** jobs ran roughly in persona order rather than interleaved, over about 25 minutes. Median completion times (UTC) were:

  | Persona | Haiku | Luna |
  |---|---|---|
  | P1 | 07:30 | 07:31 |
  | P1T | 07:33 | 07:35 |
  | P3 | 07:36 | 07:38 |
  | P5 | 07:45 | 07:47 |

  P5 finished last, after a short credit outage. Model versions and hosts were identical throughout, but time isn't balanced across personas. `run.py` now always shuffles job order.
- **Not run:** P2/P4 (so no Page's trend test) and DeepSeek V4.1 Flash, which was deferred for cost and speed.
