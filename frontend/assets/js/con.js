const API_BASE = window.API_BASE || "";

    const thresholdText = document.getElementById("thresholdText");
    const statusText = document.getElementById("statusText");
    const tableWrap = document.getElementById("tableWrap");
    const limitSelect = document.getElementById("limitSelect");
    const refreshBtn = document.getElementById("refreshBtn");

    refreshBtn.addEventListener("click", loadConfidence);
    limitSelect.addEventListener("change", loadConfidence);
    loadConfidence();

    async function loadConfidence() {
      refreshBtn.disabled = true;
      statusText.textContent = "Loading...";

      try {
        const response = await fetch(API_BASE + "/api/confidence?limit=" + encodeURIComponent(limitSelect.value));
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || data.error || "Failed to load confidence records.");
        }

        thresholdText.textContent = "Current unknown threshold: below " + Math.round(data.threshold * 100) + "% confidence is treated as Unknown.";
        renderTable(data.records || []);
        statusText.textContent = "Updated " + new Date().toLocaleTimeString();
      } catch (error) {
        tableWrap.innerHTML = '<div class="empty">' + esc(error.message || "Failed to load confidence records.") + '</div>';
        statusText.textContent = "";
      } finally {
        refreshBtn.disabled = false;
      }
    }

    function renderTable(records) {
      if (records.length === 0) {
        tableWrap.innerHTML = '<div class="empty">No confidence records found yet.</div>';
        return;
      }

      const rows = records.map((item) => {
        const confidence = Number(item.confidence || 0);
        const statusClass = item.is_unknown ? "unknown" : "known";
        const statusText = item.is_unknown ? "Unknown" : "Known";
        return (
          "<tr>" +
            "<td>" + esc(item.filename || "") + "</td>" +
            "<td>" + esc(item.predicted_label || "Unknown") + "</td>" +
            '<td class="confidence">' + esc((confidence * 100).toFixed(2) + "%") + "</td>" +
            '<td class="' + statusClass + '">' + statusText + "</td>" +
            "<td>" + esc(item.reason || "") + "</td>" +
          "</tr>"
        );
      }).join("");

      tableWrap.innerHTML =
        "<table>" +
          "<thead>" +
            "<tr>" +
              "<th>File</th>" +
              "<th>Prediction</th>" +
              "<th>Confidence</th>" +
              "<th>Status</th>" +
              "<th>Reason</th>" +
            "</tr>" +
          "</thead>" +
          "<tbody>" + rows + "</tbody>" +
        "</table>";
    }

    function esc(value) {
      const div = document.createElement("div");
      div.textContent = String(value);
      return div.innerHTML;
    }
