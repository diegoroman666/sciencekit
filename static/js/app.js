/**
 * SciencKit — UI layer.
 *
 * This file deliberately contains no statistics. Every computation is delegated
 * to the Python engine in `core/` through a single `call()` bridge, so the
 * numbers shown here are produced by the same code the Flask server runs.
 */

const PYODIDE_VERSION = "0.28.0";

/**
 * The runtime is served from this origin (see scripts/fetch_pyodide.py) so the
 * app loads fast and keeps working offline. The CDN is only a fallback for the
 * case where the local copy was never fetched.
 */
const PYODIDE_CDN = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

/**
 * Engine modules copied into the Pyodide filesystem. All are written before
 * anything is imported, so this is a manifest rather than a load order — but
 * it must stay complete: a missing entry surfaces as an ImportError at boot.
 */
const CORE_MODULES = [
  "__init__.py",
  "fmt.py",
  "dataset.py",
  "analysis.py",
  "charts.py",
  "sample.py",
  "api.py",
];

/**
 * Site root, derived from this module's own URL (static/js/app.js → ../../).
 * Resolving relatively means the app works both at / and under a subdirectory.
 */
const BASE = new URL("../../", import.meta.url);

const state = {
  ready: false,
  dataset: null,
  view: "datos",
  model: null,
  profile: null,
  profileChart: null,
};

let pyodide = null;
let session = null;
let dispatchJson = null;

// ── helpers ────────────────────────────────────────────────────────────────

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

/** Escape a value for safe interpolation into innerHTML. */
function esc(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Format a number for display: fixed decimals, thousands separators, em dash for null. */
function num(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (typeof value !== "number") return esc(value);
  if (value !== 0 && Math.abs(value) < 1e-4) return value.toExponential(2);
  return value.toLocaleString("es-ES", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function pct(value, digits = 1) {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toLocaleString("es-ES", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`;
}

function errorBox(message) {
  return `<div class="notice-error fade-in">
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor"
         stroke-width="1.5" class="shrink-0 mt-px" aria-hidden="true">
      <circle cx="8" cy="8" r="6.4"/><path d="M8 5v4M8 11h.01"/>
    </svg>
    <span>${esc(message)}</span>
  </div>`;
}

function warnBox(message) {
  return `<div class="notice-warn fade-in">
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor"
         stroke-width="1.5" class="shrink-0 mt-px" aria-hidden="true">
      <path d="M8 2.2l6 11.3H2L8 2.2z"/><path d="M8 6.6v3M8 11.4h.01"/>
    </svg>
    <span>${esc(message)}</span>
  </div>`;
}

/** A titled panel wrapping arbitrary content. */
function panel(title, body, meta = "") {
  return `<section class="panel fade-in">
    <header class="flex items-baseline justify-between gap-3 px-4 py-3 border-b rule">
      <h3 class="label !text-[10px]">${esc(title)}</h3>
      ${meta ? `<span class="font-mono text-[10.5px] text-ink-3 dark:text-chalk-3 tnum">${meta}</span>` : ""}
    </header>
    ${body}
  </section>`;
}

/** `id` lands on the SVG holder so a later render can swap the chart in place. */
function chartPanel(title, svg, meta = "", id = "") {
  const attr = id ? ` id="${id}"` : "";
  return panel(title, `<div${attr} class="p-3 sm:p-4">${svg}</div>`, meta);
}

// ── Python bridge ──────────────────────────────────────────────────────────

async function boot() {
  const status = $("#boot-status");

  try {
    status.textContent = "Cargando runtime de Python…";
    const indexURL = await resolveRuntime();

    status.textContent = "Inicializando intérprete…";
    pyodide = await globalThis.loadPyodide({ indexURL });

    status.textContent = "Cargando motor de análisis…";
    await mountCore();

    // Build the session object once; it holds the dataset between calls.
    pyodide.runPython(`
import sys, json
sys.path.insert(0, "/home/pyodide")
from core import api as _api
_session = _api.Session()
`);
    session = pyodide.globals.get("_session");
    const apiModule = pyodide.pyimport("core.api");
    dispatchJson = (action, payload) =>
      apiModule.dispatch_json(session, action, JSON.stringify(payload || {}));

    state.ready = true;
    $("#boot").remove();
    renderSamples();
  } catch (err) {
    console.error(err);
    status.textContent = "No se pudo iniciar el motor";
    $("#boot-error").classList.remove("hidden");
    $("#boot-error").innerHTML = errorBox(
      `${err && err.message ? err.message : err}. Verifique su conexión y recargue la página.`
    );
  }
}

/**
 * Prefer the self-hosted runtime; fall back to the CDN if it is absent.
 * Returns the `indexURL` Pyodide should resolve its assets against.
 */
async function resolveRuntime() {
  const local = new URL("static/pyodide/", BASE);
  try {
    const probe = await fetch(new URL("pyodide-lock.json", local), { method: "HEAD" });
    if (probe.ok) {
      await loadScript(new URL("pyodide.js", local).href);
      return local.href;
    }
  } catch (err) {
    /* not fetched locally — fall through to the CDN */
  }

  await loadScript(`${PYODIDE_CDN}pyodide.js`);
  return PYODIDE_CDN;
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const el = document.createElement("script");
    el.src = src;
    el.onload = resolve;
    el.onerror = () => reject(new Error(`No se pudo cargar ${src}`));
    document.head.appendChild(el);
  });
}

/** Copy the Python engine into Pyodide's virtual filesystem. */
async function mountCore() {
  pyodide.FS.mkdirTree("/home/pyodide/core");

  const sources = await Promise.all(
    CORE_MODULES.map(async (name) => {
      const url = new URL(`core/${name}`, BASE);
      const response = await fetch(url, { cache: "no-cache" });
      if (!response.ok) {
        throw new Error(`No se pudo cargar core/${name} (${response.status})`);
      }
      return [name, await response.text()];
    })
  );

  for (const [name, text] of sources) {
    pyodide.FS.writeFile(`/home/pyodide/core/${name}`, text, { encoding: "utf8" });
  }
}

/** Invoke a Python action. Always resolves to an object with an `ok` flag. */
function call(action, payload) {
  if (!state.ready) return { ok: false, error: "El motor aún no está listo." };
  try {
    return JSON.parse(dispatchJson(action, payload));
  } catch (err) {
    console.error(action, err);
    return { ok: false, error: `Fallo en el motor de Python: ${err.message || err}` };
  }
}

// ── dataset loading ────────────────────────────────────────────────────────

async function loadFile(file) {
  if (!file) return;
  showEmptyError("");

  const buffer = await file.arrayBuffer();
  let binary = "";
  const bytes = new Uint8Array(buffer);
  const CHUNK = 0x8000; // chunked to avoid blowing the argument limit
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
  }

  const result = call("load", {
    filename: file.name,
    content_b64: btoa(binary),
  });

  if (!result.ok) {
    showEmptyError(result.error);
    return;
  }
  adoptDataset(result.dataset);
}

/** Load one of the bundled datasets. No key means the default (first) one. */
function loadDemo(key) {
  const result = call("demo", key ? { sample: key } : {});
  if (!result.ok) {
    showEmptyError(result.error);
    return;
  }
  adoptDataset(result.dataset);
}

// ── sample gallery ─────────────────────────────────────────────────────────

/**
 * Render the catalogue of bundled datasets. The metadata comes from the Python
 * engine, so the cards always describe the data that is actually embedded.
 */
function renderSamples() {
  const grid = $("#samples-grid");
  if (!grid) return;

  const result = call("samples", {});
  if (!result.ok) {
    grid.innerHTML = "";
    $("#samples-error").innerHTML = errorBox(result.error);
    return;
  }

  grid.innerHTML = result.samples
    .map(
      (s) => `<article class="panel p-4 flex flex-col gap-3 fade-in">
      <div class="flex items-center justify-between gap-2">
        <span class="chip chip-cat">${esc(s.area)}</span>
        <span class="font-mono text-[10px] text-ink-3 dark:text-chalk-3 tnum">
          ${s.rows} × ${s.columns}
        </span>
      </div>
      <div>
        <h4 class="text-[14px] font-medium leading-snug mb-1">${esc(s.title)}</h4>
        <p class="text-[12.5px] leading-relaxed text-ink-3 dark:text-chalk-3">
          ${esc(s.description)}
        </p>
      </div>
      <p class="font-mono text-[10px] text-ink-3 dark:text-chalk-3 leading-relaxed">
        ${s.numeric} cuantitativas · ${s.categorical} cualitativas<br>
        Sugerencia: ${esc(s.driver)} → ${esc(s.target)}
      </p>
      <div class="flex items-center gap-2 mt-auto pt-1">
        <button class="btn-primary flex-1" data-sample="${esc(s.key)}">Analizar</button>
        <button class="btn-ghost !px-3" data-download="${esc(s.key)}"
                title="Descargar ${esc(s.name)}" aria-label="Descargar ${esc(s.name)}">
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor"
               stroke-width="1.5" aria-hidden="true">
            <path d="M8 2.5v8M8 10.5L5 7.5M8 10.5l3-3M2.5 12.5v.5a1 1 0 001 1h9a1 1 0 001-1v-.5"/>
          </svg>
          CSV
        </button>
      </div>
    </article>`
    )
    .join("");
}

/** Save a bundled dataset to disk, straight from the embedded copy. */
function downloadSample(key) {
  const result = call("sample_csv", { sample: key });
  if (!result.ok) {
    $("#samples-error").innerHTML = errorBox(result.error);
    return;
  }

  // The BOM makes Excel open the accented headers as UTF-8 rather than latin-1.
  const blob = new Blob(["\ufeff", result.csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = result.name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function showEmptyError(message) {
  const target = state.dataset ? $("#stats-out") : $("#empty-error");
  if (!message) {
    $("#empty-error").innerHTML = "";
    return;
  }
  target.innerHTML = errorBox(message);
}

/** Show the start screen without discarding the dataset under analysis. */
function goHome() {
  $("#workspace").hidden = true;
  $("#empty").hidden = false;
  syncResumeButton();
  window.scrollTo({ top: 0, behavior: "auto" });
}

/** Back to the workspace, with whatever was already loaded. */
function resumeAnalysis() {
  if (!state.dataset) return;
  $("#empty").hidden = true;
  $("#workspace").hidden = false;
  window.scrollTo({ top: 0, behavior: "auto" });
}

/** The resume button only makes sense while a dataset is loaded. */
function syncResumeButton() {
  const button = $("#btn-resume");
  if (!button) return;
  button.hidden = !state.dataset;
  if (state.dataset) {
    button.textContent = `Volver a ${state.dataset.name}`;
  }
}

/** Adopt a freshly parsed dataset: reset state, populate every control. */
function adoptDataset(dataset) {
  state.dataset = dataset;
  state.model = null;
  state.profile = null;

  $("#empty").hidden = true;
  $("#workspace").hidden = false;
  syncResumeButton();

  renderInspector();
  populateSelects();
  renderStats();
  renderChart();
  $("#reg-out").innerHTML = "";
  renderProbability();
}

function renderInspector() {
  const ds = state.dataset;
  const numeric = ds.columns.filter((c) => c.is_numeric).length;

  $("#status-line").innerHTML =
    `<span class="text-signal dark:text-signal-soft">●</span> ` +
    `<span class="text-ink-2 dark:text-chalk-2">${esc(ds.name)}</span> — ` +
    `${ds.rows} filas · ${ds.columns.length} columnas ` +
    `(${numeric} cuantitativas, ${ds.columns.length - numeric} cualitativas)`;

  const nameEl = $("#ds-name");
  nameEl.textContent = ds.name;
  nameEl.title = ds.name;
  $("#ds-shape").textContent = `${ds.rows} filas × ${ds.columns.length} columnas`;

  $("#ds-columns").innerHTML = ds.columns
    .map(
      (c) => `<li class="flex items-center justify-between gap-2">
        <span class="font-mono text-[11px] text-ink-2 dark:text-chalk-2 truncate"
              title="${esc(c.name)}">${esc(c.name)}</span>
        <span class="chip ${c.is_numeric ? "chip-num" : "chip-cat"} shrink-0"
              title="${c.is_numeric ? "Cuantitativa" : "Cualitativa"}">
          ${c.is_numeric ? "num" : "cat"}
        </span>
      </li>`
    )
    .join("");
}

/** Fill every <select> with the appropriate column subset. */
function populateSelects() {
  const all = state.dataset.columns;
  const numeric = all.filter((c) => c.is_numeric);

  const options = (cols) =>
    cols.map((c) => `<option value="${esc(c.name)}">${esc(c.name)}</option>`).join("");

  $("#stats-col").innerHTML = options(all);
  $("#chart-x").innerHTML = options(all);
  $("#chart-y").innerHTML = options(numeric);
  $("#reg-x").innerHTML = options(numeric);
  $("#reg-y").innerHTML = options(numeric);
  $("#prob-col").innerHTML = numeric.length
    ? options(numeric)
    : `<option value="">Sin variables cuantitativas</option>`;

  // Sensible defaults: first numeric on X, a different numeric on Y.
  if (numeric.length) {
    $("#chart-x").value = numeric[0].name;
    $("#reg-x").value = numeric[0].name;
    const second = numeric[1] || numeric[0];
    $("#chart-y").value = second.name;
    $("#reg-y").value = second.name;
    $("#stats-col").value = numeric[0].name;
  }

  syncChartControls();
}

// ── 01 · descriptive statistics ────────────────────────────────────────────

function renderStats() {
  const column = $("#stats-col").value;
  const out = $("#stats-out");
  if (!column) {
    out.innerHTML = "";
    return;
  }

  const result = call("describe", { column });
  if (!result.ok) {
    out.innerHTML = errorBox(result.error);
    return;
  }

  out.innerHTML =
    result.kind === "quantitative"
      ? renderQuantitative(result, column)
      : renderQualitative(result, column);
}

function renderQuantitative(result, column) {
  const stats = result.stats;
  const groups = [
    ["Tendencia central", "center"],
    ["Dispersión", "spread"],
    ["Posición", "position"],
  ];

  const blocks = groups
    .map(([title, key]) => {
      const items = stats.measures.filter((m) => m.group === key);
      const cells = items
        .map((m) => {
          const value =
            m.value === null
              ? `<span class="text-ink-3 dark:text-chalk-3">${esc(m.note || "—")}</span>`
              : `${num(m.value, 3)}${m.suffix ? `<span class="text-[13px] text-ink-3 dark:text-chalk-3">${esc(m.suffix)}</span>` : ""}`;
          return `<div class="metric">
            <span class="label !text-[9px] flex items-center gap-1.5">
              ${esc(m.label)}
              <span class="text-ink-3/70 dark:text-chalk-3/70 normal-case tracking-normal">${esc(m.symbol)}</span>
            </span>
            <span class="metric-value">${value}</span>
          </div>`;
        })
        .join("");

      return `<div class="flex-1 min-w-[240px]">
        <p class="label px-3.5 pb-1">${esc(title)}</p>
        ${cells}
      </div>`;
    })
    .join("");

  return (
    panel(
      `Medidas de ${column}`,
      `<div class="flex flex-wrap">${blocks}</div>`,
      `n = ${stats.n}${stats.missing ? ` · ${stats.missing} vacíos` : ""}`
    ) + chartPanel("Histograma", result.chart, `${stats.histogram.bins.length} intervalos`)
  );
}

function renderQualitative(result, column) {
  const table = result.table;
  const rows = table.rows
    .map(
      (r) => `<tr>
        <td class="max-w-[220px] truncate" title="${esc(r.value)}">${esc(r.value)}</td>
        <td class="num">${r.count}</td>
        <td class="num">${pct(r.relative, 2)}</td>
        <td class="num">${pct(r.cumulative, 2)}</td>
        <td class="w-[26%] min-w-[80px]">
          <span class="prop-bar" style="width:${(r.count / table.max_count) * 100}%"></span>
        </td>
      </tr>`
    )
    .join("");

  // Headers are spelled out rather than using fᵢ / hᵢ / Hᵢ: the header style
  // uppercases text, which would render relative and cumulative identically.
  const tableHtml = `<div class="max-h-[420px] overflow-auto thin-scroll">
    <table class="data-table">
      <thead><tr>
        <th>Valor</th>
        <th class="num">Frecuencia</th>
        <th class="num">Relativa</th>
        <th class="num">Acumulada</th>
        <th></th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;

  const note = table.truncated
    ? warnBox(`Se muestran las ${table.rows.length} categorías más frecuentes de ${table.distinct}.`)
    : "";

  return (
    `<div class="notice !border-rule dark:!border-rule-dark text-ink-2 dark:text-chalk-2">
      <span>Variable <strong class="text-ink dark:text-chalk">cualitativa</strong>:
      se resume con una tabla de frecuencias, no con medidas de tendencia central.</span>
    </div>` +
    note +
    panel(
      `Frecuencias de ${column}`,
      tableHtml,
      `${table.distinct} categorías · n = ${table.total}`
    ) +
    chartPanel("Distribución", result.chart)
  );
}

// ── 02 · charts ────────────────────────────────────────────────────────────

/** Show/hide the Y-axis and fit controls depending on the chart type. */
function syncChartControls() {
  const type = $("#chart-type").value;
  const bivariate = type === "scatter";

  $("#chart-y-wrap").classList.toggle("hidden", !bivariate);
  $("#chart-fit-wrap").classList.toggle("hidden", !bivariate);
  $("#chart-x-label").textContent = bivariate ? "Eje X" : "Variable";

  // Histograms need a numeric column; bars accept anything.
  const cols = state.dataset ? state.dataset.columns : [];
  const pool = type === "histogram" || bivariate ? cols.filter((c) => c.is_numeric) : cols;
  const current = $("#chart-x").value;
  $("#chart-x").innerHTML = pool
    .map((c) => `<option value="${esc(c.name)}">${esc(c.name)}</option>`)
    .join("");
  if (pool.some((c) => c.name === current)) $("#chart-x").value = current;
}

function renderChart() {
  if (!state.dataset) return;
  const out = $("#chart-out");
  const type = $("#chart-type").value;

  const payload = { type, x: $("#chart-x").value };
  if (type === "scatter") {
    payload.y = $("#chart-y").value;
    payload.fit = $("#chart-fit").checked;
  }
  if (!payload.x) {
    out.innerHTML = errorBox("No hay variables compatibles con este tipo de gráfico.");
    return;
  }

  const result = call("chart", payload);
  if (!result.ok) {
    out.innerHTML = errorBox(result.error);
    return;
  }

  let meta = `${result.points} puntos`;
  if (result.dropped) meta += ` · ${result.dropped} filas incompletas omitidas`;
  if (result.distinct) meta = `${result.distinct} categorías · n = ${result.points}`;

  let fitNote = "";
  if (result.fit) {
    fitNote = `<div class="flex flex-wrap gap-x-6 gap-y-2 px-4 py-3 border-t rule">
      <span class="font-mono text-[11.5px] text-ink-2 dark:text-chalk-2">
        <span class="label !text-[9px] mr-1.5">Ajuste</span>
        y = ${num(result.fit.m, 4)}x ${result.fit.b < 0 ? "−" : "+"} ${num(Math.abs(result.fit.b), 3)}
      </span>
      <span class="font-mono text-[11.5px] text-ink-2 dark:text-chalk-2">
        <span class="label !text-[9px] mr-1.5">R²</span>${num(result.fit.r2, 4)}
      </span>
      <span class="font-mono text-[11.5px] text-ink-2 dark:text-chalk-2">
        <span class="label !text-[9px] mr-1.5">r</span>${num(result.fit.r, 4)}
      </span>
    </div>`;
  }

  const title =
    type === "scatter"
      ? `${$("#chart-y").value} frente a ${$("#chart-x").value}`
      : type === "histogram"
        ? `Histograma de ${$("#chart-x").value}`
        : `Frecuencia de ${$("#chart-x").value}`;

  out.innerHTML = panel(title, `<div class="p-3 sm:p-4">${result.chart}</div>${fitNote}`, meta);
}

// ── 03 · regression & prediction ───────────────────────────────────────────

function trainModel() {
  const out = $("#reg-out");
  const result = call("regression", { x: $("#reg-x").value, y: $("#reg-y").value });

  if (!result.ok) {
    state.model = null;
    out.innerHTML = errorBox(result.error);
    return;
  }

  const report = result.report;
  state.model = report;

  const m = report.model;
  const tone =
    report.quality.tone === "strong"
      ? "text-signal dark:text-signal-soft"
      : report.quality.tone === "moderate"
        ? "text-warn dark:text-warn-dark"
        : "text-flame dark:text-flame-soft";

  const metrics = [
    ["R²", "Bondad de ajuste", pct(m.r2, 2), tone],
    ["r", "Correlación de Pearson", num(m.r, 4), ""],
    ["m", "Pendiente", num(m.m, 5), ""],
    ["b", "Intercepto", num(m.b, 4), ""],
    ["Sₑ", "Error estándar", num(m.std_error, 4), ""],
    ["n", "Pares completos", String(m.n), ""],
  ]
    .map(
      ([symbol, label, value, cls]) => `<div class="metric">
        <span class="label !text-[9px] flex items-center gap-1.5">
          ${esc(label)}
          <span class="text-ink-3/70 dark:text-chalk-3/70 normal-case tracking-normal">${symbol}</span>
        </span>
        <span class="metric-value ${cls}">${value}</span>
      </div>`
    )
    .join("");

  const equation = `<div class="px-4 py-5 border-b rule">
    <p class="label mb-2">Modelo ajustado</p>
    <p class="font-mono text-[clamp(1rem,3.4vw,1.45rem)] tracking-[-0.01em] text-ink dark:text-chalk">
      ${esc(report.y)} = <span class="text-flame dark:text-flame-soft">${num(m.m, 5)}</span>
      · ${esc(report.x)} ${m.b < 0 ? "−" : "+"}
      <span class="text-flame dark:text-flame-soft">${num(Math.abs(m.b), 4)}</span>
    </p>
    <p class="mt-3 font-mono text-[11px] uppercase tracking-[0.12em] ${tone}">
      Ajuste ${esc(report.quality.label)}
    </p>
  </div>`;

  const interpretation = `<div class="px-4 py-4 border-t rule">
    <p class="label mb-2">Interpretación</p>
    <p class="text-[13.5px] leading-relaxed text-ink-2 dark:text-chalk-2">
      ${esc(report.interpretation)}
    </p>
  </div>`;

  const dropped = report.dropped
    ? warnBox(`${report.dropped} filas se omitieron por tener valores ausentes o no numéricos.`)
    : "";

  out.innerHTML =
    dropped +
    panel(
      "Métricas del modelo",
      equation + `<div class="flex flex-wrap">
        ${metrics.replace(/class="metric"/g, 'class="metric flex-1 min-w-[150px]"')}
      </div>` + interpretation
    ) +
    chartPanel("Dispersión y recta de ajuste", result.chart, `n = ${m.n}`, "reg-chart") +
    predictorForm(report);

  $("#predict-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") runPrediction();
  });
  $("#btn-predict").addEventListener("click", runPrediction);
}

function predictorForm(report) {
  const m = report.model;
  return panel(
    "Simulador de predicción",
    `<div class="p-4">
      <div class="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
        <div>
          <label class="label block mb-1.5" for="predict-input">
            Valor de ${esc(report.x)}
          </label>
          <input id="predict-input" class="field" type="text" inputmode="decimal"
                 placeholder="rango observado: ${num(m.x_min, 2)} – ${num(m.x_max, 2)}">
        </div>
        <button id="btn-predict" class="btn-primary">Predecir</button>
      </div>
      <div id="predict-out" class="mt-4"></div>
    </div>`
  );
}

function runPrediction() {
  const out = $("#predict-out");
  const raw = $("#predict-input").value.trim();
  if (!raw) {
    out.innerHTML = errorBox("Introduzca un valor para predecir.");
    return;
  }

  const result = call("predict", { value: raw });
  if (!result.ok) {
    out.innerHTML = errorBox(result.error);
    return;
  }

  const p = result.prediction;
  out.innerHTML =
    `<div class="fade-in border rule rounded-card overflow-hidden">
      <div class="px-4 py-4 flex flex-wrap items-end gap-x-8 gap-y-3">
        <div>
          <p class="label mb-1.5">${esc(result.y)} estimado</p>
          <p class="font-mono text-[34px] leading-none tracking-[-0.03em] tnum
                    text-flame dark:text-flame-soft">${num(p.y, 2)}</p>
        </div>
        <div>
          <p class="label mb-1.5">Intervalo ≈95%</p>
          <p class="font-mono text-[15px] tnum text-ink-2 dark:text-chalk-2">
            ± ${num(p.interval, 2)}
          </p>
        </div>
        <div>
          <p class="label mb-1.5">Entrada</p>
          <p class="font-mono text-[15px] tnum text-ink-2 dark:text-chalk-2">
            ${esc(result.x)} = ${num(p.x, 2)}
          </p>
        </div>
      </div>
      <div class="px-4 py-3 border-t rule">
        <p class="text-[13px] leading-relaxed text-ink-2 dark:text-chalk-2">${esc(p.advice)}</p>
      </div>
    </div>` +
    (p.warning ? warnBox(p.warning) : "");

  // Re-render the scatter with the predicted point marked.
  const chart = $("#reg-chart");
  if (chart) chart.innerHTML = result.chart;
}

// ── 04 · probability ───────────────────────────────────────────────────────

function renderProbability() {
  const out = $("#prob-out");
  const column = $("#prob-col").value;

  if (!column) {
    out.innerHTML = errorBox(
      "Este dataset no contiene variables cuantitativas, necesarias para modelar una distribución normal."
    );
    return;
  }

  const result = call("normal", { column });
  if (!result.ok) {
    out.innerHTML = errorBox(result.error);
    return;
  }

  const p = result.profile;
  state.profile = p;
  // Kept so a cleared query can put the plain curve back, unshaded.
  state.profileChart = result.chart;

  const stats = [
    ["Media", "μ", num(p.mu, 4)],
    ["Desv. estándar", "σ", num(p.sigma, 4)],
    ["Mediana", "Q2", num(p.median, 4)],
    ["Mínimo", "min", num(p.min, 3)],
    ["Máximo", "max", num(p.max, 3)],
    ["Observaciones", "n", String(p.n)],
  ]
    .map(
      ([label, symbol, value]) => `<div class="metric flex-1 min-w-[140px]">
        <span class="label !text-[9px] flex items-center gap-1.5">
          ${esc(label)}
          <span class="text-ink-3/70 dark:text-chalk-3/70 normal-case tracking-normal">${symbol}</span>
        </span>
        <span class="metric-value">${value}</span>
      </div>`
    )
    .join("");

  // Empirical rule: observed vs. expected coverage within k standard deviations.
  const empirical = p.empirical
    .map(
      (e) => `<tr>
        <td>μ ± ${e.k}σ</td>
        <td class="num">${pct(e.observed, 2)}</td>
        <td class="num text-ink-3 dark:text-chalk-3">${pct(e.expected, 2)}</td>
        <td class="num">${((e.observed - e.expected) * 100 >= 0 ? "+" : "") +
          num((e.observed - e.expected) * 100, 2)} pp</td>
      </tr>`
    )
    .join("");

  out.innerHTML =
    panel(
      `Perfil de ${column}`,
      `<div class="flex flex-wrap">${stats}</div>
       <div class="px-4 py-3 border-t rule">
         <p class="text-[13px] text-ink-2 dark:text-chalk-2">
           Distribución <strong class="text-ink dark:text-chalk">${esc(p.shape)}</strong>
           (asimetría de Pearson ${num(p.skew, 3)}).
         </p>
       </div>`,
      `n = ${p.n}`
    ) +
    panel(
      "Regla empírica — ajuste a la normal",
      `<div class="overflow-x-auto thin-scroll">
        <table class="data-table">
          <thead><tr>
            <th>Intervalo</th>
            <th class="num">Observado</th>
            <th class="num">Teórico</th>
            <th class="num">Δ</th>
          </tr></thead>
          <tbody>${empirical}</tbody>
        </table>
      </div>`
    ) +
    calculatorForm() +
    chartPanel(
      `Curva normal de ${column}`,
      result.chart,
      `μ = ${num(p.mu, 3)} · σ = ${num(p.sigma, 3)}`,
      "prob-chart"
    );

  $("#prob-kind").addEventListener("change", syncProbInputs);
  $("#btn-prob").addEventListener("click", computeProbability);
  ["#prob-a", "#prob-b"].forEach((sel) =>
    $(sel).addEventListener("keydown", (e) => {
      if (e.key === "Enter") computeProbability();
    })
  );
  syncProbInputs();
}

function calculatorForm() {
  const p = state.profile;
  const hint = `${num(p.min, 2)} – ${num(p.max, 2)}`;
  return panel(
    "Calculadora de probabilidad",
    `<div class="p-4">
      <div class="grid gap-3 sm:grid-cols-[1.4fr_1fr_1fr_auto] sm:items-end">
        <div>
          <label class="label block mb-1.5" for="prob-kind">Consulta</label>
          <select id="prob-kind" class="field">
            <option value="less">P(X &lt; a) — cola izquierda</option>
            <option value="greater">P(X &gt; a) — cola derecha</option>
            <option value="between">P(a &lt; X &lt; b) — intervalo</option>
            <option value="outside">P(X &lt; a ó X &gt; b) — colas</option>
          </select>
        </div>
        <div>
          <label class="label block mb-1.5" for="prob-a">Valor a</label>
          <input id="prob-a" class="field" type="text" inputmode="decimal" placeholder="${hint}">
        </div>
        <div id="prob-b-wrap">
          <label class="label block mb-1.5" for="prob-b">Valor b</label>
          <input id="prob-b" class="field" type="text" inputmode="decimal" placeholder="${hint}">
        </div>
        <button id="btn-prob" class="btn-primary">Calcular</button>
      </div>
      <div id="prob-result" class="mt-4"></div>
    </div>`
  );
}

function syncProbInputs() {
  const kind = $("#prob-kind").value;
  const needsB = kind === "between" || kind === "outside";
  $("#prob-b-wrap").classList.toggle("hidden", !needsB);

  // Drop the previous answer: it belongs to the query that was just replaced,
  // and leaving it on screen next to the new controls reads as if it were the
  // result of them. The curve goes back to its unshaded state for the same
  // reason — a shaded region with no number beside it is a claim about a query
  // nobody made.
  const previous = $("#prob-result");
  if (previous) previous.innerHTML = "";
  const chart = $("#prob-chart");
  if (chart && state.profileChart) chart.innerHTML = state.profileChart;
}

function computeProbability() {
  const out = $("#prob-result");
  const p = state.profile;
  const kind = $("#prob-kind").value;

  const result = call("probability", {
    mu: p.mu,
    sigma: p.sigma,
    kind,
    a: $("#prob-a").value,
    b: $("#prob-b").value,
  });

  if (!result.ok) {
    out.innerHTML = errorBox(result.error);
    return;
  }

  const r = result.result;
  const zs = r.z_values
    .map(
      (z, i) => `<span class="font-mono text-[12px] text-ink-2 dark:text-chalk-2 tnum">
        z<sub>${r.bounds.length > 1 ? (i === 0 ? "a" : "b") : ""}</sub> = ${num(z, 4)}
      </span>`
    )
    .join('<span class="text-rule dark:text-rule-dark">·</span>');

  out.innerHTML = `<div class="fade-in border rule rounded-card overflow-hidden">
    <div class="px-4 py-4 flex flex-wrap items-end gap-x-8 gap-y-3">
      <div>
        <p class="label mb-1.5">${esc(r.expression)}</p>
        <p class="font-mono text-[34px] leading-none tracking-[-0.03em] tnum
                  text-flame dark:text-flame-soft">${num(r.percent, 4)}<span class="text-[20px]">%</span></p>
      </div>
      <div>
        <p class="label mb-1.5">Probabilidad</p>
        <p class="font-mono text-[15px] tnum text-ink-2 dark:text-chalk-2">${num(r.value, 6)}</p>
      </div>
      ${r.odds ? `<div>
        <p class="label mb-1.5">Equivalencia</p>
        <p class="font-mono text-[15px] text-ink-2 dark:text-chalk-2">${esc(r.odds)}</p>
      </div>` : ""}
    </div>
    <div class="px-4 py-3 border-t rule flex flex-wrap items-center gap-3">
      <span class="label">Puntuaciones z</span>${zs}
    </div>
  </div>`;

  // Repaint the curve with the queried region shaded.
  const chart = $("#prob-chart");
  if (chart) chart.innerHTML = result.chart;
}

// ── navigation & wiring ────────────────────────────────────────────────────

function switchView(view) {
  state.view = view;
  $$("#rail .rail-item").forEach((btn) =>
    btn.setAttribute("aria-current", String(btn.dataset.view === view))
  );
  $$("[data-panel]").forEach((section) =>
    section.classList.toggle("hidden", section.dataset.panel !== view)
  );
}

function toggleTheme() {
  const root = document.documentElement;
  const dark = root.getAttribute("data-theme") === "dark";
  const next = dark ? "light" : "dark";
  root.setAttribute("data-theme", next);
  try {
    localStorage.setItem("sk-theme", next);
  } catch (e) {
    /* private mode — the toggle still works for this session */
  }
  syncThemeIcon();
}

function syncThemeIcon() {
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  $("#icon-sun").classList.toggle("hidden", dark);
  $("#icon-moon").classList.toggle("hidden", !dark);
}

function wire() {
  syncThemeIcon();
  $("#btn-theme").addEventListener("click", toggleTheme);

  const picker = $("#file-input");
  $("#btn-load").addEventListener("click", () => picker.click());
  $("#btn-load-2").addEventListener("click", () => picker.click());
  picker.addEventListener("change", (e) => {
    loadFile(e.target.files[0]);
    e.target.value = ""; // allow re-selecting the same file
  });

  $("#btn-home").addEventListener("click", goHome);
  $("#btn-resume").addEventListener("click", resumeAnalysis);
  $("#btn-demo").addEventListener("click", () => loadDemo());

  // Gallery cards are rendered after boot, so the listener sits on the grid.
  $("#samples-grid").addEventListener("click", (e) => {
    const load = e.target.closest("[data-sample]");
    if (load) {
      $("#samples-error").innerHTML = "";
      loadDemo(load.dataset.sample);
      return;
    }
    const save = e.target.closest("[data-download]");
    if (save) {
      $("#samples-error").innerHTML = "";
      downloadSample(save.dataset.download);
    }
  });

  // Drag & drop onto the empty-state target.
  const drop = $("#drop");
  const overlay = $("#drop-overlay");
  let depth = 0;
  const show = (on) => {
    overlay.classList.toggle("hidden", !on);
    overlay.classList.toggle("flex", on);
  };
  ["dragenter", "dragover"].forEach((evt) =>
    drop.addEventListener(evt, (e) => {
      e.preventDefault();
      if (evt === "dragenter") depth++;
      show(true);
    })
  );
  drop.addEventListener("dragleave", () => {
    depth = Math.max(0, depth - 1);
    if (!depth) show(false);
  });
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    depth = 0;
    show(false);
    if (e.dataTransfer.files.length) loadFile(e.dataTransfer.files[0]);
  });

  $$("#rail .rail-item").forEach((btn) =>
    btn.addEventListener("click", () => switchView(btn.dataset.view))
  );

  $("#stats-col").addEventListener("change", renderStats);

  $("#chart-type").addEventListener("change", () => {
    syncChartControls();
    renderChart();
  });
  ["#chart-x", "#chart-y", "#chart-fit"].forEach((sel) =>
    $(sel).addEventListener("change", renderChart)
  );

  $("#btn-train").addEventListener("click", trainModel);
  $("#prob-col").addEventListener("change", renderProbability);
}

wire();
boot();
