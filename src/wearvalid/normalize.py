"""Layer 1 — Statistical normalization.

Every validation study reports agreement differently: Bland-Altman limits of
agreement, mean bias, RMSE, MAPE, MAE, ICC, CCC, "% within 3%", or (worst of
all) a Pearson correlation. This module reduces whatever was reported to a
single canonical form:

    {bias, precision, agreement, accuracy_proxy} + a `fidelity` flag

so that heterogeneous studies become comparable. The cardinal rule of
measurement validation is encoded here: *correlation is not agreement*, and
*MAPE cannot be decomposed into trueness and precision*. We never invent
information that the source study did not contain; we only convert losslessly
where the math permits and flag everything else.
"""
from dataclasses import dataclass, field
from typing import List, Optional

# 95% limits of agreement span +/- 1.96 SD of the paired differences.
LOA_Z = 1.96


@dataclass
class Canonical:
    """A study measurement reduced to a common axis (native metric units)."""

    bias: Optional[float] = None            # systematic error (device - criterion)
    precision: Optional[float] = None       # SD of paired differences (random error)
    agreement: Optional[float] = None       # ICC or CCC, 0..1
    agreement_kind: Optional[str] = None    # 'ccc' | 'icc'
    accuracy_proxy: Optional[float] = None  # MAPE %, MAE units, or % within band
    accuracy_kind: Optional[str] = None     # 'mape' | 'mae' | 'pct_within'
    fidelity: str = "incomparable"          # exact | derived | lossy | incomparable
    notes: List[str] = field(default_factory=list)


def normalize(reported: dict) -> Canonical:
    """Reduce a study's `reported` statistics dict to canonical form.

    Priority ladder (best information first):
      1. Bland-Altman (bias + limits of agreement) -> trueness AND precision.
      2. RMSE (+ bias)                              -> precision (decomposed).
      3. Bias alone                                 -> trueness only.
    Agreement coefficients (CCC/ICC) and accuracy proxies (MAPE/MAE/% within)
    are captured alongside, but a measurement carrying *only* a lossy proxy can
    never be treated as precision-grade evidence downstream.
    """
    c = Canonical()

    # --- Disqualify correlation-only evidence outright -----------------------
    usable_keys = set(reported) - {"pearson_r", "spearman_r", "r2"}
    if not usable_keys:
        c.fidelity = "incomparable"
        c.notes.append(
            "Correlation only (r / r^2): measures association, not agreement. "
            "A device can correlate perfectly while being systematically wrong. "
            "Rejected as validity evidence."
        )
        return c

    # --- Trueness + precision -----------------------------------------------
    if "loa_lower" in reported and "loa_upper" in reported:
        lo, hi = reported["loa_lower"], reported["loa_upper"]
        c.bias = reported.get("bias", (lo + hi) / 2.0)
        c.precision = (hi - lo) / (2.0 * LOA_Z)
        c.fidelity = "exact" if "bias" in reported else "derived"
        c.notes.append(
            "Bland-Altman: bias=%.3g, SD_diff=(LoA range)/%.2f=%.3g."
            % (c.bias, 2.0 * LOA_Z, c.precision)
        )
    elif "rmse" in reported:
        rmse = reported["rmse"]
        c.bias = reported.get("bias")
        if c.bias is not None and abs(c.bias) <= rmse:
            c.precision = (rmse ** 2 - c.bias ** 2) ** 0.5
            c.fidelity = "derived"
            c.notes.append(
                "RMSE decomposition: SD_diff=sqrt(RMSE^2 - bias^2)=%.3g." % c.precision
            )
        else:
            c.precision = rmse
            c.fidelity = "derived"
            c.notes.append("RMSE used as precision proxy (bias unavailable).")
    elif "bias" in reported:
        c.bias = reported["bias"]
        c.notes.append("Bias (mean difference) reported; precision unavailable.")

    # --- Agreement coefficient ----------------------------------------------
    if "ccc" in reported:
        c.agreement, c.agreement_kind = reported["ccc"], "ccc"
    elif "icc" in reported:
        c.agreement, c.agreement_kind = reported["icc"], "icc"

    # --- Lossy accuracy proxies ---------------------------------------------
    if "mape" in reported:
        c.accuracy_proxy, c.accuracy_kind = reported["mape"], "mape"
        c.notes.append(
            "MAPE is lossy: it conflates bias and random error into one number "
            "and cannot be decomposed."
        )
    elif "pct_within_band" in reported:
        c.accuracy_proxy, c.accuracy_kind = reported["pct_within_band"], "pct_within"
    elif "mae" in reported:
        c.accuracy_proxy, c.accuracy_kind = reported["mae"], "mae"

    # --- Settle fidelity -----------------------------------------------------
    if c.precision is not None:
        pass  # already exact/derived
    elif c.agreement is not None or c.accuracy_proxy is not None:
        c.fidelity = "lossy"
    elif c.bias is not None:
        c.fidelity = "lossy"  # trueness only, no scatter -> cannot resolve usability
    else:
        c.fidelity = "incomparable"

    return c
