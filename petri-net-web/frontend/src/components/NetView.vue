<script setup>
import { computed, ref, watch } from "vue";
import api from "../api";
import { setStatus, store, toast } from "../store";
import ExportMenu from "./ExportMenu.vue";
import InputTabs from "./InputTabs.vue";
import NetCanvas from "./NetCanvas.vue";
import PropertiesPanel from "./PropertiesPanel.vue";
import ReachabilityCanvas from "./ReachabilityCanvas.vue";
import SessionsPanel from "./SessionsPanel.vue";
import StepPanel from "./StepPanel.vue";

const graphMode = ref("auto");
const queryMarking = ref("");
const activeCanvas = ref("net");
const firing = ref(null);

const netPayload = computed(() => {
  const model = store.model;
  if (!model) return null;
  return {
    places: model.places || [],
    transitions: model.transitions || [],
    inputs: model.inputs || {},
    outputs: model.outputs || {},
    inhibitors: model.inhibitors || {},
    delays: model.delays || {},
  };
});

const deadlocksFor = computed(() => {
  if (store.structureKind === "coverability") return null;
  return store.report ? store.report.deadlocks : null;
});

async function refreshStateView() {
  const st = await api.getState(store.sessionId);
  store.marking = st.current_marking;
  store.active = st.active_transitions || [];
  store.history = st.history || [];
}

async function buildGraphAndProps() {
  if (!store.sessionId) return;
  setStatus("Построение графа достижимости…");
  store.structure = null;
  store.structureKind = null;
  store.graphStats = null;
  store.report = null;
  let graph;
  try {
    graph = await api.buildGraph(store.sessionId, graphMode.value);
  } catch (err) {
    if (err.code === "cap_exceeded") {
      toast(
        "Превышен лимит узлов. Выберите режим «Покрываемость (Кэрп–Миллер)» и повторите.",
        true
      );
    } else {
      toast(err.message, true);
    }
    setStatus("Остановлено: ошибка.");
    return;
  }
  store.structure = graph.structure;
  store.structureKind = graph.kind;
  store.graphStats = {
    nodes: graph.node_count,
    edges: graph.edge_count,
    kind: graph.kind,
  };
  setStatus("Вычисление свойств…");
  let report;
  try {
    report = await api.analyzeProperties(store.sessionId, null);
  } catch (err) {
    toast(err.message, true);
    setStatus("Остановлено: ошибка.");
    return;
  }
  store.report = report;
  try {
    await refreshStateView();
  } catch (err) {
    toast(err.message, true);
    return;
  }
  setStatus("Готово.");
}

async function gotoMarking(markingArray) {
  if (!store.sessionId || !Array.isArray(markingArray)) return;
  if (
    store.marking &&
    JSON.stringify(markingArray) === JSON.stringify(store.marking)
  ) {
    return;
  }
  try {
    await api.gotoMarking(store.sessionId, markingArray);
    await refreshStateView();
  } catch (err) {
    toast(err.message, true);
  }
}

async function fireTransition(t) {
  if (!store.sessionId || !t) return;
  if (!store.active.includes(t)) {
    toast(`Переход ${t} сейчас не разрешён`, true);
    return;
  }
  const ts = Date.now();
  firing.value = { t, ts };
  try {
    await api.fireAction(store.sessionId, "fire", t);
    await refreshStateView();
  } catch (err) {
    toast(err.message, true);
  } finally {
    setTimeout(() => {
      if (firing.value && firing.value.ts === ts) firing.value = null;
    }, 400);
  }
}

async function stepAction(action, transition) {
  if (!store.sessionId) return;
  try {
    await api.fireAction(store.sessionId, action, transition);
    await refreshStateView();
  } catch (err) {
    toast(err.message, true);
  }
}

async function run(format, payload, name) {
  if (!payload && format !== "text") return;
  setStatus("Разбор описания…");
  let resp;
  try {
    resp = await api.parseSession(format, payload, name || null);
  } catch (err) {
    toast(err.message, true);
    setStatus("Остановлено: ошибка.");
    return;
  }
  store.sessionId = resp.session_id;
  store.name = resp.name || "";
  store.model = resp;
  store.marking = resp.initial_marking || null;
  store.active = [];
  store.history = [];
  store.structure = null;
  store.structureKind = null;
  store.graphStats = null;
  store.report = null;
  store.queryResult = "";
  store.rev += 1;
  await buildGraphAndProps();
}

function readQueryMarking() {
  if (!store.model || !store.model.places.length) {
    toast("Сначала проанализируйте сеть", true);
    return null;
  }
  const parts = (queryMarking.value || "")
    .split(",")
    .map((p) => p.trim())
    .filter((p) => p.length > 0);
  const places = store.model.places;
  if (parts.length !== places.length) {
    toast(`Маркировка должна содержать ${places.length} значений`, true);
    return null;
  }
  const values = [];
  for (const part of parts) {
    const v = parseInt(part, 10);
    if (!Number.isFinite(v) || v < 0) {
      toast("Значения маркировки должны быть целыми числами ≥ 0", true);
      return null;
    }
    values.push(v);
  }
  return values;
}

function singleQueryValue(kind) {
  const block = store.report && store.report.queries;
  if (!block) return null;
  const key = kind === "reachable" ? "is_reachable" : "is_coverable";
  const value = block[key];
  if (value === null || value === undefined) return null;
  if (typeof value === "boolean") return value;
  if (typeof value === "object") {
    const keys = Object.keys(value);
    return keys.length ? value[keys[0]] : null;
  }
  return null;
}

async function runQuery(kind) {
  if (!store.sessionId) {
    toast("Сначала проанализируйте сеть", true);
    return;
  }
  const values = readQueryMarking();
  if (values === null) return;
  const queries =
    kind === "reachable" ? { reachable_marking: values } : { coverable_marking: values };
  try {
    store.report = await api.analyzeProperties(store.sessionId, queries);
    const answer = singleQueryValue(kind);
    store.queryResult = answer === null ? "не определено (ω)" : answer ? "да" : "нет";
  } catch (err) {
    toast(err.message, true);
  }
}

function clearAnalysisView() {
  store.sessionId = null;
  store.name = "";
  store.model = null;
  store.marking = null;
  store.active = [];
  store.history = [];
  store.structure = null;
  store.structureKind = null;
  store.graphStats = null;
  store.report = null;
  store.queryResult = "";
  window.Registry.net = null;
  window.Registry.graph = null;
  setStatus("");
}

async function loadSession(sessionId) {
  try {
    const summary = await api.getSession(sessionId);
    store.sessionId = summary.session_id;
    store.name = summary.name || "";
    store.model = summary;
    store.marking = summary.current_marking || null;
    store.active = [];
    store.history = [];
    store.structure = null;
    store.structureKind = null;
    store.graphStats = null;
    store.report = null;
    store.queryResult = "";
    store.rev += 1;
    if (summary.graph_built) {
      const graph = await api.getStoredGraph(sessionId);
      store.structure = graph.structure;
      store.structureKind = graph.kind;
      store.graphStats = {
        nodes: graph.node_count,
        edges: graph.edge_count,
        kind: graph.kind,
      };
      if (summary.report_computed) {
        const res = await fetch(api.exportReportUrl(sessionId));
        if (!res.ok) throw new Error("сохранённый отчёт недоступен");
        store.report = await res.json();
      } else {
        store.report = await api.analyzeProperties(sessionId, null);
      }
    }
    await refreshStateView();
  } catch (err) {
    toast(err.message, true);
  }
}

function onCleared(sessionId) {
  if (sessionId === store.sessionId) clearAnalysisView();
}

// «Сохранить в сессию» из экрана «Задание из практикума» (SolverView)
watch(
  () => store.pendingBuild,
  (value) => {
    if (value && store.sessionId) {
      store.pendingBuild = false;
      buildGraphAndProps();
    }
  }
);
</script>

<template>
  <div class="net-view">
    <InputTabs @run="run" />

    <section id="analysis" v-show="store.sessionId">
      <div class="canvas-row">
        <div>
          <NetCanvas
            :net="netPayload"
            :marking="store.marking"
            :active="store.active"
            :firing="firing"
            :selected="activeCanvas === 'net'"
            @select="activeCanvas = 'net'"
            @fire="fireTransition"
          />
          <div class="canvas-caption">
            Сеть Петри
            <template v-if="netPayload && netPayload.inhibitors && Object.keys(netPayload.inhibitors).length">
              (⊣ — ингибиторная дуга)
            </template>
          </div>
        </div>
        <div>
          <ReachabilityCanvas
            :structure="store.structure"
            :current="store.marking"
            :deadlocks="deadlocksFor"
            :selected="activeCanvas === 'graph'"
            @select="activeCanvas = 'graph'"
            @goto="gotoMarking"
          />
          <div class="canvas-caption">
            {{
              store.graphStats && store.graphStats.kind === "coverability"
                ? "Дерево покрываемости (Кэрп–Миллер)"
                : "Граф достижимости"
            }}
          </div>
        </div>
      </div>

      <div id="build-row">
        <select v-model="graphMode" title="Режим построения">
          <option value="auto">Авто</option>
          <option value="bounded">Ограниченный</option>
          <option value="coverability">Покрываемость (Кэрп–Миллер)</option>
        </select>
        <button type="button" id="btn-build-graph" class="primary" @click="buildGraphAndProps">
          Построить граф
        </button>
        <span id="graph-stats" class="status">
          <template v-if="store.graphStats">
            узлов: {{ store.graphStats.nodes }}, рёбер: {{ store.graphStats.edges }}
          </template>
        </span>
      </div>

      <div id="step-panel">
        <h3>Пошаговое проигрывание</h3>
        <StepPanel
          :active="store.active"
          :history="store.history"
          @fire="fireTransition"
          @undo="stepAction('undo', null)"
          @reset="stepAction('reset', null)"
          @goto="gotoMarking"
        />
      </div>

      <div id="props-panel">
        <h3>Свойства</h3>
        <PropertiesPanel :report="store.report" :kind="store.structureKind" />
      </div>

      <div id="query-row">
        <label for="query-marking">Проверка маркировки (через запятую):</label>
        <input id="query-marking" v-model="queryMarking" placeholder="7, 4, 2, 5, 4, 3" />
        <button type="button" id="btn-query-reach" @click="runQuery('reachable')">
          Достижима?
        </button>
        <button type="button" id="btn-query-cover" @click="runQuery('coverable')">
          Покрывается?
        </button>
        <span id="query-result" class="status">{{ store.queryResult }}</span>
      </div>

      <div id="export-row">
        <ExportMenu :session-id="store.sessionId" :active-canvas="activeCanvas" />
      </div>

      <div id="sessions-row">
        <SessionsPanel @open="loadSession" @cleared="onCleared" />
      </div>
    </section>
  </div>
</template>
