"""SciencKit — Flask development server.

Serves the UI and exposes the analysis engine over HTTP. The engine itself
lives in `core/` and is shared verbatim with the static (Pyodide) build, so
this module contains routing only — no statistics.

    python app.py            # http://127.0.0.1:5000
    flask --app app run      # same, via the Flask CLI
"""

from __future__ import annotations

import os
import secrets

from flask import Flask, jsonify, render_template, request, send_from_directory

from core import __version__
from core.api import ACTIONS, Session, dispatch

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

# One in-process Session per worker. The dev server is single-user by design;
# the deployed build runs entirely client-side, where each browser tab owns its
# own Session, so no cross-user state is possible there.
_session = Session()


@app.context_processor
def inject_globals():
    """`url()` resolves asset paths in templates.

    Templates call `url('static/css/app.css')` rather than `url_for`, because
    `build.py` renders the same templates without a Flask app context. Both
    define this helper identically, so the markup is byte-identical either way.
    """
    return {
        "url": lambda path: "/" + path.lstrip("/"),
        "version": __version__,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/core/<path:filename>")
def core_source(filename: str):
    """Serve the Python engine so the browser runtime can import it.

    Restricted to `.py` files inside `core/`; `send_from_directory` rejects
    any path that escapes the directory.
    """
    if not filename.endswith(".py"):
        return jsonify({"ok": False, "error": "Not found"}), 404
    return send_from_directory(
        os.path.join(app.root_path, "core"), filename, mimetype="text/x-python"
    )


@app.post("/api/<action>")
def api(action: str):
    """Run an engine action server-side. Mirrors the in-browser bridge exactly."""
    if action not in ACTIONS:
        return jsonify({"ok": False, "error": f"Acción desconocida: {action}"}), 404

    payload = request.get_json(silent=True) or {}
    result = dispatch(_session, action, payload)
    return jsonify(result), (200 if result.get("ok") else 400)


@app.get("/health")
def health():
    return jsonify({"ok": True, "version": __version__, "actions": sorted(ACTIONS)})


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


if __name__ == "__main__":
    app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(16)
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=port, debug=True)
