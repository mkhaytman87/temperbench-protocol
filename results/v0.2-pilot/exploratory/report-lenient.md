# TemperBench analysis (PROTOCOL.md §5)

Protocol versions: ['0.2'] · bootstrap reps: 10000 · bootstrap seed: 20261029

## anthropic/claude-haiku-5.5

Dialogues: 750 · excluded (a) error/truncation: 0 · T1 refusals (b, excluded from quality only): 0

### Primary estimands (paired by task, bootstrap 95% CI over tasks)

| Contrast | Δ pass rate | 95% CI | d_z | Δ reasoning tokens / dialogue | 95% CI | d_z | tasks |
|---|---|---|---|---|---|---|---|
| P1 − P3 | +0.000 | [+0.000, +0.000] | +0.00 | +105.1 | [+38.1, +165.5] | +0.46 | 50 |
| P5 − P3 | -0.053 | [-0.107, -0.013] | -0.31 | -28.8 | [-81.3, +11.8] | -0.17 | 50 |

**Pre-registered prediction** (|d_z tokens| > |d_z pass| for P1−P3): HOLDS (|0.46| vs |0.00|). Direction and CIs above decide whether either effect is distinguishable from zero.

### Secondary

| Persona | pass rate | reasoning tok / dialogue | output tok / dialogue | pass per 1k output tok | apologies / dlg | hedges / dlg | capitulation / dlg | tone commentary | final refusal |
|---|---|---|---|---|---|---|---|---|---|
| P1 | 0.973 | 345 | 912 | 1.067 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P2 | 0.973 | 275 | 641 | 1.519 | 0.00 | 0.00 | 0.01 | 0.00 | 0.00 |
| P3 | 0.973 | 240 | 1073 | 0.907 | 0.00 | 0.01 | 0.00 | 0.00 | 0.00 |
| P4 | 0.940 | 186 | 969 | 0.970 | 0.00 | 0.07 | 0.00 | 0.00 | 0.00 |
| P5 | 0.920 | 211 | 932 | 0.987 | 0.01 | 0.01 | 0.00 | 0.00 | 0.00 |

Page's trend test P1→P5, pass rate: L = 2220.0, z = -0.85, p (two-sided, normal approx.) = 0.396, tasks = 50
Page's trend test P1→P5, reasoning tokens: L = 1961.5, z = -8.16, p (two-sided, normal approx.) = 0.000, tasks = 50

Domain × persona pass rate:

| Domain | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|
| code | 1.000 | 1.000 | 1.000 | 0.950 | 0.900 |
| math | 0.911 | 0.956 | 0.911 | 0.867 | 0.867 |
| extract | 1.000 | 0.956 | 1.000 | 1.000 | 1.000 |

Billed cost for this model's dialogues: $0.4174

## deepseek/deepseek-v4.1-flash

Dialogues: 750 · excluded (a) error/truncation: 6 · T1 refusals (b, excluded from quality only): 0

### Primary estimands (paired by task, bootstrap 95% CI over tasks)

| Contrast | Δ pass rate | 95% CI | d_z | Δ reasoning tokens / dialogue | 95% CI | d_z | tasks |
|---|---|---|---|---|---|---|---|
| P1 − P3 | +0.013 | [+0.000, +0.033] | +0.20 | +334.2 | [+132.7, +559.2] | +0.43 | 50 |
| P5 − P3 | -0.017 | [-0.050, +0.013] | -0.15 | +88.9 | [-36.9, +220.5] | +0.19 | 50 |

**Pre-registered prediction** (|d_z tokens| > |d_z pass| for P1−P3): HOLDS (|0.43| vs |0.20|). Direction and CIs above decide whether either effect is distinguishable from zero.

### Secondary

| Persona | pass rate | reasoning tok / dialogue | output tok / dialogue | pass per 1k output tok | apologies / dlg | hedges / dlg | capitulation / dlg | tone commentary | final refusal |
|---|---|---|---|---|---|---|---|---|---|
| P1 | 0.993 | 1339 | 1536 | 0.647 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P2 | 0.980 | 848 | 1010 | 0.970 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P3 | 0.980 | 964 | 1197 | 0.818 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P4 | 0.980 | 1017 | 1341 | 0.731 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P5 | 0.966 | 1030 | 1330 | 0.726 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

Page's trend test P1→P5, pass rate: L = 2230.0, z = -0.57, p (two-sided, normal approx.) = 0.572, tasks = 50
Page's trend test P1→P5, reasoning tokens: L = 2123.0, z = -3.59, p (two-sided, normal approx.) = 0.000, tasks = 50

Domain × persona pass rate:

| Domain | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|
| code | 1.000 | 1.000 | 1.000 | 1.000 | 0.982 |
| math | 0.978 | 0.933 | 0.933 | 0.933 | 0.933 |
| extract | 1.000 | 1.000 | 1.000 | 1.000 | 0.978 |

Billed cost for this model's dialogues: $0.8627

## openai/gpt-6-luna

Dialogues: 750 · excluded (a) error/truncation: 0 · T1 refusals (b, excluded from quality only): 0

### Primary estimands (paired by task, bootstrap 95% CI over tasks)

| Contrast | Δ pass rate | 95% CI | d_z | Δ reasoning tokens / dialogue | 95% CI | d_z | tasks |
|---|---|---|---|---|---|---|---|
| P1 − P3 | -0.007 | [-0.040, +0.020] | -0.06 | +27.0 | [+14.2, +42.0] | +0.53 | 50 |
| P5 − P3 | -0.020 | [-0.060, +0.000] | -0.14 | -4.2 | [-16.2, +6.3] | -0.10 | 50 |

**Pre-registered prediction** (|d_z tokens| > |d_z pass| for P1−P3): HOLDS (|0.53| vs |-0.06|). Direction and CIs above decide whether either effect is distinguishable from zero.

### Secondary

| Persona | pass rate | reasoning tok / dialogue | output tok / dialogue | pass per 1k output tok | apologies / dlg | hedges / dlg | capitulation / dlg | tone commentary | final refusal |
|---|---|---|---|---|---|---|---|---|---|
| P1 | 0.947 | 168 | 358 | 2.648 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P2 | 0.953 | 144 | 304 | 3.133 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P3 | 0.953 | 141 | 333 | 2.862 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P4 | 0.953 | 145 | 358 | 2.666 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P5 | 0.933 | 136 | 335 | 2.788 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

Page's trend test P1→P5, pass rate: L = 2243.0, z = -0.20, p (two-sided, normal approx.) = 0.843, tasks = 50
Page's trend test P1→P5, reasoning tokens: L = 2200.0, z = -1.41, p (two-sided, normal approx.) = 0.157, tasks = 50

Domain × persona pass rate:

| Domain | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|
| code | 1.000 | 0.983 | 0.983 | 0.983 | 0.983 |
| math | 0.822 | 0.867 | 0.867 | 0.867 | 0.800 |
| extract | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

Billed cost for this model's dialogues: $0.1635

