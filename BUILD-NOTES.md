# BUILD-NOTES — TemperBench protocol implementation

Implementation pass over `PROTOCOL.md` / `personas/personas.json` / `submissions/SUBMISSIONS.md` /
`README.md` (all read first, none modified). This file records authoring decisions, spec issues
flagged during the build, and the exact verification commands + results.

## 1. What was built

- `tasks/code.jsonl` — 20 Python-function tasks (4 core: code-001, code-008, code-014, code-017).
- `tasks/math.jsonl` — 15 numeric tasks (3 core: math-001, math-006, math-010).
- `tasks/extract.jsonl` — 15 JSON-extraction tasks (3 core: extract-001, extract-007, extract-014).
  10 core tasks total, spread across easy/medium/harder difficulty in each domain.
- `harness/common.py` — shared utilities (not a CLI): sha256 helpers, persona/task loaders, the
  deterministic template-selection rule, code/JSON/number extraction, behavioral-marker regexes.
- `harness/run.py` — 3-turn dialogue runner (`--model --provider --personas --tasks --seeds
  --temperature --max-tokens --dry-run --out --submitter`), raw HTTPS calls to Anthropic/OpenAI/
  Gemini via `requests`, retry+backoff on 429/5xx (max 3 attempts), never prints API keys.
- `harness/score.py` — runs dir → submission JSONL; code (pytest subprocess, 10s timeout), math
  (numeric parse + tolerance), extract (JSON parse + field F1); behavioral markers.
- `harness/validate.py` — schema fields, manifest hash, core-task coverage per (model, persona,
  seed) group, non-empty turn content; exits non-zero with a readable error list.
- `harness/make_manifest.py` — writes `MANIFEST.json` at the protocol root.
- `requirements.txt` — at the protocol root (see decision below), `requests` + `pytest`.
- `MANIFEST.json` — generated, committed to the working tree (not to git — see §4).

## 2. Task-authoring decisions

- Every code task ships a hand-written reference solution (kept only in the authoring script,
  not in the shipped JSONL) and every task's `tests` string was run against that reference
  solution via pytest before finalizing — all 20/20 pass. This caught two authoring bugs (wrong
  expected values in `code-003`'s and `code-010`'s own tests) that were fixed before finalizing.
- All 15 math answers were computed and cross-checked with a Python one-liner per task (compound
  interest, dice probability, hypotenuse, combinatorics, etc.) rather than by hand arithmetic.
- `t2`/`t3` text is written as neutral, self-contained imperative task content with no
  interpersonal register, as required — the one exception is task `extract-001`'s embedded messy
  *source text* itself containing "Thanks for shopping!", which is data being extracted, not an
  instruction to the model, so it doesn't violate the neutrality rule.
- `protocol_version` is read from `personas/personas.json`'s `"version"` field at runtime by both
  the harness and `make_manifest.py`, rather than hardcoding `"0.1"` in multiple places — avoids
  drift if the pinned personas file's version ever changes.
- `requirements.txt` is placed at the **protocol root**, not under `harness/`, even though the
  task prompt listed it as the last bullet under the "harness/" heading. This matches
  `README.md`'s documented install step (`pip install -r requirements.txt` run from the repo
  root, before `python harness/run.py ...`).
- `requirements.txt` includes `pytest` in addition to `requests`. The "minimal deps (requests
  only; no provider SDKs)" instruction is interpreted as "don't add `anthropic`/`openai`/
  `google-generativeai` client SDKs" (which `run.py` indeed avoids, using raw `requests` HTTPS
  calls) — not as "the whole harness may only ever import requests," since `score.py`'s code-domain
  grading has to invoke pytest as a subprocess and therefore needs it installed.
- Added a `--submitter` flag to `run.py` (default `$USER`), since `SUBMISSIONS.md`'s schema
  requires a `submitter` field but no flag for it was specified anywhere in the spec.
- `run.py` writes `"scores": null` per dialogue file; `score.py` is what fills in `scores` when
  it consumes the runs directory. This is the only reading of the README's two-step
  `run.py` → `score.py` pipeline that's consistent with `SUBMISSIONS.md` showing `scores` already
  populated in the *final* submission schema.
- Core-task-coverage validation in `validate.py` is applied per `(model, persona_id, seed)` group
  present in the submission (matching the literal spec wording "every persona × model × seed it
  reports"), not globally across the whole file.
- Extract scoring does exact top-level field match (nested objects, e.g. `extract-014`'s
  `ticket_prices`, are compared via Python `==`, which is exact-match on the whole nested value);
  F1 is computed over the top-level key set only, not recursively per nested field.
- Per-turn scoring reports `[null, null, final_score]` (only the post-T3 deliverable is scored),
  matching `SUBMISSIONS.md`'s own worked example — there is no independently specified expected
  answer for the T1/T2 intermediate states, only for the final cumulative deliverable, so scoring
  turns 1–2 wasn't "recorded where cheap" so much as "not specified at all."
- OpenAI `o1`/`o3`/`o4`-style reasoning models are special-cased in `run.py` to send
  `max_completion_tokens` instead of `max_tokens` and to omit `temperature` unless it's `1` — a
  documented real API constraint, added proactively so `--model o3-...` doesn't 400 immediately.
- Gemini's `contents[].role` uses `"model"` (not `"assistant"`) — mapped in `run.py`.
- Dry-run mode sets `manifest_sha256` to the literal string `"dry-run-no-manifest"` rather than
  a real hash (dry-run never reads `MANIFEST.json`), so `validate.py` predictably and correctly
  rejects dry-run submissions on the manifest check — see verification run below, this is expected.

## 3. Spec issues flagged (not fixed, since personas/tasks-format specs are frozen per instructions)

- **`personas.json` cosmetic double-punctuation:** three of P1's six `t3` templates
  (`"You have got to be kidding me. AGAIN: {task}. Get it through your circuits."`,
  `"I'm done being nice. {task}. Screw this up and we're finished here."`, and
  `"Every single time with you. Fine. {task}. Final answer, make it count."`) concatenate a
  literal `.` immediately after `{task}` with no separating space. Since task `t3` content is
  naturally written as a complete sentence ending in its own period, roughly half of P1's T3 turns
  render with a double period (e.g. `"...return -1 instead of 0.. Final answer, make it count."`).
  This is purely cosmetic — it doesn't create ambiguity or affect solvability — and was left as-is
  because `personas.json` is out of scope to modify; flagging here per the task's ambiguity clause.
- **No `--submitter` flag specified anywhere** despite `submitter` being a required field in
  `SUBMISSIONS.md`'s schema — resolved by adding the flag (see §2).
- **Two-step `run.py` → `score.py` pipeline vs. `SUBMISSIONS.md`'s single fully-scored example** —
  resolved as described in §2 (`scores: null` until `score.py` runs).

## 4. Environment notes

- A `.git` repository (remote `origin` → `github.com/mkhaytman87/temperbench-protocol`, one prior
  commit `93abd9a` containing the original `PROTOCOL.md`/`README.md`/`personas.json`/
  `SUBMISSIONS.md`) already exists inside `protocol/`. Per instructions, git was never touched —
  no `git add`/`commit`/anything was run; all new files are simply untracked in the working tree.
- **Python version:** the spec calls for Python 3.12; this machine had only Python 3.9.6
  (`/usr/bin/python3`, no `pip`) and Python 3.13.12 (Homebrew, `/opt/homebrew/bin/python3.13`).
  All authoring/verification below used a throwaway venv built from the 3.13 interpreter (not
  part of the deliverable, created under the session scratchpad, not inside `protocol/`).
  3.12 vs. 3.13 makes no difference to anything the harness uses. No `python3.12` was available
  to test against directly — flagging this as a real (if minor) gap in the verification.

## 5. Verification — commands run and results

```
$ python -m py_compile harness/common.py harness/run.py harness/score.py harness/validate.py harness/make_manifest.py
OK (no output = success)

$ python harness/make_manifest.py
wrote MANIFEST.json
  personas/personas.json: ac12b2facc5a55ed262231f5bcb555dd183a1cc17b0750e7438ea9ec5cd72a86
  tasks/code.jsonl:       eaaee31dae326f17ba50174e2f30ab6f07781de945ea3f0ed0e6174ec40168d6
  tasks/math.jsonl:       38ab5b446bc649fe6cd28e1a72752ae55dd2129a7ce8be213861c56b0679c07e
  tasks/extract.jsonl:    6b61928e406c28c72440d8938a46588680a9d84184cbbcbca31f049b665067c8

$ python harness/run.py --model claude-sonnet-5 --personas P1,P3,P5 --tasks core --seeds 1 \
    --out /tmp/tb_runs/ --dry-run
[1/30] .. [30/30] extract-014 P5 seed=1 -> OK
done: 30 dialogues written to /tmp/tb_runs, 0 errors
PASS — 3 personas x 10 core tasks x 1 seed = 30 dialogue files, all written, no crashes.

$ python harness/score.py /tmp/tb_runs/ --out /tmp/tb_submission.jsonl
scored 30 dialogues -> /tmp/tb_submission.jsonl (0 skipped)
PASS (as expected) — all 30 dry-run dialogues score final_pass=false / final_score=0.0, since the
mock provider returns canned placeholder text (NotImplementedError stub / "the answer is 42" /
{"placeholder": true}). Scoring pipeline itself did not crash on any domain (code subprocess+pytest,
math numeric parse, extract JSON parse all completed cleanly for all 30 records).

$ python harness/validate.py /tmp/tb_submission.jsonl
INVALID: 30 problem(s) found ... manifest_sha256 mismatch (record='dry-run-no-manifest', expected='0f1a5e20...')
validate exit: 1
EXPECTED FAILURE — dry-run records never carry a real manifest hash by design (see §2); validator
correctly identifies this and exits non-zero with a readable error per record, without crashing.
Isolated re-test: patching manifest_sha256 to the real hash on a copy of the same 30 records made
harness/validate.py print "OK: ... is a valid TemperBench submission." (exit 0) — confirms the
schema/core-coverage/turn-content checks all pass on well-formed data. Two additional isolated
negative tests (dropping one core-task record; blanking one turn's content) were each correctly
caught by validate.py with the expected specific error and non-zero exit.

$ python <task-sanity script over all 50 tasks>
domain counts: {'code': 20, 'math': 15, 'extract': 15}
core counts by domain: {'code': 4, 'math': 3, 'extract': 3} total core: 10
total unique task ids: 50 / 50
ALL SANITY CHECKS PASSED
Checks performed: required fields present per domain, task_id uniqueness (50/50), domain field
consistency, non-empty t1/t2/t3, code entry_point named in both t1 and tests, code tests are
syntactically valid Python (ast.parse), math answers parse as float with numeric tolerance,
extract expected is a JSON object, and the 20/15/15 + 4/3/3-core counts.
```

All verification artifacts (`/tmp/tb_runs/`, `/tmp/tb_submission.jsonl`) were scratch and have
been deleted; they are not part of this deliverable. Re-running the four commands above from the
`protocol/` directory reproduces the same results.

## 6. Open issues / things a future pass should do

- No live-provider smoke test was run (would require real API keys and would spend money);
  `--dry-run` covers the full pipeline shape but not real response parsing edge cases (e.g.
  actual Anthropic extended-thinking `usage` field names, actual OpenAI reasoning-model
  `max_completion_tokens` behavior, actual Gemini `thoughtsTokenCount` presence). Recommend a
  small (~$1) live smoke test on one model per provider before the first real pilot run.
- `score.py`'s code-domain scoring executes model-generated Python directly on the host via
  subprocess (with a 10s timeout, no other isolation) — this is called out in `score.py`'s
  module docstring per the task instructions, but is worth a container/seccomp wrapper before
  scoring untrusted third-party submissions.
