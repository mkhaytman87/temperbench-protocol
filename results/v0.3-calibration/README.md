# v0.3 calibration data (neutral persona only)

Used only to select tasks (PROTOCOL.md §2.3 and §8); it is never part of any persona contrast.

- `checkpoint1-3turn-*.jsonl.gz`: the first v0.3 battery, 3 turns with the full spec in turn 1. The run was stopped at a checkpoint at 96% pass (199/207), and that battery was replaced. Its scores refer to the superseded 3-turn candidate tasks (git commit `15cdcb6`).
- `checkpoint2-5turn-*.jsonl.gz`: the 5-turn battery, P3, seed 4. The run was capped at about 25% of budget, in shuffled order. Pass rates: Haiku 53/54, Luna 44/51, DeepSeek 10/11. This led to the "ceiling" selection rule (keep all non-truncation-prone tasks).
