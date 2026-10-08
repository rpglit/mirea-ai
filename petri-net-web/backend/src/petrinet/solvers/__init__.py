"""Solver package: the unified catalog and entry points (ARCH section 2.5).

``solve(task_id, data) -> Report`` and ``catalog(group) -> list[TaskInfo]``.
Catalog: 71 methodic tasks — PN 40 (solvers_pn + solvers_pn_ext), LSS 23
(solvers_lss), FA 8 (solvers_fa). Errors: UnknownTaskError (422),
ValidationError (422), CapExceededError (413), SolverError (500).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from petrinet.errors import UnknownTaskError
from petrinet.solvers.report import Report, SolveFn, TaskInfo
from petrinet.solvers.solvers_fa import REGISTRY as FA_REGISTRY
from petrinet.solvers.solvers_fa import solve_fa
from petrinet.solvers.solvers_lss import REGISTRY as LSS_REGISTRY
from petrinet.solvers.solvers_lss import solve_lss
from petrinet.solvers.solvers_pn import REGISTRY as PN_REGISTRY
from petrinet.solvers.solvers_pn import solve_pn
from petrinet.solvers.solvers_pn_ext import REGISTRY as PN_EXT_REGISTRY
from petrinet.solvers.solvers_pn_ext import solve_pn_ext

__all__ = ["CATALOG", "SolveFn", "TaskInfo", "Report", "catalog", "solve"]

CATALOG: list[TaskInfo] = PN_REGISTRY + PN_EXT_REGISTRY + LSS_REGISTRY + FA_REGISTRY

_BY_ID: dict[str, TaskInfo] = {t.task_id: t for t in CATALOG}

_CUSTOM_ROUTES: dict[str, Callable[[str, dict[str, Any]], Report]] = {
    "describe": lambda tid, d: solve_pn(tid, d),
    "model": lambda tid, d: solve_pn(tid, d),
    "firing": lambda tid, d: solve_pn(tid, d),
    "firing_count": lambda tid, d: solve_pn(tid, d),
    "firing_scenarios": lambda tid, d: solve_pn(tid, d),
    "extend": lambda tid, d: solve_pn(tid, d),
    "classification": lambda tid, d: solve_pn(tid, d),
    "mu_min": lambda tid, d: solve_pn(tid, d),
    "matrices": lambda tid, d: solve_pn(tid, d),
    "minsky": lambda tid, d: solve_pn(tid, d),
    "priority": lambda tid, d: solve_pn_ext(tid, d),
    "temporal": lambda tid, d: solve_pn_ext(tid, d),
    "inhibitor": lambda tid, d: solve_pn_ext(tid, d),
    "colored": lambda tid, d: solve_pn_ext(tid, d),
    "ode": lambda tid, d: solve_lss(tid, d),
    "impulse": lambda tid, d: solve_lss(tid, d),
    "transfer": lambda tid, d: solve_lss(tid, d),
    "freq": lambda tid, d: solve_lss(tid, d),
    "link": lambda tid, d: solve_lss(tid, d),
    "statespace": lambda tid, d: solve_lss(tid, d),
    "normalize": lambda tid, d: solve_fa(tid, d),
    "simulate": lambda tid, d: solve_fa(tid, d),
    "compare": lambda tid, d: solve_fa(tid, d),
    "to_mealy": lambda tid, d: solve_fa(tid, d),
}


def catalog(group: str | None = None) -> list[TaskInfo]:
    """Return the catalog, optionally filtered by group (PN / LSS / FA)."""
    if group is None:
        return list(CATALOG)
    if group not in ("PN", "LSS", "FA"):
        raise UnknownTaskError(f"group:{group}")
    return [t for t in CATALOG if t.group == group]


def solve(task_id: str, data: dict[str, Any] | None = None) -> Report:
    """Solve one catalog (or custom) task and return the methodic Report."""
    info = _BY_ID.get(task_id)
    if info is not None:
        return info.fn(data or {})
    if task_id.startswith("custom:"):
        group_name = task_id.split(":", 1)[1]
        fn = _CUSTOM_ROUTES.get(group_name)
        if fn is None:
            raise UnknownTaskError(task_id)
        return fn(task_id, data or {})
    raise UnknownTaskError(task_id)
