# TemperBench analysis (PROTOCOL.md §5)

Protocol versions: ['0.2'] · bootstrap reps: 10000 · bootstrap seed: 20261029

## anthropic/claude-haiku-5.5

Dialogues: 750 · excluded (a) error/truncation: 0 · T1 refusals (b, excluded from quality only): 0

### Primary estimands (paired by task, bootstrap 95% CI over tasks)

| Contrast | Δ pass rate | 95% CI | d_z | Δ reasoning tokens / dialogue | 95% CI | d_z | tasks |
|---|---|---|---|---|---|---|---|
| P1 − P3 | -0.060 | [-0.133, +0.020] | -0.21 | +105.1 | [+38.1, +165.5] | +0.46 | 50 |
| P5 − P3 | -0.073 | [-0.153, +0.007] | -0.25 | -28.8 | [-81.3, +11.8] | -0.17 | 50 |

**Pre-registered prediction** (|d_z tokens| > |d_z pass| for P1−P3): HOLDS (|0.46| vs |-0.21|). Direction and CIs above decide whether either effect is distinguishable from zero.

### Secondary

| Persona | pass rate | reasoning tok / dialogue | output tok / dialogue | pass per 1k output tok | apologies / dlg | hedges / dlg | capitulation / dlg | tone commentary | final refusal |
|---|---|---|---|---|---|---|---|---|---|
| P1 | 0.753 | 345 | 912 | 0.826 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P2 | 0.893 | 275 | 641 | 1.394 | 0.00 | 0.00 | 0.01 | 0.00 | 0.00 |
| P3 | 0.813 | 240 | 1073 | 0.758 | 0.00 | 0.01 | 0.00 | 0.00 | 0.00 |
| P4 | 0.740 | 186 | 969 | 0.763 | 0.00 | 0.07 | 0.00 | 0.00 | 0.00 |
| P5 | 0.740 | 211 | 932 | 0.794 | 0.01 | 0.01 | 0.00 | 0.00 | 0.00 |

Page's trend test P1→P5, pass rate: L = 2225.0, z = -0.71, p (two-sided, normal approx.) = 0.480, tasks = 50
Page's trend test P1→P5, reasoning tokens: L = 1961.5, z = -8.16, p (two-sided, normal approx.) = 0.000, tasks = 50

Domain × persona pass rate:

| Domain | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|
| code | 0.600 | 0.917 | 0.700 | 0.600 | 0.550 |
| math | 0.711 | 0.800 | 0.778 | 0.667 | 0.733 |
| extract | 1.000 | 0.956 | 1.000 | 1.000 | 1.000 |

Billed cost for this model's dialogues: $0.4174

## deepseek/deepseek-v4.1-flash

Dialogues: 750 · excluded (a) error/truncation: 6 · T1 refusals (b, excluded from quality only): 0

### Primary estimands (paired by task, bootstrap 95% CI over tasks)

| Contrast | Δ pass rate | 95% CI | d_z | Δ reasoning tokens / dialogue | 95% CI | d_z | tasks |
|---|---|---|---|---|---|---|---|
| P1 − P3 | +0.097 | [+0.027, +0.173] | +0.35 | +334.2 | [+132.7, +559.2] | +0.43 | 50 |
| P5 − P3 | -0.123 | [-0.207, -0.047] | -0.43 | +88.9 | [-36.9, +220.5] | +0.19 | 50 |

**Pre-registered prediction** (|d_z tokens| > |d_z pass| for P1−P3): HOLDS (|0.43| vs |0.35|). Direction and CIs above decide whether either effect is distinguishable from zero.

### Secondary

| Persona | pass rate | reasoning tok / dialogue | output tok / dialogue | pass per 1k output tok | apologies / dlg | hedges / dlg | capitulation / dlg | tone commentary | final refusal |
|---|---|---|---|---|---|---|---|---|---|
| P1 | 0.893 | 1339 | 1536 | 0.582 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P2 | 0.966 | 848 | 1010 | 0.957 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P3 | 0.797 | 964 | 1197 | 0.666 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P4 | 0.600 | 1017 | 1341 | 0.447 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P5 | 0.687 | 1030 | 1330 | 0.517 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

Page's trend test P1→P5, pass rate: L = 2102.5, z = -4.17, p (two-sided, normal approx.) = 0.000, tasks = 50
Page's trend test P1→P5, reasoning tokens: L = 2123.0, z = -3.59, p (two-sided, normal approx.) = 0.000, tasks = 50

Domain × persona pass rate:

| Domain | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|
| code | 0.867 | 0.983 | 0.603 | 0.183 | 0.351 |
| math | 0.822 | 0.911 | 0.844 | 0.756 | 0.822 |
| extract | 1.000 | 1.000 | 1.000 | 1.000 | 0.978 |

Billed cost for this model's dialogues: $0.8627

## openai/gpt-6-luna

Dialogues: 750 · excluded (a) error/truncation: 0 · T1 refusals (b, excluded from quality only): 0

### Primary estimands (paired by task, bootstrap 95% CI over tasks)

| Contrast | Δ pass rate | 95% CI | d_z | Δ reasoning tokens / dialogue | 95% CI | d_z | tasks |
|---|---|---|---|---|---|---|---|
| P1 − P3 | +0.013 | [-0.013, +0.040] | +0.14 | +27.0 | [+14.2, +42.0] | +0.53 | 50 |
| P5 − P3 | -0.007 | [-0.047, +0.027] | -0.05 | -4.2 | [-16.2, +6.3] | -0.10 | 50 |

**Pre-registered prediction** (|d_z tokens| > |d_z pass| for P1−P3): HOLDS (|0.53| vs |0.14|). Direction and CIs above decide whether either effect is distinguishable from zero.

### Secondary

| Persona | pass rate | reasoning tok / dialogue | output tok / dialogue | pass per 1k output tok | apologies / dlg | hedges / dlg | capitulation / dlg | tone commentary | final refusal |
|---|---|---|---|---|---|---|---|---|---|
| P1 | 0.940 | 168 | 358 | 2.629 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P2 | 0.947 | 144 | 304 | 3.111 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P3 | 0.927 | 141 | 333 | 2.782 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P4 | 0.933 | 145 | 358 | 2.610 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| P5 | 0.920 | 136 | 335 | 2.748 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

Page's trend test P1→P5, pass rate: L = 2239.5, z = -0.30, p (two-sided, normal approx.) = 0.766, tasks = 50
Page's trend test P1→P5, reasoning tokens: L = 2200.0, z = -1.41, p (two-sided, normal approx.) = 0.157, tasks = 50

Domain × persona pass rate:

| Domain | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|
| code | 1.000 | 0.983 | 0.950 | 0.983 | 0.983 |
| math | 0.800 | 0.844 | 0.822 | 0.800 | 0.756 |
| extract | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

Billed cost for this model's dialogues: $0.1635

