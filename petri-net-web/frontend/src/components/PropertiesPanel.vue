<script setup>
import { computed } from "vue";
import { compactTuple, yesNo } from "../store";
import Formula from "./Formula.vue";
import { labelTex, markingToTex } from "../math/tex";

const props = defineProps({
  report: { type: Object, default: null },
  kind: { type: String, default: null },
});

const VERDICT_NOTES = {
  живая: "для любой текущей позиции существует последовательность, в которой может сработать любой заданный переход",
  тупиковая: "существует достижимая маркировка, в которой ни один переход не может сработать",
  частичнотупиковая:
    "есть маркировка, где часть переходов перестает срабатывать, а другая часть продолжает работать бесконечно долго",
};

function interleave(segments, separator) {
  const out = [];
  segments.forEach((seg, i) => {
    if (i > 0) out.push({ text: separator });
    out.push(seg);
  });
  return out;
}

const rows = computed(() => {
  if (!props.report) return [];
  const r = props.report;
  const out = [];

  if (r.verdict) {
    out.push({
      name: "Живость сети",
      value: r.verdict,
      note: VERDICT_NOTES[r.verdict] || "",
    });
  } else if (props.kind === "coverability") {
    out.push({
      name: "Живость сети",
      value: "не определена (ω-приближение)",
      note: "по дереву покрываемости точный вердикт не даётся",
    });
  }

  if (r.global_k === null || r.global_k === undefined) {
    out.push({
      name: "k-ограниченная",
      value: "неограничена (k = ω)",
      segments: [{ text: "неограничена" }, { tex: "k = \\omega" }],
      note: "количество меток в каждой позиции не превышает некоторое целое k",
    });
  } else {
    out.push({
      name: "k-ограниченная",
      value: `k = ${r.global_k}`,
      segments: [{ tex: `k = ${r.global_k}` }],
      note: "количество меток в каждой позиции не превышает некоторое целое k",
    });
  }

  const perPlace = r.per_place_k || {};
  const placeKeys = Object.keys(perPlace);
  if (placeKeys.length) {
    out.push({
      name: "Ограниченность по позициям",
      value: placeKeys
        .map((p) => {
          const k = perPlace[p];
          return k === null || k === undefined ? `${p}: ω` : `${p} ≤ ${k}`;
        })
        .join(", "),
      segments: interleave(
        placeKeys.map((p) => {
          const k = perPlace[p];
          return k === null || k === undefined
            ? { tex: `${labelTex(p)} = \\omega` }
            : { tex: `${labelTex(p)} \\le ${k}` };
        }),
        ", "
      ),
      note: "",
    });
  }

  if (r.safe) {
    out.push({
      name: "Безопасная",
      value: "да (k = 1)",
      segments: [{ text: "да" }, { tex: "k = 1" }],
      note: "каждая позиция содержит не более одной метки",
    });
  } else {
    out.push({
      name: "Безопасная",
      value: "нет",
      note: "каждая позиция содержит не более одной метки",
    });
  }

  // API отдаёт conservative как объект {per_transition, constant_sum, conservative}
  const cons =
    r.conservative && typeof r.conservative === "object"
      ? r.conservative
      : null;
  const consValue = cons ? Boolean(cons.conservative) : Boolean(r.conservative);
  let consText = yesNo(consValue);
  if (!consValue && cons) {
    const unbalanced = Object.entries(cons.per_transition || {})
      .filter(([, info]) => info && info.equal === false)
      .map(([t, info]) => `${t}: ${info.in}≠${info.out}`);
    if (unbalanced.length) {
      consText += ` (${unbalanced.join(", ")})`;
    } else if (cons.constant_sum === false) {
      consText += " (сумма меток не постоянна)";
    }
  }
  out.push({
    name: "Консервативная",
    value: consText,
    note: "сумма меток во всех позициях постоянна; на каждом переходе число входных дуг равно числу выходных",
  });

  const deadlocks = Array.isArray(r.deadlocks) ? r.deadlocks : [];
  out.push({
    name: "Тупики",
    value: deadlocks.length
      ? `${deadlocks.length}: ${deadlocks.map((m) => `(${compactTuple(m)})`).join(", ")}`
      : "0 (нет)",
    segments: deadlocks.length
      ? [{ text: `${deadlocks.length}:` }, ...interleave(deadlocks.map((m) => ({ tex: markingToTex(m) })), ", ")]
      : null,
    note: "маркировки, в которых не разрешён ни один переход",
  });

  const deadTransitions = Array.isArray(r.dead_transitions) ? r.dead_transitions : [];
  out.push({
    name: "Мёртвые переходы",
    value: deadTransitions.length ? deadTransitions.join(", ") : "нет",
    note: "переходы, не разрешённые ни в одной достижимой маркировке",
  });

  out.push({
    name: "Обратимость (home state)",
    value: yesNo(Boolean(r.home_state)),
    note: "начальная маркировка достижима из любой достижимой маркировки",
  });

  const liveness = r.liveness || {};
  if (liveness.level !== undefined && liveness.level !== null) {
    out.push({
      name: "Уровень живости сети",
      value: String(liveness.level),
      note: "L0 — мёртвая, L1 — жива хотя бы из начальной маркировки, L2 — жива из каждой достижимой, L3 — нет мёртвых переходов, L4 — живая сеть",
    });
  }

  const tLive = liveness.transitions || {};
  const tKeys = Object.keys(tLive);
  if (tKeys.length) {
    out.push({
      name: "Живость по переходам",
      value: tKeys
        .map((t) => {
          const info = tLive[t] || {};
          const occurs = info.occurs ? "возникает" : "не возникает";
          const level =
            info.level !== undefined && info.level !== null ? String(info.level) : "—";
          return `${t}: ${level} (${occurs})`;
        })
        .join("; "),
      note: "по каждому переходу: уровень L0–L4 и возникает ли он из текущей маркировки",
    });
  }

  const stats = r.stats || {};
  out.push({
    name: "Маркировок (узлов) / рёбер",
    value: `${stats.node_count !== undefined ? stats.node_count : "—"} / ${
      stats.edge_count !== undefined ? stats.edge_count : "—"
    }`,
    note: props.kind === "coverability" ? "дерево покрываемости" : "граф достижимости",
  });

  if (r.mu_min) {
    out.push({
      name: "Минимальная маркировка µmin",
      value: `(${(r.mu_min || []).join(", ")})`,
      segments: [{ tex: markingToTex(r.mu_min) }],
      note: "маркировка минимального срабатывания (по одному разу на переход)",
    });
  }

  return out;
});
</script>

<template>
  <div>
    <div
      v-if="report && report.approximation === 'omega'"
      id="props-caveat"
      class="caveat"
    >
      Дискретная (ω) приближённая оценка — сеть неограниченна
    </div>
    <table v-if="rows.length" id="props" class="props-table">
      <thead>
        <tr>
          <th>Свойство</th>
          <th>Значение</th>
          <th>Пояснение</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.name">
          <td class="props-name">{{ row.name }}</td>
          <td class="props-value">
            <template v-if="row.segments">
              <template v-for="(seg, i) in row.segments" :key="i">
                <Formula v-if="seg.tex" :tex="seg.tex" />
                <span v-else>{{ seg.text }}</span>
              </template>
            </template>
            <span v-else>{{ row.value }}</span>
          </td>
          <td class="props-note">{{ row.note }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">Свойства будут вычислены после построения графа.</p>
  </div>
</template>
