// ShelfAnalytics frontend configuration.
// When FastAPI serves this frontend, API calls use the same origin. When the
// frontend is served separately for development, common frontend ports fall
// back to the backend on port 8000. To force another backend, set
// window.API_BASE before this script loads.
(function () {
  if (window.API_BASE !== undefined) {
    return;
  }

  const standaloneFrontendPorts = new Set(["3000", "3001", "5173"]);
  window.API_BASE = standaloneFrontendPorts.has(location.port)
    ? location.protocol + "//" + location.hostname + ":8000"
    : "";
})();
