import math

from wearvalid.normalize import LOA_Z, normalize


def test_bland_altman_decomposes_bias_and_precision():
    c = normalize({"loa_lower": -2.7, "loa_upper": 5.9})
    assert math.isclose(c.bias, 1.6, abs_tol=1e-9)
    assert math.isclose(c.precision, (5.9 - -2.7) / (2 * LOA_Z), rel_tol=1e-9)
    assert c.fidelity == "derived"


def test_bland_altman_uses_reported_bias_when_present():
    c = normalize({"bias": 1.0, "loa_lower": -3.0, "loa_upper": 5.0})
    assert c.bias == 1.0
    assert c.fidelity == "exact"


def test_rmse_decomposition():
    c = normalize({"rmse": 5.0, "bias": 3.0})
    assert math.isclose(c.precision, 4.0, rel_tol=1e-9)  # sqrt(25-9)=4
    assert c.fidelity == "derived"


def test_correlation_only_is_rejected():
    c = normalize({"pearson_r": 0.98})
    assert c.fidelity == "incomparable"
    assert c.precision is None and c.agreement is None
    assert any("correlation" in n.lower() for n in c.notes)


def test_mape_is_lossy_and_not_decomposed():
    c = normalize({"mape": 7.05})
    assert c.precision is None and c.bias is None
    assert c.accuracy_kind == "mape"
    assert c.fidelity == "lossy"


def test_ccc_captured_as_agreement():
    c = normalize({"ccc": 0.10})
    assert c.agreement == 0.10 and c.agreement_kind == "ccc"
    assert c.fidelity == "lossy"
