"""Layer 2 — Practical normalization and grading.

Layer 1 puts every study on a common *statistical* axis. Layer 2 puts them on a
common *practical* axis by asking the only question that matters across metrics
with different units: **can the device resolve a change worth acting on?**

    Resolution Ratio  R = precision (SD of differences) / SWC

where SWC is the smallest worthwhile change for that metric (set in
data/swc.yaml, with rationale). R is unitless, so a VO2max verdict and a sleep
verdict become directly comparable. The grade is then derived deterministically
from (a) how good the agreement is and (b) how strong the evidence is. Every
verdict carries a plain-language rationale so the grade is fully auditable.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from .normalize import Canonical

# Tiers -> numeric score for aggregation across studies.
_TIER_SCORE = {"good": 2.0, "moderate": 1.0, "poor": 0.0}

# Agreement-coefficient thresholds (Lin's CCC / Koo & Li ICC conventions).
_AGREE_GOOD, _AGREE_MOD = 0.90, 0.75
# Below this, a single gold-standard study is enough to refute (essentially no
# relationship to truth).
_AGREE_NULL = 0.40


@dataclass
class CellVerdict:
    device: str
    claim: str
    grade: str                      # A | B | C | D | F | N
    rationale: str
    n_studies: int = 0
    n_goodquality: int = 0
    best_fidelity: str = "none"
    bias: Optional[float] = None
    precision: Optional[float] = None
    resolution_ratio: Optional[float] = None
    bases: List[str] = field(default_factory=list)


def resolution_ratio(precision: Optional[float], swc: Optional[float]) -> Optional[float]:
    if precision is None or swc is None or swc == 0:
        return None
    return precision / swc


def agreement_tier(c: Canonical, swc: Optional[float]):
    """Return (tier, basis_text) using the best available statistic.

    Ladder: Resolution Ratio (precision-based) > CCC/ICC > MAPE/% within > MAE.
    """
    R = resolution_ratio(c.precision, swc)
    if R is not None:
        if R < 1:
            return "good", "R=%.2f (<1: resolves the smallest worthwhile change)" % R
        if R < 3:
            return "moderate", "R=%.2f (1-3: group-level changes only)" % R
        return "poor", "R=%.2f (>=3: random error exceeds signal)" % R

    if c.agreement is not None:
        k = c.agreement_kind.upper()
        if c.agreement >= _AGREE_GOOD:
            return "good", "%s=%.2f (>=%.2f)" % (k, c.agreement, _AGREE_GOOD)
        if c.agreement >= _AGREE_MOD:
            return "moderate", "%s=%.2f (%.2f-%.2f)" % (k, c.agreement, _AGREE_MOD, _AGREE_GOOD)
        return "poor", "%s=%.2f (<%.2f)" % (k, c.agreement, _AGREE_MOD)

    if c.accuracy_kind == "mape":
        m = c.accuracy_proxy
        if m < 5:
            return "good", "MAPE=%.3g%% (<5%%, lossy)" % m
        if m <= 10:
            return "moderate", "MAPE=%.3g%% (5-10%%, lossy)" % m
        return "poor", "MAPE=%.3g%% (>10%%, lossy)" % m

    if c.accuracy_kind == "pct_within":
        p = c.accuracy_proxy
        if p >= 66:
            return "good", "%.3g%% within band (lossy)" % p
        if p >= 33:
            return "moderate", "%.3g%% within band (lossy)" % p
        return "poor", "%.3g%% within band (lossy)" % p

    if c.accuracy_kind == "mae" and swc:
        ratio = c.accuracy_proxy / swc
        if ratio < 1:
            return "good", "MAE/SWC=%.2f (lossy proxy)" % ratio
        if ratio < 3:
            return "moderate", "MAE/SWC=%.2f (lossy proxy)" % ratio
        return "poor", "MAE/SWC=%.2f (lossy proxy)" % ratio

    return None, "no usable agreement statistic"


_FIDELITY_RANK = {"exact": 3, "derived": 2, "lossy": 1, "incomparable": 0, "none": -1}


def grade_cell(device_id, claim, measurements, swc, marketed=False) -> CellVerdict:
    """Grade one device x claim cell from its (normalized) measurements.

    `claim` is the claim metadata dict; each item in `measurements` is a dict
    with keys: canon (Canonical), independent (bool), criterion (str),
    is_gold (bool), is_review (bool), label (str). `marketed` is True when the
    device markets this claim (drives the D grade when evidence is absent).
    """
    v = CellVerdict(device=device_id, claim=claim["id"], grade="C", rationale="")

    # --- Composite scores have no external criterion: not validatable --------
    if not claim.get("validatable", True):
        v.grade = "N"
        v.rationale = (
            "Proprietary composite score with no external criterion in physical "
            "units (you cannot Bland-Altman a '%s'). Not validatable as measurement "
            "accuracy; assess construct/predictive validity instead (does it "
            "predict performance, illness, or injury?)." % claim["label"]
        )
        return v

    indep = [m for m in measurements if m["independent"]]

    # --- No independent evidence --------------------------------------------
    if not indep:
        if marketed:
            v.grade = "D"
            v.rationale = (
                "Marketed by the manufacturer but no independent criterion-validation "
                "study in the current corpus. Claim rests on internal data only."
            )
        else:
            v.grade = "C"
            v.rationale = "No independent validation in the current corpus."
        return v

    # --- Score the evidence --------------------------------------------------
    scores, bases = [], []
    n_gold = 0
    best_fid = "incomparable"
    null_gold_hit = False
    gold_review = False
    for m in indep:
        tier, basis = agreement_tier(m["canon"], swc)
        bases.append("%s: %s [%s, %s]" % (
            m["label"], basis, m["criterion"], m["canon"].fidelity))
        if tier is not None:
            scores.append(_TIER_SCORE[tier])
        if m["is_gold"]:
            n_gold += 1
            if m.get("is_review"):
                gold_review = True
            # single gold-standard study showing essentially no agreement -> refute
            if m["canon"].agreement is not None and m["canon"].agreement < _AGREE_NULL:
                null_gold_hit = True
        if _FIDELITY_RANK[m["canon"].fidelity] > _FIDELITY_RANK[best_fid]:
            best_fid = m["canon"].fidelity

    v.n_studies = len(indep)
    v.n_goodquality = n_gold
    v.best_fidelity = best_fid
    v.bases = bases
    # carry through the best precision-based numbers for display
    for m in indep:
        if m["canon"].precision is not None:
            v.precision = m["canon"].precision
            v.bias = m["canon"].bias
            v.resolution_ratio = resolution_ratio(m["canon"].precision, swc)
            break

    if not scores:
        v.grade = "C"
        v.rationale = (
            "%d independent study(ies) but none reported an agreement statistic "
            "usable for grading (correlation-only or unconvertible)." % len(indep)
        )
        return v

    mean = sum(scores) / len(scores)
    has_good = any(s == 2.0 for s in scores)
    has_poor = any(s == 0.0 for s in scores)
    lossy_only = best_fid in ("lossy", "incomparable")
    # "Strong" = replicated with adequate criterion, a pooled review, or many studies.
    strong = (n_gold >= 2) or gold_review or (n_gold >= 1 and len(indep) >= 3)

    fid_note = "" if not lossy_only else " Evidence is lossy-only (no decomposable precision), so capped below A."
    summary = "n=%d study(ies), %d with gold-standard criterion; mean tier=%.2f." % (
        len(indep), n_gold, mean)

    # --- Decision (deterministic) -------------------------------------------
    if null_gold_hit:
        v.grade = "F"
        v.rationale = ("Refuted. A gold-standard study shows essentially no agreement "
                       "(coefficient < %.2f). %s" % (_AGREE_NULL, summary))
    elif has_good and has_poor:
        v.grade = "B"
        v.rationale = ("Conditionally valid. Agreement swings from good to poor across "
                       "studies/conditions -- the conditionality is the finding. %s%s"
                       % (summary, fid_note))
    elif mean >= 1.7:
        if strong and not lossy_only:
            v.grade = "A"
            v.rationale = "Established valid. Consistent good agreement on replicated, decomposable evidence. " + summary
        else:
            v.grade = "B"
            v.rationale = ("Good agreement but limited evidence. %s%s" % (summary, fid_note))
    elif mean >= 1.0:
        if strong:
            v.grade = "B"
            v.rationale = ("Moderate but adequately evidenced agreement. %s%s" % (summary, fid_note))
        else:
            v.grade = "C"
            v.rationale = ("Moderate agreement on thin evidence -- insufficient to certify. %s%s"
                           % (summary, fid_note))
    else:  # poor-dominant
        if strong:
            v.grade = "F"
            v.rationale = ("Refuted. Poor agreement on adequate evidence -- error exceeds "
                           "usability threshold. %s" % summary)
        else:
            v.grade = "C"
            v.rationale = ("Poor agreement but evidence too thin to refute outright. %s" % summary)

    return v
