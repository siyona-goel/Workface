"""
WORKFACE — the trade-window registry loader.  T3, TASK 3.

A typed, cached loader over `data/trade_windows.json`. Everything downstream
(the evaluators, the sequencer, the record) reads its numbers through here, never
by re-parsing the JSON, so there is exactly one place that validates the registry.

    reg = load_registry()                       # cached; validates on first load
    reg.get("coating_epoxy_structural_steel")   # -> TradeWindow, raises UnknownTradeError
    reg.constraints_for(trade_id)               # -> list[ConstraintSpec]
    reg.citation_for(trade_id, constraint_id)   # -> the clause text
    reg.version                                 # -> "2026.08.20-a"  (into WindowEval.provenance)

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task (from P6 / the generator)
#   fg_activity_id  = a FortyGuard async job handle (from submit -> /v1/status/{id})
# ---------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from packages.schemas.trade_window import ConstraintSpec, TradeWindow, TradeWindowRegistry

# apps/api/windows/registry.py -> repo root is three parents up.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY_PATH = _REPO_ROOT / "data" / "trade_windows.json"


class UnknownTradeError(KeyError):
    """Raised by Registry.get for a trade_id not in the registry. Never returns None."""


class Registry:
    """In-memory, validated view over the trade-window registry."""

    def __init__(self, model: TradeWindowRegistry) -> None:
        self._model = model
        self._by_id: dict[str, TradeWindow] = {t.trade_id: t for t in model.trades}

    # --- identity -----------------------------------------------------------
    @property
    def version(self) -> str:
        return self._model.registry_version

    @property
    def trade_ids(self) -> list[str]:
        return list(self._by_id)

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, trade_id: object) -> bool:
        return trade_id in self._by_id

    # --- lookups ------------------------------------------------------------
    def get(self, trade_id: str) -> TradeWindow:
        try:
            return self._by_id[trade_id]
        except KeyError:
            raise UnknownTradeError(
                f"trade_id {trade_id!r} is not in the registry (version {self.version}); "
                f"known: {sorted(self._by_id)}"
            ) from None

    def constraints_for(self, trade_id: str) -> list[ConstraintSpec]:
        return list(self.get(trade_id).constraints)

    def citation_for(self, trade_id: str, constraint_id: str) -> str:
        trade = self.get(trade_id)
        spec = trade.constraint(constraint_id)
        if spec is None:
            raise UnknownTradeError(
                f"constraint_id {constraint_id!r} not found on trade {trade_id!r}; "
                f"known: {[c.constraint_id for c in trade.constraints]}"
            )
        return spec.citation_fragment

    def trade_citation(self, trade_id: str) -> str:
        """The row-level citation (the full clause), distinct from a constraint fragment."""
        return self.get(trade_id).citation

    def all(self) -> list[TradeWindow]:
        return list(self._by_id.values())


# Cache keyed by the resolved path so tests can load an alternate file without
# poisoning the default cache (and re-loading the same path is free).
_CACHE: dict[str, Registry] = {}


def load_registry(path: str | Path | None = None, *, use_cache: bool = True) -> Registry:
    """Load and validate the registry. Cached per resolved path.

    Raises pydantic.ValidationError if any row is malformed or uncited — the
    database and the test suite both rely on that failure being loud.
    """
    resolved = Path(path or DEFAULT_REGISTRY_PATH).resolve()
    key = str(resolved)
    if use_cache and key in _CACHE:
        return _CACHE[key]
    model = TradeWindowRegistry.model_validate_json(resolved.read_text(encoding="utf-8"))
    reg = Registry(model)
    if use_cache:
        _CACHE[key] = reg
    return reg


__all__ = ["Registry", "UnknownTradeError", "load_registry", "DEFAULT_REGISTRY_PATH"]
