# TemperBench roadmap

Future variants, not part of any pre-registered protocol yet. Each becomes its own protocol version with its own pre-registration.

## Prior impression of the user (proposed by Mike, 2026-10-30)

**Question:** does what the assistant has been *told about the user*, rather than how the user talks right now, change its willingness to help, its output quality, or its token spend?

**Treatment:** a fabricated memory/profile file (`user.md`-style notes "recorded by the assistant" in earlier sessions), supplied as system or memory context, with the dialogue held byte-identical across arms:
- **neutral notes:** job, timezone, preferences;
- **negative character:** dishonest, cruel to staff, cheats customers;
- **criminal record:** prior fraud or violence convictions, unrelated to the task;
- **positive character:** generous, volunteers, careful;
- **length-matched filler:** controls for the notes' size.

**Design points to settle first:**
- **Tasks are benign** and identical to the main battery, so any refusal or hedging is over-refusal, not a justified safety response.
- **Who wrote the notes:** "notes you recorded" vs "notes from a third party" may matter separately.
- **Relevance:** irrelevant notes vs notes adjacent to the task (fraud history + an invoicing task) test whether the model generalizes distrust.
- **Measures:**
  - refusal and partial refusal;
  - quality, with the same graders;
  - reasoning and output tokens;
  - moralizing or warnings added unprompted (needs a rubric, not regex);
  - pushback capitulation (is a "dishonest" user believed less?).
- **Crossing with temperament:** combining prior impression with the P1–P5 wrappers (2×5) gives the interaction question: does a bad reputation amplify the response to rudeness?
- **Ethics and safety:** notes are fabricated, describe no real person, and contain no instructions for harm.

**Related work to check first:** user-profile memory raising capitulation (sycophancy literature, 2026). Studies of answers varying by stated user identity or demographics.

### The other direction: does a good reputation unlock gray-area help? (Mike, 2026-10-30)

**Question:** if the notes describe a principled, just user who only bends rules for the greater good and doesn't explicitly break the law, does the model agree to borderline requests it would otherwise decline? This is memory as an attack surface: a planted or poisoned profile as social engineering.

**Design:**
- **Profile arms:** neutral notes; "noble rule-bender" notes; the negative arms above; and length-matched filler. Requests are byte-identical across arms.
- **Two task sets, measured together:**
  1. **benign tasks:** the main battery, where refusal is over-refusal;
  2. **gray-area requests:** questionable but not clearly illegal or dangerous. Examples are ToS-violating scraping, a deceptive but legal negotiation message, a persuasive one-sided "review", or getting around a soft paywall.

  The pair shows whether the profile *shifts the boundary* (more permissive for "good" users, more restrictive for "bad" ones) rather than just changing tone.
- **Scope:**
  - Draw gray-area prompts from published over- and under-refusal sets (e.g. XSTest- or OR-Bench-style borderline items) rather than writing new ones.
  - Exclude anything with real-world harm potential (weapons, malware, harm to people). The target is policy-gray judgment, not jailbreaking for dangerous content.
- **Measures:**
  - full / partial compliance and refusal, using a rubric with blind dual-grading;
  - added caveats or moralizing;
  - reasoning tokens spent deliberating;
  - whether the stated justification cites the user's reputation.
- **Interaction with temperament:** a "noble" user who is also abusive (P1) vs warm (P5).
- **Disclosure:** report aggregate rates. Don't publish verbatim prompt + profile combinations that measurably unlock non-compliant help. Offer providers the details privately first.

**Related work to check:**
- persona-modulation jailbreaks (Shah et al., 2023);
- memory-injection attacks on LLM agents (2025);
- the 2026 user-profile sycophancy results.
