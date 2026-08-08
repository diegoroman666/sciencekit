# SciencKit

Herramienta web de minería y análisis de datos. Se carga un `.csv`, `.tsv` o
`.xlsx` y se obtiene estadística descriptiva, gráficos, regresión lineal y
probabilidad normal sobre esos datos.

El motor de cálculo está escrito en **Python** y la interfaz con **Tailwind
CSS**. Los datos nunca se envían a un servidor: el análisis ocurre en el propio
navegador.

---

## Los cuatro módulos

| # | Módulo | Qué hace |
|---|--------|----------|
| 01 | **Datos estadísticos** | Media, mediana, moda, desviación, varianza, coeficiente de variación, rango, cuartiles, IQR e histograma. Si la variable es cualitativa, tabla de frecuencias (absoluta, relativa y acumulada). |
| 02 | **Gráficos** | Dispersión X-Y con recta de ajuste opcional, histograma y barras de frecuencia. |
| 03 | **Predicción** | Regresión lineal por mínimos cuadrados con R², correlación de Pearson y error estándar, más un simulador que proyecta valores y avisa cuando la entrada es una extrapolación. |
| 04 | **Probabilidad** | Distribución normal ajustada a la variable: P(X&lt;a), P(X&gt;a), intervalos y colas, con la región sombreada sobre la curva y comprobación de la regla empírica. |

## Cómo funciona

El punto poco habitual del proyecto: **el mismo código Python se ejecuta en dos
sitios distintos.**

```
core/                        motor de análisis — sólo biblioteca estándar
├── fmt.py                   formato numérico español (coma decimal)
├── dataset.py               lectura de CSV/XLSX e inferencia de tipos
├── analysis.py              estadística, regresión, probabilidad
├── charts.py                gráficos SVG generados desde Python
├── sample.py                cinco datasets de ejemplo incrustados
└── api.py                   dispatch(): única superficie de operaciones
        │
        ├──────────────► app.py      Flask, CPython           (desarrollo)
        └──────────────► app.js      Pyodide, CPython en WASM  (producción)
```

`core/` no importa nada fuera de la biblioteca estándar, así que se puede
importar tal cual bajo CPython y bajo [Pyodide](https://pyodide.org) (CPython
compilado a WebAssembly). Las dos rutas llaman a `core.api.dispatch()`, de modo
que **no existe una segunda implementación de la estadística**: los números del
sitio publicado los produce el mismo código que ejecuta el servidor local.

Netlify no ejecuta Python en el servidor, y por eso el sitio desplegado es
estático y corre el motor en el navegador. `app.js` no contiene ni una fórmula:
sólo transporta datos hacia Python y pinta lo que devuelve.

Los gráficos también son Python — `core/charts.py` genera el SVG directamente,
sin librería de charting. Los colores se referencian como variables CSS, así que
un gráfico cambia de tema claro a oscuro sin volver a renderizarse.

### Detalles de implementación

- **Lector de `.xlsx` sin dependencias**: un `.xlsx` es un zip de XML, así que
  `dataset.py` lo lee con `zipfile` + `xml.etree` en lugar de `openpyxl`. El
  motor se mantiene sin dependencias y por tanto importable en Pyodide sin
  descargar ruedas.
- **Filas alineadas**: las filas con huecos se descartan por pares al ajustar un
  modelo, en lugar de emparejar por índice y desalinear X e Y tras el primer
  hueco.
- **`math.erf`** para la CDF normal, en vez de la aproximación de Abramowitz &
  Stegun: más simple y exacto a precisión de máquina.
- **Números en español** en toda la interfaz, incluida la prosa generada y las
  etiquetas de los ejes (`0,01822`, no `0.01822`).

## Puesta en marcha

Requisitos previos: **Python 3.11+**, **Node 18+** y **Git**.

```bash
git clone -b claude/python-tailwind-web-project-szj7r2 \
    https://github.com/diegoroman666/sciencekit
cd sciencekit
```

Después, según el sistema:

<details open>
<summary><b>Windows</b> (PowerShell, incluida la terminal de VS Code)</summary>

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
npm install
npm run setup     # descarga Pyodide y las fuentes, y compila los estilos
npm run dev       # http://127.0.0.1:5000
```

Si `Activate.ps1` da un error de directivas de ejecución, ejecute una vez:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

</details>

<details>
<summary><b>macOS y Linux</b></summary>

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install
npm run setup     # descarga Pyodide y las fuentes, y compila los estilos
npm run dev       # http://127.0.0.1:5000
```

</details>

Los scripts de npm localizan el intérprete por su cuenta —`python3`, `python` o
el lanzador `py` de Windows— y prefieren el virtualenv del proyecto si existe,
así que funcionan con el venv activado o sin activar.

Durante el desarrollo de estilos conviene dejar Tailwind en modo vigilancia en
otra terminal:

```bash
npm run watch:css
```

## Scripts

| Comando | Efecto |
|---------|--------|
| `npm run dev` | Servidor Flask de desarrollo en el puerto 5000. |
| `npm run watch:css` | Recompila `static/css/app.css` al guardar. |
| `npm run build:css` | Compila y minifica los estilos. |
| `npm run fetch:assets` | Descarga Pyodide y las fuentes a `static/`. |
| `npm run build` | Todo lo anterior y genera el sitio estático en `dist/`. |
| `npm run setup` | `fetch:assets` + `build:css`, para dejarlo listo tras clonar. |
| `python scripts/make_sample.py` | Regenera los cinco datasets de ejemplo. |

Los activos descargados (`static/pyodide/`, `static/fonts/`) y los compilados
(`static/css/app.css`, `dist/`) no están en git: `npm run build` los reconstruye.

## Despliegue

`netlify.toml` ya está configurado:

- **Build**: `python3 -m pip install -r requirements.txt && npm run build`
- **Publish**: `dist`

Netlify ejecuta el build, que descarga los activos, compila Tailwind y renderiza
las plantillas Jinja a HTML estático. El resultado es un directorio de archivos
planos, sin servidor.

Para servir `dist/` en local y comprobar exactamente lo que verá Netlify:

```bash
npm run build
python3 -m http.server 8080 --directory dist
```

## API HTTP (sólo desarrollo)

El servidor Flask expone el mismo dispatch por HTTP, útil para probar el motor
sin navegador:

```bash
curl -X POST localhost:5000/api/demo -H 'Content-Type: application/json' -d '{}'
curl -X POST localhost:5000/api/regression -H 'Content-Type: application/json' \
     -d '{"x":"Fertilizante_kg_ha","y":"Rendimiento_ton_ha"}'
```

Acciones: `load`, `demo`, `samples`, `sample_csv`, `describe`, `frequency`,
`chart`, `regression`, `predict`, `normal`, `probability`.

## Datasets de ejemplo

Cinco tablas de áreas distintas viajan incrustadas en `core/sample.py` y, como
archivo suelto, en `sample_data/`. La pantalla de inicio las lista: un clic las
analiza y el botón «CSV» las descarga. Todas están construidas para que los
módulos se puedan explorar de verdad — cada una tiene un predictor claro y
varias variables que, por separado, ajustan mal.

| Área | Archivo | Filas × cols. | Relación principal | R² |
| --- | --- | --- | --- | --- |
| Agronomía | `rendimiento_cultivos.csv` | 140 × 9 | `Fertilizante_kg_ha` → `Rendimiento_ton_ha` | 0,76 |
| Salud | `salud_cardiovascular.csv` | 150 × 9 | `Edad` → `Presion_sistolica` | 0,73 |
| Educación | `rendimiento_academico.csv` | 160 × 8 | `Horas_estudio_sem` → `Puntaje_final` | 0,53 |
| Economía | `ventas_retail.csv` | 150 × 8 | `Inversion_publicidad_kUSD` → `Ventas_kUSD` | 0,87 |
| Medio ambiente | `calidad_aire.csv` | 150 × 9 | `Trafico_veh_hora` → `PM25_ug_m3` | 0,75 |

Los datos son sintéticos y deterministas: `python scripts/make_sample.py`
reproduce los cinco archivos byte a byte.

## Historia

El repositorio contenía originalmente un prototipo en Flutter/Dart de la misma
herramienta. La lógica estadística se portó a `core/` conservando las fórmulas y
corrigiendo, por el camino, la desalineación de filas con huecos y varias
divisiones por cero que devolvían `NaN` en lugar de un error legible.
