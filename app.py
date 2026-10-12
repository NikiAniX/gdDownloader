"""Bootstrap — loads blueprints from JSON, creates Flask app, starts server."""

import importlib.util
import json
import os
import sys

from flask import Flask


def create_app() -> Flask:
    """Build the Flask application from ``blueprints.json``."""
    app = Flask(__name__)

    manifest_path = os.path.join(os.path.dirname(__file__), "blueprints.json")
    with open(manifest_path, "r") as f:
        config = json.load(f)

    for entry in config.get("blueprints", []):
        mod_path = entry["path"]
        mod_name = entry["name"]
        url_prefix = entry["url_prefix"]

        abs_path = os.path.join(os.path.dirname(__file__), mod_path, "__init__.py")
        spec = importlib.util.spec_from_file_location(mod_name, abs_path)  # noqa: SIM115
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        bp = getattr(mod, mod_name)
        app.register_blueprint(bp, url_prefix=url_prefix)

    return app


if __name__ == "__main__":
    host = os.environ.get("GD_HOST", "0.0.0.0")
    port = int(os.environ.get("GD_PORT", 5006))
    app = create_app()
    app.run(host=host, port=port)
