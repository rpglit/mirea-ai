// API client: fetch wrapper with typed errors (Russian messages from the
// backend, ADR-0006). All error.code values stay English (NFR-107).

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
      suggestion: err.suggestion,
      status: res.status,
    });
  }
  return data;
}

const api = {
  request,
  parseSession: (format, payload, name) =>
    request("POST", "/parse", { format, payload, name }),
  buildGraph: (sessionId, mode) =>
    request("POST", "/graph", { session_id: sessionId, mode }),
  getStoredGraph: (sessionId) =>
    request("GET", `/sessions/${sessionId}/graph`),
  analyzeProperties: (sessionId, queries, withBlock) =>
    request(
      "POST",
      "/properties",
      Object.assign(
        { session_id: sessionId },
        queries ? { queries } : {},
        withBlock ? { with: withBlock } : {}
      )
    ),
  fireAction: (sessionId, action, transition) =>
    request("POST", "/fire", { session_id: sessionId, action, transition }),
  gotoMarking: (sessionId, marking) =>
    request("POST", "/goto", { session_id: sessionId, marking }),
  getState: (sessionId) => request("GET", `/state/${sessionId}`),
  listSessions: (limit) =>
    request("GET", limit ? `/sessions?limit=${limit}` : "/sessions"),
  getSession: (sessionId) => request("GET", `/sessions/${sessionId}`),
  deleteSession: (sessionId) => request("DELETE", `/sessions/${sessionId}`),
  matrices: (sessionId) => request("POST", "/matrices", { session_id: sessionId }),
  minimalMarking: (sessionId, parallel) =>
    request("POST", "/minimal-marking", {
      session_id: sessionId,
      parallel: Boolean(parallel),
    }),
  solve: (taskId, data) =>
    request("POST", "/solve", { task_id: taskId, data }),
  catalog: (group) =>
    request("GET", group ? `/catalog?group=${group}` : "/catalog"),
  exportReportUrl: (sessionId) => `/sessions/${sessionId}/export/report`,
  exportMarkingsUrl: (sessionId) => `/sessions/${sessionId}/export/markings`,
};

export default api;
