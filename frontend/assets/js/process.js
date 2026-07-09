const API_BASE = window.API_BASE || "";

    const fileInput = document.getElementById("fileInput");
    const dropZone = document.getElementById("dropZone");
    const fileName = document.getElementById("fileName");
    const uploadPreview = document.getElementById("uploadPreview");
    const uploadPreviewImg = document.getElementById("uploadPreviewImg");
    const runBtn = document.getElementById("runBtn");
    const spinner = document.getElementById("spinner");
    const errorMsg = document.getElementById("errorMsg");

    const detectionCard = document.getElementById("detectionCard");
    const cropsCard = document.getElementById("cropsCard");
    const classifiedCard = document.getElementById("classifiedCard");
    const reportCard = document.getElementById("reportCard");
    const downloadPdfBtn = document.getElementById("downloadPdfBtn");

    let currentReportData = null;

    const detectionInfo = document.getElementById("detectionInfo");
    const detectionImage = document.getElementById("detectionImage");
    const cropsGrid = document.getElementById("cropsGrid");
    const classifiedGrid = document.getElementById("classifiedGrid");
    const reportMetrics = document.getElementById("reportMetrics");
    const labelCounts = document.getElementById("labelCounts");
    const missingLabels = document.getElementById("missingLabels");

    let selectedFile = null;

    dropZone.addEventListener("dragover", (event) => {
      event.preventDefault();
      dropZone.classList.add("dragover");
    });

    dropZone.addEventListener("dragleave", () => {
      dropZone.classList.remove("dragover");
    });

    dropZone.addEventListener("drop", (event) => {
      event.preventDefault();
      dropZone.classList.remove("dragover");
      const file = event.dataTransfer.files && event.dataTransfer.files[0];
      if (file) {
        setFile(file);
      }
    });

    fileInput.addEventListener("change", () => {
      const file = fileInput.files && fileInput.files[0];
      if (file) {
        setFile(file);
      }
    });

    function setFile(file) {
      if (!file.type.startsWith("image/")) {
        return;
      }
      selectedFile = file;
      runBtn.disabled = false;

      clearResults();
    }

    function clearResults() {
      detectionCard.classList.add("hidden");
      cropsCard.classList.add("hidden");
      classifiedCard.classList.add("hidden");
      reportCard.classList.add("hidden");
      cropsGrid.innerHTML = "";
      classifiedGrid.innerHTML = "";
      reportMetrics.innerHTML = "";
      labelCounts.innerHTML = "";
      missingLabels.innerHTML = "";
      errorMsg.style.display = "none";
    }


    runBtn.addEventListener("click", async () => {
      if (!selectedFile) {
        return;
      }

      runBtn.disabled = true;
      spinner.style.display = "block";
      errorMsg.style.display = "none";
      clearResults();

      const formData = new FormData();
      formData.append("image", selectedFile);

      try {
        spinner.textContent = "Step 1/3: Uploading image and running YOLO detection...";
        const response = await fetch(API_BASE + "/detect-shelf", {
          method: "POST",
          body: formData,
        });

        const detectData = await response.json();
        if (!response.ok) {
          throw new Error(detectData.detail || detectData.error || "Request failed");
        }

        renderDetection(detectData);
        renderCrops(detectData);

        spinner.textContent = "Step 2/3: Classifying cropped products with SwinV2...";
        const classifyData = new FormData();
        classifyData.append("run_id", detectData.run_id);

        const classifyResponse = await fetch(API_BASE + "/classify-detected-crops", {
          method: "POST",
          body: classifyData,
        });

        const classification = await classifyResponse.json();
        if (!classifyResponse.ok) {
          throw new Error(classification.detail || classification.error || "Classification failed");
        }

        renderClassifiedProducts(classification);
        renderReport(classification);
      } catch (error) {
        errorMsg.textContent = error.message;
        errorMsg.style.display = "block";
      } finally {
        spinner.style.display = "none";
        runBtn.disabled = false;
      }
    });

    downloadPdfBtn.addEventListener("click", async () => {
      if (!currentReportData) return;

      if (!window.jspdf || !window.jspdf.jsPDF) {
        showError("PDF export is unavailable because the PDF library failed to load.");
        return;
      }

      downloadPdfBtn.disabled = true;
      errorMsg.style.display = "none";

      try {
        await generatePdf(currentReportData);
      } catch (error) {
        showError(error.message || "PDF export failed.");
      } finally {
        downloadPdfBtn.disabled = false;
      }
    });







    function renderDetection(data) {
      detectionInfo.textContent = "Total detections: " + data.total_detections;
      if (data.detection_image_b64) {
        detectionImage.src = "data:image/jpeg;base64," + data.detection_image_b64;
      } else {
        detectionImage.src = API_BASE + data.detection_image_url;
      }
      detectionCard.classList.remove("hidden");
    }

    function renderCrops(data) {
      cropsGrid.innerHTML = "";
      data.crops.forEach((crop) => {
        const el = document.createElement("article");
        el.className = "crop";

        const img = document.createElement("img");
        img.alt = "Crop";
        if (crop.crop_image_b64) {
          img.src = "data:image/jpeg;base64," + crop.crop_image_b64;
        } else {
          img.src = API_BASE + crop.crop_url;
        }
        el.appendChild(img);

        const meta = document.createElement("div");
        meta.className = "crop-meta";
        meta.innerHTML =
          '<strong>' + esc(crop.crop_filename) + '</strong>' +
          '<span>Box: [' + crop.bbox.x1 + ', ' + crop.bbox.y1 + ', ' + crop.bbox.x2 + ', ' + crop.bbox.y2 + ']</span>';
        el.appendChild(meta);

        cropsGrid.appendChild(el);
      });
      cropsCard.classList.remove("hidden");
    }

    function renderClassifiedProducts(data) {
      classifiedGrid.innerHTML = "";

      data.classifications.forEach((item) => {
        const el = document.createElement("article");
        el.className = "crop";

        const img = document.createElement("img");
        img.alt = "Classified crop";
        if (item.crop_image_b64) {
          img.src = "data:image/jpeg;base64," + item.crop_image_b64;
        } else {
          img.src = API_BASE + item.crop_url;
        }
        el.appendChild(img);

        const statusClass = item.is_unknown ? "unknown" : "known";

        const meta = document.createElement("div");
        meta.className = "crop-meta";
        meta.innerHTML =
          '<strong>' + esc(item.predicted_label) + '</strong>' +
          '<span class="pill ' + statusClass + '">' + (item.is_unknown ? "Unknown" : "Matched") + '</span>' +
          '<span>File: ' + esc(item.crop_filename) + '</span>';
        el.appendChild(meta);

        classifiedGrid.appendChild(el);
      });

      classifiedCard.classList.remove("hidden");
    }

    function toAbsoluteUrl(urlPath) {
      if (!urlPath) {
        return "";
      }
      if (urlPath.startsWith("http://") || urlPath.startsWith("https://")) {
        return urlPath;
      }
      return API_BASE + (urlPath.startsWith("/") ? urlPath : "/" + urlPath);
    }

    function renderReport(data) {
      currentReportData = data;
      reportMetrics.innerHTML = "";
      reportMetrics.appendChild(metric("Detections", data.total_detections));
      reportMetrics.appendChild(metric("Known", data.total_detections - data.unknown_count));
      reportMetrics.appendChild(metric("Unknown", data.unknown_count));
      reportMetrics.appendChild(metric("Model Labels", data.existing_labels.length));

      labelCounts.innerHTML = "";
      const countEntries = Object.entries(data.label_counts || {});
      if (countEntries.length === 0) {
        labelCounts.appendChild(chip("No known labels detected"));
      } else {
        countEntries.forEach(([label, count]) => {
          labelCounts.appendChild(chip(label + ": " + count));
        });
      }

      missingLabels.innerHTML = "";
      if (!data.missing_labels || data.missing_labels.length === 0) {
        missingLabels.appendChild(chip("None"));
      } else {
        data.missing_labels.forEach((label) => {
          missingLabels.appendChild(chip(label));
        });
      }

      reportCard.classList.remove("hidden");
    }

    async function generatePdf(data) {
      if (!window.jspdf || !window.jspdf.jsPDF) {
        throw new Error("PDF export is unavailable because the PDF library failed to load.");
      }

      const jsPDF = window.jspdf.jsPDF;
      const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
      const pageWidth = doc.internal.pageSize.getWidth();
      const pageHeight = doc.internal.pageSize.getHeight();
      const margin = 14;
      const contentWidth = pageWidth - margin * 2;
      const columnGap = 4;
      const metricWidth = (contentWidth - columnGap * 3) / 4;
      const metricHeight = 22;
      const sectionGap = 10;
      let cursorY = margin;

      function ensureSpace(heightNeeded) {
        if (cursorY + heightNeeded <= pageHeight - margin) {
          return;
        }
        doc.addPage();
        cursorY = margin;
      }

      function drawWrappedText(text, x, y, maxWidth, lineHeight) {
        const lines = doc.splitTextToSize(String(text), maxWidth);
        doc.text(lines, x, y);
        return lines.length * lineHeight;
      }

      function drawMetricBox(x, y, label, value) {
        doc.setDrawColor(215, 208, 199);
        doc.setFillColor(255, 255, 255);
        doc.roundedRect(x, y, metricWidth, metricHeight, 2, 2, "FD");
        doc.setFont("helvetica", "bold");
        doc.setFontSize(8);
        doc.setTextColor(106, 98, 91);
        doc.text(String(label).toUpperCase(), x + metricWidth / 2, y + 6, { align: "center" });
        doc.setFont("times", "bold");
        doc.setFontSize(17);
        doc.setTextColor(24, 18, 13);
        doc.text(String(value), x + metricWidth / 2, y + 15, { align: "center" });
      }

      function drawSectionLabel(text) {
        ensureSpace(8);
        doc.setFont("helvetica", "bold");
        doc.setFontSize(8);
        doc.setTextColor(106, 98, 91);
        doc.text(String(text).toUpperCase(), margin, cursorY);
        cursorY += 6;
      }

      function drawRowList(title, items, emptyText) {
        const rowItems = items.length > 0 ? items : [emptyText];
        drawSectionLabel(title);

        rowItems.forEach((item) => {
          const rowLines = doc.splitTextToSize(String(item), contentWidth - 12);
          const rowHeight = Math.max(10, rowLines.length * 5 + 4);
          ensureSpace(rowHeight + 2);
          doc.setDrawColor(215, 208, 199);
          doc.setFillColor(255, 255, 255);
          doc.roundedRect(margin, cursorY, contentWidth, rowHeight, 2, 2, "FD");
          doc.setFont("times", "normal");
          doc.setFontSize(11);
          doc.setTextColor(34, 23, 15);
          doc.text("•", margin + 5, cursorY + 6);
          doc.text(rowLines, margin + 10, cursorY + 6);
          cursorY += rowHeight + 3;
        });

        cursorY += 3;
      }

      doc.setFillColor(255, 255, 255);
      doc.rect(0, 0, pageWidth, pageHeight, "F");

      doc.setFont("times", "bold");
      doc.setFontSize(22);
      doc.setTextColor(24, 18, 13);
      doc.text("Classification Report", margin, cursorY);
      cursorY += 4;

      doc.setDrawColor(32, 32, 32);
      doc.setLineWidth(0.5);
      doc.line(margin, cursorY + 2, pageWidth - margin, cursorY + 2);
      cursorY += 8;

      doc.setFont("times", "normal");
      doc.setFontSize(11);
      doc.setTextColor(91, 83, 75);
      cursorY += drawWrappedText(
        "This report summarizes the current shelf image analysis with product counts, matched labels, and model labels that were not detected in the uploaded image.",
        margin,
        cursorY,
        contentWidth,
        5
      ) + 4;

      drawSectionLabel("Summary Metrics");
      ensureSpace(metricHeight + 2);

      const metrics = [
        ["Detections", data.total_detections],
        ["Known", data.total_detections - data.unknown_count],
        ["Unknown", data.unknown_count],
        ["Model Labels", (data.existing_labels || []).length],
      ];

      metrics.forEach(([label, value], index) => {
        const x = margin + index * (metricWidth + columnGap);
        drawMetricBox(x, cursorY, label, value);
      });
      cursorY += metricHeight + sectionGap;

      const countEntries = Object.entries(data.label_counts || {}).map(([label, count]) => label + ": " + count);
      drawRowList("Detected Label Counts", countEntries, "No known labels detected");
      drawRowList("Configured Labels Not Found In This Image", data.missing_labels || [], "None");

      doc.save("classification_report_" + new Date().toISOString().split("T")[0] + ".pdf");
    }


    function showError(message) {
      errorMsg.textContent = message;
      errorMsg.style.display = "block";
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
