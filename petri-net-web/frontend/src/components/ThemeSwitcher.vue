<script setup>
import { store } from "../store";
import { applyTheme } from "../theme";

function onChange() {
  applyTheme(store.theme);
}
</script>

<template>
  <span class="theme-switcher">
    <span class="theme-switcher-label">Тема</span>
    <select
      class="theme-select"
      aria-label="Тема"
      v-model="store.theme"
      @change="onChange"
    >
      <option value="light">Светлая</option>
      <option value="dark">Тёмная</option>
      <option value="system">Системная</option>
      <option value="tokyo-night">Tokyo Night</option>
      <option value="catppuccin-mocha">Catppuccin Mocha</option>
      <option value="synthwave84">Synthwave '84</option>
    </select>
  </span>
</template>
