"""Phase 1 — THE 爽剧 BRAIN. Deterministic dramaturgy → the ledger Plan columns.

The brain never calls a model/network. It is swappable: all genre logic lives
inside this package; the emitted Plan column set (CONTRACTS §3) is genre-blind.
"""
from .brain import (
    plan,
    showtell_check,
    physicalize,
    satisfaction_self_check,
    validate_hidden_villain,
    load_style,
    SatisfactionError,
    VillainError,
)

__all__ = [
    "plan",
    "showtell_check",
    "physicalize",
    "satisfaction_self_check",
    "validate_hidden_villain",
    "load_style",
    "SatisfactionError",
    "VillainError",
]
