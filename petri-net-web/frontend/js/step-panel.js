// Step panel: active transitions, step/undo/reset buttons, step history.
"use strict";

window.StepPanel = (function () {
  let selectedTransition = null;
  let lastFirePayload = null;
  let actionCallback = null;
  let wired = false;

  function compactTuple(marking) {
    return marking
      .map(function (v) {
        return v === null || v === undefined ? "ω" : String(v);
      })
      .join(",");
  }

  function stepLine(step) {
    const from = compactTuple(step.from);
    const to = compactTuple(step.to);
    if (step.kind === "goto" || step.transition === null || step.transition === undefined) {
      return from + " ⇢ " + to + " (переход по клику)";
    }
    return from + " → " + to + " (" + window.Ui.escapeHtml(step.transition) + ")";
  }

  function renderHistory(history) {
    const list = document.getElementById("history-list");
    if (!list) return;
    if (!history || !history.length) {
      list.innerHTML = "";
      return;
    }
    list.innerHTML = history
      .map(function (step) {
        return '<div class="history-line">' + stepLine(step) + "</div>";
      })
      .join("");
  }

  function applySelection() {
    const list = document.getElementById("active-list");
    if (!list) return;
    const buttons = list.querySelectorAll("button.btn-transition");
    for (let i = 0; i < buttons.length; i += 1) {
      const isSelected = buttons[i].getAttribute("data-transition") === selectedTransition;
      buttons[i].classList.toggle("selected", isSelected);
      buttons[i].classList.toggle("active", isSelected);
    }
  }

  function renderActive(activeTransitions) {
    const list = document.getElementById("active-list");
    if (!list) return;
    if (selectedTransition !== null && activeTransitions.indexOf(selectedTransition) === -1) {
      selectedTransition = null;
    }
    list.innerHTML = activeTransitions
      .map(function (t) {
        const isSelected = t === selectedTransition;
        const cls = isSelected ? "btn-transition selected active" : "btn-transition";
        return (
          '<button type="button" class="' + cls + '" data-transition="' + window.Ui.escapeHtml(t) + '">' +
          window.Ui.escapeHtml(t) +
          "</button>"
        );
      })
      .join("");
  }

  function wireOnce() {
    if (wired) return;
    wired = true;

    const activeList = document.getElementById("active-list");
    if (activeList) {
      activeList.addEventListener("click", function (event) {
        const target = event.target;
        if (!target || target.tagName !== "BUTTON") return;
        const t = target.getAttribute("data-transition");
        if (t === null) return;
        selectedTransition = t;
        applySelection();
      });
    }

    const stepBtn = document.getElementById("btn-step");
    if (stepBtn) {
      stepBtn.addEventListener("click", function () {
        if (!actionCallback) return;
        if (selectedTransition === null) {
          window.Ui.toast("Сначала выберите активный переход", true);
          return;
        }
        actionCallback("fire", selectedTransition);
      });
    }

    const undoBtn = document.getElementById("btn-undo");
    if (undoBtn) {
      undoBtn.addEventListener("click", function () {
        if (actionCallback) actionCallback("undo", null);
      });
    }

    const resetBtn = document.getElementById("btn-reset");
    if (resetBtn) {
      resetBtn.addEventListener("click", function () {
        if (actionCallback) actionCallback("reset", null);
      });
    }
  }

  function render(activeTransitions, historyTail) {
    const transitions = Array.isArray(activeTransitions) ? activeTransitions : [];
    lastFirePayload = {
      active_transitions: transitions,
      history_tail: Array.isArray(historyTail) ? historyTail : [],
    };
    wireOnce();
    renderActive(transitions);
    if (historyTail !== undefined && historyTail !== null) {
      renderHistory(historyTail);
    }
  }

  function onAction(fn) {
    actionCallback = fn;
    wireOnce();
  }

  function setFullHistory(historyArray) {
    renderHistory(Array.isArray(historyArray) ? historyArray : []);
  }

  return {
    render: render,
    onAction: onAction,
    setFullHistory: setFullHistory,
  };
})();
