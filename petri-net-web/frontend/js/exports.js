// Exports: PNG (Cytoscape), JSON report, CSV markings; window.Registry for canvas instances.
"use strict";

window.Registry = {};

window.Exports = (function () {
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

  async function downloadReport(sessionId) {
    const res = await fetch(Api.exportReportUrl(sessionId));
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      const err = data.error || { message: res.statusText };
      throw new Error(err.message);
    }
    const blob = await res.blob();
    downloadBlob(blob, "report.json");
  }

  async function downloadMarkings(sessionId) {
    const res = await fetch(Api.exportMarkingsUrl(sessionId));
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      const err = data.error || { message: res.statusText };
      throw new Error(err.message);
    }
    const blob = await res.blob();
    downloadBlob(blob, "markings.csv");
  }

  async function exportPng(canvasKey) {
    const cy = window.Registry[canvasKey];
    if (!cy) {
      Ui.toast("Канвас ещё не построен", true);
      return;
    }
    const blob = await new Promise((resolve, reject) =>
      cy.png({ outputType: "png", scale: 2, bg: "#ffffff" }).then(resolve, reject)
    );
    downloadBlob(blob, canvasKey === "net" ? "net.png" : "reachability.png");
  }

  return { downloadBlob, downloadReport, downloadMarkings, exportPng };
})();
