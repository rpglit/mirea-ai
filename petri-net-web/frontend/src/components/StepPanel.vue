<script setup>
import { compactTuple } from "../store";

const props = defineProps({
  active: { type: Array, default: () => [] },
  history: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
});

const emit = defineEmits(["fire", "undo", "reset", "goto"]);

function lineText(step) {
  const from = compactTuple(step.from);
  const to = compactTuple(step.to);
  if (step.kind === "goto" || step.transition === null || step.transition === undefined) {
    return `${from} ⇢ ${to} (переход по клику)`;
  }
  return `${from} → ${to} (${step.transition})`;
}

function fireFirst() {
  if (!props.active.length) {
    return;
  }
  emit("fire", props.active[0]);
}

function onHistoryClick(step, index) {
  if (!Array.isArray(step.to)) return;
  emit("goto", step.to);
}
</script>

<template>
  <div>
    <div id="active-list" class="transition-buttons">
      <template v-if="!loading">
        <button
          v-for="t in active"
          :key="t"
          type="button"
          class="btn-transition"
          :title="`Сработать ${t} (один клик)`"
          @click="emit('fire', t)"
        >
          {{ t }}
        </button>
      </template>
      <span v-if="loading" class="muted">Загрузка…</span>
      <span v-else-if="!active.length" class="muted">нет разрешённых переходов</span>
    </div>

    <div class="step-buttons">
      <button
        type="button"
        id="btn-step"
        class="primary"
        :disabled="!active.length"
        @click="fireFirst"
      >
        Срабатывание
      </button>
      <button type="button" id="btn-undo" @click="emit('undo')">Отмена</button>
      <button type="button" id="btn-reset" @click="emit('reset')">Сброс</button>
      <span class="muted">клик или Enter по шагу истории восстанавливает его состояние</span>
    </div>

    <div id="history-list" class="history">
      <button
        v-for="(step, i) in history"
        :key="i"
        type="button"
        class="history-line"
        :title="`Шаг ${i + 1}: восстановить состояние (Enter)`"
        @click="onHistoryClick(step, i)"
      >
        {{ lineText(step) }}
      </button>
    </div>
  </div>
</template>
