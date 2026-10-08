<script setup>
import { store, toast } from "../store";

const props = defineProps({
  sessionId: { type: String, default: null },
  activeCanvas: { type: String, default: "net" },
});

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// BUG-1: cy.png() с output: "blob-promise" возвращает Blob
async function pngOf(key, filename) {
  const cy = window.Registry[key];
  if (!cy) return false;
  const blob = await cy.png({ output: "blob-promise", scale: 2, bg: "#ffffff" });
  downloadBlob(blob, filename);
  return true;
}

async function exportPng() {
  if (props.activeCanvas === "net") {
    try {
      await pngOf("net", "net.png");
    } catch (err) {
      toast("PNG: " + err.message, true);
    }
  } else {
    try {
      await pngOf("graph", "reachability.png");
    } catch (err) {
      toast("PNG: " + err.message, true);
    }
  }
}

async function exportAllPng() {
  const keys = [
    ["net", "net.png"],
    ["graph", "reachability.png"],
    ["automaton", "automaton.png"],
  ].filter(([key]) => window.Registry[key]);
  if (!keys.length) {
    toast("Нет построенных канвасов для PNG", true);
    return;
  }
  for (const [key, filename] of keys) {
    try {
      // small pause so the browser saves each download separately
      await pngOf(key, filename);
      await new Promise((resolve) => setTimeout(resolve, 300));
    } catch (err) {
      toast(`PNG ${filename}: ${err.message}`, true);
    }
  }
}

async function downloadFrom(url, filename) {
  const res = await fetch(url);
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const err = data.error || { message: res.statusText };
    throw new Error(err.message);
  }
  downloadBlob(await res.blob(), filename);
}

async function exportJson() {
  if (!props.sessionId) {
    toast("Нет активной сессии", true);
    return;
  }
  try {
    await downloadFrom(`/sessions/${props.sessionId}/export/report`, "report.json");
  } catch (err) {
    toast(err.message, true);
  }
}

async function exportCsv() {
  if (!props.sessionId) {
    toast("Нет активной сессии", true);
    return;
  }
  try {
    await downloadFrom(`/sessions/${props.sessionId}/export/markings`, "markings.csv");
  } catch (err) {
    toast(err.message, true);
  }
}
</script>

<template>
  <div>
    <button type="button" id="btn-export-png" @click="exportPng">
      PNG {{ activeCanvas === "net" ? "сети" : "графа" }}
    </button>
    <button type="button" id="btn-export-all-png" @click="exportAllPng">PNG всех</button>
    <button type="button" id="btn-export-json" @click="exportJson">JSON отчёта</button>
    <button type="button" id="btn-export-csv" @click="exportCsv">CSV маркировок</button>
  </div>

</template>
