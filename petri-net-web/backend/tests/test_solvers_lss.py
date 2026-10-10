"""LSS solver tests: methodic anchors (MATERIALS_ANALYSIS sections 3.2 and 8)."""

from __future__ import annotations

import json

import pytest
import sympy as sp

from petrinet.errors import UnknownTaskError, ValidationError
from petrinet.solvers.report import Report
from petrinet.solvers.solvers_lss import _TASKS, REGISTRY, solve_lss


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


# --- tex fields (iteration 3, MATH_RENDER_PLAN section 4) -------------------------


def test_lss08_phi_tex() -> None:
    a = _answer("TASK-LSS-08")
    assert a["phi_tex"] == "\\frac{1}{s + 5}"
    assert a["phi"] == "1/(s + 5)"  # старый ключ не тронут


def test_lss01_ode_tex_fields() -> None:
    a = _answer("TASK-LSS-01")
    assert "P_tex" in a and a["P_tex"] == "s^{2} + 1"
    assert "\\left" in a["y_tex"] and "\\frac" in a["y_tex"]
    assert "\\left" in a["y_h_tex"]  # C_1 cos(t) + C_2 sin(t), без exp
    assert "^" in a["y_p_tex"]
    steps = solve_lss("TASK-LSS-01").to_dict()["solution"]
    data1 = steps[0]["data"]
    assert data1["roots"] == {"-I": 1, "I": 1}
    assert data1["roots_tex"] == "- i,\\;i"
    assert steps[1]["data"].get("y_h_tex") == a["y_h_tex"]
    assert steps[2]["data"].get("y_p_tex") == a["y_p_tex"]
    assert steps[3]["data"].get("y_tex") == a["y_tex"]


def test_lss14_parts_tex() -> None:
    r = solve_lss("TASK-LSS-14").to_dict()
    part_a = r["answer"]["а) y(t) при x(t) = cos 3t"]
    assert "y" in part_a and "y_tex" in part_a
    part_b = r["answer"]["б) передаточная и частотные характеристики"]
    # детерминизм: tex == sp.latex от str-значения
    assert part_b["phi_tex"] == sp.latex(sp.sympify(part_b["phi"]))
    assert "\\frac" in part_b["phi_tex"]
    assert "A_tex" in part_b and "phi_f_tex" in part_b
    assert r["solution"][0]["data"]["roots_tex"] == "3 - i,\\;3 + i"


def test_lss11_link_tex_fields() -> None:
    a = _answer("TASK-LSS-11")
    assert a["law_tex"] == "T y'(t) + y(t) = k x(t)"
    assert "\\frac" in a["phi_tex"]
    assert "g_tex" in a and "A_tex" in a and "phi_f_tex" in a


def test_lss13_catalog_tex_rows() -> None:
    rows = {r["name"]: r for r in _answer("TASK-LSS-13")["links"]}
    assert len(rows) == 11
    for row in rows.values():
        assert isinstance(row["law_tex"], str) and row["law_tex"]
        assert isinstance(row["phi_tex"], str) and row["phi_tex"]
        assert "g_tex" in row
    assert rows["following"]["law_tex"] == "y(t) = x(t)"
    assert rows["integrator"]["phi_tex"] == "\\frac{1}{s}"


def test_lss18_impulse_rows_tex() -> None:
    rows = {r["name"]: r for r in _answer("TASK-LSS-18")["links"]}
    assert len(rows) == 6
    assert rows["following"]["g_tex"] == "\\delta\\left(t - \\tau\\right)"
    assert all(isinstance(r["g_tex"], str) and r["g_tex"] for r in rows.values())


def test_lss22_statespace_tex() -> None:
    a = _answer("TASK-LSS-22")
    assert a["W_tex"] == "\\frac{c_{1} + c_{2} s}{a_{0} + a_{1} s + a_{2} s^{2}}"
    eqs = a["x0_equations_tex"]
    assert isinstance(eqs, list) and len(eqs) == 2
    assert eqs[0] == "y_{0} = c_{1} x_{1} + c_{2} x_{2}"
    assert "\\frac" in eqs[1] and "y0p" in eqs[1]
    assert all(isinstance(e, str) and "**" not in e for e in eqs)
    assert set(a["x0_tex"]) == {"x1", "x2"}


def test_lss23_statespace_tex() -> None:
    a = _answer("TASK-LSS-23")
    assert a["W"] == "1/(s + 1)"  # старый ключ не тронут
    assert a["W_tex"] == "\\frac{1}{s + 1}"
    assert a["x0_equations_tex"] == ["2 x_{1} + x_{2} = 1", "2 x_{1} + x_{2} = -1"]


def test_roots_tex_is_string() -> None:
    def roots_tex(task_id: str, step_idx: int = 0) -> str:
        steps = solve_lss(task_id).to_dict()["solution"]
        for i, st in enumerate(steps):
            data = st.get("data") or {}
            if "roots" in data:
                assert i == step_idx, f"{task_id}: шаг {i} != {step_idx}"
                return data["roots_tex"]
        raise AssertionError(f"{task_id}: roots не найдены")

    # регрессия приёмки: roots_tex — ОДНА TeX-строка (не dict с int-значениями)
    assert roots_tex("TASK-LSS-02") == "-1,\\;0"
    assert roots_tex("TASK-LSS-03") == "-1,\\;0"
    lss04 = roots_tex("TASK-LSS-04")
    assert lss04 == "-1\\;(^2)"  # кратность 2 видна
    assert roots_tex("TASK-LSS-15", step_idx=2) == "-7"
    for value in (lss04, roots_tex("TASK-LSS-02"), roots_tex("TASK-LSS-15", step_idx=2)):
        assert isinstance(value, str) and "**" not in value


def test_statement_tex_all_tasks() -> None:
    assert len(_TASKS) == 23
    for tid, task in _TASKS.items():
        tex = task.get("statement_tex")
        assert isinstance(tex, str) and tex, tid
        assert "\\" in tex, tid
        assert "**" not in tex, tid


def test_given_statement_tex() -> None:
    given = solve_lss("TASK-LSS-08").to_dict()["given"]
    assert given["statement_tex"] == "y^{\\prime}(t) + 5y(t) = x(t)"
    assert given["statement"]  # старый ключ не тронут
    # parts-задачи: statement в given не был — statement_tex тоже не появляется
    given14 = solve_lss("TASK-LSS-14").to_dict()["given"]
    assert "statement" not in given14 and "statement_tex" not in given14


def test_tex_determinism_double_run() -> None:
    for i in range(1, 24):
        tid = f"TASK-LSS-{i:02d}"
        first = json.dumps(solve_lss(tid).to_dict(), sort_keys=True)
        second = json.dumps(solve_lss(tid).to_dict(), sort_keys=True)
        assert first == second, tid
