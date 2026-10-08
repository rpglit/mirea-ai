"""LSS solver tests: methodic anchors (MATERIALS_ANALYSIS sections 3.2 and 8)."""

from __future__ import annotations

import pytest
import sympy as sp

from petrinet.errors import UnknownTaskError, ValidationError
from petrinet.solvers.report import Report
from petrinet.solvers.solvers_lss import REGISTRY, solve_lss


def _answer(task_id: str, **spec) -> dict:
    report = solve_lss(task_id, spec)
    assert isinstance(report, Report)
    return report.answer


# --- ODE solutions (M4) ---------------------------------------------------------

def test_lss01() -> None:
    a = _answer("TASK-LSS-01")
    assert a["y_p"] == "2*t**2 + 3*t - 3"
    # 3*cos(t) - 3*sin(t) + 2*t**2 + 3*t - 3 (simplify merges the trig part)
    assert "cos(t + pi/4)" in a["y"]
    assert "2*t**2 + 3*t" in a["y"]
    notes = solve_lss("TASK-LSS-01").notes
    assert any("y^(2)(0) = 1" in n and "согласуется" in n for n in notes)


def test_lss02() -> None:
    a = _answer("TASK-LSS-02")
    assert a["y"] == "3*t**2/2 + t - 1 + exp(-t)"
    notes = solve_lss("TASK-LSS-02").notes
    assert any("НЕ согласуется" in n for n in notes)  # y''(0) = 4 != 1


def test_lss03() -> None:
    a = _answer("TASK-LSS-03")
    assert a["y_p"] == "5*exp(-2*t)/2"
    assert "5*exp(-2*t)/2" in a["y"] and "5*exp(-t)" in a["y"]


def test_lss04_resonance() -> None:
    a = _answer("TASK-LSS-04")
    assert a["y_p"] == "t**3*exp(-t)/6"
    assert a["y"] == "t*(t**2 + 6)*exp(-t)/6"


def test_lss05() -> None:
    a = _answer("TASK-LSS-05")
    assert a["y_p"] == "-2*cos(2*t)/3"
    assert "2*cos(t)/3" in a["y"] and "sin(t)" in a["y"]


def test_lss14_grade() -> None:
    a = _answer("TASK-LSS-14")
    part_a = a["а) y(t) при x(t) = cos 3t"]
    assert part_a["y_p"] == "-18*sin(3*t)/65 + cos(3*t)/65"
    part_b = a["б) передаточная и частотные характеристики"]
    assert part_b["phi"] == "5/(s**2 - 6*s + 10)"
    assert part_b["A"] == "5/sqrt(omega**4 + 16*omega**2 + 100)"


def test_lss15_grade() -> None:
    a = _answer("TASK-LSS-15")
    assert a["а) весовая функция"]["g"] == "3*exp(-7*t + 7*tau)"
    assert a["б) y(t) при x(t) = 2e^{−t/2}"]["y"] == "exp(-7*t)/13 + 12*exp(-t/2)/13"


# --- impulse / weight functions ---------------------------------------------------

def test_lss06_17() -> None:
    assert _answer("TASK-LSS-06")["g"] == "exp(8*t - 8*tau)"
    assert _answer("TASK-LSS-17")["g"] == "exp(-5*t + 5*tau)"


def test_lss07_16_19() -> None:
    assert _answer("TASK-LSS-07")["g"] == "k*exp((-t + tau)/T)/T"
    a16 = _answer("TASK-LSS-16")
    assert a16["весовая функция"]["g"] == "k*exp((-t + tau)/T)/T"
    assert a16["передаточная функция"]["phi"] == "k/(T*s + 1)"
    assert _answer("TASK-LSS-19")["g"] == "exp(-h*(t - tau)/J)/J"


def test_lss20_oscillatory() -> None:
    a = _answer("TASK-LSS-20")
    assert "sqrt(T**2*(xi**2 - 1))" in a["g"]
    assert "exp(-2*xi*(t - tau)/T)" in a["g"]
    notes = solve_lss("TASK-LSS-20").notes
    assert any("sinh" in n and "sin" in n for n in notes)


# --- transfer and frequency ----------------------------------------------------------

def test_lss08_09() -> None:
    assert _answer("TASK-LSS-08")["phi"] == "1/(s + 5)"
    assert _answer("TASK-LSS-09")["phi"] == "1/(s**2 - 3*s + 2)"


def test_lss10_general() -> None:
    a = _answer("TASK-LSS-10")
    assert a["phi"] == "(b0 + b1*s)/(a0 + a1*s + a2*s**2)"
    assert "A" in a and "phi_f" in a


def test_lss11_harmonic() -> None:
    a = _answer("TASK-LSS-11")
    assert a["phi"] == "k/(T*s + 1)"
    assert a["A"] == "k/sqrt(T**2*omega**2 + 1)"
    assert a["phi_f"] == "-atan(T*omega)"
    assert a["g"] == "k*exp((-t + tau)/T)/T"


def test_lss12_oscillatory_link() -> None:
    a = _answer("TASK-LSS-12")
    assert a["phi"] == "k/(T**2*s**2 + 2*T*s*xi + 1)"
    assert a["A"] == "k/sqrt(4*T**2*omega**2*xi**2 + (T**2*omega**2 - 1)**2)"
    assert "sin(t*sqrt(1 - xi**2)/T)" in a["g"]


# --- standard links --------------------------------------------------------------------

def test_lss13_catalog() -> None:
    a = _answer("TASK-LSS-13")
    rows = {r["name"]: r for r in a["links"]}
    assert len(rows) == 11
    assert rows["following"]["phi"] == "1"
    assert rows["delay"]["phi"] == "exp(-a*s)"
    assert rows["integrator"]["phi"] == "1/s"
    assert rows["forcing1"]["phi"] == "k*(T*s + 1)"
    assert rows["aperiodic"]["phi"] == "k/(T*s + 1)"


def test_lss18_impulse_links() -> None:
    a = _answer("TASK-LSS-18")
    rows = {r["name"]: r for r in a["links"]}
    assert len(rows) == 6
    assert "DiracDelta" in rows["following"]["g"]
    assert "Heaviside" in rows["integrator"]["g"]
    assert "DiracDelta(t - tau, 1)" in rows["differentiator"]["g"]


# --- state space --------------------------------------------------------------------------

def test_lss21_state_matrices() -> None:
    a = _answer("TASK-LSS-21")
    assert a["F"][0] == [0, 1]
    assert sp.sympify(a["F"][1][0]) == -sp.Symbol("c") / sp.Symbol("m")
    assert sp.sympify(a["F"][1][1]) == -sp.Symbol("h") / sp.Symbol("m")
    assert sp.sympify(a["B"][1][0]) == 1 / sp.Symbol("m")
    assert a["W"] == "1/(c + h*s + m*s**2)"
    assert a["C"] == [[1, 0]]
    assert a["D"] == [[0]]


def test_lss22_initial_conditions() -> None:
    a = _answer("TASK-LSS-22")
    eqs = a["x0_equations"]
    assert "c1*x1 + c2*x2" in eqs[0] and "y0" in eqs[0]
    assert "y0p" in eqs[1]
    # methodic scalar form: -c2(a0/a2)x1 + (c1 - c2(a1/a2))x2
    assert "a0*x1" in eqs[1] and "a1*x2" in eqs[1]


def test_lss23_transfer_and_inconsistency() -> None:
    r = solve_lss("TASK-LSS-23")
    assert r.answer["W"] == "1/(s + 1)"
    assert any("(s + 2)/(s**2 + 3*s + 2)" in n for n in r.notes)
    assert any("несогласованности источника" in n for n in r.notes)


# --- custom and registry ------------------------------------------------------------------

def test_custom_transfer() -> None:
    a = _answer("custom:transfer", a=[1, 2, 1])
    assert a["phi"] == "1/(s**2 + 2*s + 1)"


def test_custom_impulse() -> None:
    a = _answer("custom:impulse", a=[2, 6])
    assert a["g"] == "exp(-3*t + 3*tau)/2"


def test_ode_needs_enough_ics() -> None:
    with pytest.raises(ValidationError):
        solve_lss(
            "custom:ode",
            {"a": [1, 0, 1], "rhs": [{"type": "poly", "coeffs": [1]}], "ics": [0]},
        )


def test_unknown_task_raises() -> None:
    with pytest.raises(UnknownTaskError):
        solve_lss("TASK-LSS-99", {})


def test_registry() -> None:
    ids = {t.task_id for t in REGISTRY}
    assert len(ids) == 23
    assert all(t.group == "LSS" and t.input_kind == "lss" for t in REGISTRY)


def test_report_structure() -> None:
    data = solve_lss("TASK-LSS-08").to_dict()
    assert data["task_id"] == "TASK-LSS-08"
    assert data["given"]["statement"]
    assert data["find"]
    assert [s["step"] for s in data["solution"]] == list(range(1, len(data["solution"]) + 1))
