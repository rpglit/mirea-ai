// Properties panel: Russian labels for the analysis report.
"use strict";

window.PropertiesPanel = (function () {
  function yesNo(flag) {
    return flag ? "да" : "нет";
  }

  function row(label, valueHtml) {
    return (
      "<dt>" + window.Ui.escapeHtml(label) + "</dt>" +
      "<dd>" + valueHtml + "</dd>"
    );
  }

  function compactTuple(marking) {
    return marking
      .map(function (v) {
        return v === null || v === undefined ? "ω" : String(v);
      })
      .join(",");
  }

  function setCaveatVisible(visible) {
    const caveat = document.getElementById("props-caveat");
    if (caveat) caveat.classList.toggle("hidden", !visible);
  }

  function render(report) {
    const dl = document.getElementById("props");
    if (!dl || !report) return;

    const parts = [];
    const stats = report.stats || {};
    const nodeCount = stats.node_count !== undefined ? stats.node_count : stats.nodes;
    const edgeCount = stats.edge_count !== undefined ? stats.edge_count : stats.edges;

    parts.push(row("Маркировок (узлов)", nodeCount === undefined ? "—" : String(nodeCount)));
    parts.push(row("Рёбер", edgeCount === undefined ? "—" : String(edgeCount)));
    parts.push(row("Ограничена (bounded)", yesNo(Boolean(report.bounded))));
    parts.push(
      row(
        "Глобальная k",
        report.global_k === null || report.global_k === undefined
          ? "ω (неограниченна)"
          : String(report.global_k)
      )
    );
    parts.push(row("Безопасна (safe)", yesNo(Boolean(report.safe))));

    const perPlace = report.per_place_k || {};
    const placeKeys = Object.keys(perPlace);
    parts.push(
      row(
        "Ограниченность по позициям",
        placeKeys.length
          ? placeKeys
              .map(function (p) {
                const k = perPlace[p];
                return (
                  window.Ui.escapeHtml(p) +
                  (k === null || k === undefined ? ": ω" : " ≤ " + String(k))
                );
              })
              .join(", ")
          : "—"
      )
    );

    const liveness = report.liveness || {};
    parts.push(
      row(
        "Живость (уровень сети)",
        liveness.level !== undefined && liveness.level !== null
          ? window.Ui.escapeHtml(liveness.level)
          : "—"
      )
    );

    const tLive = liveness.transitions || {};
    const tKeys = Object.keys(tLive);
    parts.push(
      row(
        "Живость по переходам",
        tKeys.length
          ? tKeys
              .map(function (t) {
                const info = tLive[t] || {};
                const occurs = info.occurs ? "возникает" : "не возникает";
                const level =
                  info.level !== undefined && info.level !== null
                    ? window.Ui.escapeHtml(info.level)
                    : "—";
                return window.Ui.escapeHtml(t) + ": " + level + " (" + occurs + ")";
              })
              .join(", ")
          : "—"
      )
    );

    const deadlocks = Array.isArray(report.deadlocks) ? report.deadlocks : [];
    parts.push(
      "<dt>" + window.Ui.escapeHtml("Тупики (deadlocks)") + "</dt>" +
      "<dd>" + String(deadlocks.length) + "</dd>"
    );
    if (deadlocks.length) {
      parts.push(
        '<dd style="grid-column: 2"><ul style="max-height: 160px; overflow: auto; margin: 0; padding-left: 18px;">' +
          deadlocks
            .map(function (m) {
              return "<li>" + window.Ui.escapeHtml(compactTuple(m)) + "</li>";
            })
            .join("") +
          "</ul></dd>"
      );
    } else {
      parts.push('<dd style="grid-column: 2">нет</dd>');
    }

    const deadTransitions = Array.isArray(report.dead_transitions) ? report.dead_transitions : [];
    parts.push(
      row(
        "Мёртвые переходы",
        deadTransitions.length
          ? deadTransitions.map(function (t) {
              return window.Ui.escapeHtml(t);
            }).join(", ")
          : "нет"
      )
    );

    parts.push(row("Обратимость (home state)", yesNo(Boolean(report.home_state))));
    parts.push(row("Без тупиков (deadlock-free)", yesNo(Boolean(report.deadlock_free))));

    dl.innerHTML = parts.join("");
    setCaveatVisible(report.approximation === "omega");
  }

  return {
    render: render,
    setCaveatVisible: setCaveatVisible,
  };
})();
