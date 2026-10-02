// Sessions panel: list / restore / delete stored sessions.
"use strict";

window.SessionsPanel = (function () {
  let loadFn = null;
  let clearedFn = null;
  let currentId = null;

  function formatDate(value) {
    if (value === null || value === undefined || value === "") return "";
    try {
      const d = new Date(value);
      if (!Number.isNaN(d.getTime())) return d.toLocaleString("ru-RU");
    } catch (err) {
      return String(value);
    }
    return String(value);
  }

  function buildItem(session) {
    const li = document.createElement("li");

    const item = document.createElement("button");
    item.type = "button";
    item.className = "session-item" + (session.session_id === currentId ? " current" : "");
    item.setAttribute("data-session-id", session.session_id);

    const name = document.createElement("span");
    name.className = "session-name";
    name.textContent = session.name || session.session_id;
    item.appendChild(name);

    const formatted = formatDate(session.created_at);
    if (formatted) {
      const date = document.createElement("span");
      date.className = "session-date";
      date.textContent = " · " + formatted;
      item.appendChild(date);
    }

    item.addEventListener("click", function () {
      currentId = session.session_id;
      if (typeof loadFn === "function") loadFn(session.session_id);
    });

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "session-remove";
    removeBtn.setAttribute("data-session-id", session.session_id);
    removeBtn.setAttribute("title", "Удалить сессию");
    removeBtn.textContent = "✕";
    removeBtn.addEventListener("click", function (event) {
      event.stopPropagation();
      remove(session.session_id);
    });

    li.appendChild(item);
    li.appendChild(removeBtn);
    return li;
  }

  async function refresh() {
    const list = document.getElementById("sessions-list");
    if (!list) return;
    let sessions = [];
    try {
      sessions = await Api.listSessions();
    } catch (err) {
      sessions = [];
    }
    list.innerHTML = "";
    (Array.isArray(sessions) ? sessions : []).forEach(function (session) {
      if (session && session.session_id) list.appendChild(buildItem(session));
    });
  }

  async function remove(sessionId) {
    try {
      await Api.deleteSession(sessionId);
    } catch (err) {
      Ui.toast(err.message, true);
      return;
    }
    const wasCurrent = sessionId === currentId;
    if (wasCurrent) currentId = null;
    await refresh();
    if (wasCurrent && typeof clearedFn === "function") clearedFn(sessionId);
  }

  function onLoad(fn) {
    if (typeof fn === "function") loadFn = fn;
  }

  function onCleared(fn) {
    if (typeof fn === "function") clearedFn = fn;
  }

  function setCurrent(sessionId) {
    currentId = sessionId || null;
    const list = document.getElementById("sessions-list");
    if (list) {
      list.querySelectorAll(".session-item").forEach(function (node) {
        node.classList.toggle("current", node.getAttribute("data-session-id") === currentId);
      });
    }
  }

  return {
    refresh: refresh,
    onLoad: onLoad,
    onCleared: onCleared,
    setCurrent: setCurrent,
    remove: remove,
  };
})();
