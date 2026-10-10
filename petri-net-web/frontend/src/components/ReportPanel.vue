<script setup>
import { computed, ref } from "vue";
import { compactTuple, prettyFormula, toast } from "../store";
import AutomatonCanvas from "./AutomatonCanvas.vue";
import AnswerValue from "./AnswerValue.vue";
import Formula from "./Formula.vue";
import { markingToTex, matrixToTex, MATRIX_KEYS } from "../math/tex";

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
  Object.keys(given.value)
    .filter((key) => !key.endsWith("_tex"))
    .map((key) => ({ key, value: given.value[key] }))
);

const answerRows = computed(() =>
  Object.keys(answer.value)
    .filter((key) => key !== "graph" && !key.endsWith("_tex"))
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

// raw→tex карта: пары (str-значение, *_tex-компаньон) из answer (включая
// parts-подобъекты) и всех solution[].data; сортировка по длине raw ↓
const rawTexPairs = computed(() => {
  const pairs = [];
  const collect = (node) => {
    if (Array.isArray(node)) {
      node.forEach(collect);
      return;
    }
    if (!node || typeof node !== "object") return;
    for (const key of Object.keys(node)) {
      if (key.endsWith("_tex")) continue;
      const tex = node[key + "_tex"];
      if (tex !== undefined) {
        const raw = node[key];
        if (typeof raw === "string" && typeof tex === "string" && raw.length) {
          pairs.push([raw, tex]);
        } else if (
          raw && typeof raw === "object" && !Array.isArray(raw) &&
          tex && typeof tex === "object" && !Array.isArray(tex)
        ) {
          for (const k2 of Object.keys(raw)) {
            if (typeof raw[k2] === "string" && typeof tex[k2] === "string") {
              pairs.push([raw[k2], tex[k2]]);
            }
          }
        } else if (
          Array.isArray(raw) && Array.isArray(tex) &&
          raw.length === tex.length &&
          raw.every((x) => typeof x === "string") &&
          tex.every((x) => typeof x === "string")
        ) {
          raw.forEach((r, i) => pairs.push([r, tex[i]]));
        }
      }
      collect(node[key]);
    }
  };
  collect(props.report.answer || {});
  solution.value.forEach((step) => {
    if (step && step.data) collect(step.data);
  });
  const uniq = new Map();
  pairs.forEach(([raw, tex]) => {
    if (!uniq.has(raw)) uniq.set(raw, tex);
  });
  return [...uniq.entries()].sort((a, b) => b[0].length - a[0].length);
});

function splitFormulaText(text, pairs) {
  let segments = [String(text || "")];
  for (const [raw, tex] of pairs) {
    const next = [];
    for (const seg of segments) {
      if (seg !== null && typeof seg === "object") {
        next.push(seg);
        continue;
      }
      const parts = seg.split(raw);
      for (let i = 0; i < parts.length; i += 1) {
        if (i > 0) next.push({ tex });
        next.push(parts[i]);
      }
    }
    segments = next;
  }
  return segments;
}

function stepSegments(step) {
  return splitFormulaText(step.text, rawTexPairs.value);
}

// строки данных шага: формульные значения — через <Formula>, остальное plain
function stepDataEntries(step) {
  const data = step && step.data;
  if (!data || typeof data !== "object" || Array.isArray(data)) return null;
  const out = [];
  for (const key of Object.keys(data)) {
    if (key.endsWith("_tex")) continue;
    const val = data[key];
    const tex = data[key + "_tex"];
    if (typeof val === "string") {
      out.push(
        typeof tex === "string"
          ? { key, kind: "formula", tex }
          : { key, kind: "plain", text: cellText(val) }
      );
    } else if (Array.isArray(val) && val.length && val.every((x) => Array.isArray(x))) {
      out.push(
        MATRIX_KEYS.has(key)
          ? { key, kind: "formula", tex: matrixToTex(val) }
          : { key, kind: "plain", text: cellText(val) }
      );
    } else if (Array.isArray(val) && val.length && val.every((x) => typeof x === "number" || x === null)) {
      out.push({ key, kind: "formula", tex: markingToTex(val) });
    } else if (
      Array.isArray(val) && val.length && val.every((x) => typeof x === "string") &&
      Array.isArray(tex) && tex.length === val.length && tex.every((x) => typeof x === "string")
    ) {
      out.push({ key, kind: "formula-list", rows: tex });
    } else if (val !== null && typeof val === "object" && !Array.isArray(val)) {
      if (typeof tex === "string" && tex.length) {
        out.push({ key, kind: "formula", tex });
      } else if (
        tex && typeof tex === "object" && !Array.isArray(tex) &&
        Object.keys(val).every((k2) => typeof val[k2] === "number" || typeof val[k2] === "string")
      ) {
        out.push({
          key,
          kind: "dict-formula",
          rows: Object.keys(val).map((k2) => ({
            k: k2,
            tex: typeof tex[k2] === "string" ? tex[k2] : null,
            v: val[k2],
          })),
        });
      } else {
        out.push({ key, kind: "plain", text: cellText(val) });
      }
    } else {
      out.push({ key, kind: "plain", text: cellText(val) });
    }
  }
  return out;
}

// каталог звеньев (LSS-13/18): строки со скалярными значениями + *_tex
const CATALOG_COL_LABELS = { title: "Звено", law: "Закон «вход-выход»", phi: "Φ(s)", g: "g(t, τ)" };
const CATALOG_COLS = ["title", "law", "phi", "g"];

function isLinkCatalog(value) {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.every(
      (row) =>
        row &&
        typeof row === "object" &&
        !Array.isArray(row) &&
        Object.values(row).every((v) => v === null || typeof v === "string")
    ) &&
    value.some((row) => Object.keys(row).some((k) => k.endsWith("_tex")))
  );
}

const catalogCols = computed(() => {
  const value = answer.value.links;
  if (!isLinkCatalog(value)) return [];
  const first = value[0];
  return CATALOG_COLS.filter((col) => first[col] !== undefined);
});

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

    <h3 class="report-block">Дано</h3>
    <dl class="given-dl">
      <template v-for="row in givenRows" :key="row.key">
        <dt>{{ row.key }}</dt>
        <dd>
          <Formula
            v-if="row.key === 'statement' && typeof given.statement_tex === 'string'"
            :tex="given.statement_tex"
            display
          />
          <pre v-else-if="typeof row.value === 'string'" class="formula" style="margin: 0">{{
            row.value
          }}</pre>
          <pre v-else-if="row.value !== null && typeof row.value === 'object'" class="formula" style="margin: 0">{{
            JSON.stringify(row.value, null, 1)
          }}</pre>
          <template v-else>{{ row.value }}</template>
        </dd>
      </template>
    </dl>

    <h3 class="report-block">Найти</h3>
    <ol>
      <li v-for="(item, i) in find" :key="i">{{ item }}</li>
    </ol>

    <h3 class="report-block">Решение</h3>
    <div v-for="step in solution" :key="step.step" class="step-block">
      <h4>
        Шаг {{ step.step }}. {{ step.title }}
      </h4>
      <pre class="step-text"><template v-for="(seg, i) in stepSegments(step)" :key="i"><Formula
          v-if="seg !== null && typeof seg === 'object'"
          :tex="seg.tex"
        /><template v-else>{{ seg }}</template></template></pre>
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
        <template v-else-if="stepDataEntries(step)">
          <template v-for="entry in stepDataEntries(step)" :key="entry.key">
            <div v-if="entry.kind === 'formula'" class="data-entry">
              <div class="answer-key">{{ entry.key }}</div>
              <Formula :tex="entry.tex" display />
            </div>
            <div v-else-if="entry.kind === 'formula-list'" class="data-entry">
              <div class="answer-key">{{ entry.key }}</div>
              <Formula v-for="(t, i) in entry.rows" :key="i" :tex="t" display />
            </div>
            <div v-else-if="entry.kind === 'dict-formula'" class="data-entry">
              <div class="answer-key">{{ entry.key }}</div>
              <table class="data-table">
                <tbody>
                  <tr v-for="r in entry.rows" :key="r.k">
                    <td>
                      <Formula v-if="r.tex" :tex="r.tex" />
                      <template v-else>{{ r.k }}</template>
                    </td>
                    <td>{{ r.v }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="data-entry">
              <table class="data-table">
                <tbody>
                  <tr>
                    <td style="font-weight: 600">{{ entry.key }}</td>
                    <td>{{ entry.text }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </template>
      </template>
    </div>
    <p v-if="!solution.length" class="muted">Решение не требуется (задача-модель).</p>

    <h3 class="report-block">Ответ</h3>
    <div class="answer-block">
      <div
        v-for="row in answerRows"
        :key="row.key"
        class="answer-block"
      >
        <div class="answer-key">{{ row.label }}</div>
        <template v-if="row.key === 'links' && isLinkCatalog(row.value) && catalogCols.length">
          <table class="data-table">
            <thead>
              <tr>
                <th v-for="col in catalogCols" :key="col">{{ CATALOG_COL_LABELS[col] || col }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in row.value" :key="i">
                <td v-for="col in catalogCols" :key="col">
                  <Formula v-if="typeof r[col + '_tex'] === 'string'" :tex="r[col + '_tex']" />
                  <template v-else>{{ r[col] === null ? "—" : r[col] }}</template>
                </td>
              </tr>
            </tbody>
          </table>
        </template>
        <AnswerValue v-else :value="row.value" :key-name="row.key" :container="answer" />
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

    <h3 v-if="notes.length" class="report-block">Пояснения</h3>
    <ul v-if="notes.length">
      <li v-for="(note, i) in notes" :key="i">{{ note }}</li>
    </ul>
  </section>
</template>
