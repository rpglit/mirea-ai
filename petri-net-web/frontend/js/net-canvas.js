// Net canvas (Cytoscape): places with tokens, transitions, weighted arcs.
"use strict";

window.NetCanvas = (function () {
  const CANVAS_ID = "canvas-net";
  let currentNet = null;

  function placeLabel(name, tokens) {
    return name + " (" + tokens + ")";
  }

  function ensurePrefix(id, prefix) {
    return /^([pt]):/.test(id) ? id : prefix + ":" + id;
  }

  function edgesFromMaps(net) {
    const edges = [];
    (net.transitions || []).forEach(function (t) {
      const inputs = (net.inputs && net.inputs[t]) || {};
      Object.keys(inputs).forEach(function (p) {
        edges.push({
          data: {
            id: "e:in:" + t + ":" + p,
            source: "p:" + p,
            target: "t:" + t,
            weight: inputs[p],
            direction: "input",
          },
        });
      });
      const outputs = (net.outputs && net.outputs[t]) || {};
      Object.keys(outputs).forEach(function (p) {
        edges.push({
          data: {
            id: "e:out:" + t + ":" + p,
            source: "t:" + t,
            target: "p:" + p,
            weight: outputs[p],
            direction: "output",
          },
        });
      });
    });
    return edges;
  }

  function edgesFromArcs(arcs) {
    return arcs.map(function (a) {
      let source = a.source;
      let target = a.target;
      if (a.direction === "input") {
        source = ensurePrefix(source, "p");
        target = ensurePrefix(target, "t");
      } else if (a.direction === "output") {
        source = ensurePrefix(source, "t");
        target = ensurePrefix(target, "p");
      }
      return {
        data: {
          id: "e:" + (a.direction || "arc") + ":" + source + ":" + target,
          source: source,
          target: target,
          weight: a.weight,
          direction: a.direction,
        },
      };
    });
  }

  function buildElements(net) {
    const elements = [];
    (net.places || []).forEach(function (p, i) {
      const tokens = net.marking && net.marking[i] !== undefined ? net.marking[i] : 0;
      elements.push({
        data: {
          id: "p:" + p,
          kind: "place",
          label: placeLabel(p, tokens),
          tokens: tokens,
        },
      });
    });
    (net.transitions || []).forEach(function (t) {
      elements.push({
        data: { id: "t:" + t, kind: "transition", label: t },
      });
    });
    if (Array.isArray(net.arcs) && net.arcs.length) {
      elements.push.apply(elements, edgesFromArcs(net.arcs));
    } else {
      elements.push.apply(elements, edgesFromMaps(net));
    }
    return elements;
  }

  function style() {
    return [
      {
        selector: "node",
        style: {
          "background-color": "#ffffff",
          "border-width": 2,
          "border-color": "#000000",
          label: "data(label)",
          color: "#000000",
          "font-size": 12,
          "text-valign": "bottom",
          "text-halign": "center",
          "text-wrap": "wrap",
          "width": 56,
          "height": 56,
        },
      },
      {
        selector: 'node[kind = "transition"]',
        style: {
          shape: "rectangle",
          "background-color": "#e8eef7",
          "width": 48,
          "height": 48,
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
          label: "data(weight)",
          color: "#222222",
          "font-size": 10,
          "text-background-color": "#ffffff",
          "text-background-opacity": 0.75,
          "text-background-padding": 2,
        },
      },
      {
        selector: 'edge[data(weight) = "1"]',
        style: {
          label: "",
        },
      },
    ];
  }

  function render(net) {
    currentNet = net;
    if (window.Registry) {
      window.Registry = window.Registry || {};
      const previous = window.Registry.net;
      if (previous && typeof previous.destroy === "function") {
        try {
          previous.destroy();
        } catch (err) {
          // ignore already-destroyed instances
        }
      }
    }
    window.Registry = window.Registry || {};

    const cy = cytoscape({
      container: document.getElementById(CANVAS_ID),
      elements: buildElements(net),
      style: style(),
      wheelSensitivity: 0.2,
    });

    window.Registry.net = cy;
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
    return cy;
  }

  function setMarking(markingArray, places) {
    const cy = window.Registry && window.Registry.net;
    if (!cy) return;
    const names =
      places && places.length
        ? places
        : currentNet && currentNet.places
          ? currentNet.places
          : [];
    names.forEach(function (p, i) {
      const n = markingArray && markingArray[i] !== undefined ? markingArray[i] : 0;
      const node = cy.getElementById("p:" + p);
      if (!node.empty()) {
        node.data({ tokens: n, label: placeLabel(p, n) });
      }
    });
  }

  return { render: render, setMarking: setMarking };
})();
