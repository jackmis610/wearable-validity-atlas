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

# Below this agreement coefficient, a single gold-standard study is enough to
# refute (essentially no relationship to truth). Tier cut-points live in
# accuracy_from_canon (the single source of truth for good/moderate/poor).
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
    accuracy_score: Optional[float] = None     # 0-100: how close to criterion when measured
    confidence_score: Optional[float] = None   # 0-100: how much to trust the accuracy score
    bases: List[str] = field(default_factory=list)


def resolution_ratio(precision: Optional[float], swc: Optional[float]) -> Optional[float]:
    if precision is None or swc is None or swc == 0:
        return None
    return precision / swc


def _stat_source(c: Canonical, swc: Optional[float]) -> str:
    """Human-readable description of which statistic drove the score."""
    R = resolution_ratio(c.precision, swc)
    if R is not None:
        return "R=%.2f" % R
    if c.agreement is not None:
        return "%s=%.2f" % (c.agreement_kind.upper(), c.agreement)
    if c.accuracy_kind == "mape":
        return "MAPE=%.3g%%" % c.accuracy_proxy
    if c.accuracy_kind == "pct_within":
        return "%.3g%% within band" % c.accuracy_proxy
    if c.accuracy_kind == "mae" and swc:
        return "MAE/SWC=%.2f" % (c.accuracy_proxy / swc)
    return "?"


def agreement_tier(c: Canonical, swc: Optional[float]):
    """Return (tier, basis_text), derived from the accuracy score.

    Tier is a pure function of `accuracy_from_canon`, so the displayed number
    and the tier can never contradict: >=80 good, 50-80 moderate, <50 poor.
    """
    a = accuracy_from_canon(c, swc)
    if a is None:
        return None, "no usable agreement statistic"
    tier = "good" if a >= 80 else "moderate" if a >= 50 else "poor"
    lossy = "" if c.fidelity in ("exact", "derived") else ", lossy"
    return tier, "%s -> accuracy %.0f/100 (%s%s)" % (_stat_source(c, swc), a, tier, lossy)


_FIDELITY_RANK = {"exact": 3, "derived": 2, "lossy": 1, "incomparable": 0, "none": -1}
# Confidence contribution of the best available fidelity.
_FIDELITY_CONF = {"exact": 20, "derived": 18, "lossy": 6, "incomparable": 0, "none": 0}


def _ratio_to_score(R):
    """Map a Resolution Ratio (or MAE/SWC ratio) to a 0-100 accuracy score.

    Anchored to the tier cut-points so the number never contradicts the tier:
    R=0 -> 100, R=1 (resolves SWC) -> 80, R=3 -> 50.
    """
    if R <= 1:
        return max(0.0, 100 - 20 * R)
    if R < 3:
        return max(0.0, 80 - 15 * (R - 1))
    return max(0.0, 50 - 10 * (R - 3))


def accuracy_from_canon(c, swc):
    """Accuracy score (0-100) for a single measurement, or None if unmeasurable.

    This is the single source of truth: tiers are derived from it (see
    `agreement_tier`), so a score >=80 ALWAYS means 'good', 50-80 'moderate',
    <50 'poor'. Each statistic's mapping is anchored to its domain-conventional
    tier cut-points: CCC/ICC 0.90 (good) & 0.75 (moderate); MAPE 5% & 10%;
    "% within band" 66% & 33%; Resolution Ratio R 1 & 3.
    """
    R = resolution_ratio(c.precision, swc)
    if R is not None:
        return _ratio_to_score(max(R, 0.0))
    if c.agreement is not None:                       # CCC / ICC
        v = min(1.0, max(0.0, c.agreement))
        if v >= 0.90:
            return 80 + 200 * (v - 0.90)              # 0.90->80, 1.00->100
        if v >= 0.75:
            return 50 + 200 * (v - 0.75)              # 0.75->50, 0.90->80
        return (v / 0.75) * 50                        # 0->0, 0.75->50
    if c.accuracy_kind == "mape":
        m = max(0.0, c.accuracy_proxy)
        if m <= 5:
            return 100 - 4 * m                        # 0->100, 5->80
        if m <= 10:
            return 80 - 6 * (m - 5)                   # 5->80, 10->50
        return max(0.0, 50 - 2 * (m - 10))            # 10->50, 35->0
    if c.accuracy_kind == "pct_within":
        p = min(100.0, max(0.0, c.accuracy_proxy))
        if p >= 66:
            return 80 + (p - 66) * (20 / 34.0)        # 66->80, 100->100
        if p >= 33:
            return 50 + (p - 33) * (30 / 33.0)        # 33->50, 66->80
        return (p / 33.0) * 50                        # 0->0, 33->50
    if c.accuracy_kind == "mae" and swc:
        return _ratio_to_score(max(c.accuracy_proxy / swc, 0.0))
    return None


def grade_cell(device_id, claim, measurements, swc, marketed=False) -> CellVerdict:
    """Grade one device x claim cell from its (normalized) measurements.

    `claim` is the claim metadata dict; each item in `measurements` is a dict
    with keys: canon (Canonical), independent (bool), criterion (str),
    is_gold (bool), is_review (bool), label (str). `marketed` is True when the
    device markets this claim (drives the D grade when evidence is absent).
    """
    v = CellVerdict(device=device_id, claim=claim["id"], grade="C", rationale="")

    indep = [m for m in measurements if m["independent"]]

    # --- No independent evidence --------------------------------------------
    if not indep:
        v.accuracy_score = None          # nothing was measured
        if marketed:
            v.grade = "D"
            v.confidence_score = 3.0      # we only know that they claim it
            v.rationale = (
                "Marketed by the manufacturer but no independent criterion-validation "
                "study in the current corpus. Claim rests on internal data only."
            )
        else:
            v.grade = "C"
            v.confidence_score = 0.0
            v.rationale = "No independent validation in the current corpus."
        return v

    # --- Score the evidence --------------------------------------------------
    scores, bases, acc_scores = [], [], []
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
        a = accuracy_from_canon(m["canon"], swc)
        if a is not None:
            acc_scores.append(a)
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
    if acc_scores:
        v.accuracy_score = round(sum(acc_scores) / len(acc_scores), 1)
    # carry through the best precision-based numbers for display
    for m in indep:
        if m["canon"].precision is not None:
            v.precision = m["canon"].precision
            v.bias = m["canon"].bias
            v.resolution_ratio = resolution_ratio(m["canon"].precision, swc)
            break

    if not scores:
        v.grade = "C"
        v.confidence_score = float(min(40, _FIDELITY_CONF[best_fid] + 5 * len(indep)))
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

    # --- Confidence score (0-100): how much to trust the accuracy number -----
    conf = 0.0
    if n_gold >= 1:
        conf += 35
    if n_gold >= 2:
        conf += 20                    # replication with a gold criterion
    elif len(indep) >= 2:
        conf += 8                     # replication without a gold criterion
    if gold_review:
        conf += 20                    # pooled across many primary studies
    conf += _FIDELITY_CONF[best_fid]  # decomposable evidence is worth more
    conf += -10 if (has_good and has_poor) else 8   # consistency
    v.confidence_score = float(max(0, min(100, round(conf))))

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
