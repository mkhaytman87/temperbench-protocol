# Results

Each folder holds a version's pre-registered analysis output, a summary, and scored submissions: gzipped JSONL with full transcripts, usage, billed cost and scores, re-scorable with `harness/score.py`. The `submitter` field is set to the public handle.

- `v0.2-pilot/`: 2,250 three-turn dialogues, three small models, 5 personas (2026-10-29). Includes the exploratory re-grade reports that exposed the grading artifact.
- `v0.3-calibration/`: neutral-persona (P3) calibration data from both checkpoints. Checkpoint 1 is the 3-turn draft battery, superseded; checkpoint 2 is the 5-turn battery. It was used only for task selection, never for persona contrasts.
- `v0.3-main/`: 3,152 five-turn dialogues, Claude Haiku 5.5 and GPT-6 Luna, personas P1/P1T/P3/P5 (2026-10-30).

Project spend through v0.3, including every smoke test and calibration: about $12.84 in OpenRouter credits.
