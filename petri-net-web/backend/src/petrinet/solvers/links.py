"""The 11 standard links (MATERIALS_ANALYSIS section 3.2, TASK-LSS-13).

Each entry: title, the input-output law, transfer function phi(s), weight
function g(t, tau) (sympy, distributions where the methodic uses them) and
frequency characteristics for the dynamic links. Symbols: T, k, xi, a, alpha.
"""

from __future__ import annotations

from typing import Any

import sympy as sp

s = sp.symbols("s")
t = sp.symbols("t", nonnegative=True)
tau = sp.symbols("tau", nonnegative=True)
omega = sp.symbols("omega", positive=True)
T = sp.symbols("T", positive=True)
k = sp.symbols("k")
xi = sp.symbols("xi", positive=True)
a = sp.symbols("a", positive=True)

delta = lambda x: sp.DiracDelta(x)  # noqa: E731
step = lambda x: sp.Heaviside(x)  # noqa: E731

LINKS: dict[str, dict[str, Any]] = {
    "following": {
        "title": "идеальная следящая система",
        "law": "y(t) = x(t)",
        "phi": sp.Integer(1),
        "g": delta(t - tau),
        "g_note": "выход мгновенно равен входу",
    },
    "extrapolator": {
        "title": "идеальный экстраполятор",
        "law": f"y(t) = x(t + {a})",
        "phi": sp.exp(a * s),
        "g": delta(t - (tau - a)),
        "g_note": "выход в момент t равен входу в момент t + a (прогноз)",
    },
    "delay": {
        "title": "идеальное запаздывающее звено",
        "law": f"y(t) = x(t - {a})",
        "phi": sp.exp(-a * s),
        "g": delta(t - (tau + a)),
        "g_note": "выход повторяет вход с запаздыванием a",
    },
    "amplifier": {
        "title": "безынерционный усилитель",
        "law": "y(t) = k·x(t)",
        "phi": k,
        "g": k * delta(t - tau),
    },
    "differentiator": {
        "title": "идеальное дифференцирующее звено",
        "law": "y(t) = x′(t)",
        "phi": s,
        "g": delta(t - tau).diff(t),
        "freq_note": "при s = iω: |Φ| = ω, φ(ω) = π/2 (опережение на π/2)",
    },
    "integrator": {
        "title": "идеальное интегрирующее звено",
        "law": "y(t) = ∫x(β)dβ",
        "phi": 1 / s,
        "g": step(t - tau),
        "g_note": "единичная ступень: 0 при t < τ, 1 при t ≥ τ",
        "freq_note": "при s = iω: |Φ| = 1/ω, φ(ω) = −π/2 (отставание на π/2)",
    },
    "forcing1": {
        "title": "форсирующее звено 1-го порядка",
        "law": "y(t) = k·(T·x′(t) + x(t))",
        "phi": k * (T * s + 1),
        "g": k * (T * delta(t - tau).diff(t) + delta(t - tau)),
    },
    "forcing2": {
        "title": "форсирующее звено 2-го порядка",
        "law": "y(t) = k·(T²·x″(t) + 2α·T·x′(t) + x(t))",
        "phi": k * (T**2 * s**2 + 2 * a * T * s + 1),
        "g": k
        * (T**2 * delta(t - tau).diff(t, 2) + 2 * a * T * delta(t - tau).diff(t) + delta(t - tau)),
    },
    "aperiodic": {
        "title": "апериодическое звено",
        "law": "T·y′(t) + y(t) = k·x(t)",
        "phi": k / (T * s + 1),
        "g": (k / T) * sp.exp(-(t - tau) / T),
        "A": k / sp.sqrt(1 + T**2 * omega**2),
        "phi_f": -sp.atan(T * omega),
    },
    "harmonic": {
        "title": "гармонические колебания (частный случай апериодического, s = iω)",
        "law": "T·y′(t) + y(t) = k·x(t)",
        "phi": k / (T * s + 1),
        "g": (k / T) * sp.exp(-(t - tau) / T),
        "A": k / sp.sqrt(1 + T**2 * omega**2),
        "phi_f": -sp.atan(T * omega),
        "note": "Φ(iω) = k(1 − iωT)/(1 + ω²T²)",
    },
    "oscillatory": {
        "title": "колебательное звено",
        "law": "T²·y″(t) + 2Tξ·y′(t) + y(t) = k·x(t), T > 0, 0 < ξ < 1",
        "phi": k / (T**2 * s**2 + 2 * T * xi * s + 1),
        "g": k / (T * sp.sqrt(1 - xi**2))
        * sp.exp(-xi * t / T)
        * sp.sin(sp.sqrt(1 - xi**2) * t / T),
        "g_note": "гасящие колебания с частотой √(1−ξ²)/T (ср. TASK-LSS-20)",
        "A": k
        / sp.sqrt((1 - T**2 * omega**2) ** 2 + 4 * T**2 * xi**2 * omega**2),
        "phi_f": -sp.atan(2 * T * xi * omega / (1 - T**2 * omega**2)),
    },
}


def link_info(name: str) -> dict[str, Any]:
    """Return the catalog entry of one standard link."""
    entry = LINKS.get(name)
    if entry is None:
        from petrinet.errors import ValidationError

        raise ValidationError(
            [
                {
                    "path": "name",
                    "message": f"неизвестное звено: {name} (каталог: {', '.join(LINKS)})",
                }
            ]
        )
    return dict(entry)
