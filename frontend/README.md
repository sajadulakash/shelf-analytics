# ShelfAnalytics – Frontend

Static HTML/CSS/JS app. No build step — serve the folder with any static server.

## Run

```bash
python -m http.server 3000     # then open http://127.0.0.1:3000
```

## Configure the backend URL

The frontend calls the backend over HTTP. Set the API base in
[`assets/js/config.js`](assets/js/config.js):

```js
window.API_BASE = window.API_BASE || "http://127.0.0.1:8000";
```

Change it if the backend runs on a different host/port.

## Pages

- `index.html` – Get Task Report (batch analysis of shop folders + PDF)
- `process.html` – Explore Process (upload → detect → crop → classify → report)
- `con.html` – Confidence log viewer
- `labels.html` – Manage Labels (placeholder, not implemented yet)

## Assets

- `assets/css/` – `app.css` (shared by index + process), `labels.css`, `con.css`
- `assets/js/` – `config.js` (API base), per-page scripts, `vendor/` (jsPDF, html2pdf)
