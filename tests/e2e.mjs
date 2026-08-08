/**
 * End-to-end and usability suite.
 *
 * Drives the real app in a real browser — Pyodide, the Python engine and the
 * UI together — because that is the only place the three meet. Everything the
 * Python tests cannot see lives here: the gallery, the downloads, the four
 * modules wired to their controls, keyboard access, the mobile layout and both
 * themes.
 *
 *   python app.py &                     # or serve dist/
 *   node tests/e2e.mjs [http://127.0.0.1:5000]
 *
 * Chromium is located via PLAYWRIGHT_CHROMIUM (defaults to the bundled one).
 */

import { chromium } from "playwright";

const BASE = process.argv[2] || process.env.SK_BASE_URL || "http://127.0.0.1:5000";
const EXECUTABLE = process.env.PLAYWRIGHT_CHROMIUM || undefined;
const BOOT_TIMEOUT = 180_000;

let passed = 0;
const failures = [];

async function check(name, fn) {
  try {
    await fn();
    passed++;
    console.log(`  ✓ ${name}`);
  } catch (err) {
    failures.push({ name, message: err && err.message ? err.message : String(err) });
    console.log(`  ✗ ${name}\n      ${err && err.message ? err.message : err}`);
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function equal(actual, expected, message) {
  if (actual !== expected) {
    throw new Error(`${message}: esperado ${expected}, obtenido ${actual}`);
  }
}

function section(title) {
  console.log(`\n${title}`);
}

/** Console errors are failures: a silent exception is still a broken page. */
function watchConsole(page, sink) {
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const url = (msg.location() && msg.location().url) || "";
    // Self-hosted fonts are fetched by `npm run setup`; a bare checkout without
    // them is a missing asset, not a defect in the page.
    if (/\.woff2?($|\?)/.test(url) || /favicon/.test(url)) return;
    sink.push(`${msg.text()} ${url}`.trim());
  });
  page.on("pageerror", (err) => sink.push(`pageerror: ${err.message}`));
}

async function boot(browser, options = {}) {
  const page = await browser.newPage({
    viewport: options.viewport || { width: 1280, height: 900 },
    colorScheme: options.colorScheme || "light",
  });
  const errors = [];
  watchConsole(page, errors);
  await page.goto(BASE, { waitUntil: "load" });
  await page.waitForSelector("#samples-grid article", { timeout: BOOT_TIMEOUT });
  return { page, errors };
}

/** The engine's own catalogue — the source of truth the UI must agree with. */
async function catalogue(page) {
  return page.evaluate(() =>
    JSON.parse(window.__sk_dispatch ? window.__sk_dispatch("samples", {}) : "{}")
  );
}

async function main() {
  const browser = await chromium.launch({ executablePath: EXECUTABLE });
  const consoleErrors = [];

  // ── boot & gallery ──────────────────────────────────────────────────────
  section("Arranque y galería");
  const { page, errors } = await boot(browser);
  consoleErrors.push(...errors);

  await check("el overlay de arranque desaparece cuando el motor está listo", async () => {
    equal(await page.locator("#boot").count(), 0, "overlay");
  });

  await check("la galería muestra las cinco tarjetas", async () => {
    equal(await page.locator("#samples-grid article").count(), 5, "tarjetas");
  });

  const cards = await page.$$eval("#samples-grid article", (nodes) =>
    nodes.map((n) => ({
      area: n.querySelector(".chip").textContent.trim(),
      title: n.querySelector("h4").textContent.trim(),
      meta: n.querySelector(".tnum").textContent.trim(),
      key: n.querySelector("[data-sample]").dataset.sample,
      download: n.querySelector("[data-download]").dataset.download,
    }))
  );

  await check("cada tarjeta declara área, título, tamaño y ambos botones", async () => {
    for (const card of cards) {
      assert(card.area.length > 2, `área vacía en ${card.key}`);
      assert(card.title.length > 4, `título vacío en ${card.key}`);
      assert(/^\d+ × \d+$/.test(card.meta), `meta mal formada: ${card.meta}`);
      equal(card.download, card.key, "clave de descarga");
    }
  });

  await check("las áreas de las tarjetas no se repiten", async () => {
    const areas = cards.map((c) => c.area);
    equal(new Set(areas).size, areas.length, "áreas únicas");
  });

  await check("no hay desbordamiento horizontal en escritorio", async () => {
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    assert(overflow <= 0, `la página desborda ${overflow}px`);
  });

  await check("el pie muestra el crédito de desarrollo", async () => {
    const footer = (await page.locator("footer").innerText()).replace(/\s+/g, " ");
    assert(/Diego Rom[áa]n/.test(footer), `pie sin crédito: ${footer}`);
    assert(/IEI/.test(footer), "pie sin IEI");
    assert(/2026/.test(footer), "pie sin el año");
    assert(/[Dd]erechos reservados/.test(footer), "pie sin derechos reservados");
  });

  // ── every dataset through every module ──────────────────────────────────
  section("Los cinco datasets a través de los cuatro módulos");

  for (const card of cards) {
    const fresh = await boot(browser);
    consoleErrors.push(...fresh.errors);
    const p = fresh.page;

    await check(`${card.key}: se carga desde la tarjeta`, async () => {
      await p.click(`[data-sample="${card.key}"]`);
      await p.waitForSelector("#workspace:not([hidden])");
      const status = await p.locator("#status-line").innerText();
      const [rows, columns] = card.meta.split(" × ");
      assert(status.includes(`${rows} filas`), `estado sin filas: ${status}`);
      assert(status.includes(`${columns} columnas`), `estado sin columnas: ${status}`);
      equal(await p.locator("#empty").isVisible(), false, "estado vacío oculto");
    });

    await check(`${card.key}: módulo 01 calcula todas las variables`, async () => {
      const options = await p.$$eval("#stats-col option", (o) => o.map((n) => n.value));
      assert(options.length >= 6, "pocas columnas en el selector");
      for (const name of options) {
        await p.selectOption("#stats-col", name);
        await p.waitForTimeout(30);
        const out = await p.locator("#stats-out").innerText();
        assert(!/notice-error/.test(await p.locator("#stats-out").innerHTML()),
          `error en ${name}`);
        assert(out.length > 40, `salida vacía para ${name}`);
      }
      // A quantitative column shows metrics; a qualitative one a table.
      const numeric = await p.$$eval("#reg-x option", (o) => o.map((n) => n.value));
      await p.selectOption("#stats-col", numeric[0]);
      assert((await p.locator("#stats-out .metric").count()) >= 8, "faltan métricas");
      assert((await p.locator("#stats-out svg").count()) >= 1, "falta el histograma");
    });

    await check(`${card.key}: módulo 02 dibuja los tres tipos de gráfico`, async () => {
      await p.click('[data-view="graficos"]');
      for (const type of ["scatter", "histogram", "bars"]) {
        await p.selectOption("#chart-type", type);
        await p.waitForTimeout(60);
        assert((await p.locator("#chart-out svg").count()) >= 1, `sin SVG en ${type}`);
        const html = await p.locator("#chart-out").innerHTML();
        assert(!html.includes("notice-error"), `error en ${type}`);
        assert(!html.includes("NaN"), `NaN en ${type}`);
      }
      await p.selectOption("#chart-type", "scatter");
      await p.check("#chart-fit");
      await p.waitForTimeout(60);
      assert((await p.locator("#chart-out").innerText()).includes("R²"), "sin R² con ajuste");
    });

    await check(`${card.key}: módulo 03 ajusta y predice`, async () => {
      await p.click('[data-view="prediccion"]');
      await p.click("#btn-train");
      await p.waitForSelector("#reg-out .metric");
      const metrics = await p.locator("#reg-out").innerText();
      assert(/R²/.test(metrics), "sin R²");
      assert(!/NaN/.test(metrics), "NaN en las métricas");

      await p.fill("#predict-input", "10");
      await p.click("#btn-predict");
      await p.waitForTimeout(120);
      const prediction = await p.locator("#reg-out").innerText();
      assert(/proyecta|Predicción|predic/i.test(prediction), "sin resultado de predicción");
    });

    await check(`${card.key}: módulo 04 resuelve las cuatro consultas`, async () => {
      await p.click('[data-view="probabilidad"]');
      await p.waitForSelector("#prob-kind");
      for (const kind of ["less", "greater", "between", "outside"]) {
        await p.selectOption("#prob-kind", kind);
        const needsB = kind === "between" || kind === "outside";
        const mu = Number(await p.getAttribute("#prob-a", "placeholder").then((s) =>
          (s || "").replace(/[^\d,.-]/g, "").replace(".", "").replace(",", ".")
        ));
        const a = Number.isFinite(mu) && mu !== 0 ? mu * 0.9 : 1;
        await p.fill("#prob-a", String(Math.round(a * 100) / 100).replace(".", ","));
        if (needsB) {
          await p.fill("#prob-b", String(Math.round(a * 1.2 * 100) / 100).replace(".", ","));
        }
        await p.click("#btn-prob");
        await p.waitForTimeout(120);
        const out = await p.locator("#prob-result").innerText();
        assert(/%/.test(out), `sin porcentaje para ${kind}: ${out}`);
        assert(!/NaN/.test(out), `NaN para ${kind}`);
        assert(!/notice-error/.test(await p.locator("#prob-result").innerHTML()),
          `error para ${kind}: ${out}`);
      }
    });

    await check(`${card.key}: cambiar de consulta no deja el resultado anterior`, async () => {
      await p.selectOption("#prob-kind", "less");
      await p.fill("#prob-a", "1");
      await p.click("#btn-prob");
      assert((await p.locator("#prob-result").innerText()).includes("%"), "sin resultado previo");
      await p.selectOption("#prob-kind", "greater");
      await p.waitForTimeout(80);
      equal(
        (await p.locator("#prob-result").innerText()).trim(),
        "",
        "el resultado de la consulta anterior sigue en pantalla"
      );
    });

    await p.close();
  }

  // ── downloads ───────────────────────────────────────────────────────────
  section("Descargas");
  const dl = await boot(browser);
  consoleErrors.push(...dl.errors);

  for (const card of cards) {
    await check(`${card.key}: el CSV se descarga y es legible`, async () => {
      const [download] = await Promise.all([
        dl.page.waitForEvent("download", { timeout: 30_000 }),
        dl.page.click(`[data-download="${card.key}"]`),
      ]);
      const name = download.suggestedFilename();
      assert(name.endsWith(".csv"), `nombre inesperado: ${name}`);

      const fs = await import("node:fs");
      const buffer = fs.readFileSync(await download.path());
      equal(buffer.slice(0, 3).toString("hex"), "efbbbf", "BOM UTF-8");

      const text = buffer.toString("utf8").replace(/^﻿/, "");
      const lines = text.trim().split("\n");
      const [rows, columns] = card.meta.split(" × ").map(Number);
      equal(lines.length, rows + 1, "filas del archivo");
      equal(lines[0].split(",").length, columns, "columnas del archivo");
      assert(!/undefined|NaN/.test(text), "el CSV contiene valores inválidos");
    });
  }

  await check("un CSV descargado se puede volver a cargar en la app", async () => {
    const [download] = await Promise.all([
      dl.page.waitForEvent("download"),
      dl.page.click('[data-download="salud"]'),
    ]);
    await dl.page.setInputFiles("#file-input", await download.path());
    await dl.page.waitForSelector("#workspace:not([hidden])");
    const status = await dl.page.locator("#status-line").innerText();
    assert(status.includes("150 filas"), `estado tras recargar: ${status}`);
    assert(status.includes("9 columnas"), `columnas tras recargar: ${status}`);
  });
  await dl.page.close();

  // ── uploads & errors ────────────────────────────────────────────────────
  section("Carga de archivos y manejo de errores");
  const up = await boot(browser);
  consoleErrors.push(...up.errors);

  await check("un archivo ilegible muestra un error sin romper la app", async () => {
    const fs = await import("node:fs");
    const os = await import("node:os");
    const path = await import("node:path");
    const file = path.join(os.tmpdir(), "sk-basura.csv");
    fs.writeFileSync(file, "");
    await up.page.setInputFiles("#file-input", file);
    await up.page.waitForTimeout(400);
    const error = await up.page.locator("#empty-error").innerText();
    assert(error.trim().length > 0, "no se mostró ningún error");
    equal(await up.page.locator("#workspace").isVisible(), false, "workspace no debe abrirse");
  });

  await check("tras el error, cargar un dataset válido sigue funcionando", async () => {
    await up.page.click('[data-sample="ventas"]');
    await up.page.waitForSelector("#workspace:not([hidden])");
    assert((await up.page.locator("#status-line").innerText()).includes("150 filas"), "estado");
  });

  await check("arrastrar y soltar un archivo lo carga", async () => {
    const drop = await boot(browser);
    consoleErrors.push(...drop.errors);
    await drop.page.evaluate(() => {
      const csv = "a,b\n1,2\n3,4\n5,7\n";
      const file = new File([csv], "arrastrado.csv", { type: "text/csv" });
      const transfer = new DataTransfer();
      transfer.items.add(file);
      const zone = document.querySelector("#drop");
      zone.dispatchEvent(new DragEvent("dragenter", { bubbles: true, dataTransfer: transfer }));
      zone.dispatchEvent(new DragEvent("drop", { bubbles: true, dataTransfer: transfer }));
    });
    await drop.page.waitForSelector("#workspace:not([hidden])", { timeout: 15_000 });
    const status = await drop.page.locator("#status-line").innerText();
    assert(status.includes("arrastrado.csv"), `estado: ${status}`);
    await drop.page.close();
  });
  await up.page.close();

  // ── usability ───────────────────────────────────────────────────────────
  section("Usabilidad y accesibilidad");
  const ux = await boot(browser);
  consoleErrors.push(...ux.errors);

  await check("la página declara idioma, título y un solo h1", async () => {
    equal(await ux.page.getAttribute("html", "lang"), "es", "lang");
    assert((await ux.page.title()).length > 8, "título corto");
    equal(await ux.page.locator("h1").count(), 1, "número de h1");
  });

  await check("todos los botones tienen nombre accesible", async () => {
    const unnamed = await ux.page.$$eval("button", (nodes) =>
      nodes
        .filter((n) => {
          const label = (n.getAttribute("aria-label") || n.textContent || "").trim();
          return label.length === 0;
        })
        .map((n) => n.outerHTML.slice(0, 80))
    );
    equal(unnamed.length, 0, `botones sin nombre: ${unnamed.join(" | ")}`);
  });

  await check("todos los selects tienen etiqueta asociada", async () => {
    const orphans = await ux.page.$$eval("select", (nodes) =>
      nodes
        .filter((n) => !n.id || !document.querySelector(`label[for="${n.id}"]`))
        .map((n) => n.id || n.outerHTML.slice(0, 60))
    );
    equal(orphans.length, 0, `selects sin etiqueta: ${orphans.join(", ")}`);
  });

  await check("los gráficos se anuncian como imágenes con descripción", async () => {
    await ux.page.click('[data-sample="cultivos"]');
    await ux.page.waitForSelector("#stats-out svg");
    const described = await ux.page.$$eval("#stats-out svg", (nodes) =>
      nodes.every((n) => n.getAttribute("role") === "img" && n.getAttribute("aria-label"))
    );
    assert(described, "algún SVG no tiene role/aria-label");
  });

  await check("el riel marca el módulo activo con aria-current", async () => {
    await ux.page.click('[data-view="graficos"]');
    equal(
      await ux.page.getAttribute('[data-view="graficos"]', "aria-current"),
      "true",
      "aria-current activo"
    );
    equal(
      await ux.page.getAttribute('[data-view="datos"]', "aria-current"),
      "false",
      "aria-current inactivo"
    );
  });

  await check("se puede navegar con el teclado hasta activar un módulo", async () => {
    await ux.page.click('[data-view="datos"]');
    await ux.page.focus('[data-view="prediccion"]');
    await ux.page.keyboard.press("Enter");
    equal(
      await ux.page.getAttribute('[data-view="prediccion"]', "aria-current"),
      "true",
      "activación por teclado"
    );
  });

  await check("el foco es visible en los controles principales", async () => {
    await ux.page.focus("#btn-load");
    const outline = await ux.page.evaluate(() => {
      const style = getComputedStyle(document.querySelector("#btn-load"), null);
      return `${style.outlineStyle}|${style.outlineWidth}|${style.boxShadow}`;
    });
    assert(outline !== "none|0px|none", `sin indicador de foco: ${outline}`);
  });

  await check("Enter en el simulador ejecuta la predicción", async () => {
    await ux.page.click('[data-view="prediccion"]');
    await ux.page.click("#btn-train");
    await ux.page.waitForSelector("#predict-input");
    await ux.page.fill("#predict-input", "150");
    await ux.page.press("#predict-input", "Enter");
    await ux.page.waitForTimeout(150);
    assert(
      /proyecta|predic/i.test(await ux.page.locator("#reg-out").innerText()),
      "Enter no ejecutó la predicción"
    );
  });

  await check("el cambio de tema persiste tras recargar", async () => {
    await ux.page.click("#btn-theme");
    const theme = await ux.page.getAttribute("html", "data-theme");
    await ux.page.reload({ waitUntil: "load" });
    await ux.page.waitForSelector("#samples-grid article", { timeout: BOOT_TIMEOUT });
    equal(await ux.page.getAttribute("html", "data-theme"), theme, "tema tras recargar");
  });
  await ux.page.close();

  // ── responsive & dark ───────────────────────────────────────────────────
  section("Diseño responsivo y tema oscuro");
  const mobile = await boot(browser, {
    viewport: { width: 390, height: 844 },
    colorScheme: "dark",
  });
  consoleErrors.push(...mobile.errors);

  await check("móvil: la página no desborda horizontalmente", async () => {
    const overflow = await mobile.page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    assert(overflow <= 1, `desborda ${overflow}px`);
  });

  await check("móvil: la galería se apila en una columna", async () => {
    const boxes = await mobile.page.$$eval("#samples-grid article", (nodes) =>
      nodes.map((n) => n.getBoundingClientRect().left)
    );
    equal(new Set(boxes.map(Math.round)).size, 1, "columnas en móvil");
  });

  await check("móvil: se puede trabajar con un dataset", async () => {
    await mobile.page.click('[data-sample="aire"]');
    await mobile.page.waitForSelector("#workspace:not([hidden])");
    await mobile.page.click('[data-view="graficos"]');
    assert((await mobile.page.locator("#chart-out svg").count()) >= 1, "sin gráfico en móvil");
    const overflow = await mobile.page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    assert(overflow <= 1, `el workspace desborda ${overflow}px en móvil`);
  });

  await mobile.page.close();

  // ── contrast ────────────────────────────────────────────────────────────
  section("Contraste de texto (WCAG AA, 4,5:1)");

  /**
   * Measures every text node the app actually paints, against the background
   * actually behind it — walking up for the first opaque ancestor, the way a
   * reader's eye does.
   */
  const measureContrast = () =>
    // eslint-disable-next-line no-undef
    Array.from(document.querySelectorAll("body *"))
      .filter((node) => {
        const text = Array.from(node.childNodes)
          .filter((n) => n.nodeType === 3)
          .map((n) => n.textContent.trim())
          .join("");
        if (!text) return false;
        const box = node.getBoundingClientRect();
        return box.width > 0 && box.height > 0;
      })
      .map((node) => {
        const parse = (value) => (value.match(/[\d.]+/g) || [0, 0, 0]).slice(0, 3).map(Number);
        const alpha = (value) => {
          const parts = value.match(/[\d.]+/g) || [];
          return parts.length > 3 ? Number(parts[3]) : 1;
        };
        const luminance = ([r, g, b]) => {
          const channel = (c) => {
            const v = c / 255;
            return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
          };
          return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
        };

        let background = null;
        for (let el = node; el; el = el.parentElement) {
          const value = getComputedStyle(el).backgroundColor;
          if (alpha(value) > 0.85) {
            background = parse(value);
            break;
          }
        }
        if (!background) return null;

        const style = getComputedStyle(node);
        if (alpha(style.color) < 0.85) return null;
        const [high, low] = [luminance(background), luminance(parse(style.color))]
          .sort((a, b) => b - a);
        return {
          ratio: (high + 0.05) / (low + 0.05),
          size: parseFloat(style.fontSize),
          text: node.textContent.trim().slice(0, 32),
          selector: node.tagName.toLowerCase() + (node.id ? `#${node.id}` : ""),
        };
      })
      .filter(Boolean);

  const report = (failing) =>
    failing
      .slice(0, 6)
      .map((f) => `${f.selector} "${f.text}" ${f.ratio.toFixed(2)}:1 @${f.size}px`)
      .join(" | ");

  for (const scheme of ["light", "dark"]) {
    const themed = await boot(browser, { colorScheme: scheme });
    consoleErrors.push(...themed.errors);

    // 4,5:1 for body text; large text may use 3:1, but nothing here relies on
    // that, so one threshold covers the page.
    await check(`${scheme}: la pantalla de inicio alcanza 4,5:1`, async () => {
      const samples = await themed.page.evaluate(measureContrast);
      assert(samples.length > 30, `sólo se midieron ${samples.length} nodos`);
      const failing = samples.filter((s) => s.ratio < 4.5);
      equal(failing.length, 0, report(failing));
    });

    await check(`${scheme}: el área de trabajo alcanza 4,5:1`, async () => {
      await themed.page.click('[data-sample="cultivos"]');
      await themed.page.waitForSelector("#stats-out .metric");
      const views = ["datos", "graficos", "prediccion", "probabilidad"];
      const failing = [];
      for (const view of views) {
        await themed.page.click(`[data-view="${view}"]`);
        if (view === "prediccion") {
          await themed.page.click("#btn-train");
          await themed.page.waitForSelector("#predict-input");
        }
        // Park the pointer away from the controls and let the 150 ms colour
        // transition finish: a button caught mid-hover reads as a false
        // failure, since neither the start nor the end colour is on screen.
        await themed.page.mouse.move(0, 0);
        await themed.page.waitForTimeout(300);
        failing.push(...(await themed.page.evaluate(measureContrast)).filter((s) => s.ratio < 4.5));
      }
      equal(failing.length, 0, report(failing));
    });

    await check(`${scheme}: el botón primario contrasta también con el puntero encima`, async () => {
      await themed.page.click('[data-view="datos"]');
      await themed.page.hover("#btn-load");
      await themed.page.waitForTimeout(300);
      const ratio = await themed.page.evaluate(() => {
        const parse = (v) => (v.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
        const luminance = ([r, g, b]) => {
          const channel = (c) => {
            const v = c / 255;
            return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
          };
          return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
        };
        const button = document.querySelector("#btn-load");
        const style = getComputedStyle(button);
        const background = parse(
          style.backgroundColor.startsWith("rgba(0, 0, 0, 0)")
            ? getComputedStyle(document.body).backgroundColor
            : style.backgroundColor
        );
        const [a, b] = [luminance(background), luminance(parse(style.color))].sort(
          (x, y) => y - x
        );
        return (a + 0.05) / (b + 0.05);
      });
      assert(ratio >= 4.5, `botón con hover a ${ratio.toFixed(2)}:1`);
    });

    await check(`${scheme}: el botón primario contrasta con su etiqueta`, async () => {
      const ratio = await themed.page.evaluate(() => {
        const parse = (v) => (v.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
        const luminance = ([r, g, b]) => {
          const channel = (c) => {
            const v = c / 255;
            return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
          };
          return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
        };
        const button = document.querySelector(".btn-primary");
        const style = getComputedStyle(button);
        const [a, b] = [
          luminance(parse(style.backgroundColor)),
          luminance(parse(style.color)),
        ].sort((x, y) => y - x);
        return (a + 0.05) / (b + 0.05);
      });
      assert(ratio >= 4.5, `botón primario a ${ratio.toFixed(2)}:1`);
    });

    await themed.page.close();
  }

  // ── final ───────────────────────────────────────────────────────────────
  section("Consola");
  await check("ningún error de consola en toda la sesión", async () => {
    equal(consoleErrors.length, 0, `errores: ${consoleErrors.slice(0, 5).join(" | ")}`);
  });

  await page.close();
  await browser.close();

  console.log(`\n${passed} comprobaciones correctas, ${failures.length} fallidas`);
  if (failures.length) {
    for (const failure of failures) console.log(`  ✗ ${failure.name}: ${failure.message}`);
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
