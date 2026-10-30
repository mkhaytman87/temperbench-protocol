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
