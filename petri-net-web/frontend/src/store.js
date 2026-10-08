// One reactive store per ARCH section 3: the source of truth is the API
// responses; the view is switched without a router (net / home).

import { reactive } from "vue";

export const SMOKE_TEXT = `S = (P, T, I, O, µ),
P = {p1, p2, p3, p4, p5, p6}, T = {t1, t2, t3, t4, t5},
I(t1) = {p1, p1}, O(t1) = {p2},
I(t2) = {p1, p6}, O(t2) = {p3, p3},
I(t3) = {p2},       O(t3) = {p4, p4, p4},
I(t4) = {p2, p3, p4, p4}, O(t4) = {p5, p6},
I(t5) = {p5, p5},   O(t5) = {p1, p3},
µ = (7, 4, 2, 5, 4, 3).`;

export const store = reactive({
  view: "net",
  // net view
  sessionId: null,
  name: "",
  model: null,
  marking: null,
  active: [],
  history: [],
  structure: null,
  structureKind: null,
  graphStats: null,
  report: null,
  queryResult: "",
  rev: 0,
  pendingBuild: false,
  // home view («Задание из практикума»)
  task: null,
  solverReport: null,
  solverBusy: false,
  // ui
  status: "",
  busy: false,
  toast: { text: "", error: false, visible: false },
});

let toastTimer = 0;

export function toast(text, isError = false) {
  store.toast = { text: String(text), error: Boolean(isError), visible: true };
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    store.toast.visible = false;
  }, 6000);
}

export function setStatus(text) {
  store.status = text;
}

export function compactTuple(marking) {
  return (marking || [])
    .map((v) => (v === null || v === undefined ? "ω" : String(v)))
    .join(",");
}

export function tupleEquals(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
  return a.every((v, i) => v === b[i]);
}

export function yesNo(flag) {
  return flag ? "да" : "нет";
}

export function prettyFormula(value) {
  if (value === null || value === undefined) return "—";
  return String(value)
    .replace(/\*\*/g, "^")
    .replace(/(\d)\*(?=\D)/g, "$1·")
    .replace(/\*(?=\d)/g, "·");
}

export function splitCsv(value) {
  return String(value === null || value === undefined ? "" : value)
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

export function toInt(value) {
  const v = parseInt(value, 10);
  return Number.isFinite(v) ? v : null;
}
