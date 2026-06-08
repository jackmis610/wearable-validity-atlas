"""wearvalid — an auditable validity grading engine for consumer wearables.

Layer 1 (normalize.py) reduces heterogeneous validation statistics to a common
form; Layer 2 (grade.py) converts that to a practical Resolution Ratio and a
deterministic, fully-traceable letter grade.
"""
__version__ = "0.1.0"

from .normalize import Canonical, normalize
from .grade import CellVerdict, grade_cell, resolution_ratio

__all__ = [
    "Canonical", "normalize", "CellVerdict", "grade_cell", "resolution_ratio",
    "__version__",
]
