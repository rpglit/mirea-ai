<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import cytoscape from "cytoscape";

const props = defineProps({
  graph: { type: Object, default: null },
  path: { type: Array, default: null },
  registryKey: { type: String, default: "automaton" },
});

const el = ref(null);
let cy = null;

function nodeLabel(state) {
  const found = (props.graph.nodes || []).find((n) => n[0] === state);
  if (!found) return state;
  return found[1] ? `${found[0]}/${found[1]}` : found[0];
}

function render() {
  if (cy) {
    cy.destroy();
    cy = null;
  }
  if (!props.graph || !el.value) {
    window.Registry[props.registryKey] = null;
    return;
  }
  const nodes = (props.graph.nodes || []).map(([si, wi]) => ({
    data: {
      id: si,
      kind: "state",
      label: wi ? `${si}/${wi}` : si,
      start: si === props.graph.s0,
    },
  }));
  const edges = (props.graph.edges || []).map(([si, pj, sk, wq], i) => ({
    data: {
      id: `e${i}:${si}-${pj}-${sk}`,
      source: si,
      target: sk,
      label: wq ? `${pj}/${wq}` : pj,
      input: pj,
    },
  }));

  const style = [
    {
      selector: "node",
      style: {
        "background-color": "#ffffff",
        "border-width": 2,
        "border-color": "#000000",
        label: "data(label)",
        color: "#000000",
        "font-size": 14,
        "text-valign": "center",
        "text-halign": "center",
        width: 64,
        height: 64,
      },
    },
    // начальное состояние — двойная обводка
    {
      selector: "node[start]",
      style: {
        "border-width": 5,
        "border-color": "#0d47a1",
      },
    },
    {
      selector: "node.path-state",
      style: {
        "background-color": "#c8e6c9",
      },
    },
    {
      selector: "node.path-current",
      style: {
        "background-color": "#66bb6a",
        "border-color": "#1b5e20",
      },
    },
    {
      selector: "edge",
      style: {
        "curve-style": "bezier",
        "line-color": "#444444",
        "target-arrow-color": "#444444",
        "target-arrow-shape": "triangle",
        width: 1.5,
        label: "data(label)",
        color: "#222222",
        "font-size": 11,
        "text-background-color": "#ffffff",
        "text-background-opacity": 0.75,
        "text-background-padding": 2,
      },
    },
    {
      selector: "edge.path-edge",
      style: {
        "line-color": "#2e7d32",
        "target-arrow-color": "#2e7d32",
        width: 3,
        color: "#1b5e20",
      },
    },
  ];

  cy = cytoscape({
    container: el.value,
    elements: [...nodes, ...edges],
    style,
  });
  window.Registry[props.registryKey] = cy;
  cy.layout({
    name: "cose",
    animate: false,
    fit: true,
    quality: "good",
    randomize: false,
    nodeRepulsion: 6000,
    idealEdgeLength: 110,
    padding: 30,
  }).run();
  cy.fit(undefined, 30);
  applyPath();
}

function applyPath() {
  if (!cy) return;
  cy.nodes().removeClass("path-state path-current");
  cy.edges().removeClass("path-edge");
  if (!Array.isArray(props.path) || !props.path.length) return;
  const visited = new Set(props.path);
  cy.nodes().forEach((node) => {
    if (visited.has(node.id())) node.addClass("path-state");
  });
  const last = props.path[props.path.length - 1];
  const current = cy.getElementById(last);
  if (!current.empty()) current.addClass("path-current");
  for (let i = 1; i < props.path.length; i += 1) {
    const from = props.path[i - 1];
    const to = props.path[i];
    cy.edges()
      .filter((edge) => edge.data("source") === from && edge.data("target") === to)
      .addClass("path-edge");
  }
}

watch(() => props.graph, render, { deep: true });
watch(() => props.path, applyPath);

onMounted(render);

onBeforeUnmount(() => {
  if (cy) {
    if (window.Registry[props.registryKey] === cy) window.Registry[props.registryKey] = null;
    cy.destroy();
    cy = null;
  }
});
</script>

<template>
  <div ref="el" class="canvas" style="height: 340px"></div>

</template>
