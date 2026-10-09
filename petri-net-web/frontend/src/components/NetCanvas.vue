<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import cytoscape from "cytoscape";
import { effectiveTheme } from "../theme";
import { GRAPH_PALETTES } from "../theme/palettes";

const props = defineProps({
  net: { type: Object, default: null },
  marking: { type: Array, default: null },
  active: { type: Array, default: () => [] },
  firing: { type: Object, default: null },
  selected: { type: Boolean, default: false },
});

const emit = defineEmits(["fire", "select"]);

const el = ref(null);
let cy = null;
let fireTimer = 0;

function placeLabel(name, tokens) {
  return `${name} (${tokens})`;
}

function edgeLabel(direction, weight, delay) {
  const parts = [];
  if (weight !== undefined && weight > 1) parts.push(String(weight));
  if (delay !== undefined && delay !== null) parts.push(`τ${delay}`);
  return parts.join(" ");
}

function buildElements(net) {
  const elements = [];
  (net.places || []).forEach((p, i) => {
    const tokens =
      props.marking && props.marking[i] !== undefined ? props.marking[i] : 0;
    elements.push({
      data: { id: `p:${p}`, kind: "place", label: placeLabel(p, tokens) },
    });
  });
  (net.transitions || []).forEach((t) => {
    elements.push({
      data: { id: `t:${t}`, kind: "transition", label: t, active: false },
    });
  });
  (net.transitions || []).forEach((t) => {
    const inputs = (net.inputs && net.inputs[t]) || {};
    Object.keys(inputs).forEach((p) => {
      elements.push({
        data: {
          id: `e:in:${t}:${p}`,
          source: `p:${p}`,
          target: `t:${t}`,
          direction: "input",
          label: edgeLabel("input", inputs[p]),
        },
      });
    });
    const outputs = (net.outputs && net.outputs[t]) || {};
    Object.keys(outputs).forEach((p) => {
      const delay = net.delays && net.delays[t] ? net.delays[t][p] : undefined;
      elements.push({
        data: {
          id: `e:out:${t}:${p}`,
          source: `t:${t}`,
          target: `p:${p}`,
          direction: "output",
          label: edgeLabel("output", outputs[p], delay),
        },
      });
    });
    const inhibitors = (net.inhibitors && net.inhibitors[t]) || [];
    inhibitors.forEach((p) => {
      elements.push({
        data: {
          id: `e:inh:${t}:${p}`,
          source: `p:${p}`,
          target: `t:${t}`,
          direction: "inhibitor",
          label: "",
        },
      });
    });
  });
  return elements;
}

function style(palette) {
  return [
    {
      selector: "node",
      style: {
        "background-color": palette.nodeFill,
        "border-width": 2,
        "border-color": palette.nodeBorder,
        label: "data(label)",
        color: palette.nodeLabel,
        "font-size": 12,
        "text-valign": "bottom",
        "text-halign": "center",
        "text-wrap": "wrap",
        width: 56,
        height: 56,
      },
    },
    {
      selector: 'node[kind = "transition"]',
      style: {
        shape: "rectangle",
        "background-color": palette.transitionFill,
        color: palette.transitionLabel,
        width: 48,
        height: 48,
      },
    },
    // BUG-10: разрешённые переходы — зелёным
    {
      selector: 'node[kind = "transition"].active',
      style: {
        "background-color": palette.activeFill,
        "border-color": palette.activeBorder,
        "border-width": 3,
        color: palette.activeStrong,
      },
    },
    {
      selector: 'node[kind = "transition"].firing',
      style: {
        "background-color": palette.firingFill,
        "border-color": palette.activeStrong,
        width: 58,
        height: 58,
      },
    },
    {
      selector: "edge",
      style: {
        "curve-style": "bezier",
        "line-color": palette.edge,
        "target-arrow-color": palette.edge,
        "target-arrow-shape": "triangle",
        width: 1.5,
        label: "data(label)",
        color: palette.edgeLabel,
        "font-size": 10,
        "text-background-color": palette.edgeLabelBg,
        "text-background-opacity": 0.75,
        "text-background-padding": 2,
      },
    },
    {
      selector: 'edge[direction = "inhibitor"]',
      style: {
        "line-style": "dashed",
        "target-arrow-shape": "tee",
        "line-color": palette.inhibitor,
        "target-arrow-color": palette.inhibitor,
      },
    },
  ];
}

function render() {
  if (cy) {
    cy.destroy();
    cy = null;
  }
  if (!props.net || !el.value) {
    window.Registry.net = null;
    return;
  }
  cy = cytoscape({
    container: el.value,
    elements: buildElements(props.net),
    style: style(GRAPH_PALETTES[effectiveTheme()]),
  });
  window.Registry.net = cy;
  cy.on("tap", 'node[kind = "transition"]', (evt) => {
    const name = evt.target.id().slice(2);
    emit("fire", name);
  });
  cy.on("tap", (evt) => {
    if (evt.target === cy) emit("select");
  });
  cy.layout({
    name: "cose",
    animate: false,
    fit: true,
    quality: "good",
    randomize: false,
    nodeRepulsion: 8000,
    idealEdgeLength: 90,
    padding: 30,
  }).run();
  cy.fit(undefined, 30);
  // the container may still settle its size after mount — refit once
  setTimeout(() => {
    if (cy) cy.fit(undefined, 30);
  }, 150);
  applyActive();
}

function applyActive() {
  if (!cy) return;
  (props.net ? props.net.transitions || [] : []).forEach((t) => {
    const node = cy.getElementById(`t:${t}`);
    if (node.empty()) return;
    node.toggleClass("active", props.active.includes(t));
  });
}

function applyMarking() {
  if (!cy || !props.marking) return;
  (props.net ? props.net.places || [] : []).forEach((p, i) => {
    const n = props.marking[i] !== undefined ? props.marking[i] : 0;
    const node = cy.getElementById(`p:${p}`);
    if (!node.empty()) node.data("label", placeLabel(p, n));
  });
}

function applyFiring() {
  if (!cy) return;
  clearTimeout(fireTimer);
  if (props.firing) {
    const node = cy.getElementById(`t:${props.firing.t}`);
    if (!node.empty()) {
      node.addClass("firing");
      fireTimer = setTimeout(() => {
        node.removeClass("firing");
      }, 250);
    }
  }
}

function restyleTheme() {
  if (!cy) return;
  cy.style(style(GRAPH_PALETTES[effectiveTheme()]));
}

function fitNow() {
  if (!cy || !el.value) return;
  const rect = el.value.getBoundingClientRect();
  if (!rect || (rect.width === 0 && rect.height === 0)) return;
  try {
    cy.resize();
    cy.fit(undefined, 30);
  } catch (err) {
    // канвас может быть скрыт (v-show) или разрушаться — следующий render починит
  }
}

let resizeTimer = 0;
function onWindowResize() {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(fitNow, 200);
}

watch(effectiveTheme, restyleTheme);
watch(() => props.net, render, { deep: true });
watch(() => props.marking, () => {
  applyMarking();
  applyActive();
});
watch(() => props.active, applyActive);
watch(() => props.firing, applyFiring);

onMounted(() => {
  render();
  window.addEventListener("resize", onWindowResize);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", onWindowResize);
  clearTimeout(resizeTimer);
  clearTimeout(fireTimer);
  if (cy) {
    if (window.Registry.net === cy) window.Registry.net = null;
    cy.destroy();
    cy = null;
  }
});
</script>

<template>
  <div
    ref="el"
    id="canvas-net"
    class="canvas"
    :class="{ 'active-canvas': selected }"
    @click="emit('select')"
  ></div>
</template>
