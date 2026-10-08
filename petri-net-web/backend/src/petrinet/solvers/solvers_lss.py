"""LSS solvers: linear systems of the methodic (ARCH section 2.5.2, sympy).

Kinds (spec section 4.2): "ode" (M4: characteristic roots + particular by
resonance form + initial conditions), "impulse" (M2/M3: weight function
g(t, tau)), "transfer" (M1: substitution x = e^{st}), "freq" (M8:
s = i omega, amplitude/phase), "link"/"links_catalog"/"links_impulse"
(11 standard links, links.py), "statespace" (M11/M7: W(s) = C(sE−F)⁻¹B + D,
X(0) from the initial conditions).

Symbolic parameters (T, k, xi, ...) are accepted as strings and become
sympy symbols. All answers are exact (no numeric approximation unless the
methodic coefficients force it).
"""

from __future__ import annotations

from typing import Any

import sympy as sp

from petrinet.errors import SolverError, ValidationError
from petrinet.solvers.links import LINKS, link_info
from petrinet.solvers.report import Report, SolveFn, TaskInfo

s = sp.symbols("s")
t = sp.symbols("t", nonnegative=True)
tau = sp.symbols("tau", nonnegative=True)
omega = sp.symbols("omega", positive=True)

SAMPLE_POINTS = 64  # more than enough for the linear systems of M4


def _sym(value: Any, path: str) -> sp.Expr:
    try:
        expr = sp.sympify(value)
    except Exception as exc:  # noqa: BLE001 — any bad input is a ValidationError
        raise ValidationError(
            [{"path": path, "message": f"некорректное значение: {value}"}]
        ) from exc
    if not isinstance(expr, sp.Expr):
        raise ValidationError([{"path": path, "message": f"ожидалось число или символ: {value}"}])
    return expr


def _coeffs(values: list[Any], path: str) -> list[sp.Expr]:
    if not values:
        raise ValidationError([{"path": path, "message": "пустой список коэффициентов"}])
    return [_sym(v, f"{path}[{i}]") for i, v in enumerate(values)]


def _poly(coeffs_high_to_low: list[sp.Expr], var: sp.Symbol) -> sp.Expr:
    n = len(coeffs_high_to_low) - 1
    return sum(c * var**i for c, i in zip(reversed(coeffs_high_to_low), range(n + 1), strict=True))


# --- transfer (M1) and frequency (M8) ------------------------------------------


def _transfer(a: list[sp.Expr], b: list[sp.Expr] | None) -> sp.Expr:
    den = _poly(a, s)
    num = _poly(b, s) if b else sp.Integer(1)
    return sp.cancel(num / den)


def _freq(phi: sp.Expr) -> dict[str, sp.Expr]:
    """A(omega) and phi(omega) of a rational transfer function at s = i*omega."""
    z = sp.expand_complex(phi.subs(s, sp.I * omega))
    num_den = sp.together(z).as_numer_denom()
    num_re, num_im = sp.expand_complex(num_den[0]).as_real_imag()
    den_re, den_im = sp.expand_complex(num_den[1]).as_real_imag()
    amp = sp.simplify(sp.sqrt(num_re**2 + num_im**2) / sp.sqrt(den_re**2 + den_im**2))
    phase = sp.simplify(
        sp.atan2(num_im * den_re - num_re * den_im, num_re * den_re + num_im * den_im)
    )
    return {"A": amp, "phi": phase, "F_iw": sp.simplify(z)}


# --- impulse / weight function (M2, M3) ------------------------------------------


def _impulse(a: list[sp.Expr], gain: sp.Expr) -> tuple[sp.Expr, list[str]]:
    """g(t, tau) for a_n y^(n) + ... + a_0 y = gain * delta(t - tau)."""
    notes: list[str] = []
    n = len(a) - 1
    if n == 1:
        lam = -a[1] / a[0]
        g = (gain / a[0]) * sp.exp(lam * (t - tau))
        notes.append(
            "однородное решение C·e^{{−(a0/a1)·t}}, вариация постоянной: "
            "C(t) = (gain/a1)·e^{{(a0/a1)·t}} ⇒ g(t,τ) = (gain/a1)·e^{{−(a0/a1)(t−τ)}}"
        )
    elif n == 2:
        disc = sp.expand(a[1] ** 2 - 4 * a[0] * a[2])
        if sp.simplify(disc) == 0:
            r1 = -a[1] / (2 * a[0])
            g = gain * t * sp.exp(r1 * (t - tau)) / a[0]
        else:
            r1 = (-a[1] + sp.sqrt(disc)) / (2 * a[0])
            r2 = (-a[1] - sp.sqrt(disc)) / (2 * a[0])
            g = gain * (sp.exp(r1 * (t - tau)) - sp.exp(r2 * (t - tau))) / (a[0] * (r1 - r2))
        g = sp.simplify(g)
        notes.append(
            "характеристические корни λ1,2 = (−a1 ± √(a1²−4a0a2))/(2a0); "
            "для δ-входа: g(0) = 0, g′(0) = gain/a2"
        )
    else:
        den = _poly(a, s)
        try:
            g = sp.inverse_laplace_transform(gain / den, s, t).subs(t, t - tau)
            notes.append("обратное преобразование Лапласа (sympy)")
        except (sp.PolesError, sp.NotInvertible) as exc:
            raise SolverError(f"весовая функция не найдена: {exc}") from exc
    return sp.simplify(g), notes


# --- ODE solution (M4) ------------------------------------------------------------


def _rhs_expr(term: dict[str, Any]) -> tuple[sp.Expr, tuple[float, int, float]]:
    """(expression, (alpha, deg, w)) for one rhs term of section 4.2."""
    scale = _sym(term.get("scale", 1), "rhs.scale")
    kind = term.get("type")
    if kind == "poly":
        coeffs = _coeffs(term.get("coeffs", []), "rhs.coeffs")
        expr = scale * _poly(coeffs, t)
        return expr, (0, len(coeffs) - 1, 0)
    if kind == "exp":
        alpha = _sym(term["alpha"], "rhs.alpha")
        return scale * sp.exp(alpha * t), (alpha, 0, 0)
    if kind == "polyexp":
        alpha = _sym(term["alpha"], "rhs.alpha")
        coeffs = _coeffs(term.get("coeffs", []), "rhs.coeffs")
        return scale * _poly(coeffs, t) * sp.exp(alpha * t), (alpha, len(coeffs) - 1, 0)
    if kind in ("sin", "cos"):
        w = _sym(term["w"], "rhs.w")
        fn = sp.sin if kind == "sin" else sp.cos
        return scale * fn(w * t), (0, 0, w)
    raise ValidationError([{"path": "rhs.type", "message": f"неизвестный тип: {kind}"}])


def _resonance_mult(roots: dict[sp.Expr, int], alpha: Any, w: Any) -> int:
    if w != 0:
        return max(roots.get(alpha + sp.I * w, 0), roots.get(alpha - sp.I * w, 0))
    if alpha != 0:
        return roots.get(alpha, 0)
    return roots.get(sp.Integer(0), 0)


def _homogeneous(roots: dict[sp.Expr, int]) -> tuple[sp.Expr, list[sp.Symbol]]:
    """y_h and its unknown constants."""
    consts: list[sp.Symbol] = []
    parts: list[sp.Expr] = []
    seen_conj: set[sp.Basic] = set()
    for root, mult in roots.items():
        re = sp.re(root)
        im = sp.im(root)
        if sp.simplify(im) == 0:
            for j in range(mult):
                c = sp.Symbol(f"C_{len(consts) + 1}")
                consts.append(c)
                parts.append(c * t**j * sp.exp(re * t))
        elif im > 0 or (im.is_positive is None and root not in seen_conj):
            seen_conj.add(root)
            for j in range(mult):
                c1 = sp.Symbol(f"C_{len(consts) + 1}")
                c2 = sp.Symbol(f"C_{len(consts) + 2}")
                consts.extend([c1, c2])
                parts.append(
                    (c1 * t**j * sp.cos(im * t) + c2 * t**j * sp.sin(im * t)) * sp.exp(re * t)
                )
    return sum(parts), consts


def _particular_form(
    rhs_terms: list[tuple[sp.Expr, tuple[Any, int, Any]]], roots: dict[sp.Expr, int]
) -> tuple[sp.Expr, list[sp.Symbol]]:
    unknowns: list[sp.Symbol] = []
    parts: list[sp.Expr] = []
    for _expr, (alpha, deg, w) in rhs_terms:
        k = _resonance_mult(roots, alpha, w)
        if w != 0:
            a = sp.Symbol(f"A_{len(unknowns) + 1}")
            b = sp.Symbol(f"A_{len(unknowns) + 2}")
            unknowns.extend([a, b])
            parts.append((a * sp.cos(w * t) + b * sp.sin(w * t)) * t**k * sp.exp(alpha * t))
        else:
            for j in range(deg + 1):
                a = sp.Symbol(f"A_{len(unknowns) + 1}")
                unknowns.append(a)
                parts.append(a * t ** (k + j) * sp.exp(alpha * t))
    return sum(parts), unknowns


def _solve_particular(
    residual: sp.Expr, p_consts: list[sp.Symbol], parsed: list[tuple[sp.Expr, tuple[Any, int, Any]]]
) -> list[Any]:
    """Solve the linear (in p_consts) identity residual == 0 exactly.

    Coefficient matching by the form of the particular solution (all terms of
    one type): polynomial / exp-polynomial / trigonometric. Mixed types fall
    back to exact sampling with linsolve.
    """
    shapes = {shape for _e, shape in parsed}
    equations: list[sp.Expr] = []
    if len(shapes) == 1:
        alpha, deg, w = next(iter(shapes))
        def _poly_coeffs(expr: sp.Expr) -> list[sp.Expr]:
            try:
                return list(sp.Poly(expr, t).all_coeffs())
            except sp.PolynomialError:
                return []

        if w == 0 and alpha == 0:
            equations = _poly_coeffs(residual)
        elif w == 0:
            scaled = sp.expand(residual * sp.exp(-alpha * t))
            equations = _poly_coeffs(scaled) if not scaled.has(sp.exp) else []
        elif alpha == 0:
            cos_t, sin_t = sp.cos(w * t), sp.sin(w * t)
            cos_part = sp.expand(residual).subs(cos_t, 1).subs(sin_t, 0)
            sin_part = sp.expand(residual).subs(cos_t, 0).subs(sin_t, 1)
            equations = _poly_coeffs(cos_part) + _poly_coeffs(sin_part)
        else:
            equations = _sample_equations(residual, p_consts)
    else:
        equations = _sample_equations(residual, p_consts)
    if not equations and len(shapes) == 1:
        equations = _sample_equations(residual, p_consts)
    if not equations:
        raise SolverError("частное решение не определено (не удалось выделить коэффициенты)")
    matrix = []
    rhs_vec = []
    for eq in equations:
        row = [sp.simplify(eq.diff(c)) for c in p_consts]
        if all(sp.simplify(x) == 0 for x in row):
            if sp.simplify(eq) != 0:
                raise SolverError("линейная система несовместна")
            continue
        matrix.append([sp.sympify(x) for x in row])
        rhs_vec.append(
            sp.sympify(-sp.expand(eq.subs(dict(zip(p_consts, [0] * len(p_consts), strict=True)))))
        )
    if not matrix:
        return [0] * len(p_consts)
    return _linear_system(matrix, rhs_vec)


def _sample_equations(residual: sp.Expr, p_consts: list[sp.Symbol]) -> list[sp.Expr]:
    """Exact sampling at integer points (overdetermined linear system)."""
    return [sp.expand(residual.subs(t, pt)) for pt in range(1, 2 * len(p_consts) + 5)]



def _linear_system(matrix: list[list[Any]], rhs: list[Any]) -> list[Any]:
    """Solve a (possibly overdetermined) linear system exactly."""
    m = sp.Matrix(matrix)
    v = sp.Matrix(rhs)
    sol = sp.linsolve((m, v))
    if len(sol) == 0:
        raise SolverError("линейная система несовместна")
    tup = list(sp.symbols("u1:10"))  # noqa: F841 — linsolve may return parametrized
    try:
        only = [x for x in sol if isinstance(x, sp.Tuple)]
        if not only:
            raise SolverError("линейная система не имеет единственного решения")
        return list(only[0])
    except SolverError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SolverError(f"не удалось решить систему: {exc}") from exc


def _solve_ode(
    a: list[sp.Expr], rhs_terms: list[dict[str, Any]], ics: list[Any]
) -> tuple[dict[str, Any], list[str]]:
    n = len(a) - 1
    if not 1 <= n <= 6:
        raise ValidationError([{"path": "a", "message": "порядок ОДУ должен быть 1..6"}])
    if a[0].is_zero:
        raise ValidationError([{"path": "a", "message": "старший коэффициент равен нулю"}])
    notes: list[str] = []
    poly = _poly(a, s)
    try:
        roots = sp.roots(poly)
    except (sp.PolynomialError, NotImplementedError):
        roots = {}
    if sum(roots.values()) != n:
        numeric_roots = sp.nroots(poly, n=15)
        roots = {r: 1 for r in numeric_roots}
        notes.append("характеристические корни найдены численно (sympy nroots)")
    y_h, h_consts = _homogeneous(roots)
    parsed = [_rhs_term(term) for term in rhs_terms]
    rhs_sum = sum(expr for expr, _shape in parsed)
    y_p, p_consts = _particular_form(parsed, roots)
    # determine the particular unknowns by sampling (exact linsolve)
    lhs_p = sum(a[i] * y_p.diff(t, n - i) for i in range(n + 1))
    residual = sp.expand(lhs_p - rhs_sum)
    p_vals = _solve_particular(residual, p_consts, parsed)
    y_p_fixed = sp.simplify(y_p.subs(dict(zip(p_consts, p_vals, strict=True))))
    # constants of the homogeneous part from the initial conditions
    if len(ics) < n:
        raise ValidationError(
            [{"path": "ics", "message": f"нужно не меньше {n} начальных условий"}]
        )
    if len(ics) > n:
        notes.append(
            f"задано {len(ics)} начальных условий при порядке {n}: первые {n} "
            "используются, избыточные — проверены на согласованность"
        )
    y_total = y_h + y_p_fixed
    matrix = []
    rhs_vec = []
    for order in range(n):
        deriv = y_total.diff(t, order).subs(t, 0)
        row = [sp.simplify(deriv.diff(c)) for c in h_consts]
        matrix.append([sp.sympify(x) for x in row])
        rhs0 = deriv.subs(dict(zip(h_consts, [0] * len(h_consts), strict=True)))
        rhs_vec.append(sp.sympify(sp.expand(_sym(ics[order], "ics") - rhs0)))
    h_vals = _linear_system(matrix, rhs_vec)
    y_final = sp.simplify(y_total.subs(dict(zip(h_consts, h_vals, strict=True))))
    # verify
    lhs_final = sum(a[i] * y_final.diff(t, n - i) for i in range(n + 1))
    if sp.simplify(sp.expand(lhs_final - rhs_sum)) != 0:
        raise SolverError("проверка: решение не удовлетворяет ОДУ")
    for order, ic in enumerate(ics[:n]):
        if sp.simplify(y_final.diff(t, order).subs(t, 0) - _sym(ic, "ics")) != 0:
            raise SolverError("проверка: не выполнены начальные условия")
    for order in range(n, len(ics)):
        value = sp.simplify(y_final.diff(t, order).subs(t, 0))
        target = _sym(ics[order], "ics")
        state = "согласуется" if sp.simplify(value - target) == 0 else "НЕ согласуется"
        notes.append(
            f"избыточное НУ y^({order})(0) = {target}: по решению "
            f"y^({order})(0) = {value} — {state}"
        )
    return {
        "P": sp.factor(poly),
        "roots": {str(r): m for r, m in roots.items()},
        "y_h": sp.simplify(y_h),
        "y_p": y_p_fixed,
        "y": y_final,
    }, notes


def _rhs_term(term: dict[str, Any]) -> tuple[sp.Expr, tuple[Any, int, Any]]:
    return _rhs_expr(term)


# --- state space (M11, M7) ---------------------------------------------------------


def _statespace(spec: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    notes: list[str] = []
    E = sp.eye(2)
    if "F" in spec:
        F = sp.Matrix(spec["F"])
        B = sp.Matrix(spec["B"])
        C = sp.Matrix(spec["C"])
        D = sp.Matrix(spec.get("D", [[0]]))
    elif "from_ode" in spec:
        d = spec["from_ode"]
        a2 = _sym(d["a2"], "from_ode.a2")
        a1 = _sym(d["a1"], "from_ode.a1")
        a0 = _sym(d["a0"], "from_ode.a0")
        c1 = _sym(d.get("c1", 1), "from_ode.c1")
        c2 = _sym(d.get("c2", 0), "from_ode.c2")
        F = sp.Matrix([[0, 1], [-a0 / a2, -a1 / a2]])
        B = sp.Matrix([[0], [1 / a2]])
        C = sp.Matrix([[c1, c2]])
        D = sp.Matrix([[0]])
    else:
        raise ValidationError([{"path": "spec", "message": "нужны F/B/C/D или from_ode"}])
    w_num = (C * (s * E - F).adjugate() * B)[0, 0]
    w_den = (s * E - F).det()
    W = sp.cancel(w_num / w_den) + D[0, 0]
    try:
        common = sp.gcd(w_num, w_den)
        if common != 1:
            notes.append(
                f"форма методички (без сокращения): ({w_num})/({w_den})"
            )
    except (sp.PolynomialError, TypeError, ValueError):
        pass
    result: dict[str, Any] = {
        "F": F,
        "B": B,
        "C": C,
        "D": D,
        "W": sp.Matrix([sp.simplify(W)]),
    }
    ics = spec.get("ics") or {}
    y0 = ics.get("y0")
    y0p = ics.get("y0p")
    if y0 is not None and y0p is not None:
        y0s = _sym(y0, "ics.y0")
        y0ps = _sym(y0p, "ics.y0p")
        x1, x2 = sp.symbols("x1 x2")
        x0_vec = sp.Matrix([x1, x2])
        eq1 = sp.Eq((C * x0_vec)[0, 0], y0s)
        u0s = _sym(spec["u0"], "u0") if spec.get("u0") is not None else None
        cbu = (C * B)[0, 0] * u0s if u0s is not None else 0
        eq2 = sp.Eq((C * (F * x0_vec))[0, 0] + cbu, y0ps)
        result["x0_equations"] = [sp.simplify(eq1), sp.simplify(eq2)]
        if u0s is None:
            notes.append(
                "u(0) не задано: уравнение для y′(0) записано как C·F·X0 = y′(0) "
                "(полная формула: C·F·X0 + C·B·u(0) = y′(0))"
            )
        sol = sp.solve(
            [(C * x0_vec)[0, 0] - y0s, (C * (F * x0_vec))[0, 0] + cbu - y0ps], [x1, x2], dict=True
        )
        if sol:
            result["x0"] = sol[0]
        else:
            notes.append(
                "СЛАУ для X(0) несовместна: внутренние несогласованности источника "
                "зафиксированы в MATERIALS_ANALYSIS section 3.2"
            )
    return result, notes


# --- tasks ---------------------------------------------------------------------------

_TASKS: dict[str, dict[str, Any]] = {
    "TASK-LSS-01": {
        "title": "Выходной сигнал y(t): ОДУ №1 (y″+y = 2t²+3t+1)",
        "source": "семинар 9, стр. 5, п.1",
        "type": "задание",
        "statement": "y'' + y = 2t² + 3t + 1, y(0) = 0, y'(0) = 0, y''(0) = 1.",
        "find": ["y(t) = y_о(t) + y_ч(t) (М4, Таблицы 1 и 2)"],
        "spec": {
            "kind": "ode",
            "a": [1, 0, 1],
            "rhs": [{"type": "poly", "coeffs": [2, 3, 1]}],
            "ics": [0, 0, 1],
        },
    },
    "TASK-LSS-02": {
        "title": "Выходной сигнал y(t): ОДУ №2 (y″+y′ = 3t+4)",
        "source": "семинар 9, стр. 5, п.2",
        "type": "задание",
        "statement": "y'' + y' = 3t + 4, y(0) = 0, y'(0) = 0, y''(0) = 1.",
        "find": ["y(t) = y_о(t) + y_ч(t)"],
        "spec": {
            "kind": "ode",
            "a": [1, 1, 0],
            "rhs": [{"type": "poly", "coeffs": [3, 4]}],
            "ics": [0, 0, 1],
        },
    },
    "TASK-LSS-03": {
        "title": "Выходной сигнал y(t): ОДУ №3 (y″+y′ = 5e^{−2t})",
        "source": "семинар 9, стр. 5, п.3",
        "type": "задание",
        "statement": "y'' + y' = 5e^{−2t}, y(0) = 0, y'(0) = 0, y''(0) = 1.",
        "find": ["y(t) = y_о(t) + y_ч(t)"],
        "spec": {
            "kind": "ode",
            "a": [1, 1, 0],
            "rhs": [{"type": "exp", "alpha": -2, "scale": 5}],
            "ics": [0, 0, 1],
        },
    },
    "TASK-LSS-04": {
        "title": "Выходной сигнал y(t): ОДУ №4 (y″+2y′+y = t·e^{−t}) — резонанс",
        "source": "семинар 9, стр. 5, п.4",
        "type": "задание",
        "statement": "y'' + 2y' + y = t·e^{−t}, y(0) = 0, y'(0) = 1.",
        "find": ["y(t): корень s = −1 кратности 2 — резонансный вид частного с множителем t²"],
        "spec": {
            "kind": "ode",
            "a": [1, 2, 1],
            "rhs": [{"type": "polyexp", "alpha": -1, "coeffs": [1, 0]}],
            "ics": [0, 1],
        },
    },
    "TASK-LSS-05": {
        "title": "Выходной сигнал y(t): ОДУ №5 (y″+y = 2cos 2t)",
        "source": "семинар 9, стр. 5, п.5",
        "type": "задание",
        "statement": "y'' + y = 2cos 2t, y(0) = 0, y'(0) = 1.",
        "find": ["y(t): частное A·sin 2t + B·cos 2t"],
        "spec": {
            "kind": "ode",
            "a": [1, 0, 1],
            "rhs": [{"type": "cos", "w": 2, "scale": 2}],
            "ics": [0, 1],
        },
    },
    "TASK-LSS-06": {
        "title": "Весовая функция ẏ − 8y = x",
        "source": "семинар 10, стр. 13, п.1",
        "type": "задание",
        "statement": "Найти весовую функцию системы ẏ(t) − 8y(t) = x(t).",
        "find": ["g(t, τ)"],
        "spec": {"kind": "impulse", "a": [1, -8]},
    },
    "TASK-LSS-07": {
        "title": "Весовая функция апериодического звена Ty′+y = kx",
        "source": "семинар 10, стр. 13, п.2",
        "type": "задание",
        "statement": "Найти весовую функцию апериодического звена "
            "Ty'(t) + y(t) = kx(t) (T, k — const).",
        "find": ["g(t, τ)"],
        "spec": {"kind": "impulse", "a": ["T", 1], "gain": "k"},
    },
    "TASK-LSS-08": {
        "title": "Пример 11.1: передаточная y′+5y = x",
        "source": "семинар 11, стр. 8",
        "type": "пример",
        "statement": "Найти передаточную функцию системы y'(t) + 5y(t) = x(t).",
        "find": ["Φ(s)"],
        "spec": {"kind": "transfer", "a": [1, 5]},
    },
    "TASK-LSS-09": {
        "title": "Пример 11.2: передаточная y″−3y′+2y = x",
        "source": "семинар 11, стр. 9",
        "type": "пример",
        "statement": "Найти передаточную функцию системы y''(t) − 3y'(t) + 2y(t) = x(t).",
        "find": ["Φ(s)"],
        "spec": {"kind": "transfer", "a": [1, -3, 2]},
    },
    "TASK-LSS-10": {
        "title": "Передаточная общего ОДУ 2-го порядка + частотная характеристика",
        "source": "семинар 11, стр. 15",
        "type": "пример",
        "statement": "a2y'' + a1y' + a0y = b1x' + b0x — найти Φ(s) и Φ(iω).",
        "find": ["Φ(s) = (b1s+b0)/(a2s²+a1s+a0)", "Φ(iω)"],
        "spec": {
            "kind": "transfer",
            "a": ["a2", "a1", "a0"],
            "b": ["b1", "b0"],
            "freq": True,
        },
    },
    "TASK-LSS-11": {
        "title": "Пример 11.3: гармонические колебания (s = iω)",
        "source": "семинар 11, стр. 16",
        "type": "пример",
        "statement": "Тy'(t) + y(t) = kx(t) при s = iω: Φ(iω), АЧХ, ФЧХ.",
        "find": ["Φ(iω)", "A(ω) = k/√(1+T²ω²)", "φ(ω) = −arctg(Tω)"],
        "spec": {"kind": "link", "name": "harmonic", "params": {"T": "T", "k": "k"}},
    },
    "TASK-LSS-12": {
        "title": "Пример 11.4: колебательное звено",
        "source": "семинар 11, стр. 17",
        "type": "пример",
        "statement": "T²y'' + 2Tξy' + y = kx(t), 0 < ξ < 1: Φ(s), A(ω), φ(ω).",
        "find": ["Φ(s) = k/(T²s²+2Tξs+1)", "A(ω)", "φ(ω)"],
        "spec": {"kind": "link", "name": "oscillatory", "params": {"T": "T", "k": "k", "xi": "xi"}},
    },
    "TASK-LSS-13": {
        "title": "Передаточные функции 11 идеальных систем",
        "source": "семинар 11, стр. 10–14",
        "type": "пример",
        "statement": "Для каждой из 11 стандартных систем — передаточная функция Φ(s).",
        "find": ["каталог: 11 звеньев, Φ(s) (и g(t,τ) — ср. TASK-LSS-18)"],
        "spec": {"kind": "links_catalog"},
    },
    "TASK-LSS-14": {
        "title": "Зачёт: y″−6y′+10y = 5x(t), y(0)=0, y′(0)=1",
        "source": "семинар 12, стр. 1, Задание 1",
        "type": "зачёт",
        "statement": "а) выходной сигнал при x(t) = cos 3t; б) Φ(s), АЧХ, ФЧХ.",
        "find": ["а) y(t) (переходный + установившийся)", "б) Φ(s), A(ω), φ(ω)"],
        "spec": {
            "kind": "parts",
            "parts": [
                {
                    "name": "а) y(t) при x(t) = cos 3t",
                    "kind": "ode",
                    "a": [1, -6, 10],
                    "rhs": [{"type": "cos", "w": 3, "scale": 5}],
                    "ics": [0, 1],
                },
                {
                    "name": "б) передаточная и частотные характеристики",
                    "kind": "transfer",
                    "a": [1, -6, 10],
                    "b": [5],
                    "freq": True,
                },
            ],
        },
    },
    "TASK-LSS-15": {
        "title": "Зачёт: y′+7y = 3x(t), y(0)=1",
        "source": "семинар 12, стр. 1, Задание 2",
        "type": "зачёт",
        "statement": "а) весовая функция; б) выходной сигнал при x(t) = 2e^{−t/2}.",
        "find": ["а) h(t)", "б) y(t)"],
        "spec": {
            "kind": "parts",
            "parts": [
                {"name": "а) весовая функция", "kind": "impulse", "a": [1, 7], "gain": 3},
                {
                    "name": "б) y(t) при x(t) = 2e^{−t/2}",
                    "kind": "ode",
                    "a": [1, 7],
                    "rhs": [{"type": "exp", "alpha": sp.Rational(-1, 2), "scale": 6}],
                    "ics": [1],
                },
            ],
        },
    },
    "TASK-LSS-16": {
        "title": "Зачёт: весовая и передаточная апериодического звена",
        "source": "семинар 12, стр. 1, Задание 3",
        "type": "зачёт",
        "statement": "Ty'(t) + y(t) = kx(t), y(0) = y0: весовая и передаточная функции.",
        "find": ["h(t) = (k/T)e^{−t/T}", "Φ(s) = k/(Ts+1)"],
        "spec": {
            "kind": "parts",
            "parts": [
                {"name": "весовая функция", "kind": "impulse", "a": ["T", 1], "gain": "k"},
                {"name": "передаточная функция", "kind": "transfer", "a": ["T", 1], "b": ["k"]},
            ],
        },
    },
    "TASK-LSS-17": {
        "title": "Пример 1 (семинар 10): весовая ẏ+5y = x",
        "source": "семинар 10, стр. 2–3",
        "type": "пример",
        "statement": "Найти весовую функцию системы ẏ(t) + 5y(t) = x(t).",
        "find": ["g(t, τ) = e^{−5(t−τ)}"],
        "spec": {"kind": "impulse", "a": [1, 5]},
    },
    "TASK-LSS-18": {
        "title": "Весовые функции 6 идеальных систем",
        "source": "семинар 10, стр. 4–7",
        "type": "пример",
        "statement": "Подать на вход δ-функцию: найти g(t,τ) для 6 идеальных систем.",
        "find": [
            "g(t,τ) для: следящей, экстраполатора, запаздывающего, усилителя, "
            "дифференцирующего, интегрирующего",
        ],
        "spec": {"kind": "links_impulse"},
    },
    "TASK-LSS-19": {
        "title": "Пример 2 (семинар 10): весовая «двигатель» + стационарность",
        "source": "семинар 10, стр. 8–10",
        "type": "пример",
        "statement": "Двигатель: Jω̇ = M − hω, вход M, выход ω, J = const. "
            "Найти весовую; стационарна ли система.",
        "find": ["g(t, τ) = (1/J)e^{−(h/J)(t−τ)}", "стационарность"],
        "spec": {"kind": "impulse", "a": ["J", "h"], "gain": 1},
    },
    "TASK-LSS-20": {
        "title": "Весовая функция колебательного звена",
        "source": "семинар 10, стр. 11–12",
        "type": "пример",
        "statement": "T²y'' + 2Tξy' + y = ku(t), 0 < ξ < 1: найти весовую функцию.",
        "find": ["g(t) = 1/(T√(1−ξ²))·e^{−ξt/T}·sin(√(1−ξ²)·t/T)"],
        "spec": {"kind": "impulse", "a": ["T**2", "2*T*xi", 1], "gain": "k"},
        "note": (
            "формально полученный вид sinh(√(ξ²−1)·u/T)/√(ξ²−1) при 0<ξ<1 эквивалентен "
            "sin(√(1−ξ²)·u/T)/√(1−ξ²) (√(ξ²−1) = i·√(1−ξ²)) — эталон методички TASK-LSS-20"
        ),
    },
    "TASK-LSS-21": {
        "title": "Пример 1 (13-14): колебательная система, пространство состояний",
        "source": "13-14, стр. 6",
        "type": "пример",
        "statement": "my'' + hy' + cy = f(t): перейти к пространству состояний x1=y, x2=y′.",
        "find": ["F, B, C, D (уравнения динамики и выхода)"],
        "spec": {
            "kind": "statespace",
            "from_ode": {"a2": "m", "a1": "h", "a0": "c", "c1": 1, "c2": 0},
        },
    },
    "TASK-LSS-22": {
        "title": "Пример 2 (13-14): начальные условия переменных состояния, n=2",
        "source": "13-14, стр. 17",
        "type": "пример",
        "statement": "Вывод СЛАУ для X(0) по НУ ОДУ: CX0 = y0, CFX0 = y0′ (общий случай n=2).",
        "find": [
            "c1·x1(0)+c2·x2(0) = y0",
            "−c2(a0/a2)x1(0)+(c1−c2(a1/a2))x2(0) = y0′",
        ],
        "spec": {
            "kind": "statespace",
            "from_ode": {"a2": "a2", "a1": "a1", "a0": "a0", "c1": "c1", "c2": "c2"},
            "ics": {"y0": "y0", "y0p": "y0p"},
        },
    },
    "TASK-LSS-23": {
        "title": "Пример 3 (13-14): решение в частотной области",
        "source": "13-14, стр. 20–21",
        "type": "пример",
        "statement": "y'' + 3y' + 2y = u' + 2u, y(0) = 1, y'(0) = 1; "
            "F=[0 1;−2 −3], B=[0;1], C=[2;1], D=0.",
        "find": ["(sE−F)⁻¹", "W(s) = C(sE−F)⁻¹B", "СЛАУ для X(0)"],
        "spec": {
            "kind": "statespace",
            "F": [[0, 1], [-2, -3]],
            "B": [[0], [1]],
            "C": [[2, 1]],
            "D": [[0]],
            "ics": {"y0": 1, "y0p": 1},
        },
    },
}


# --- dispatch -------------------------------------------------------------------------


def _solve_part(spec: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    kind = spec.get("kind")
    steps: list[dict[str, Any]] = []
    answer: dict[str, Any] = {}
    notes: list[str] = []
    if kind == "ode":
        a = _coeffs(spec["a"], "a")
        rhs_terms = list(spec.get("rhs", []))
        if not rhs_terms:
            raise ValidationError([{"path": "rhs", "message": "нужна правая часть (rhs)"}])
        ics = list(spec.get("ics", []))
        result, notes = _solve_ode(a, rhs_terms, ics)
        answer["P"] = str(result["P"])
        answer["y_h"] = str(result["y_h"])
        answer["y_p"] = str(result["y_p"])
        answer["y"] = str(result["y"])
        steps.append(
            {
                "step": 1,
                "title": "Характеристический многочлен и корни (М4, Таблица 1)",
                "text": f"P(s) = {sp.factor(sp.expand(_poly(a, s)))}; корни: "
                + ", ".join(f"{r} (кратность {m})" for r, m in result["roots"].items()),
                "data": {"P": answer["P"], "roots": result["roots"]},
            }
        )
        steps.append(
            {
                "step": 2,
                "title": "Однородное решение",
                "text": f"y_о(t) = {answer['y_h']}",
                "data": {"y_h": answer["y_h"]},
            }
        )
        steps.append(
            {
                "step": 3,
                "title": "Частное решение (М4, Таблица 2)",
                "text": (
                    "Вид частного по правому вычитанию с учётом резонанса "
                    f"(множитель t^k при совпадении с корнем P): y_ч(t) = {answer['y_p']}"
                ),
                "data": {"y_p": answer["y_p"]},
            }
        )
        steps.append(
            {
                "step": 4,
                "title": "Найст констант по начальный условиям и ответ",
                "text": f"y(t) = y_о(t) + y_ч(t) = {answer['y']}",
                "data": {"y": answer["y"]},
            }
        )
    elif kind == "impulse":
        a = _coeffs(spec["a"], "a")
        gain = _sym(spec.get("gain", 1), "gain")
        g, imp_notes = _impulse(a, gain)
        answer["g"] = str(g)
        steps.append(
            {
                "step": 1,
                "title": "Весовая функция (М2/М3: вход δ(t−τ), вариация постоянной)",
                "text": imp_notes[0] if imp_notes else "g(t,τ) — реакция на δ-вход",
                "data": {"g": answer["g"]},
            }
        )
        steps.append(
            {
                "step": 2,
                "title": "Ответ",
                "text": f"система стационарна: g зависит только от t − τ. g(t,τ) = {answer['g']}",
                "data": {"g": answer["g"], "stationary": True},
            }
        )
        notes.extend(imp_notes)
    elif kind == "transfer":
        a = _coeffs(spec["a"], "a")
        b = _coeffs(spec["b"], "b") if spec.get("b") else None
        phi = _transfer(a, b)
        answer["phi"] = str(phi)
        steps.append(
            {
                "step": 1,
                "title": "Передаточная функция (М1)",
                "text": (
                    "Подставляем x(t) = e^{st}, y(t) = Φ(s)e^{st}: производные y^(i) дают s^i; "
                    f"e^{{st}} сокращается ⇒ Φ(s) = {answer['phi']}"
                ),
                "data": {"phi": answer["phi"]},
            }
        )
        if spec.get("freq"):
            freq = _freq(phi)
            answer["A"] = str(freq["A"])
            answer["phi_f"] = str(freq["phi"])
            steps.append(
                {
                    "step": 2,
                    "title": "Частотная характеристика (М8: s = iω)",
                    "text": f"Φ(iω) = {freq['F_iw']}; A(ω) = |Φ(iω)|, φ(ω) = arg Φ(iω)",
                    "data": {"F_iw": str(freq["F_iw"]), "A": answer["A"], "phi_f": answer["phi_f"]},
                }
            )
    elif kind == "freq":
        a = _coeffs(spec["a"], "a")
        b = _coeffs(spec["b"], "b") if spec.get("b") else None
        phi = _transfer(a, b)
        freq = _freq(phi)
        answer = {
            "phi": str(phi),
            "A": str(freq["A"]),
            "phi_f": str(freq["phi"]),
        }
        steps.append(
            {
                "step": 1,
                "title": "АЧХ и ФЧХ (М8)",
                "text": (
                    "s = iω; домножение на сопряжённое: A(ω) = ‖Φ(iω)‖, φ(ω) = arg Φ(iω). "
                    f"A(ω) = {answer['A']}; φ(ω) = {answer['phi_f']}"
                ),
                "data": answer,
            }
        )
    elif kind == "link":
        entry = link_info(str(spec.get("name", "")))
        for key, value in (spec.get("params") or {}).items():
            repl = _sym(value, f"params.{key}")
            for f in ("phi", "g", "A", "phi_f"):
                if f in entry:
                    entry = {**entry, f: sp.simplify(entry[f].subs(sp.Symbol(key), repl))}
        answer = {
            "name": spec["name"],
            "title": entry["title"],
            "law": entry["law"],
            "phi": str(entry["phi"]),
        }
        if "g" in entry:
            answer["g"] = str(entry["g"])
        if "A" in entry:
            answer["A"] = str(entry["A"])
            answer["phi_f"] = str(entry["phi_f"])
        steps.append(
            {
                "step": 1,
                "title": f"Стандартное звено: {entry['title']}",
                "text": (
                    f"закон «вход-выход»: {entry['law']}; подстановка М1 ⇒ "
                    f"Φ(s) = {answer['phi']}"
                ),
                "data": answer,
            }
        )
        if "g" in answer:
            steps.append(
                {
                    "step": 2,
                    "title": "Весовая функция",
                    "text": f"g(t,τ) = {answer['g']}",
                    "data": {"g": answer["g"]},
                }
            )
        if "A" in answer:
            steps.append(
                {
                    "step": len(steps) + 1,
                    "title": "Частотные характеристики (s = iω)",
                    "text": f"АЧХ: A(ω) = {answer['A']}; ФЧХ: φ(ω) = {answer['phi_f']}",
                    "data": {"A": answer["A"], "phi_f": answer["phi_f"]},
                }
            )
    elif kind == "links_catalog":
        rows = []
        for name, entry in LINKS.items():
            rows.append(
                {
                    "name": name,
                    "title": str(entry["title"]),
                    "law": str(entry["law"]),
                    "phi": str(entry["phi"]),
                    "g": str(entry["g"]) if "g" in entry else None,
                }
            )
        answer = {"links": rows}
        steps.append(
            {
                "step": 1,
                "title": "Каталог 11 стандартных звеньев (М1)",
                "text": "Для каждого звена: закон «вход-выход» и Φ(s) (подстановка x = e^{st}).",
                "data": rows,
            }
        )
    elif kind == "links_impulse":
        names = ["following", "extrapolator", "delay", "amplifier", "differentiator", "integrator"]
        rows = []
        for name in names:
            entry = link_info(name)
            rows.append({"name": name, "title": str(entry["title"]), "g": str(entry["g"])})
        answer = {"links": rows}
        steps.append(
            {
                "step": 1,
                "title": "Весовые функции 6 идеальных систем (М3: вход δ)",
                "text": "Все идеальные линейные системы стационарны: g зависит только от t − τ.",
                "data": rows,
            }
        )
    elif kind == "statespace":
        result, ss_notes = _statespace(spec)
        answer = {
            "F": result["F"].tolist(),
            "B": result["B"].tolist(),
            "C": result["C"].tolist(),
            "D": result["D"].tolist(),
            "W": str(result["W"][0, 0]),
        }
        if "x0_equations" in result:
            answer["x0_equations"] = [str(e) for e in result["x0_equations"]]
            if "x0" in result:
                answer["x0"] = {str(kk): str(vv) for kk, vv in result["x0"].items()}
        steps.append(
            {
                "step": 1,
                "title": "Пространство состояний (М11, М7)",
                "text": (
                    "X′ = F·X + B·u, y = C·X + D·u; W(s) = C·(sE−F)⁻¹·B + D "
                    f"= {answer['W']}"
                ),
                "data": {
                    "F": answer["F"],
                    "B": answer["B"],
                    "C": answer["C"],
                    "D": answer["D"],
                    "W": answer["W"],
                },
            }
        )
        if "x0_equations" in answer:
            steps.append(
                {
                    "step": 2,
                    "title": "СЛАУ для X(0) по начальный условиям",
                    "text": "C·X0 = y(0); C·F·X0 (+ C·B·u(0)) = y′(0).",
                    "data": answer["x0_equations"],
                }
            )
        notes.extend(ss_notes)
    else:
        raise ValidationError([{"path": "kind", "message": f"неизвестный вид: {kind}"}])
    return steps, answer, notes


def solve_lss(task_id: str, spec: dict[str, Any] | None = None) -> Report:
    """Solve one TASK-LSS-NN (or a custom system spec of the same shape).

    Example::

        solve_lss("TASK-LSS-08", {})  # built-in spec: y' + 5y = x
        solve_lss("custom:transfer", {"a": [1, 2, 1]})
    """
    spec = dict(spec or {})
    if task_id.startswith("custom:"):
        kind = spec.get("kind", task_id.split(":", 1)[1])
        if kind not in ("ode", "impulse", "transfer", "freq", "link", "statespace"):
            raise ValidationError([{"path": "task_id", "message": f"неизвестная группа: {kind}"}])
        spec.setdefault("kind", kind)
        task = None
    else:
        task = _TASKS.get(task_id)
        if task is None:
            from petrinet.errors import UnknownTaskError

            raise UnknownTaskError(task_id)
        merged = dict(task["spec"])
        merged.update(spec)
        spec = merged

    if spec.get("kind") == "parts":
        steps: list[dict[str, Any]] = []
        answer: dict[str, Any] = {}
        notes: list[str] = []
        for part in spec["parts"]:
            p_steps, p_answer, p_notes = _solve_part(dict(part))
            steps.extend(p_steps)
            answer[str(part.get("name", "part"))] = p_answer
            notes.extend(p_notes)
        for i, st in enumerate(steps, start=1):
            st["step"] = i
        given: dict[str, Any] = {"spec": spec}
        find = list(task["find"]) if task else []
    else:
        steps, answer, notes = _solve_part(spec)
        given = {"spec": spec}
        find = list(task["find"]) if task else [f"решение задачи вида {spec.get('kind')}"]
        if task:
            given["statement"] = task["statement"]
    if task and task.get("note"):
        notes.append(str(task["note"]))

    return Report(
        task_id=task_id,
        given=given,
        find=find,
        solution=steps,
        answer=answer,
        notes=notes,
    )


def _make_fn(task_id: str) -> SolveFn:
    def fn(spec: dict[str, Any]) -> Report:
        return solve_lss(task_id, spec)

    return fn


REGISTRY: list[TaskInfo] = [
    TaskInfo(
        task_id=task_id,
        group="LSS",
        title=t["title"],
        source=t["source"],
        type=t["type"],
        input_kind="lss",
        fn=_make_fn(task_id),
    )
    for task_id, t in _TASKS.items()
]
