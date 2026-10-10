<script setup>
import { onBeforeUnmount, onMounted } from "vue";
import { store } from "./store";
import { applyTheme, THEME_IDS } from "./theme";
import HomeView from "./components/HomeView.vue";
import NetView from "./components/NetView.vue";
import ThemeSwitcher from "./components/ThemeSwitcher.vue";

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

// Горячие клавиши (FR-615): 1 — «Сеть Петри», 2 — «Задание из практикума»,
// T — циклическая смена темы. Игнорируем, когда фокус в поле ввода.
function isTypingTarget(el) {
  if (!el || !el.tagName) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
}

function cycleTheme() {
  const idx = THEME_IDS.indexOf(store.theme);
  const next = THEME_IDS[(idx + 1) % THEME_IDS.length];
  store.theme = next;
  applyTheme(next);
}

function onKeydown(event) {
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  if (isTypingTarget(document.activeElement)) return;
  if (event.key === "1") {
    switchView("net");
  } else if (event.key === "2") {
    switchView("home");
  } else if (event.key === "t" || event.key === "T") {
    cycleTheme();
  }
}

onMounted(() => {
  document.addEventListener("keydown", onKeydown);
});

onBeforeUnmount(() => {
  document.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <header>
    <h1>Сети Петри</h1>
    <nav class="view-tabs tabs" aria-label="Экраны">
      <button
        type="button"
        class="tab"
        :class="{ active: store.view === 'net' }"
        title="Горячая клавиша: 1"
        @click="switchView('net')"
      >
        Сеть Петри
      </button>
      <button
        type="button"
        class="tab"
        :class="{ active: store.view === 'home' }"
        title="Горячая клавиша: 2"
        @click="switchView('home')"
      >
        Задание из практикума
      </button>
    </nav>
    <ThemeSwitcher />
    <span v-if="store.name || store.sessionId" id="session-badge">
      {{ store.name || store.sessionId }}
    </span>
  </header>

  <main>
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
  </main>
</template>
