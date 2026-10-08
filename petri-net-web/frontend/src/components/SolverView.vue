<script setup>
import { computed, ref, watch } from "vue";
import api from "../api";
import { setStatus, store, toast } from "../store";
import ReportPanel from "./ReportPanel.vue";

const props = defineProps({
  task: { type: Object, required: true },
});

const dataText = ref("");
const busy = ref(false);

watch(
  () => props.task,
  (task) => {
    store.solverReport = null;
    dataText.value = task.prefill ? JSON.stringify(task.prefill, null, 2) : "";
  },
  { immediate: true }
);

function parseData() {
  const raw = dataText.value.trim();
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      toast("Данные задачи должны быть JSON-объектом", true);
      return null;
    }
    return parsed;
  } catch (err) {
    toast("Данные задачи: некорректный JSON: " + err.message, true);
    return null;
  }
}

async function solve() {
  const data = parseData();
  if (data === null) return;
  busy.value = true;
  setStatus(`Решение ${props.task.task_id}…`);
  try {
    store.solverReport = await api.solve(props.task.task_id, data);
    setStatus("Готово.");
  } catch (err) {
    toast(err.message, true);
    setStatus("Остановлено: ошибка.");
  } finally {
    busy.value = false;
  }
}

const canSave = computed(() => {
  const report = store.solverReport;
  if (!report || props.task.input_kind !== "pn") return false;
  const data = parseData();
  if (data === null) return false;
  const net = data.net || (data.places ? data : null);
  return Boolean(net && typeof net === "object");
});

// сохраняет PN-сеть как именованную сессию и открывает экран «Сеть Петри»
function saveSession() {
  const data = parseData();
  if (data === null) return;
  const net = data.net || (data.places ? data : null);
  if (!net) {
    toast("Нет сети для сохранения", true);
    return;
  }
  setStatus("Сохранение в сессию…");
  api
    .parseSession("json", net, props.task.title)
    .then((resp) => {
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
      store.pendingBuild = true;
      store.view = "net";
      toast(`Сессия «${store.name || store.sessionId}» создана`);
    })
    .catch((err) => {
      toast(err.message, true);
      setStatus("Остановлено: ошибка.");
    });
}

function close() {
  store.task = null;
  store.solverReport = null;
}
</script>

<template>
  <section class="solver">
    <div class="report-actions" style="justify-content: space-between">
      <h3 style="margin: 0">
        {{ task.task_id }} — {{ task.title }}
        <span class="muted">({{ task.source }}, {{ task.type }})</span>
      </h3>
      <button type="button" @click="close">Закрыть</button>
    </div>

    <label for="task-data">Данные задачи (JSON, предзаполнены данными методички)</label>
    <textarea
      id="task-data"
      v-model="dataText"
      rows="12"
      spellcheck="false"
      placeholder="пусто — решать встроенными данными методички"
    ></textarea>

    <div class="report-actions">
      <button type="button" class="primary" :disabled="busy" @click="solve">
        {{ busy ? "Решение…" : "Решить" }}
      </button>
      <button type="button" :disabled="!canSave || busy" @click="saveSession" title="Построить сеть из этих данных как именованную сессию">
        Сохранить в сессию
      </button>
    </div>

    <ReportPanel v-if="store.solverReport" :report="store.solverReport" :task="task" />
  </section>
</template>
