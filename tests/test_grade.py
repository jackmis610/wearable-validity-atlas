from wearvalid.grade import (accuracy_from_canon, agreement_tier, grade_cell,
                             resolution_ratio)
from wearvalid.normalize import normalize

HR = {"id": "heart_rate", "label": "Heart rate", "validatable": True,
      "gold_criteria": ["ecg"]}
READINESS = {"id": "readiness", "label": "Readiness score", "validatable": False,
             "gold_criteria": []}


def _m(reported, criterion="ecg", independent=True, is_review=False, label="s"):
    return {"canon": normalize(reported), "independent": independent,
            "criterion": criterion, "is_gold": criterion in HR["gold_criteria"],
            "is_review": is_review, "label": label}


def test_resolution_ratio():
    assert resolution_ratio(1.5, 3.0) == 0.5
    assert resolution_ratio(None, 3.0) is None
    assert resolution_ratio(2.0, 0) is None


def test_resolution_ratio_drives_tier():
    tier, _ = agreement_tier(normalize({"loa_lower": -1, "loa_upper": 1}), swc=3.0)
    assert tier == "good"  # precision ~0.51, R~0.17


def test_composite_is_N():
    v = grade_cell("oura", READINESS, [], swc=None, marketed=True)
    assert v.grade == "N"


def test_marketed_without_evidence_is_D():
    v = grade_cell("samsung_galaxy", HR, [], swc=3.0, marketed=True)
    assert v.grade == "D"


def test_null_agreement_gold_study_is_refuted():
    v = grade_cell("garmin_fenix", HR, [_m({"ccc": 0.10})], swc=3.0, marketed=True)
    assert v.grade == "F"


def test_good_review_evidence_reaches_at_most_B_when_lossy():
    # systematic review, good % within band, but lossy -> capped below A
    v = grade_cell("apple_watch", HR, [_m({"pct_within_band": 71}, is_review=True)],
                   swc=3.0, marketed=True)
    assert v.grade == "B"


def test_replicated_decomposable_good_evidence_reaches_A():
    ms = [_m({"loa_lower": -1.5, "loa_upper": 1.0}, label="s1"),
          _m({"loa_lower": -1.0, "loa_upper": 1.4}, label="s2")]
    v = grade_cell("apple_watch", HR, ms, swc=3.0, marketed=True)
    assert v.grade == "A"


def test_accuracy_score_mappings():
    # CCC 0.90 -> 80 (good boundary), 1.0 -> 100
    assert accuracy_from_canon(normalize({"ccc": 0.99}), None) == 98.0
    assert round(accuracy_from_canon(normalize({"ccc": 0.10}), None), 2) == 6.67
    # R=1 (precision == swc) sits at the good/moderate boundary -> 80
    assert accuracy_from_canon(normalize({"loa_lower": -1.96, "loa_upper": 1.96}), 1.0) == 80.0
    # MAPE 5% -> 80 (good boundary); 8% -> 62
    assert accuracy_from_canon(normalize({"mape": 5}), None) == 80.0
    assert accuracy_from_canon(normalize({"mape": 8}), None) == 62.0
    # nothing measurable
    assert accuracy_from_canon(normalize({"pearson_r": 0.9}), None) is None


def test_score_tier_never_contradict():
    # The invariant: accuracy >= 80 <=> 'good' tier, across every statistic type.
    cases = [{"ccc": v / 100.0} for v in range(0, 101)]
    cases += [{"mape": m} for m in range(0, 31)]
    cases += [{"pct_within_band": p} for p in range(0, 101, 5)]
    cases += [{"loa_lower": -x, "loa_upper": x} for x in [0.5, 1, 2, 4, 8]]
    for rep in cases:
        c = normalize(rep)
        a = accuracy_from_canon(c, 2.0)
        tier, _ = agreement_tier(c, 2.0)
        if a is not None:
            assert (a >= 80) == (tier == "good"), (rep, a, tier)
            assert (a < 50) == (tier == "poor"), (rep, a, tier)


def test_swapped_loa_never_exceeds_100():
    a = accuracy_from_canon(normalize({"loa_lower": 5.9, "loa_upper": -2.7}), 2.0)
    assert 0 <= a <= 100


def test_unmeasured_cells_have_no_accuracy_but_track_confidence():
    d = grade_cell("whoop", HR, [], swc=3.0, marketed=True)   # Grade D
    assert d.grade == "D" and d.accuracy_score is None and d.confidence_score == 3.0
    n = grade_cell("oura", READINESS, [], swc=None, marketed=True)  # Grade N
    assert n.accuracy_score is None and n.confidence_score is None


def test_good_single_study_high_accuracy_modest_confidence():
    v = grade_cell("oura", HR, [_m({"ccc": 0.99})], swc=3.0, marketed=True)
    assert v.accuracy_score == 98.0
    assert 30 <= v.confidence_score <= 60        # one primary gold study, not replicated


def test_conditional_when_good_and_poor_mix():
    ms = [_m({"loa_lower": -0.5, "loa_upper": 0.5}, label="good"),
          _m({"ccc": 0.50}, label="poorish")]
    v = grade_cell("apple_watch", HR, ms, swc=3.0, marketed=True)
    assert v.grade == "B"
    assert "onditional" in v.rationale
