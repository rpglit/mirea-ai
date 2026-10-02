// Reachability graph canvas (Cytoscape): markings as nodes, click -> goto.
"use strict";

window.GraphCanvas = (function () {
  let markings = {};
  const clickHandlers = [];

  function compactMarking(arr) {
    return arr
      .map((v) => (v === null ? "\u03c9" : String(v)))
      .join(",");
  }

  function runLayout(cy) {
    const attempts = [
      {
        name: "breadthfirst",
        roots: ["n0"],
        directed: true,
        spacing: 12,
        animate: false,
        fit: true,
        padding: 4,
      },
      { name: "grid", animate: false, fit: true, padding: 4 },
    ];
    for (let i = 0; i < attempts.length; i++) {
      try {
        cy.layout(attempts[i]).run();
        return;
      } catch (e) {
        /* try next */
      }
    }
  }

  function render(structure, deadlocks) {
    const previous = window.Registry.graph;
    if (previous && typeof previous.destroy === "function") {
      previous.destroy();
    }

    const deadlockSet =
      Array.isArray(deadlocks) && deadlocks.length
        ? new Set(deadlocks.map((m) => JSON.stringify(m)))
        : null;

    markings = {};
    const elements = [];

    for (const [nodeId, marking] of structure.nodes) {
      markings[nodeId] = marking;
      elements.push({
        data: {
          id: nodeId,
          label: compactMarking(marking),
          marking: marking,
          deadlock:
            deadlockSet !== null &&
            deadlockSet.has(JSON.stringify(marking)),
        },
      });
    }

    for (const [srcId, transition, dstId] of structure.edges) {
      elements.push({
        data: {
          id: srcId + ":" + transition + ":" + dstId,
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
          "shape": "round-rectangle",
          "width": "14px",
          "height": "14px",
          "background-color": "#eef",
          "border-width": "0px",
          "label": "data(label)",
          "font-size": "7px",
          "color": "#333",
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
          "color": "#fff",
        },
      },
      {
        selector: "edge",
        style: {
          "width": "0.5px",
          "line-color": "#888",
          "curve-style": "straight",
          "target-arrow-shape": "triangle",
          "target-arrow-scale": "0.5",
          "label": "data(label)",
          "font-size": "6px",
          "color": "#888",
          "text-wrap": "none",
        },
      },
    ];

    const cy = window.cytoscape({
      container: document.getElementById("canvas-graph"),
      elements: elements,
      style: style,
      minZoom: 0.05,
      maxZoom: 8,
      wheelSensitivity: 0.2,
    });

    cy.on("tap", "node", (evt) => {
      const nodeId = evt.target.id();
      const marking = Object.prototype.hasOwnProperty.call(markings, nodeId)
        ? markings[nodeId]
        : null;
      for (const fn of clickHandlers) {
        try {
          fn(nodeId, marking);
        } catch (e) {
          /* ignore handler errors */
        }
      }
    });

    window.Registry.graph = cy;
    runLayout(cy);
    return cy;
  }

  function nodeMarking(nodeId) {
    return Object.prototype.hasOwnProperty.call(markings, nodeId)
      ? markings[nodeId]
      : null;
  }

  function onNodeClick(fn) {
    if (typeof fn === "function") {
      clickHandlers.push(fn);
    }
  }

  return { render, nodeMarking, onNodeClick };
})();
