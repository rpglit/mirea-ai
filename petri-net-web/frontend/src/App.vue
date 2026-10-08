<script setup>
import { store } from "./store";
import HomeView from "./components/HomeView.vue";
import NetView from "./components/NetView.vue";

function switchView(view) {
  store.view = view;
  setTimeout(() => {
    const registry = window.Registry;
    ["net", "graph", "automaton"].forEach((key) => {
      const cy = registry && registry[key];
      if (cy && typeof cy.resize === "function") {
        try {
          cy.resize();
        } catch (err) {
          // canvas may be mid-destroy; the next render fixes it
        }
      }
    });
  }, 50);
}
</script>

<template>
  <header>
    <h1>Сети Петри</h1>
    <nav class="view-tabs tabs">
      <button
        type="button"
        class="tab"
        :class="{ active: store.view === 'net' }"
        @click="switchView('net')"
      >
        Сеть Петри
      </button>
      <button
        type="button"
        class="tab"
        :class="{ active: store.view === 'home' }"
        @click="switchView('home')"
      >
        Задание из практикума
      </button>
    </nav>
    <span v-if="store.name || store.sessionId" id="session-badge">
      {{ store.name || store.sessionId }}
    </span>
  </header>

  <p id="status-line" class="status" role="status">{{ store.status }}</p>

  <NetView v-show="store.view === 'net'" />
  <HomeView v-show="store.view === 'home'" />

  <div
    id="toast"
    class="toast"
    :class="{ hidden: !store.toast.visible, error: store.toast.error }"
    role="alert"
  >
    {{ store.toast.text }}
  </div>
</template>
