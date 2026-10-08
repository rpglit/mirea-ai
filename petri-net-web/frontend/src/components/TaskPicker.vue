<script setup>
import { onMounted, ref } from "vue";
import api from "../api";
import { store } from "../store";

const emit = defineEmits(["select"]);

const items = ref([]);
const group = ref(null);
const loading = ref(true);
const error = ref("");

async function load() {
  loading.value = true;
  error.value = "";
  try {
    items.value = await api.catalog(group.value);
  } catch (err) {
    error.value = err.message;
  } finally {
    loading.value = false;
  }
}

function setGroup(value) {
  group.value = value;
  load();
}

onMounted(load);
</script>

<template>
  <div>
    <div class="catalog-filters">
      <button type="button" class="tab" :class="{ active: group === null }" @click="setGroup(null)">
        Все (71)
      </button>
      <button type="button" class="tab" :class="{ active: group === 'PN' }" @click="setGroup('PN')">
        Сети Петри (40)
      </button>
      <button type="button" class="tab" :class="{ active: group === 'LSS' }" @click="setGroup('LSS')">
        ЛСС (23)
      </button>
      <button type="button" class="tab" :class="{ active: group === 'FA' }" @click="setGroup('FA')">
        Автоматы (8)
      </button>
    </div>

    <p v-if="loading" class="muted">Загрузка каталога…</p>
    <p v-else-if="error" class="status">{{ error }}</p>
    <div v-else class="task-grid">
      <article
        v-for="t in items"
        :key="t.task_id"
        class="task-card"
        :class="{ selected: store.task && store.task.task_id === t.task_id }"
      >
        <button type="button" @click="emit('select', t)">Решить</button>
        <h3>{{ t.task_id }} — {{ t.title }}</h3>
        <p class="task-meta">{{ t.source }} · {{ t.type }} · {{ t.group }}</p>
      </article>
    </div>
  </div>
</template>
