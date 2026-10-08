<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import cytoscape from "cytoscape";

const props = defineProps({
  structure: { type: Object, default: null },
  current: { type: Array, default: null },
  deadlocks: { type: Array, default: null },
  selected: { type: Boolean, default: false },
});

const emit = defineEmits(["goto", "select"]);

const el = ref(null);
let cy = null;

function compactMarking(arr) {
  return (arr || []).map((v) => (v === null ? "ω" : String(v))).join(",");
}

function sameMarking(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
  return a.every((v, i) => v === b[i]);
}

function runLayout() {
  const roots = cy.nodes('[id = "n0"]').length
    ? cy.nodes('[id = "n0"]')
    : cy.nodes().slice(0, 1);
  const attempts = [
    {
      name: "breadthfirst",
      roots,
      directed: true,
      spacing: 12,
      animate: false,
      fit: true,
      padding: 4,
    },
    { name: "grid", animate: false, fit: true, padding: 4 },
  ];
  for (const attempt of attempts) {
    try {
      cy.layout(attempt).run();
      return;
    } catch (err) {
      // try the next layout
    }
  }
}

function render() {
  if (cy) {
    cy.destroy();
    cy = null;
  }
  if (!props.structure || !el.value) {
    window.Registry.graph = null;
    return;
  }
  const deadlockSet =
    Array.isArray(props.deadlocks) && props.deadlocks.length
      ? new Set(props.deadlocks.map((m) => JSON.stringify(m)))
      : null;

  const markings = {};
  const elements = [];
  for (const [nodeId, marking] of props.structure.nodes) {
    markings[nodeId] = marking;
    elements.push({
      data: {
        id: nodeId,
        label: compactMarking(marking),
        marking: marking,
        deadlock: deadlockSet !== null && deadlockSet.has(JSON.stringify(marking)),
      },
    });
  }
  for (const [srcId, transition, dstId] of props.structure.edges) {
    elements.push({
      data: {
        id: `${srcId}:${transition}:${dstId}`,
        source: srcId,
        target: dstId,
        label: transition,
      },
    });
  }

  const style = [
    {
      selector: "node",
      style: {
        shape: "round-rectangle",
        width: "14px",
        height: "14px",
        "background-color": "#eef",
        "border-width": "0px",
        label: "data(label)",
        "font-size": "7px",
        color: "#333",
        "text-wrap": "none",
        "text-valign": "bottom",
        "text-halign": "center",
        "text-margin-y": "-3px",
      },
    },
    {
      selector: "node[?deadlock]",
      style: {
        "background-color": "#d33",
        color: "#fff",
      },
    },
    // BUG-3: текущий узел подсвечен
    {
      selector: "node.current",
      style: {
        "background-color": "#1a73e8",
        "border-width": "2px",
        "border-color": "#0d47a1",
        width: "18px",
        height: "18px",
      },
    },
    {
      selector: "edge",
      style: {
        width: "0.5px",
        "line-color": "#888",
        "curve-style": "straight",
        "target-arrow-shape": "triangle",
        label: "data(label)",
        "font-size": "6px",
        color: "#888",
        "text-wrap": "none",
      },
    },
    {
      selector: "edge.current-edge",
      style: {
        width: "1.5px",
        "line-color": "#1a73e8",
        "target-arrow-color": "#1a73e8",
        color: "#0d47a1",
      },
    },
  ];

  cy = cytoscape({
    container: el.value,
    elements,
    style,
    minZoom: 0.05,
    maxZoom: 8,
  });
  window.Registry.graph = cy;
  cy.on("tap", "node", (evt) => {
    const marking = evt.target.data("marking");
    if (Array.isArray(marking)) emit("goto", marking);
  });
  cy.on("tap", "edge", (evt) => {
    const target = evt.target.target();
    const marking = target.data("marking");
    if (Array.isArray(marking)) emit("goto", marking);
  });
  applyCurrent();
  runLayout();
}

function applyCurrent() {
  if (!cy || !props.current) return;
  let found = null;
  for (const node of cy.nodes()) {
    const isCurrent = sameMarking(node.data("marking"), props.current);
    node.toggleClass("current", isCurrent);
    if (isCurrent) found = node;
  }
  cy.edges().forEach((edge) => {
    const onPath =
      found &&
      (edge.source().id() === found.id() || edge.target().id() === found.id());
    edge.toggleClass("current-edge", Boolean(onPath));
  });
}

watch(() => props.structure, render);
watch(() => props.current, applyCurrent);
watch(() => props.deadlocks, render);

onMounted(render);

onBeforeUnmount(() => {
  if (cy) {
    if (window.Registry.graph === cy) window.Registry.graph = null;
    cy.destroy();
    cy = null;
  }
});
</script>

<template>
  <div
    ref="el"
    id="canvas-graph"
    class="canvas"
    :class="{ 'active-canvas': selected }"
    @click="emit('select')"
  ></div>
</template>
