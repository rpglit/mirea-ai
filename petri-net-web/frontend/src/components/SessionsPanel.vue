<script setup>
import { onMounted, ref } from "vue";
import api from "../api";
import { store, toast } from "../store";

const emit = defineEmits(["open", "cleared"]);

const visible = ref(false);
const sessions = ref([]);

function formatDate(value) {
  if (value === null || value === undefined || value === "") return "";
  try {
    const d = new Date(value);
    if (!Number.isNaN(d.getTime())) return d.toLocaleString("ru-RU");
  } catch (err) {
    return String(value);
  }
  return String(value);
}

async function refresh() {
  try {
    sessions.value = await api.listSessions(50);
  } catch (err) {
    sessions.value = [];
  }
}

async function remove(session) {
  try {
    await api.deleteSession(session.session_id);
  } catch (err) {
    toast(err.message, true);
    return;
  }
  await refresh();
  if (session.session_id === store.sessionId) emit("cleared", session.session_id);
}

function toggle() {
  visible.value = !visible.value;
  if (visible.value) refresh();
}

onMounted(refresh);
</script>

<template>
  <div>
    <button type="button" id="btn-sessions" @click="toggle">История сессий</button>
    <div id="sessions-panel" v-show="visible">
      <ul id="sessions-list">
        <li v-for="session in sessions" :key="session.session_id">
          <button
            type="button"
            class="session-item"
            :class="{ current: session.session_id === store.sessionId }"
            :data-session-id="session.session_id"
            @click="emit('open', session.session_id)"
          >
            <span class="session-name">{{ session.name || session.session_id }}</span>
            <span v-if="formatDate(session.created_at)" class="session-date">
              · {{ formatDate(session.created_at) }}
            </span>
          </button>
          <button
            type="button"
            class="session-remove"
            title="Удалить сессию"
            @click="remove(session)"
          >
            ✕
          </button>
        </li>
        <li v-if="!sessions.length" class="muted">Сессий пока нет</li>
      </ul>
    </div>
  </div>
</template>
