// API client: typed fetch wrapper + Ui helpers (toast, status, escapeHtml).
"use strict";

window.Api = (function () {
  async function request(method, path, body) {
    const res = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = data.error || { code: "unknown", message: res.statusText };
      throw Object.assign(new Error(err.message), {
        code: err.code,
        details: err.details,
        status: res.status,
      });
    }
    return data;
  }

  return {
    request,
    parseSession: (format, payload, name) =>
      request("POST", "/parse", { format, payload, name }),
    buildGraph: (sessionId, mode) =>
      request("POST", "/graph", { session_id: sessionId, mode }),
    getStoredGraph: (sessionId) =>
      request("GET", `/sessions/${sessionId}/graph`),
    analyzeProperties: (sessionId, queries) =>
      request(
        "POST",
        "/properties",
        Object.assign({ session_id: sessionId }, queries ? { queries } : {})
      ),
    fireAction: (sessionId, action, transition) =>
      request("POST", "/fire", { session_id: sessionId, action, transition }),
    gotoMarking: (sessionId, marking) =>
      request("POST", "/goto", { session_id: sessionId, marking }),
    getState: (sessionId) => request("GET", `/state/${sessionId}`),
    listSessions: () => request("GET", "/sessions"),
    getSession: (sessionId) => request("GET", `/sessions/${sessionId}`),
    deleteSession: (sessionId) => request("DELETE", `/sessions/${sessionId}`),
    exportReportUrl: (sessionId) => `/sessions/${sessionId}/export/report`,
    exportMarkingsUrl: (sessionId) => `/sessions/${sessionId}/export/markings`,
  };
})();

window.Ui = (function () {
  let toastTimer = 0;

  function toast(message, isError) {
    const el = document.getElementById("toast");
    if (!el) return;
    el.textContent = message;
    el.classList.toggle("error", Boolean(isError));
    el.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.classList.add("hidden");
    }, 5000);
  }

  function setStatus(text) {
    const el = document.getElementById("status-line");
    if (el) el.textContent = text;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])
    );
  }

  return { toast, setStatus, escapeHtml };
})();
