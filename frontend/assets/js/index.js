const API_BASE = window.API_BASE || "";

    const getTaskReportBtn = document.getElementById("getTaskReportBtn");
    const taskLog = document.getElementById("taskLog");
    const taskErrorMsg = document.getElementById("taskErrorMsg");
    const shopPath = document.getElementById("shopPath");
    const batchReportCard = document.getElementById("batchReportCard");
    const batchMetrics = document.getElementById("batchMetrics");
    const batchTableWrap = document.getElementById("batchTableWrap");
    const downloadTaskPdfBtn = document.getElementById("downloadTaskPdfBtn");

    const activeLabels = document.getElementById("activeLabels");

    let currentTaskReportData = null;
    let configuredLabels = [];



    loadActiveLabels();
    loadTaskShops();



    async function loadActiveLabels() {
      try {
        const response = await fetch(API_BASE + "/api/labels");
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || data.error || "Failed to load labels.");
        }

        activeLabels.innerHTML = "";
        configuredLabels = data.labels || [];
        configuredLabels.forEach((label) => {
          activeLabels.appendChild(chip(label));
        });
      } catch (error) {
        taskErrorMsg.textContent = error.message || "Failed to load labels.";
        taskErrorMsg.style.display = "block";
      }
    }

    async function loadTaskShops() {
      try {
        const response = await fetch(API_BASE + "/api/task-shops");
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || data.error || "Failed to load shop folders.");
        }
        const shopCount = (data.shops || []).length;
        shopPath.textContent = data.image_root + " | " + shopCount + " shop folder" + (shopCount === 1 ? "" : "s");
      } catch (error) {
        taskErrorMsg.textContent = error.message || "Failed to load shop folders.";
        taskErrorMsg.style.display = "block";
      }
    }

    getTaskReportBtn.addEventListener("click", async () => {
      getTaskReportBtn.disabled = true;
      taskErrorMsg.style.display = "none";
      taskLog.innerHTML = "";
      batchReportCard.classList.add("hidden");
      batchMetrics.innerHTML = "";
      batchTableWrap.innerHTML = "";
      currentTaskReportData = null;

      try {
        const listResponse = await fetch(API_BASE + "/api/task-shops");
        const listData = await listResponse.json();
        if (!listResponse.ok) {
          throw new Error(listData.detail || listData.error || "Failed to load shop folders.");
        }

        const shops = listData.shops || [];
        shopPath.textContent = listData.image_root + " | " + shops.length + " shop folder" + (shops.length === 1 ? "" : "s");
        if (shops.length === 0) {
          throw new Error("No shop folders found. Add folders like ma-mudi-dokan or bismillah-shop under " + listData.image_root + ".");
        }

        const rows = [];
        for (const shop of shops) {
          const logRow = appendTaskLog(shop.shop_name, "analyzing...");
          const formData = new FormData();
          formData.append("shop_name", shop.shop_name);

          try {
            const response = await fetch(API_BASE + "/api/analyze-shop", {
              method: "POST",
              body: formData,
            });
            const row = await response.json();
            if (!response.ok) {
              throw new Error(row.detail || row.error || "Analysis failed.");
            }
            rows.push(row);
            updateTaskLog(logRow, "complete: " + row.total_detections + " products");
          } catch (error) {
            rows.push({
              shop_name: shop.shop_name,
              image_count: shop.image_count || 0,
              total_detections: 0,
              product_counts: {},
              unknown_count: 0,
              existing_labels: configuredLabels,
              missing_labels: configuredLabels,
              errors: [error.message || "Analysis failed."],
            });
            updateTaskLog(logRow, "failed");
          }
        }

        renderTaskReport(rows, listData.image_root);
      } catch (error) {
        taskErrorMsg.textContent = error.message || "Task report failed.";
        taskErrorMsg.style.display = "block";
      } finally {
        getTaskReportBtn.disabled = false;
      }
    });

    downloadTaskPdfBtn.addEventListener("click", async () => {
      if (!currentTaskReportData) return;

      if (!window.jspdf || !window.jspdf.jsPDF) {
        taskErrorMsg.textContent = "PDF export is unavailable because the PDF library failed to load.";
        taskErrorMsg.style.display = "block";
        return;
      }

      downloadTaskPdfBtn.disabled = true;
      taskErrorMsg.style.display = "none";
      try {
        generateTaskPdf(currentTaskReportData);
      } catch (error) {
        taskErrorMsg.textContent = error.message || "PDF export failed.";
        taskErrorMsg.style.display = "block";
      } finally {
        downloadTaskPdfBtn.disabled = false;
      }
    });

    function appendTaskLog(shopName, status) {
      const row = document.createElement("div");
      row.className = "task-log-row";

      const name = document.createElement("strong");
      name.textContent = shopName;
      row.appendChild(name);

      const state = document.createElement("span");
      state.textContent = status;
      row.appendChild(state);

      taskLog.appendChild(row);
      return row;
    }

    function updateTaskLog(row, status) {
      const state = row.querySelector("span");
      if (state) {
        state.textContent = status;
      }
    }

    function renderTaskReport(rows, imageRoot) {
      const labels = taskReportLabels(rows);
      const totals = {};
      let totalImages = 0;
      let totalDetections = 0;
      let totalUnknown = 0;

      rows.forEach((row) => {
        totalImages += row.image_count || 0;
        totalDetections += row.total_detections || 0;
        totalUnknown += row.unknown_count || 0;
        labels.forEach((label) => {
          totals[label] = (totals[label] || 0) + Number((row.product_counts || {})[label] || 0);
        });
      });

      currentTaskReportData = {
        image_root: imageRoot,
        shops: rows,
        labels,
        totals,
        unknown_count: totalUnknown,
      };

      batchMetrics.innerHTML = "";
      batchMetrics.appendChild(metric("Shops", rows.length));
      batchMetrics.appendChild(metric("Products", totalDetections));
      batchMetrics.appendChild(metric("Unknown", totalUnknown));

      batchTableWrap.innerHTML = "";
      batchTableWrap.appendChild(buildTaskTable(rows, labels, totals));
      batchReportCard.classList.remove("hidden");
      batchReportCard.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function taskReportLabels(rows) {
      const labels = new Set(configuredLabels || []);
      rows.forEach((row) => {
        (row.existing_labels || []).forEach((label) => labels.add(label));
        Object.keys(row.product_counts || {}).forEach((label) => labels.add(label));
      });
      return Array.from(labels).filter(Boolean).sort((a, b) => a.localeCompare(b));
    }

    function buildTaskTable(rows, labels, totals) {
      const table = document.createElement("table");
      table.className = "report-table";

      const thead = document.createElement("thead");
      const headRow = document.createElement("tr");
      headRow.appendChild(tableCell("th", "Shop Name"));
      labels.forEach((label) => headRow.appendChild(tableCell("th", label)));
      headRow.appendChild(tableCell("th", "Images"));
      headRow.appendChild(tableCell("th", "Products"));
      thead.appendChild(headRow);
      table.appendChild(thead);

      const tbody = document.createElement("tbody");
      rows.forEach((row) => {
        const tr = document.createElement("tr");
        tr.appendChild(tableCell("td", row.shop_name));
        labels.forEach((label) => {
          tr.appendChild(tableCell("td", Number((row.product_counts || {})[label] || 0)));
        });
        tr.appendChild(tableCell("td", row.image_count || 0));
        tr.appendChild(tableCell("td", row.total_detections || 0));
        tbody.appendChild(tr);

        if (row.errors && row.errors.length) {
          const errorRow = document.createElement("tr");
          const errorCell = tableCell("td", "Errors: " + row.errors.join("; "));
          errorCell.colSpan = labels.length + 3;
          errorRow.appendChild(errorCell);
          tbody.appendChild(errorRow);
        }
      });
      table.appendChild(tbody);

      const tfoot = document.createElement("tfoot");
      const totalRow = document.createElement("tr");
      totalRow.appendChild(tableCell("td", "Total"));
      labels.forEach((label) => totalRow.appendChild(tableCell("td", Number(totals[label] || 0))));
      totalRow.appendChild(tableCell("td", rows.reduce((sum, row) => sum + Number(row.image_count || 0), 0)));
      totalRow.appendChild(tableCell("td", rows.reduce((sum, row) => sum + Number(row.total_detections || 0), 0)));
      tfoot.appendChild(totalRow);
      table.appendChild(tfoot);

      return table;
    }

    function tableCell(tag, value) {
      const cell = document.createElement(tag);
      cell.textContent = value;
      return cell;
    }







    function generateTaskPdf(data) {
      if (!window.jspdf || !window.jspdf.jsPDF) {
        throw new Error("PDF export is unavailable because the PDF library failed to load.");
      }

      const jsPDF = window.jspdf.jsPDF;
      const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
      const pageWidth = doc.internal.pageSize.getWidth();
      const pageHeight = doc.internal.pageSize.getHeight();
      const margin = 14;
      const contentWidth = pageWidth - margin * 2;
      let cursorY = margin;

      function ensureSpace(heightNeeded) {
        if (cursorY + heightNeeded <= pageHeight - margin) return;
        doc.addPage();
        cursorY = margin;
      }

      function writeWrapped(text, x, y, width, lineHeight) {
        const lines = doc.splitTextToSize(String(text), width);
        doc.text(lines, x, y);
        return lines.length * lineHeight;
      }

      doc.setFont("helvetica", "bold");
      doc.setFontSize(20);
      doc.setTextColor(17, 17, 17);
      doc.text("ShelfAnalytics Task Report", margin, cursorY);
      cursorY += 8;

      doc.setFont("helvetica", "normal");
      doc.setFontSize(10);
      doc.setTextColor(90, 90, 90);
      cursorY += writeWrapped("Source folder: " + data.image_root, margin, cursorY, contentWidth, 5) + 5;

      const totalImages = data.shops.reduce((sum, row) => sum + Number(row.image_count || 0), 0);
      const totalDetections = data.shops.reduce((sum, row) => sum + Number(row.total_detections || 0), 0);
      doc.setFont("helvetica", "bold");
      doc.setTextColor(17, 17, 17);
      doc.text("Summary", margin, cursorY);
      cursorY += 6;
      doc.setFont("helvetica", "normal");
      doc.text("Shops: " + data.shops.length + "   Images: " + totalImages + "   Products: " + totalDetections + "   Unknown: " + data.unknown_count, margin, cursorY);
      cursorY += 10;

      data.shops.forEach((row) => {
        ensureSpace(24);
        doc.setDrawColor(210, 210, 210);
        doc.setFillColor(248, 248, 248);
        doc.roundedRect(margin, cursorY, contentWidth, 10, 2, 2, "FD");
        doc.setFont("helvetica", "bold");
        doc.setTextColor(17, 17, 17);
        doc.text(row.shop_name, margin + 3, cursorY + 6.5);
        doc.setFont("helvetica", "normal");
        doc.text(String(row.total_detections || 0) + " products", pageWidth - margin - 3, cursorY + 6.5, { align: "right" });
        cursorY += 14;

        const counts = Object.entries(row.product_counts || {})
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([label, count]) => label + ": " + count);
        const line = counts.length ? counts.join(", ") : "No products counted.";
        doc.setFont("helvetica", "normal");
        doc.setTextColor(55, 55, 55);
        cursorY += writeWrapped(line, margin + 3, cursorY, contentWidth - 6, 5) + 4;

        if (row.errors && row.errors.length) {
          doc.setTextColor(160, 40, 40);
          cursorY += writeWrapped("Errors: " + row.errors.join("; "), margin + 3, cursorY, contentWidth - 6, 5) + 4;
        }
      });

      doc.save("task_report_" + new Date().toISOString().split("T")[0] + ".pdf");
    }

    function metric(label, value) {
      const div = document.createElement("div");
      div.className = "metric";
      div.innerHTML = '<div class="k">' + esc(label) + '</div><div class="v">' + esc(String(value)) + '</div>';
      return div;
    }

    function pdfMetric(label, value) {
      const div = document.createElement("div");
      div.className = "pdf-metric";
      div.innerHTML = '<div class="label">' + esc(label) + '</div><div class="value">' + esc(String(value)) + '</div>';
      return div;
    }

    function pdfLabelItem(text) {
      const span = document.createElement("span");
      span.className = "pdf-label-item";
      span.textContent = text;
      return span;
    }

    function chip(text) {
      const span = document.createElement("span");
      span.className = "chip";
      span.textContent = text;
      return span;
    }

    function esc(value) {
      const div = document.createElement("div");
      div.textContent = value;
      return div.innerHTML;
    }
