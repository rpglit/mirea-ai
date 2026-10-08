<script setup>
import { computed } from "vue";
import { compactTuple, yesNo } from "../store";

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

  out.push({
    name: "k-ограниченная",
    value:
      r.global_k === null || r.global_k === undefined
        ? "неограничена (k = ω)"
        : `k = ${r.global_k}`,
    note: "количество меток в каждой позиции не превышает некоторое целое k",
  });

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
      note: "",
    });
  }

  out.push({
    name: "Безопасная",
    value: r.safe ? "да (k = 1)" : "нет",
    note: "каждая позиция содержит не более одной метки",
  });

  out.push({
    name: "Консервативная",
    value: yesNo(Boolean(r.conservative)),
    note: "сумма меток во всех позициях постоянна; на каждом переходе число входных дуг равно числу выходных",
  });

  const deadlocks = Array.isArray(r.deadlocks) ? r.deadlocks : [];
  out.push({
    name: "Тупики",
    value: deadlocks.length
      ? `${deadlocks.length}: ${deadlocks.map((m) => `(${compactTuple(m)})`).join(", ")}`
      : "0 (нет)",
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
          <td class="props-value">{{ row.value }}</td>
          <td class="props-note">{{ row.note }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">Свойства будут вычислены после построения графа.</p>
  </div>
</template>
