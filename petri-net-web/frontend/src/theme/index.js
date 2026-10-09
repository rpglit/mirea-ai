// Тема оформления: единый источник для CSS (data-theme) и JS-палитр Cytoscape.
// Сохранённый выбор (localStorage) ∈ THEME_IDS; в DOM живёт только effective-тема.

import { computed, ref } from "vue";

const STORAGE_KEY = "pn-theme";
const THEME_IDS = [
  "light",
  "dark",
  "system",
  "tokyo-night",
  "catppuccin-mocha",
  "synthwave84",
];

const media = window.matchMedia("(prefers-color-scheme: dark)");
const systemDark = ref(media.matches);

export function isThemeId(value) {
  return THEME_IDS.includes(value);
}

export function savedTheme() {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return isThemeId(value) ? value : "system";
  } catch (err) {
    return "system";
  }
}

const saved = ref(savedTheme());

const effective = computed(() =>
  saved.value === "system" ? (systemDark.value ? "dark" : "light") : saved.value
);

export function effectiveTheme() {
  return effective.value;
}

export function applyTheme(theme) {
  const id = isThemeId(theme) ? theme : "system";
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch (err) {
    // localStorage недоступен — тема действует сессионно
  }
  saved.value = id;
  document.documentElement.dataset.theme = effective.value;
  return effective.value;
}

media.addEventListener("change", (event) => {
  systemDark.value = event.matches;
  if (saved.value === "system") {
    applyTheme("system");
  }
});
