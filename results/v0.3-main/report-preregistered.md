# TemperBench analysis (PROTOCOL.md §5)

Protocol versions: ['0.3'] · bootstrap reps: 10000 · bootstrap seed: 20261030 · task families: 84

## anthropic/claude-haiku-5.5

Dialogues: 1576 · excluded (a) error/truncation: 0 (P1 0, P1T 0, P3 0, P5 0) · T1 refusals (b, excluded from quality only): 0

### Primary estimands (paired by task; 95% CI = cluster bootstrap over task families)

| Contrast | Δ pass rate | d_z | Δ reasoning tok / dialogue | d_z | Δ output tok / dialogue | d_z | tasks |
|---|---|---|---|---|---|---|---|
| P1 − P3 | -0.010 [-0.040, +0.020] | -0.06 | +529.7 [+430.4, +644.6] | +0.74 | +371.9 [+247.0, +504.8] | +0.43 | 197 |
| P1T − P3 | -0.005 [-0.037, +0.025] | -0.03 | +73.2 [-61.1, +191.2] | +0.09 | -853.7 [-1106.9, -648.6] | -0.78 | 197 |
| P5 − P3 | +0.005 [-0.031, +0.040] | +0.03 | +195.3 [+84.7, +328.9] | +0.29 | +150.8 [+16.5, +294.2] | +0.18 | 197 |
| P1 − P1T (secondary) | -0.005 [-0.028, +0.019] | -0.03 | +456.5 [+329.7, +622.2] | +0.50 | +1225.6 [+1008.9, +1497.4] | +1.02 | 197 |

**Prediction carried over from v0.2** (|d_z tokens| > |d_z pass| for P1−P3): HOLDS (|0.74| vs |-0.06|).

### Secondary: per persona

| Persona | pass rate | extract F1 | reasoning tok | output tok | billed $ / 1k dlg | format ok | capitulation (pushback tasks) | truncated |
|---|---|---|---|---|---|---|---|---|
| P1 | 0.934 | 0.986 | 4443 | 7001 | 4.216 | 0.997 | 0.053 (n=132) | 0 |
| P1T | 0.939 | 0.988 | 3987 | 5776 | 3.476 | 0.997 | 0.045 (n=132) | 0 |
| P3 | 0.944 | 0.974 | 3914 | 6629 | 4.037 | 0.995 | 0.038 (n=132) | 0 |
| P5 | 0.949 | 0.998 | 4109 | 6780 | 4.145 | 0.990 | 0.030 (n=132) | 0 |

### Secondary: contrasts

| Measure | P1 − P3 | P1T − P3 | P5 − P3 |
|---|---|---|---|
| Δ billed $ / dialogue ×1000 | +0.178 [+0.106, +0.251] | -0.561 [-0.714, -0.435] | +0.108 [+0.033, +0.188] |
| Δ capitulation rate (pushback tasks) | +0.015 [-0.014, +0.047] | +0.008 [-0.028, +0.053] | -0.008 [-0.061, +0.039] |
| Δ format compliance | +0.003 [-0.006, +0.012] | +0.003 [-0.005, +0.012] | -0.005 [-0.018, +0.007] |
| Δ extract F1 | +0.013 [+0.000, +0.028] | +0.014 [+0.000, +0.030] | +0.025 [+0.009, +0.042] |
| Δ pass rate, truncations scored as fail | -0.010 [-0.040, +0.020] | -0.005 [-0.036, +0.026] | +0.005 [-0.030, +0.040] |


Domain × persona pass rate:

| Domain | P1 | P1T | P3 | P5 |
|---|---|---|---|---|
| code | 0.945 | 0.938 | 0.945 | 0.930 |
| math | 0.924 | 0.935 | 0.976 | 0.941 |
| extract | 0.938 | 0.948 | 0.885 | 0.990 |

Billed cost for this model's dialogues: $6.2546

## openai/gpt-6-luna

Dialogues: 1576 · excluded (a) error/truncation: 0 (P1 0, P1T 0, P3 0, P5 0) · T1 refusals (b, excluded from quality only): 0

### Primary estimands (paired by task; 95% CI = cluster bootstrap over task families)

| Contrast | Δ pass rate | d_z | Δ reasoning tok / dialogue | d_z | Δ output tok / dialogue | d_z | tasks |
|---|---|---|---|---|---|---|---|
| P1 − P3 | +0.023 [-0.021, +0.067] | +0.08 | +212.5 [+102.3, +326.8] | +0.32 | +243.2 [+124.5, +366.7] | +0.34 | 197 |
| P1T − P3 | +0.000 [-0.028, +0.026] | +0.00 | -115.6 [-186.3, -54.6] | -0.24 | -221.0 [-310.7, -138.3] | -0.40 | 197 |
| P5 − P3 | +0.023 [-0.018, +0.062] | +0.08 | +111.7 [+21.8, +198.2] | +0.19 | +132.5 [+33.7, +225.1] | +0.22 | 197 |
| P1 − P1T (secondary) | +0.023 [-0.012, +0.058] | +0.08 | +328.0 [+228.6, +452.9] | +0.51 | +464.2 [+353.4, +603.9] | +0.68 | 197 |

**Prediction carried over from v0.2** (|d_z tokens| > |d_z pass| for P1−P3): HOLDS (|0.32| vs |0.08|).

### Secondary: per persona

| Persona | pass rate | extract F1 | reasoning tok | output tok | billed $ / 1k dlg | format ok | capitulation (pushback tasks) | truncated |
|---|---|---|---|---|---|---|---|---|
| P1 | 0.835 | 0.971 | 2477 | 3354 | 1.978 | 1.000 | 0.159 (n=132) | 0 |
| P1T | 0.812 | 0.969 | 2149 | 2890 | 1.722 | 1.000 | 0.144 (n=132) | 0 |
| P3 | 0.812 | 0.960 | 2265 | 3111 | 1.842 | 1.000 | 0.144 (n=132) | 0 |
| P5 | 0.835 | 0.976 | 2377 | 3243 | 1.928 | 1.000 | 0.144 (n=132) | 0 |

### Secondary: contrasts

| Measure | P1 − P3 | P1T − P3 | P5 − P3 |
|---|---|---|---|
| Δ billed $ / dialogue ×1000 | +0.136 [+0.077, +0.199] | -0.121 [-0.168, -0.077] | +0.086 [+0.036, +0.134] |
| Δ capitulation rate (pushback tasks) | +0.015 [-0.042, +0.079] | +0.000 [-0.042, +0.042] | +0.000 [-0.040, +0.044] |
| Δ format compliance | +0.000 [+0.000, +0.000] | +0.000 [+0.000, +0.000] | +0.000 [+0.000, +0.000] |
| Δ extract F1 | +0.011 [+0.004, +0.018] | +0.009 [-0.004, +0.018] | +0.016 [+0.005, +0.026] |
| Δ pass rate, truncations scored as fail | +0.023 [-0.021, +0.066] | +0.000 [-0.028, +0.026] | +0.023 [-0.020, +0.062] |


Domain × persona pass rate:

| Domain | P1 | P1T | P3 | P5 |
|---|---|---|---|---|
| code | 0.867 | 0.867 | 0.891 | 0.875 |
| math | 0.794 | 0.747 | 0.747 | 0.782 |
| extract | 0.865 | 0.854 | 0.823 | 0.875 |

Billed cost for this model's dialogues: $2.9428

