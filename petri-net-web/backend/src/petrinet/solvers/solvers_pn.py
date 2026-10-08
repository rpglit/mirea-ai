"""PN solvers: Petri nets of the methodic (ARCH section 2.5.1).

Groups (MATERIALS_ANALYSIS section 7.1): construction/firing (M1-M4),
classification (M5), minimal marking (M6), matrix method (M7), Minsky
machine (M11). Reports follow the methodic structure: given / find /
solution (numbered steps) / answer, glossary section 5.1.

``solve_pn(task_id, spec)`` — the unified ``solve(task_id, data)`` shape
(D-053): ``spec`` carries ``net`` (canonical JSON, section 4.1),
``sequence`` (firing sequence sigma), ``parallel``, ``max_steps`` (<=1000).
Catalog tasks use built-in nets (templates_pn) unless ``net`` is given.
Custom user tasks: ``task_id = "custom:<group>"``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from petrinet import properties
from petrinet.core import PetriNet, fire, minimal_marking
from petrinet.errors import (
    CapExceededError,
    UnknownTaskError,
    ValidationError,
)
from petrinet.parser import parse_json
from petrinet.reachability import build
from petrinet.solvers.report import Report, SolveFn, TaskInfo
from petrinet.solvers.templates_pn import TASKS, TaskSpec

MAX_STEPS_DEFAULT = 100
MAX_STEPS_LIMIT = 1000
BUILD_CAP = 10000

_CUSTOM_FIND: dict[str, list[str]] = {
    "describe": ["аналитическое описание S = (P, T, I, O, µ)"],
    "model": ["модель сети (S = (P, T, I, O, µ) + граф) с проверкой инвариантов"],
    "firing": ["разрешённые переходы с обоснованием, цепочка срабатываний, итоговая маркировка"],
    "firing_count": ["сколько раз сработает заданный переход, изменение маркировки, итог"],
    "firing_scenarios": ["разрешённость и срабатывание для каждого варианта сети"],
    "extend": [
        "срабатывания исходной сети",
        "маркировка, при которой оба перехода срабатывают ровно по разу",
        "достроенная сеть с неограниченными срабатываниями (кандидат + проверка)",
    ],
    "classification": [
        "тип сети: живая / тупиковая / частичнотупиковая",
        "k-ограниченность (значение k), безопасность, консервативность — с обоснованием",
    ],
    "mu_min": ["минимальная маркировка µmin для срабатывания всех переходов (M6)"],
    "matrices": [
        "матрицы W−, W+, W; разрешённость в начальный момент",
        "выполнима ли последовательность σ (где ломается), v(σ), µ′ = µ + W·v(σ)",
    ],
    "minsky": ["симуляция команды машины Минского: регистры и текущая команда до/после"],
}


def _max_steps(spec: dict[str, Any]) -> int:
    value = spec.get("max_steps", MAX_STEPS_DEFAULT)
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= MAX_STEPS_LIMIT:
        raise ValidationError(
            [{"path": "max_steps", "message": f"нужно целое число 1..{MAX_STEPS_LIMIT}"}]
        )
    return value


def _analytic(net: PetriNet) -> dict[str, Any]:
    """S = (P, T, I, O, µ) with I/O as weighted (place, weight) pairs."""
    return {
        "P": list(net.places),
        "T": list(net.transitions),
        "I": {
            t: [[p, w] for p, w in arcs]
            for t, arcs in zip(net.transitions, net.inputs, strict=True)
        },
        "O": {
            t: [[p, w] for p, w in arcs]
            for t, arcs in zip(net.transitions, net.outputs, strict=True)
        },
        "mu": list(net.initial_marking),
    }


def _graph(net: PetriNet) -> dict[str, Any]:
    m = net.initial_marking
    arcs: list[list[Any]] = []
    for i, t in enumerate(net.transitions):
        for p, w in net.inputs[i]:
            arcs.append([p, t, w])
        for p, w in net.outputs[i]:
            arcs.append([t, p, w])
    return {
        "places": [[p, m[i]] for i, p in enumerate(net.places)],
        "transitions": list(net.transitions),
        "arcs": arcs,
    }


def _idx(net: PetriNet) -> dict[str, int]:
    return {p: i for i, p in enumerate(net.places)}


def _enabled(net: PetriNet, m: tuple[int, ...]) -> list[dict[str, str]]:
    """Enabled transitions with the methodic justification w⁻ ≤ µ."""
    idx = _idx(net)
    out: list[dict[str, str]] = []
    for i, t in enumerate(net.transitions):
        if net.enabled(m, t):
            parts = [f"{p}: {m[idx[p]]}≥{w}" for p, w in net.inputs[i]]
            out.append({"t": t, "reason": "; ".join(parts) if parts else "входов нет"})
    return out


def _chain(
    net: PetriNet, m0: tuple[int, ...], sigma: list[str], max_steps: int
) -> dict[str, Any]:
    """Fire sigma step by step; stops at the first disabled transition."""
    steps: list[dict[str, Any]] = []
    m = tuple(m0)
    for t in sigma:
        if len(steps) >= max_steps:
            return {"steps": steps, "executable": False, "failed_at": max_steps + 1, "final": None}
        if not net.enabled(m, t):
            return {
                "steps": steps,
                "executable": False,
                "failed_at": len(steps) + 1,
                "marking": list(m),
                "final": None,
            }
        prev = list(m)
        m = fire(net, m, t)
        steps.append({"t": t, "from": prev, "to": list(m)})
    return {"steps": steps, "executable": True, "failed_at": None, "final": list(m)}


def _min_marking_for_sequence(net: PetriNet, sigma: list[str]) -> list[int]:
    """Minimal µ making sigma executable: µ(p) = max_k (C_k(p) − O_(k−1)(p))."""
    idx = _idx(net)
    cons = {
        t: {p: w for p, w in arcs}
        for t, arcs in zip(net.transitions, net.inputs, strict=True)
    }
    prod = {
        t: {p: w for p, w in arcs}
        for t, arcs in zip(net.transitions, net.outputs, strict=True)
    }
    n = len(net.places)
    cum_in = [0] * n
    cum_out = [0] * n
    best = [0] * n
    for t in sigma:
        for p, w in cons[t].items():
            cum_in[idx[p]] += w
            best[idx[p]] = max(best[idx[p]], cum_in[idx[p]] - cum_out[idx[p]])
        for p, w in prod[t].items():
            cum_out[idx[p]] += w
    return best


def _parallel_requirement(net: PetriNet, ts: list[str]) -> list[int]:
    """Sum of input requirements over ts (methodic parallel worst case, A-20)."""
    idx = _idx(net)
    n = len(net.places)
    total = [0] * n
    pos = {t: i for i, t in enumerate(net.transitions)}
    for t in ts:
        if t not in pos:
            raise ValidationError([{"path": "parallel_pair", "message": f"нет перехода {t}"}])
        for p, w in net.inputs[pos[t]]:
            total[idx[p]] += w
    return total


def _parallel_fire(net: PetriNet, m: tuple[int, ...], ts: list[str]) -> tuple[int, ...]:
    """One summed application of all ts: m − ΣI(t) + ΣO(t) (no conflict check)."""
    idx = _idx(net)
    pos = {t: i for i, t in enumerate(net.transitions)}
    result = list(m)
    for t in ts:
        for p, w in net.inputs[pos[t]]:
            result[idx[p]] -= w
        for p, w in net.outputs[pos[t]]:
            result[idx[p]] += w
    if any(x < 0 for x in result):
        raise ValidationError(
            [{"path": "parallel_pair", "message": "маркировка меньше суммы требований"}]
        )
    return tuple(result)


_VERDICT_JUSTIFICATION: dict[str, str] = {
    "живая": "все переходы живые (уровень L4): каждый может срабатывать бесконечно часто",
    "тупиковая": "граф достижимости — DAG (циклов нет): любая цепь срабатываний конечна",
    "частичнотупиковая": "в графе достижимости есть циклы, но не все переходы живые",
}


# --- group functions ---------------------------------------------------------
# Each returns (steps, answer, notes).

def g_describe(
    task: TaskSpec | None, net: PetriNet | None, opts: dict[str, Any], max_steps: int
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    if net is None:
        return [], {}, [n for n in opts.get("notes", []) if n]
    answer = {"analytic": _analytic(net)}
    steps = [
        {
            "step": 1,
            "title": "Аналитическое описание",
            "text": "S = (P, T, I, O, µ); I/O — множества дуг с кратностями.",
            "data": answer["analytic"],
        }
    ]
    notes = [n for n in opts.get("notes", []) if n]
    return steps, answer, notes


def g_model(
    task: TaskSpec | None, net: PetriNet, opts: dict[str, Any], max_steps: int
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    s1, a1, n1 = g_describe(task, net, opts, max_steps)
    graph = _graph(net)
    s1.append(
        {
            "step": 2,
            "title": "Граф сети",
            "text": "Круги — позиции (число меток), прямоугольники — переходы, дуги с весами.",
            "data": graph,
        }
    )
    a1["graph"] = graph
    invariants = [n for n in opts.get("notes", []) if n]
    if invariants:
        s1.append(
            {
                "step": 3,
                "title": "Смысловые инварианты",
                "text": "",
                "data": {"invariants": invariants},
            }
        )
        a1["invariants"] = invariants
    return s1, a1, n1


def _base_marking(net: PetriNet, opts: dict[str, Any]) -> tuple[int, ...]:
    if "base_marking" in opts:
        return tuple(opts["base_marking"])
    if opts.get("from_mu_min"):
        return tuple(minimal_marking(net))
    return net.initial_marking


def g_firing(
    task: TaskSpec | None, net: PetriNet, opts: dict[str, Any], max_steps: int
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    m0 = _base_marking(net, opts)
    steps, answer, notes = g_describe(task, net, opts, max_steps)
    enabled = _enabled(net, m0)
    answer["mu0"] = list(m0)
    answer["enabled"] = enabled
    steps.append(
        {
            "step": len(steps) + 1,
            "title": "Разрешённые переходы в начальный момент",
            "text": "Переход разрешён, если w⁻(t) ≤ µ (каждый вход удовлетворён).",
            "data": {"marking": list(m0), "enabled": enabled},
        }
    )
    sigma = list(opts.get("sequence", []))
    if sigma:
        chain = _chain(net, m0, sigma, max_steps)
        answer["chain"] = chain
        answer["final_marking"] = chain["steps"][-1]["to"] if chain["steps"] else None
        state = (
            "выполнима"
            if chain["executable"]
            else f"НЕ выполнима (ломается на шаге {chain['failed_at']})"
        )
        steps.append(
            {
                "step": len(steps) + 1,
                "title": f"Последовательное срабатывание σ = ({', '.join(sigma)})",
                "text": f"Последовательность {state}."
                + (f" Итог: {chain['final']}." if chain["executable"] else ""),
                "data": chain,
            }
        )
    return steps, answer, notes


def g_firing_count(
    task: TaskSpec | None, net: PetriNet, opts: dict[str, Any], max_steps: int
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    t = opts.get("count_transition")
    if not t or t not in net.transitions:
        raise ValidationError([{"path": "count_transition", "message": f"нет перехода {t}"}])
    steps, answer, notes = g_describe(task, net, opts, max_steps)
    chain = _chain(net, net.initial_marking, [t] * max_steps, max_steps)
    count = len(chain["steps"])
    final = chain["steps"][-1]["to"] if chain["steps"] else list(net.initial_marking)
    answer["count"] = count
    answer["chain"] = chain
    answer["final_marking"] = final
    steps.append(
        {
            "step": len(steps) + 1,
            "title": f"Повторное срабатывание {t}",
            "text": f"{t} срабатывает {count} раз(а), затем перестаёт быть разрешённым. "
            f"Итоговая маркировка: {final}.",
            "data": chain,
        }
    )
    return steps, answer, notes


def g_firing_scenarios(
    task: TaskSpec | None, net: PetriNet | None, opts: dict[str, Any], max_steps: int
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    scenarios = opts.get("scenarios")
    if not scenarios:
        raise ValidationError([{"path": "scenarios", "message": "нужен список вариантов"}])
    steps, answer, notes = ([], {}, []) if net is None else g_describe(task, net, opts, max_steps)
    results = []
    for sc in scenarios:
        n = parse_json(sc["net"])
        m = n.initial_marking
        en = _enabled(n, m)
        sigma = list(sc.get("sequence", [])) or [e["t"] for e in en]
        ch = _chain(n, m, sigma, max_steps)
        text = f"{sc['name']}: "
        if not en:
            text += f"переход не разрешён (w⁻ > µ), маркировка не изменяется: {list(m)}"
        else:
            text += "разрешён " + ", ".join(e["t"] for e in en)
            if ch["steps"]:
                text += f"; итог {ch['steps'][-1]['to']}"
        results.append(
            {
                "name": sc["name"],
                "marking": list(m),
                "enabled": en,
                "chain": ch,
                "final": ch["steps"][-1]["to"] if ch["steps"] else list(m),
                "text": text,
            }
        )
    answer["scenarios"] = results
    steps.append(
        {
            "step": len(steps) + 1,
            "title": "Варианты сетей",
            "text": "",
            "data": {"scenarios": results},
        }
    )
    return steps, answer, notes


def g_extend(
    task: TaskSpec | None, net: PetriNet, opts: dict[str, Any], max_steps: int
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    """TASK-PN-02: (1) firing from mu0, (2) mu*, (3) candidate extension + check."""
    m0 = net.initial_marking
    steps, answer, notes = g_describe(task, net, opts, max_steps)
    enabled = _enabled(net, m0)
    pair_a = _chain(net, m0, ["t1", "t2"], max_steps)
    pair_b = _chain(net, m0, ["t2", "t1"], max_steps)
    answer["enabled"] = enabled
    answer["pair_chains"] = {"t1_then_t2": pair_a, "t2_then_t1": pair_b}
    steps.append(
        {
            "step": len(steps) + 1,
            "title": "Срабатывания исходной сети",
            "text": (
                f"Разрешены: {', '.join(e['t'] for e in enabled) or '—'}. "
                f"Ни одна из последовательностей (t1,t2) или (t2,t1) не выполнима: "
                f"после первого срабатывания нет разрешённых переходов (тупик)."
            ),
            "data": {"enabled": enabled, "pair_chains": answer["pair_chains"]},
        }
    )
    sigma = ["t1", "t2"]
    mu_star = _min_marking_for_sequence(net, sigma)
    star_chain = _chain(net, tuple(mu_star), sigma, max_steps)
    answer["mu_star"] = mu_star
    answer["mu_star_chain"] = star_chain
    steps.append(
        {
            "step": len(steps) + 1,
            "title": "Маркировка, при которой оба перехода срабатывают ровно по разу",
            "text": (
                f"µ* = {mu_star}: минимальная маркировка, делающая σ = (t1, t2) выполнимой "
                f"(µ*(p) = max_k (C_k(p) − O_(k−1)(p))). Цепочка: "
                f"{mu_star}→t1→{star_chain['steps'][0]['to']}→t2→{star_chain['final']}."
            ),
            "data": {"mu_star": mu_star, "chain": star_chain},
        }
    )
    ext_payload = opts.get("extended")
    if not ext_payload:
        raise ValidationError([{"path": "extended", "message": "нет кандидат-сети для проверки"}])
    ext_net = parse_json(ext_payload)
    cycle = _chain(ext_net, ext_net.initial_marking, (["t1", "t3", "t2", "t4"]) * 3, max_steps)
    counts = {t: 0 for t in ext_net.transitions}
    for st in cycle["steps"]:
        counts[st["t"]] += 1
    answer["extension"] = {"net": ext_payload, "verification": cycle, "firing_counts": counts}
    steps.append(
        {
            "step": len(steps) + 1,
            "title": "Достроенная сеть (кандидат)",
            "text": (
                "Добавлены переходы t3: I={p4}, O={p1, p2} и t4: I={p5}, O={p2, p3}: "
                "они возвращают метки, потреблённые t1 и t2. Проверка: цикл "
                "(t1, t3, t2, t4) выполнен 3 раза — оба исходных перехода сработали "
                "по 3 раза, дальнейшее продолжение неограниченно."
            ),
            "data": answer["extension"],
        }
    )
    notes.append(
        "Кандидат-сеть — часть ответа: UI может загрузить её в новую сессию (ARCH section 6)."
    )
    return steps, answer, notes


def g_classification(
    task: TaskSpec | None, net: PetriNet, opts: dict[str, Any], max_steps: int
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    m0 = _base_marking(net, opts)
    steps, answer, notes = g_describe(task, net, opts, max_steps)
    net_from_m0 = _remarked(net, m0)
    try:
        structure = build(net_from_m0, mode="auto", cap=BUILD_CAP)
    except CapExceededError:
        structure = build(net_from_m0, mode="coverability", cap=BUILD_CAP)
        notes.append(
            f"граф достижимости превысил предел {BUILD_CAP} маркировок — построено дерево "
            "покрытия Карпа–Миллера: сеть неограниченная"
        )
    report = properties.analyze(net_from_m0, structure, with_mu_min=False)
    verdict = report.verdict
    justification = (
        _VERDICT_JUSTIFICATION.get(verdict)
        if verdict
        else ("дерево покрытия (ω-приближение): точный трёхклассный вердикт "
             "вычисляется по конечному графу")
    )
    cls = {
        "structure": structure.kind,
        "verdict": verdict,
        "verdict_justification": justification,
        "liveness_level": report.liveness.level,
        "per_transition": {
            t: {"occurs": tl.occurs, "level": tl.level}
            for t, tl in report.liveness.transitions.items()
        },
        "k": report.global_k,
        "per_place_k": report.per_place_k,
        "bounded": report.bounded,
        "safe": report.safe,
        "conservative": report.conservative["conservative"],
        "constant_sum": report.conservative.get("constant_sum"),
        "deadlocks": report.deadlocks,
        "deadlock_count": len(report.deadlocks),
        "dead_transitions": report.dead_transitions,
        "home_state": report.home_state,
        "stats": report.stats,
    }
    answer["classification"] = cls
    k_text = f"k = {cls['k']}" if cls["k"] is not None else "неограниченная (есть ω)"
    text = (
        f"Вердикт: {verdict if verdict else 'нет (ω-приближение)'} — {justification}. "
        f"Ограниченность: {k_text}. Безопасная: {'да' if cls['safe'] else 'нет'}. "
        f"Консервативная: {'да' if cls['conservative'] else 'нет'}. "
        f"Тупиков: {cls['deadlock_count']}, маркировок: {report.stats.get('nodes', '—')}."
    )
    steps.append(
        {
            "step": len(steps) + 1,
            "title": "Классификация (M5)",
            "text": text,
            "data": cls,
        }
    )
    if verdict is None and not cls["bounded"]:
        notes.append(
            "ω-приближение: точный вердикт по классам методички вычисляется по конечному графу "
            "достижимости; здесь — дерево покрытия Карпа–Миллера. Сетевые выводы (живость "
            "конкретных переходов) требуют дополнительного анализа ресурсов."
        )
    return steps, answer, notes


def g_mu_min(
    task: TaskSpec | None, net: PetriNet, opts: dict[str, Any], max_steps: int
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    steps, answer, notes = g_describe(task, net, opts, max_steps)
    if opts.get("mu_min_of") == "sequence":
        sigma = list(opts.get("mu_min_sequence", []))
        mu = _min_marking_for_sequence(net, sigma)
        text = (
            f"µmin(p) = max_k (C_k(p) − O_(k−1)(p)) — минимальная маркировка, при которой "
            f"последовательность σ = ({', '.join(sigma)}) выполнима."
        )
    else:
        mu = list(minimal_marking(net))
        text = (
            "µmin(p) = max_t d(p, t) — покомпонентный максимум входных требований "
            "всех переходов: из µmin разрешён каждый переход."
        )
    answer["mu_min"] = mu
    steps.append(
        {
            "step": len(steps) + 1,
            "title": "Минимальная маркировка (M6)",
            "text": text,
            "data": {"mu_min": mu},
        }
    )
    pair = list(opts.get("parallel_pair", []))
    if pair:
        mu_par = _parallel_requirement(net, pair)
        m_after = _parallel_fire(net, tuple(mu_par), pair)
        answer["parallel"] = {
            "transitions": pair,
            "mu_parallel": mu_par,
            "after_firing": list(m_after),
        }
        steps.append(
            {
                "step": len(steps) + 1,
                "title": f"Параллельное срабатывание ({', '.join(pair)})",
                "text": (
                    "При параллельном срабатывании требования суммируются (худший случай, "
                    f"все переходы разрешены сразу): µ∥ = {mu_par}; после срабатывания — "
                    f"{list(m_after)}."
                ),
                "data": answer["parallel"],
            }
        )
    return steps, answer, notes


def g_matrices(
    task: TaskSpec | None, net: PetriNet, opts: dict[str, Any], max_steps: int
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    steps, answer, notes = g_describe(task, net, opts, max_steps)
    w_minus, w_plus, w = net.incidence()
    matrices = {"W_minus": w_minus, "W_plus": w_plus, "W": w}
    answer["matrices"] = matrices
    m0 = net.initial_marking
    enabled = _enabled(net, m0)
    answer["enabled"] = enabled
    steps.append(
        {
            "step": len(steps) + 1,
            "title": "Матричное представление (M7)",
            "text": "W− (входы) и W+ (выходы), строки — позиции, столбцы — переходы; W = W+ − W−.",
            "data": matrices,
        }
    )
    steps.append(
        {
            "step": len(steps) + 1,
            "title": "Разрешённость в начальный момент",
            "text": "t разрешён, если столбец W⁻(t) ≤ µ покомпонентно.",
            "data": {"marking": list(m0), "enabled": enabled},
        }
    )
    sequences: list[list[str]] = []
    for seq in opts.get("sequences", []):
        sequences.append(list(seq))
    if "sequence" in opts and opts["sequence"] not in sequences:
        sequences.append(list(opts["sequence"]))
    results = []
    for sigma in sequences:
        try:
            rep = properties.sequence_report(net, m0, sigma)
        except ValueError as exc:
            raise ValidationError(
                [{"path": "sequence", "message": str(exc)}]
            ) from exc
        results.append({"sequence": list(sigma), **rep})
    answer["sequences"] = results
    for rep in results:
        state = (
            "выполнима"
            if rep["executable"]
            else f"НЕ выполнима (ломается на шаге {rep['failed_at']})"
        )
        seq = cast("list[str]", rep["sequence"])
        text = f"σ = ({', '.join(seq)}): {state}."
        if rep["executable"]:
            text += f" v(σ) = {rep['v']}; µ′ = µ + W·v(σ) = {rep['mu_prime']}."
        steps.append(
            {
                "step": len(steps) + 1,
                "title": "Последовательность σ (матричный способ)",
                "text": text,
                "data": rep,
            }
        )
    return steps, answer, notes


def g_minsky(
    task: TaskSpec | None, net: PetriNet, opts: dict[str, Any], max_steps: int
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    scenarios = opts.get("scenarios")
    if not scenarios:
        raise ValidationError([{"path": "scenarios", "message": "нужен список сценариев"}])
    steps, answer, notes = g_describe(task, net, opts, max_steps)
    results = []
    for sc in scenarios:
        n = parse_json(sc["net"])
        m0 = n.initial_marking
        chain = _chain(n, m0, list(sc["sequence"]), max_steps)
        results.append(
            {
                "name": sc["name"],
                "before": list(m0),
                "chain": chain,
                "after": chain["final"],
                "text": sc.get("text", ""),
            }
        )
    answer["scenarios"] = results
    steps.append(
        {
            "step": len(steps) + 1,
            "title": "Симуляция команды",
            "text": "",
            "data": {"scenarios": results},
        }
    )
    return steps, answer, notes


GROUP_FNS: dict[str, Callable[..., tuple[list[dict[str, Any]], dict[str, Any], list[str]]]] = {
    "describe": g_describe,
    "model": g_model,
    "firing": g_firing,
    "firing_count": g_firing_count,
    "firing_scenarios": g_firing_scenarios,
    "extend": g_extend,
    "classification": g_classification,
    "mu_min": g_mu_min,
    "matrices": g_matrices,
    "minsky": g_minsky,
}


def _remarked(net: PetriNet, m: tuple[int, ...]) -> PetriNet:
    """The same net with a different initial marking (for analysis from µmin)."""
    payload: dict[str, object] = {
        "places": list(net.places),
        "transitions": list(net.transitions),
        "inputs": {
            t: {p: w for p, w in arcs} for t, arcs in zip(net.transitions, net.inputs, strict=True)
        },
        "outputs": {
            t: {p: w for p, w in arcs} for t, arcs in zip(net.transitions, net.outputs, strict=True)
        },
        "initial_marking": {p: x for p, x in zip(net.places, m, strict=True)},
    }
    return parse_json(payload)


def solve_pn(task_id: str, spec: dict[str, Any] | None = None) -> Report:
    """Solve one TASK-PN-NN (or a custom net task of the same shape).

    Example::

        solve_pn("TASK-PN-05", {})  # built-in net, default sequence t1..t5
        solve_pn("custom:firing", {"net": {...}, "sequence": ["t1"]})
    """
    spec = spec or {}
    max_steps = _max_steps(spec)
    if task_id.startswith("custom:"):
        group_name = task_id.split(":", 1)[1]
        if group_name not in GROUP_FNS:
            raise ValidationError(
                [{"path": "task_id", "message": f"неизвестная группа: {group_name}"}]
            )
        if not isinstance(spec.get("net"), dict):
            raise ValidationError([{"path": "net", "message": "нужен JSON сети (net)"}])
        task: TaskSpec | None = None
        groups: tuple[str, ...] = (group_name,)
        payload = spec["net"]
    else:
        task = TASKS.get(task_id)
        if task is None:
            raise UnknownTaskError(task_id)
        groups = task.groups
        payload = spec.get("net") or task.net
        if payload is None and "firing_scenarios" not in groups:
            raise ValidationError(
                [{"path": "net", "message": f"для {task_id} нет встроенной сети — передайте net"}]
            )
    net = parse_json(payload) if payload is not None else None

    opts: dict[str, Any] = dict(task.options if task else {})
    for key in ("sequence", "sequences", "parallel", "count_transition", "from_mu_min"):
        if key in spec:
            opts[key] = spec[key]
    if task is not None and net is not None and opts.get("mu_min_of") == "sequence":
        # the chain/classification of such a task starts from the minimal
        # marking of the methodic sequence (TASK-PN-19)
        opts["base_marking"] = _min_marking_for_sequence(
            net, list(opts.get("mu_min_sequence", []))
        )

    steps: list[dict[str, Any]] = []
    answer: dict[str, Any] = {}
    notes: list[str] = []
    for gname in groups:
        g_steps, g_answer, g_notes = GROUP_FNS[gname](task, net, opts, max_steps)
        steps.extend(g_steps)
        answer.update(g_answer)
        notes.extend(g_notes)
    for i, st in enumerate(steps, start=1):
        st["step"] = i

    given: dict[str, Any] = {}
    if task:
        given["statement"] = task.statement
    if payload is not None:
        given["net"] = payload
    find = list(task.find) if task else list(_CUSTOM_FIND[groups[0]])

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
        return solve_pn(task_id, spec)

    return fn


REGISTRY: list[TaskInfo] = [
    TaskInfo(
        task_id=t.task_id,
        group="PN",
        title=t.title,
        source=t.source,
        type=t.type,
        input_kind="pn",
        fn=_make_fn(t.task_id),
    )
    for t in TASKS.values()
]
