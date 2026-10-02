// App orchestrator: tabs, intake -> parse -> graph -> properties, panel wiring.
"use strict";

window.App = (function () {
  const S = {
    sessionId: null,
    name: "",
    places: [],
    transitions: [],
    inputs: {},
    outputs: {},
    marking: null,
    history: [],
    structure: null,
    structureKind: null,
    report: null,
  };

  let graphClickWired = false;

  function el(id) {
    return document.getElementById(id);
  }

  function splitCsv(value) {
    return String(value === null || value === undefined ? "" : value)
      .split(",")
      .map(function (part) {
        return part.trim();
      })
      .filter(function (part) {
        return part.length > 0;
      });
  }

  function toInt(value) {
    const v = parseInt(value, 10);
    return Number.isFinite(v) ? v : null;
  }

  function setBadge(text, visible) {
    const badge = el("session-badge");
    if (!badge) return;
    badge.textContent = text;
    badge.classList.toggle("hidden", !visible);
  }

  function setAnalysisVisible(visible) {
    const analysis = el("analysis");
    if (analysis) analysis.classList.toggle("hidden", !visible);
  }

  function setGraphStats(graph) {
    const stats = el("graph-stats");
    if (stats) stats.textContent = "узлов: " + graph.node_count + ", рёбер: " + graph.edge_count;
  }

  function clearGraphCanvas() {
    const registry = window.Registry;
    const cy = registry && registry.graph;
    if (cy && typeof cy.destroy === "function") {
      try {
        cy.destroy();
      } catch (err) {
        return;
      }
    }
    if (registry) registry.graph = null;
  }

  function wireGraphClick() {
    if (graphClickWired) return;
    graphClickWired = true;
    GraphCanvas.onNodeClick(gotoNode);
  }

  function deadlocksFor(report) {
    const kind = (report && report.kind) || S.structureKind;
    if (kind === "coverability") return null;
    return report ? report.deadlocks : null;
  }

  function refreshStateView(st) {
    S.marking = st.current_marking;
    S.history = st.history;
    StepPanel.render(st.active_transitions, st.history);
    StepPanel.setFullHistory(st.history);
    NetCanvas.setMarking(st.current_marking, S.places);
  }

  async function buildGraphAndProps() {
    if (!S.sessionId) return;
    Ui.setStatus("Построение графа достижимости…");
    clearGraphCanvas();
    const statsEl = el("graph-stats");
    if (statsEl) statsEl.textContent = "";
    const modeEl = el("graph-mode");
    const mode = modeEl && modeEl.value ? modeEl.value : "auto";
    let graph;
    try {
      graph = await Api.buildGraph(S.sessionId, mode);
    } catch (err) {
      if (err && err.code === "cap_exceeded") {
        Ui.toast("Превышен лимит узлов. Выберите режим «Покрываемость (Кэрп–Миллер)» и повторите.", true);
        Ui.setStatus("Остановлено: превышен лимит.");
      } else {
        Ui.toast(err.message, true);
        Ui.setStatus("Остановлено: ошибка.");
      }
      return;
    }
    S.structure = graph.structure;
    S.structureKind = graph.kind;
    setGraphStats(graph);
    Ui.setStatus("Вычисление свойств…");
    let report;
    try {
      report = await Api.analyzeProperties(S.sessionId, null);
    } catch (err) {
      Ui.toast(err.message, true);
      Ui.setStatus("Остановлено: ошибка.");
      return;
    }
    S.report = report;
    GraphCanvas.render(graph.structure, deadlocksFor(report));
    wireGraphClick();
    PropertiesPanel.render(report);
    try {
      const st = await Api.getState(S.sessionId);
      refreshStateView(st);
    } catch (err) {
      Ui.toast(err.message, true);
      return;
    }
    Ui.setStatus("Готово.");
  }

  async function gotoNode(nodeId, markingArray) {
    if (!S.sessionId) return;
    if (!Array.isArray(markingArray)) return;
    if (JSON.stringify(markingArray) === JSON.stringify(S.marking)) return;
    try {
      await Api.gotoMarking(S.sessionId, markingArray);
      const st = await Api.getState(S.sessionId);
      refreshStateView(st);
    } catch (err) {
      Ui.toast(err.message, true);
    }
  }

  async function stepAction(action, transition) {
    if (!S.sessionId) return;
    try {
      await Api.fireAction(S.sessionId, action, transition);
      const st = await Api.getState(S.sessionId);
      refreshStateView(st);
    } catch (err) {
      Ui.toast(err.message, true);
    }
  }

  async function run(format, payloadBuilder) {
    let payload;
    try {
      payload = payloadBuilder();
    } catch (err) {
      Ui.toast(err.message, true);
      return;
    }
    if (payload === null || payload === undefined) return;
    Ui.setStatus("Разбор описания…");
    let resp;
    try {
      resp = await Api.parseSession(format, payload);
    } catch (err) {
      Ui.toast(err.message, true);
      Ui.setStatus("Остановлено: ошибка.");
      return;
    }
    S.sessionId = resp.session_id;
    S.name = resp.name || "";
    S.places = resp.places || [];
    S.transitions = resp.transitions || [];
    S.inputs = resp.inputs || {};
    S.outputs = resp.outputs || {};
    S.marking = resp.initial_marking || null;
    S.history = [];
    S.structure = null;
    S.structureKind = null;
    S.report = null;
    setBadge(S.name || S.sessionId, true);
    setAnalysisVisible(true);
    SessionsPanel.setCurrent(S.sessionId);
    SessionsPanel.refresh();
    NetCanvas.render({
      places: S.places,
      transitions: S.transitions,
      inputs: S.inputs,
      outputs: S.outputs,
      marking: S.marking,
    });
    StepPanel.onAction(stepAction);
    StepPanel.setFullHistory([]);
    await buildGraphAndProps();
  }

  function buildTextPayload() {
    return el("input-text").value;
  }

  function buildJsonPayload() {
    const raw = el("input-json").value.trim();
    if (!raw) {
      Ui.toast("Введите JSON-описание", true);
      return null;
    }
    try {
      return JSON.parse(raw);
    } catch (err) {
      Ui.toast("Некорректный JSON: " + err.message, true);
      return null;
    }
  }

  function buildFormPayload() {
    const places = splitCsv(el("form-places").value);
    const transitions = splitCsv(el("form-transitions").value);
    const arcs = [];
    document.querySelectorAll("#arcs-list .arc-row").forEach(function (row) {
      const dir = row.querySelector(".arc-direction");
      const src = row.querySelector(".arc-source");
      const tgt = row.querySelector(".arc-target");
      const weightInput = row.querySelector(".arc-weight");
      const source = src ? src.value.trim() : "";
      const target = tgt ? tgt.value.trim() : "";
      if (!source || !target) return;
      const weight = toInt(weightInput ? weightInput.value : "1");
      arcs.push({
        source: source,
        target: target,
        weight: weight !== null && weight >= 1 ? weight : 1,
        direction: dir && dir.value === "output" ? "output" : "input",
      });
    });
    const markingParts = splitCsv(el("form-marking").value);
    if (places.length === 0) {
      Ui.toast("Укажите хотя бы одну позицию", true);
      return null;
    }
    if (transitions.length === 0) {
      Ui.toast("Укажите хотя бы один переход", true);
      return null;
    }
    if (markingParts.length !== places.length) {
      Ui.toast("Начальная маркировка должна содержать " + places.length + " значений", true);
      return null;
    }
    const initialMarking = {};
    for (let i = 0; i < places.length; i += 1) {
      const value = toInt(markingParts[i]);
      if (value === null || value < 0) {
        Ui.toast("Значения начальной маркировки должны быть целыми числами ≥ 0", true);
        return null;
      }
      initialMarking[places[i]] = value;
    }
    return {
      places: places,
      transitions: transitions,
      arcs: arcs,
      initial_marking: initialMarking,
    };
  }

  function createArcRow() {
    const row = document.createElement("div");
    row.className = "arc-row";

    const dir = document.createElement("select");
    dir.className = "arc-direction";
    const optIn = document.createElement("option");
    optIn.value = "input";
    optIn.textContent = "вход (позиция → переход)";
    const optOut = document.createElement("option");
    optOut.value = "output";
    optOut.textContent = "выход (переход → позиция)";
    dir.appendChild(optIn);
    dir.appendChild(optOut);

    const src = document.createElement("input");
    src.className = "arc-source";
    src.placeholder = "p1";

    const tgt = document.createElement("input");
    tgt.className = "arc-target";
    tgt.placeholder = "t1";

    const weight = document.createElement("input");
    weight.className = "arc-weight";
    weight.type = "number";
    weight.min = "1";
    weight.value = "1";

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "arc-remove";
    removeBtn.setAttribute("title", "Удалить дугу");
    removeBtn.textContent = "✕";

    row.appendChild(dir);
    row.appendChild(src);
    row.appendChild(tgt);
    row.appendChild(weight);
    row.appendChild(removeBtn);
    return row;
  }

  function initTabs() {
    const tabs = el("input-tabs");
    if (!tabs) return;
    tabs.addEventListener("click", function (event) {
      const target = event.target;
      const tab = target && target.closest ? target.closest(".tab") : null;
      if (!tab) return;
      const format = tab.getAttribute("data-format");
      if (!format) return;
      tabs.querySelectorAll(".tab").forEach(function (t) {
        t.classList.toggle("active", t === tab);
      });
      document.querySelectorAll(".input-panel").forEach(function (panel) {
        panel.classList.toggle("active", panel.id === "panel-" + format);
      });
    });
  }

  function initArcs() {
    const list = el("arcs-list");
    if (!list) return;
    const addBtn = el("btn-add-arc");
    if (addBtn) {
      addBtn.addEventListener("click", function () {
        list.appendChild(createArcRow());
      });
    }
    list.addEventListener("click", function (event) {
      const target = event.target;
      const btn = target && target.closest ? target.closest(".arc-remove") : null;
      if (!btn) return;
      const row = btn.closest(".arc-row");
      if (row && row.parentElement) row.remove();
    });
    list.appendChild(createArcRow());
  }

  function initRunButtons() {
    const textBtn = el("btn-run-text");
    if (textBtn) textBtn.addEventListener("click", function () { run("text", buildTextPayload); });
    const jsonBtn = el("btn-run-json");
    if (jsonBtn) jsonBtn.addEventListener("click", function () { run("json", buildJsonPayload); });
    const formBtn = el("btn-run-form");
    if (formBtn) formBtn.addEventListener("click", function () { run("form", buildFormPayload); });
  }

  function initCanvasSelection() {
    ["canvas-net", "canvas-graph"].forEach(function (id) {
      const canvas = el(id);
      if (!canvas) return;
      canvas.addEventListener("click", function () {
        document.querySelectorAll(".canvas").forEach(function (c) {
          c.classList.toggle("active-canvas", c === canvas);
        });
      });
    });
  }

  function initExportButtons() {
    const pngBtn = el("btn-export-png");
    if (pngBtn) {
      pngBtn.addEventListener("click", async function () {
        try {
          const active = document.querySelector(".canvas.active-canvas");
          const key = active && active.id === "canvas-net" ? "net" : "graph";
          await Exports.exportPng(key);
        } catch (err) {
          Ui.toast(err.message, true);
        }
      });
    }
    const jsonBtn = el("btn-export-json");
    if (jsonBtn) {
      jsonBtn.addEventListener("click", async function () {
        if (!S.sessionId) {
          Ui.toast("Нет активной сессии", true);
          return;
        }
        try {
          await Exports.downloadReport(S.sessionId);
        } catch (err) {
          Ui.toast(err.message, true);
        }
      });
    }
    const csvBtn = el("btn-export-csv");
    if (csvBtn) {
      csvBtn.addEventListener("click", async function () {
        if (!S.sessionId) {
          Ui.toast("Нет активной сессии", true);
          return;
        }
        try {
          await Exports.downloadMarkings(S.sessionId);
        } catch (err) {
          Ui.toast(err.message, true);
        }
      });
    }
  }

  function readQueryMarking() {
    if (!S.places.length) {
      Ui.toast("Сначала проанализируйте сеть", true);
      return null;
    }
    const parts = splitCsv(el("query-marking").value);
    if (parts.length !== S.places.length) {
      Ui.toast("Маркировка должна содержать " + S.places.length + " значений", true);
      return null;
    }
    const values = [];
    for (let i = 0; i < parts.length; i += 1) {
      const v = toInt(parts[i]);
      if (v === null || v < 0) {
        Ui.toast("Значения маркировки должны быть целыми числами ≥ 0", true);
        return null;
      }
      values.push(v);
    }
    return values;
  }

  function singleQueryValue(block, key) {
    if (!block || block[key] === null || block[key] === undefined) return null;
    const value = block[key];
    if (typeof value === "boolean") return value;
    if (typeof value === "object") {
      const keys = Object.keys(value);
      return keys.length ? value[keys[0]] : null;
    }
    return null;
  }

  async function runQuery(kind) {
    if (!S.sessionId) {
      Ui.toast("Сначала проанализируйте сеть", true);
      return;
    }
    const values = readQueryMarking();
    if (values === null) return;
    const queries =
      kind === "reachable" ? { reachable_marking: values } : { coverable_marking: values };
    let report;
    try {
      report = await Api.analyzeProperties(S.sessionId, queries);
    } catch (err) {
      Ui.toast(err.message, true);
      return;
    }
    S.report = report;
    PropertiesPanel.render(report);
    const answer = singleQueryValue(
      report.queries,
      kind === "reachable" ? "is_reachable" : "is_coverable"
    );
    const resultEl = el("query-result");
    if (resultEl) {
      resultEl.textContent = answer === null ? "не определено (ω)" : answer ? "да" : "нет";
    }
  }

  function clearAnalysisView() {
    S.sessionId = null;
    S.name = "";
    S.places = [];
    S.transitions = [];
    S.inputs = {};
    S.outputs = {};
    S.marking = null;
    S.history = [];
    S.structure = null;
    S.structureKind = null;
    S.report = null;
    setBadge("", false);
    setAnalysisVisible(false);
    clearGraphCanvas();
    const stats = el("graph-stats");
    if (stats) stats.textContent = "";
    const qres = el("query-result");
    if (qres) qres.textContent = "";
    Ui.setStatus("");
  }

  async function loadSession(sessionId) {
    if (!sessionId) return;
    try {
      const summary = await Api.getSession(sessionId);
      S.sessionId = summary.session_id;
      S.name = summary.name || "";
      S.places = summary.places || [];
      S.transitions = summary.transitions || [];
      S.inputs = summary.inputs || {};
      S.outputs = summary.outputs || {};
      S.marking = summary.current_marking || null;
      S.history = [];
      S.structure = null;
      S.structureKind = null;
      S.report = null;
      setBadge(S.name || S.sessionId, true);
      setAnalysisVisible(true);
      SessionsPanel.setCurrent(S.sessionId);
      if (summary.graph_built) {
        const graph = await Api.getStoredGraph(sessionId);
        S.structure = graph.structure;
        S.structureKind = graph.kind;
        setGraphStats(graph);
        let report;
        if (summary.report_computed) {
          const res = await fetch(Api.exportReportUrl(sessionId));
          if (!res.ok) {
            throw new Error("сохранённый отчёт недоступен");
          }
          report = await res.json();
        } else {
          report = await Api.analyzeProperties(sessionId, null);
        }
        S.report = report;
        GraphCanvas.render(graph.structure, deadlocksFor(report));
        wireGraphClick();
        PropertiesPanel.render(report);
      } else {
        clearGraphCanvas();
        const stats = el("graph-stats");
        if (stats) stats.textContent = "";
      }
      const st = await Api.getState(sessionId);
      S.marking = st.current_marking;
      S.history = st.history;
      StepPanel.onAction(stepAction);
      StepPanel.render(st.active_transitions);
      StepPanel.setFullHistory(st.history);
      NetCanvas.render({
        places: S.places,
        transitions: S.transitions,
        inputs: S.inputs,
        outputs: S.outputs,
        marking: st.current_marking,
      });
      NetCanvas.setMarking(st.current_marking, S.places);
      SessionsPanel.refresh();
    } catch (err) {
      Ui.toast(err.message, true);
    }
  }

  function initSessions() {
    const btn = el("btn-sessions");
    const panel = el("sessions-panel");
    if (btn && panel) {
      btn.addEventListener("click", function () {
        panel.classList.toggle("hidden");
        if (!panel.classList.contains("hidden")) SessionsPanel.refresh();
      });
    }
    SessionsPanel.onLoad(loadSession);
    SessionsPanel.onCleared(clearAnalysisView);
    SessionsPanel.refresh();
  }

  function init() {
    initTabs();
    initArcs();
    initRunButtons();
    initCanvasSelection();
    initExportButtons();
    initSessions();
    const buildBtn = el("btn-build-graph");
    if (buildBtn) buildBtn.addEventListener("click", function () { buildGraphAndProps(); });
    const reachBtn = el("btn-query-reach");
    if (reachBtn) reachBtn.addEventListener("click", function () { runQuery("reachable"); });
    const coverBtn = el("btn-query-cover");
    if (coverBtn) coverBtn.addEventListener("click", function () { runQuery("coverable"); });
  }

  document.addEventListener("DOMContentLoaded", init);

  return { state: S };
})();
