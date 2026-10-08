<script setup>
import { computed, ref } from "vue";
import { compactTuple, prettyFormula, toast } from "../store";
import AutomatonCanvas from "./AutomatonCanvas.vue";

const props = defineProps({
  report: { type: Object, required: true },
  task: { type: Object, default: null },
});

const ANSWER_LABELS = {
  enabled: "Разрешённые переходы",
  final_marking: "Итоговая маркировка",
  marking: "Маркировка",
  mu_min: "Минимальная маркировка µmin",
  mu_star: "Маркировка µ*",
  mu_prime: "µ′ = µ + W·v(σ)",
  y: "y(t) = y_о(t) + y_ч(t)",
  y_h: "y_о(t) — решение однородного",
  y_p: "y_ч(t) — частное решение",
  P: "P(λ) — характеристический многочлен",
  roots: "Корни P(λ)",
  g: "g(t, τ) — весовая функция",
  phi: "Φ(s) — передаточная функция",
  W: "W(s) — передаточная функция",
  A: "A(ω) — амплитудно-частотная характеристика",
  phi_f: "φ(ω) — фазо-частотная характеристика",
  F_iw: "F(iω) = Φ(iω)",
  states: "Последовательность состояний",
  output_word: "Выходное слово",
  enumeration: "Перечисление (φ, ψ)",
  table: "Таблица переходов",
  graph: "Граф автомата",
  mealy: "Эквивалентный автомат Мили",
  r1: "Автомат 1",
  r2: "Автомат 2",
  equal: "Эквивалентны на слове",
  v: "v(σ) — вектор срабатываний",
  sigma: "Последовательность σ",
  ticks: "Автоматные такты",
  links: "Стандартные звенья",
  W_minus: "W− (входы)",
  W_plus: "W+ (выходы)",
};

const given = computed(() => props.report.given || {});
const find = computed(() => props.report.find || []);
const solution = computed(() => props.report.solution || []);
const answer = computed(() => props.report.answer || {});
const notes = computed(() => props.report.notes || []);

const givenRows = computed(() =>
  Object.keys(given.value).map((key) => ({ key, value: given.value[key] }))
);

const answerRows = computed(() =>
  Object.keys(answer.value)
    .filter((key) => key !== "graph")
    .map((key) => ({
      key,
      label: ANSWER_LABELS[key] || key,
      value: answer.value[key],
    }))
);

// граф автомата в ответе (FA normalize/simulate); вложенный граф mealy
// отрисовывается блоком «Эквивалентный автомат Мили»
const automatonGraph = computed(() => answer.value.graph || null);

// прохождение слова по тактам (FA simulate)
const statesPath = computed(() => {
  const states = answer.value.states;
  return Array.isArray(states) ? states : null;
});
const tick = ref(-1);

const pathUpToTick = computed(() => {
  if (!statesPath.value || tick.value < 0) return statesPath.value;
  return statesPath.value.slice(0, tick.value + 1);
});

function nextTick() {
  if (!statesPath.value) return;
  tick.value = tick.value >= statesPath.value.length - 1 ? -1 : tick.value + 1;
}

function resetTick() {
  tick.value = -1;
}

function isMealy(value) {
  return (
    value &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    (value.enumeration !== undefined || value.table !== undefined || value.graph !== undefined)
  );
}

function isFaTable(value) {
  return value && typeof value === "object" && Array.isArray(value.cols) && Array.isArray(value.rows);
}

function isListOfScalars(value) {
  return (
    Array.isArray(value) &&
    value.length &&
    value.every(
      (v) => typeof v === "number" || typeof v === "string" || typeof v === "boolean"
    )
  );
}

function isListOfTuples(value) {
  return Array.isArray(value) && value.length && value.every((v) => Array.isArray(v));
}

function cellText(val) {
  if (Array.isArray(val)) {
    if (val.length && val.every((x) => Array.isArray(x))) {
      return val.map((r) => compactTuple(r)).join("; ");
    }
    if (val.length && val.every((x) => x && typeof x === "object")) {
      return val.map((x) => JSON.stringify(x)).join("; ");
    }
    return compactTuple(val);
  }
  if (val !== null && typeof val === "object") return JSON.stringify(val);
  return prettyFormula(val);
}

function tupleText(value) {
  if (Array.isArray(value) && (value.length <= 12 || value.every((v) => typeof v === "number"))) {
    return `(${compactTuple(value)})`;
  }
  if (Array.isArray(value)) return value.map((v) => (Array.isArray(v) ? compactTuple(v) : v)).join("; ");
  return String(value);
}

// экспорт PNG графа автомата (FR-503)
async function exportAutomatonPng() {
  const cy = window.Registry.automaton;
  if (!cy) {
    toast("Граф автомата не построен", true);
    return;
  }
  try {
    const blob = await cy.png({ output: "blob-promise", scale: 2, bg: "#ffffff" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "automaton.png";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    toast("PNG: " + err.message, true);
  }
}
</script>

<template>
  <section class="report">
    <h3>Отчёт по {{ report.task_id }}</h3>

    <h4>Дано</h4>
    <dl class="given-dl">
      <template v-for="row in givenRows" :key="row.key">
        <dt>{{ row.key }}</dt>
        <dd>
          <pre v-if="typeof row.value === 'string'" class="formula" style="margin: 0">{{
            row.value
          }}</pre>
          <pre v-else-if="row.value !== null && typeof row.value === 'object'" class="formula" style="margin: 0">{{
            JSON.stringify(row.value, null, 1)
          }}</pre>
          <template v-else>{{ row.value }}</template>
        </dd>
      </template>
    </dl>

    <h4>Найти</h4>
    <ol>
      <li v-for="(item, i) in find" :key="i">{{ item }}</li>
    </ol>

    <h4>Решение</h4>
    <div v-for="step in solution" :key="step.step" class="step-block">
      <h5 style="margin: 10px 0 2px">
        Шаг {{ step.step }}. {{ step.title }}
      </h5>
      <pre class="step-text">{{ step.text }}</pre>
      <template v-if="step.data">
        <table
          v-if="step.data.cols !== undefined && step.data.rows !== undefined"
          class="data-table"
        >
          <thead>
            <tr>
              <th></th>
              <th v-for="col in step.data.cols" :key="col">{{ col }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in step.data.rows" :key="i">
              <td>{{ row[0] }}</td>
              <td v-for="(cell, j) in row.slice(1)" :key="j">{{ cell }}</td>
            </tr>
          </tbody>
        </table>
        <template
          v-else-if="typeof step.data === 'object' && !Array.isArray(step.data)"
        >
          <template v-for="(val, key) in step.data" :key="key">
            <table v-if="isListOfTuples(val)" class="data-table">
              <tbody>
                <tr v-for="(row, i) in val" :key="i">
                  <td v-for="(cell, j) in row" :key="j">{{
                    cell === null || cell === undefined ? "—" : prettyFormula(cell)
                  }}</td>
                </tr>
              </tbody>
            </table>
            <table v-else class="data-table">
              <tbody>
                <tr>
                  <td style="font-weight: 600">{{ key }}</td>
                  <td>{{ cellText(val) }}</td>
                </tr>
              </tbody>
            </table>
          </template>
        </template>
      </template>
    </div>
    <p v-if="!solution.length" class="muted">Решение не требуется (задача-модель).</p>

    <h4>Ответ</h4>
    <div class="answer-block">
      <div
        v-for="row in answerRows"
        :key="row.key"
        class="answer-block"
      >
        <div class="answer-key">{{ row.label }}</div>
        <pre v-if="typeof row.value === 'string'" class="formula">{{
          prettyFormula(row.value)
        }}</pre>
        <span v-else-if="row.value === null">—</span>
        <span v-else-if="typeof row.value === 'number' || typeof row.value === 'boolean'">{{
          row.value === true ? "да" : row.value === false ? "нет" : row.value
        }}</span>
        <span v-else-if="isFaTable(row.value)">
          <table class="data-table">
            <thead>
              <tr>
                <th></th>
                <th v-for="col in row.value.cols" :key="col">{{ col }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in row.value.rows" :key="i">
                <td>{{ r[0] }}</td>
                <td v-for="(cell, j) in r.slice(1)" :key="j">{{ cell }}</td>
              </tr>
            </tbody>
          </table>
        </span>
        <span v-else-if="isMealy(row.value)">
          <pre v-if="row.value.enumeration" class="formula">
{{ row.value.enumeration.join("\n") }}</pre
          >
          <table v-if="row.value.table" class="data-table">
            <thead>
              <tr>
                <th></th>
                <th v-for="col in row.value.table.cols" :key="col">{{ col }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in row.value.table.rows" :key="i">
                <td>{{ r[0] }}</td>
                <td v-for="(cell, j) in r.slice(1)" :key="j">{{ cell }}</td>
              </tr>
            </tbody>
          </table>
          <AutomatonCanvas
            v-if="row.value.graph"
            :graph="row.value.graph"
            :registry-key="row.key"
          />
        </span>
        <span v-else-if="Array.isArray(row.value) && !row.value.length">(пусто)</span>
        <span v-else-if="isListOfScalars(row.value)">{{ tupleText(row.value) }}</span>
        <span v-else-if="isListOfTuples(row.value)">
          <table class="data-table">
            <tbody>
              <tr v-for="(r, i) in row.value" :key="i">
                <td v-for="(cell, j) in r" :key="j">{{
                  typeof cell === "string" ? prettyFormula(cell) : cell
                }}</td>
              </tr>
            </tbody>
          </table>
        </span>
        <span v-else-if="typeof row.value === 'object'"
          ><table class="data-table">
            <tbody>
              <tr v-for="(val, key) in row.value" :key="key">
                <td style="font-weight: 600">{{ key }}</td>
                <td>{{ cellText(val) }}</td>
              </tr>
            </tbody>
          </table>
        </span>
      </div>
      <p v-if="!answerRows.length && !automatonGraph" class="muted">
        Ответ — в шагах решения.
      </p>
    </div>

    <div v-if="automatonGraph" class="answer-block">
      <div class="answer-key">Граф автомата</div>
      <AutomatonCanvas :graph="automatonGraph" :path="pathUpToTick" />
      <div v-if="statesPath && statesPath.length > 1" class="tick-controls">
        <button type="button" @click="nextTick">
          {{ tick < 0 ? "Показать прохождение" : "Следующий такт" }}
        </button>
        <button type="button" @click="resetTick">Показать весь путь</button>
        <span class="muted">
          <template v-if="tick < 0">путь целиком</template>
          <template v-else>такт {{ tick + 1 }} из {{ statesPath.length }}</template>
        </span>
      </div>
      <div class="tick-controls">
        <button type="button" @click="exportAutomatonPng">PNG графа</button>
      </div>
    </div>

    <h4 v-if="notes.length">Пояснения</h4>
    <ul v-if="notes.length">
      <li v-for="(note, i) in notes" :key="i">{{ note }}</li>
    </ul>
  </section>
</template>
