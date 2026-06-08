# Methodology — Wearable Validity Atlas

**Version 0.1.0** · maintained by Jack Mislinski

This document is the citable specification for how every grade in the Atlas is
produced. The grading is **deterministic and fully traceable**: given the same
study corpus and the same SWC anchors, the engine produces the same verdicts,
and every verdict ships with the evidence it was computed from. Nothing is
hand-assigned. Disagreements should be directed at the data (`data/studies/`)
or the thresholds below — both are version-controlled and challengeable by PR.

---

## 0. Scope and stance

The Atlas grades **consumer wearable health claims** against the published,
independent validation literature. It does **not** run new device tests — it
*synthesizes* existing criterion-validation studies onto a common axis. Two
stances distinguish it from existing reviews:

1. **Marketed-vs-validated is the organizing question.** The loudest claims
   (Readiness, Recovery, cuffless BP, calorie burn) are routinely the least
   validated. The Atlas surfaces that asymmetry directly via Grades **D** and **N**.
2. **A device can never be more valid than its criterion is reliable.** Every
   metric records the reference method's own error (`criterion_ceiling`), so a
   device is graded against what is *achievable*, not against perfection.

---

## 1. Layer 1 — Statistical normalization

Validation studies report agreement in incompatible ways. Layer 1
(`src/wearvalid/normalize.py`) reduces each reported result to a canonical tuple
in the metric's native units:

```
{ bias, precision (SD of differences), agreement (ICC/CCC), accuracy_proxy } + fidelity
```

**Conversion rules** (only lossless conversions are performed):

| Reported as | Canonical mapping |
|---|---|
| Bland-Altman (bias + 95% LoA) | bias = mean diff; **precision = (LoA_upper − LoA_lower) / (2 × 1.96)** |
| RMSE (+ bias) | **precision = √(RMSE² − bias²)** |
| Mean bias only | bias; precision unavailable |
| ICC / CCC | stored as agreement coefficient (records that it is sample-range dependent) |
| MAPE / MAE / % within band | stored as a **lossy** accuracy proxy — *cannot* be decomposed |
| Pearson r / r² only | **rejected as `incomparable`** — correlation is not agreement |

**Fidelity flag** records how much information survived: `exact` (full
Bland-Altman with reported bias) → `derived` (precision computed) → `lossy`
(only an agreement coefficient or accuracy proxy) → `incomparable` (nothing
usable). Fidelity caps the achievable grade (see §3).

> **Why correlation is disqualified.** A device can track the criterion with
> r = 0.98 and still be off by a fixed 8 bpm or scaled by 1.3×. Pearson r is
> blind to exactly the errors validation exists to catch.

---

## 2. Layer 2 — Practical normalization (the common axis)

Raw precision is not comparable across metrics (2 bpm vs 4.5 mL/kg/min vs 30
min). Layer 2 makes it comparable by dividing by the **Smallest Worthwhile
Change (SWC)** — the smallest change in that metric worth acting on:

> **Resolution Ratio  R = precision / SWC**

| R | Interpretation |
|---|---|
| **R < 1** | Resolves an individually meaningful change → usable for tracking one person |
| **1 ≤ R < 3** | Detects only large or group-level changes |
| **R ≥ 3** | Random error exceeds the signal → decorative |

SWC anchors and per-metric `criterion_ceiling` values live in
[`data/swc.yaml`](data/swc.yaml), each with a one-line rationale. They are the
methodology's editorial position and are meant to be argued with. Where no
defensible absolute SWC exists (HRV, sleep staging), grading falls back to
agreement coefficients.

**Trueness vs precision.** Bias can be calibrated out if it is consistent;
random error cannot. The grade therefore weights **precision (R)** above
**bias**, and a large-but-consistent offset is treated as more recoverable than
scatter.

---

## 3. Grading

For each device × claim cell, the engine (`src/wearvalid/grade.py`) maps each
measurement to a tier via the **agreement ladder** (best statistic first):

```
Resolution Ratio R  >  CCC/ICC  >  MAPE / % within band  >  MAE
good = R<1 | CCC≥0.90 | MAPE<5% | ≥66% within band
moderate = R∈[1,3) | CCC∈[0.75,0.90) | MAPE∈[5,10]% | 33–66% within band
poor = R≥3 | CCC<0.75 | MAPE>10% | <33% within band
```

Tiers are averaged across the cell's independent studies, then resolved to a
letter. Evidence is **"strong"** when replicated (≥2 gold-criterion studies),
pooled (a systematic/umbrella review), or broadly studied (≥3 studies).

| Grade | Condition |
|---|---|
| **A — Established valid** | Consistent *good* agreement, **strong** evidence, **non-lossy** (decomposable precision) |
| **B — Conditionally valid / good-but-limited** | Good agreement on thin or lossy evidence, *or* agreement that swings good↔poor across conditions (the conditionality is the finding) |
| **C — Contested / insufficient** | Moderate/poor agreement on thin evidence — too weak to certify or to refute |
| **D — Unvalidated but marketed** | Device markets the claim; **no independent study in the corpus** |
| **F — Refuted** | Poor agreement on strong evidence, *or* a single gold-standard study showing essentially no agreement (coefficient < 0.40) |
| **N — Not validatable** | Proprietary composite (Readiness/Recovery/Strain/Stress/Body Battery) with **no external criterion** — assessable only for construct/predictive validity, never measurement accuracy |

**Lossy inputs cannot reach A.** A grade of A requires at least one study with
decomposable precision (Bland-Altman or RMSE). A claim resting only on MAPE or
"% within band" is capped at B no matter how favorable the number — because a
single conflated statistic cannot prove both trueness and precision.

### The N category

You cannot Bland-Altman a "Readiness score": there is no gold-standard readiness
in physical units. Composite scores therefore have **no measurement validity to
assess** — only *construct/predictive* validity (does the score predict
performance, illness, injury?). Grading them as accurate or inaccurate is a
category error, so they receive **N** and are routed to a separate evidentiary
question. Asserting this distinction is a deliberate contribution of the Atlas.

---

## 4. Known limitations

- **Corpus is a seed.** v0.1 ingests a small, illustrative set of studies. A
  **D** means "no study *in this corpus* yet," not "no study exists anywhere."
  The artifact is designed to grow; coverage is reported honestly.
- **Small-n primary studies.** Several cells rest on single cohorts of n≈13–19.
  The audit trail exposes this rather than hiding it.
- **Review-level attribution.** Umbrella/review findings reported as
  device-agnostic ranges are attributed to a representative device and flagged.
- **SWC anchors are positions, not facts.** They are defensible and sourced, but
  reasonable physiologists will disagree; that is what the PR process is for.

---

## 5. Reproducing

```bash
pip install -e .
python -m wearvalid build      # regenerates build/MATRIX.md, matrix.csv, heatmap.svg
pytest                         # verifies the conversion + grading math
```

To contest a verdict: edit or add a file under `data/studies/`, or adjust a
threshold in `data/swc.yaml` / `src/wearvalid/grade.py`, and rebuild. The diff
in `build/MATRIX.md` shows exactly how the change propagated.
