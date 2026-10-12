# gdDownloader — Claude Setup & Architecture Reference

## Quick Start for Claude

```bash
python app.py          # dev server on :5006
python -m pytest       # run tests (if any)
```

## Core Rules

- **No hardcoded imports** — all feature blueprints are declared in `blueprints.json` and loaded at runtime. Never add a `from . import X` for new modules; update the JSON instead.
- **File upload validation** — always merge `request.form` + `request.files` into one dict before passing to validators (see `modules/gdDownloader/routes.py`).
- **External plugins** use a `"path"` in blueprints.json that points to an **absolute filesystem path** (not an import name).

## Architecture

```
gdDownloader/
├── app.py                      # entry point — loader + factory + server
├── blueprints.json             # manifest: directory → blueprint name → URL prefix
├── requirements.txt            # Dependencies
├── drive_ids.txt               # Default input: comma-separated Drive IDs
├── modules/                    # Feature directories — one per plugin/blueprint
│   └── gdDownloader/           # Google Drive download-and-delete (self-contained)
│       ├── __init__.py         # exports gdDownloader_bp
│       ├── routes.py           # /gdDownloader POST handler
│       ├── validators/         # input validation (relative imports)
│       │   ├── __init__.py
│       │   └── inputs.py       # validate_form_inputs()
│       └── services/           # business logic (framework-free)
│           ├── __init__.py
│           └── gd_service.py   # download_and_delete() + GdDownloadResult
├── tests/                      # Pytest suite
└── .venv/                      # Python virtual environment
```

- **Loader** (`app.py`): reads `blueprints.json`, calls `importlib.util.spec_from_file_location` for each module path.
- **Factory** (`create_app`): builds Flask app, registers blueprints from the manifest.
- **Routes**: thin HTTP layer — validate → delegate to service → return JSON.
- **Services**: pure Python classes/functions, no framework imports (ported from original CLI script).
- **Validators**: return `(ok, messages)` tuples; never raise exceptions.
- **Tests**: `conftest.py` shares fixtures; run with `.venv/bin/python -m pytest tests/`.

## Adding a Feature Blueprint

1. Create `modules/<name>/__init__.py` that re-exports the blueprint under the configured `"name"` key.
2. Append to `blueprints.json`:
   ```json
   { "path": "modules/gdDownloader", "name": "gdDownloader_bp", "url_prefix": "/gdDownloader" }
   ```

## Dependencies

| Package | Role |
|---|---|
| flask | WSGI web framework |
| google-api-python-client | Google Drive API client |
| google-auth-oauthlib | OAuth 2.0 flow for user authentication |
