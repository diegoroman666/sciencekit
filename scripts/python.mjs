/**
 * Cross-platform Python launcher for the npm scripts.
 *
 * The interpreter is not called the same thing everywhere: `python3` on
 * macOS/Linux, `python` or the `py` launcher on Windows. Hardcoding one of them
 * breaks `npm run build` on the other platform, so this resolves it at runtime.
 *
 * A project virtualenv wins when present, which means the npm scripts work
 * whether or not the venv is activated in the current shell.
 *
 *   node scripts/python.mjs scripts/fetch_pyodide.py
 *   node scripts/python.mjs app.py
 */

import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const windows = process.platform === "win32";

/** Interpreters to try, best first. Venv paths come first so it is preferred. */
function candidates() {
  const venv = windows
    ? [path.join(ROOT, ".venv", "Scripts", "python.exe")]
    : [path.join(ROOT, ".venv", "bin", "python3"), path.join(ROOT, ".venv", "bin", "python")];

  const system = windows
    ? [["python", []], ["py", ["-3"]], ["python3", []]]
    : [["python3", []], ["python", []]];

  return [
    ...venv.filter(existsSync).map((exe) => [exe, []]),
    ...system,
  ];
}

/** True when the interpreter exists and is Python 3.10+. */
function usable(exe, prefix) {
  const probe = spawnSync(exe, [...prefix, "-c", "import sys; print(sys.version_info[:2])"], {
    encoding: "utf8",
    windowsHide: true,
  });
  if (probe.error || probe.status !== 0) return false;
  const match = /\((\d+),\s*(\d+)\)/.exec(probe.stdout || "");
  if (!match) return false;
  const [major, minor] = [Number(match[1]), Number(match[2])];
  return major === 3 && minor >= 10;
}

const args = process.argv.slice(2);
if (args.length === 0) {
  console.error("uso: node scripts/python.mjs <script.py> [args…]");
  process.exit(2);
}

let chosen = null;
for (const [exe, prefix] of candidates()) {
  if (usable(exe, prefix)) {
    chosen = [exe, prefix];
    break;
  }
}

if (!chosen) {
  console.error(
    "\nerror: no se encontró Python 3.10 o superior.\n\n" +
    "  Instálelo desde https://www.python.org/downloads/ y asegúrese de marcar\n" +
    '  "Add Python to PATH" durante la instalación.\n\n' +
    "  Se probaron: " + candidates().map(([e, p]) => [e, ...p].join(" ")).join(", ") + "\n"
  );
  process.exit(1);
}

const [exe, prefix] = chosen;
const child = spawn(exe, [...prefix, ...args], {
  stdio: "inherit",
  cwd: ROOT,
  windowsHide: true,
});

child.on("error", (err) => {
  console.error(`error: no se pudo ejecutar ${exe}: ${err.message}`);
  process.exit(1);
});
child.on("exit", (code, signal) => {
  process.exit(signal ? 1 : code ?? 0);
});
