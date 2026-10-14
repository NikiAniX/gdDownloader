# gdDownloader

Flask API service that downloads (and optionally deletes) files/folders from Google Drive via a POST endpoint.

## Project Structure

```
gdDownloader/
├── app.py                      # Bootstrap — loads blueprints from JSON, creates Flask app
├── blueprints.json             # Feature manifest (add plugins without touching code)
├── requirements.txt            # Dependencies
├── openapi.json                # OpenAPI 3 spec for the API (import into Swagger UI / Postman)
├── drive_ids.txt               # Default input: comma-separated Drive file/folder IDs
├── modules/                    # Feature directories — one per plugin/blueprint
│   └── gdDownloader/           # Google Drive download-and-delete feature
│       ├── __init__.py         # exports gdDownloader_bp
│       ├── routes.py           # /gdDownloader POST route handler
│       ├── validators/         # Input validation (relative imports)
│       │   ├── __init__.py
│       │   └── inputs.py       # validate_form_inputs()
│       └── services/           # Business logic (framework-free)
│           ├── __init__.py
│           └── gd_service.py   # download_and_delete() + GdDownloadResult
├── tests/                      # Pytest suite
└── .venv/                      # Python virtual environment
```

## Setup

```bash
# 1. Create & activate the venv (skip if already done)
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Place your OAuth credentials:
#    Put 'credentials.json' (from Google Cloud Console) in the project root.
```

## Running

```bash
python app.py
# → http://0.0.0.0:5006
```

## API

The OpenAPI 3 spec lives in [`openapi.json`](openapi.json). Paste it into [editor.swagger.io](https://editor.swagger.io) or import it into Postman to explore the API. Keep it in sync when the route changes.

### POST `/gdDownloader`

Downloads files or folders from Google Drive for the given IDs. Files are saved to disk and optionally deleted from Drive.

| Field | Type | Required | Description |
|---|---|---|---|
| `drive_ids` | string | yes | Comma-separated Drive file/folder IDs (e.g. `1AbC...xyz,2DeF...uvw`) |
| `output_dir` | string | no | Local directory to save downloaded files (default: `./google_drive_downloaded`) |
| `delete_after` | string | no | `'true'` or `'false'` — delete source from Drive after download (default: `'true'`) |

**Response** (success):

```json
{
  "status": "success",
  "logs": [
    "\nProcessing ID: 1AbC...xyz (My Folder)",
    "Successfully downloaded: ./google_drive_downloaded/My Folder/report.pdf",
    "Deleted file from Google Drive: report.pdf (1AbC...xyz)",
    "Deleted root folder from Google Drive: My Folder (1AbC...xyz)"
  ]
}
```

**Error response** (bad input):

```json
{
  "status": "error",
  "logs": [
    "'drive_ids' is required (comma-separated IDs)."
  ]
}
```

## Testing

Run the suite:

```bash
.venv/bin/python -m pytest tests/ -v
```

## Environment Overrides (optional)

| Variable | Default | Purpose |
|---|---|---|
| `GD_HOST` | `0.0.0.0` | Bind address |
| `GD_PORT` | `5006` | Bind port |

## Adding a New Feature Blueprint

Every feature lives as a directory under `modules/`. To register one:

1. **Create the module** — `modules/<name>/__init__.py` must export the blueprint under the key in `blueprints.json`.
2. **Append to `blueprints.json`**:

```json
{
  "blueprints": [
    {
      "path": "modules/gdDownloader",
      "name": "gdDownloader_bp",
      "url_prefix": "/gdDownloader"
    },
    {
      "path": "modules/newFeature",
      "name": "newFeature_bp",
      "url_prefix": "/newFeature"
    }
  ]
}
```

No edits to `app.py` are needed. The loader reads `blueprints.json` at startup, imports each module by path via `importlib`, and calls `getattr(module, name)`.

## Technology Stack

| Layer | Tech |
|---|---|
| Web framework | [Flask](https://flask.palletsprojects.com/) (WSGI, micro-framework) |
| Google Drive API | [google-api-python-client](https://github.com/googleapis/google-api-python-client) |
| OAuth | [google-auth-oauthlib](https://github.com/googleapis/google-auth-library-python) |
| Testing | pytest |

## Design Decisions

1. **Blueprints from JSON** — feature directories are loaded by `blueprints.json` at runtime, not hardcoded in Python. Adding a route = one new directory + one JSON line.
2. **Each feature is self-contained** — services and validators live inside the module directory so they use relative imports (`from .validators.inputs import ...`).
3. **Validators never raise** — they return `(ok, messages)` tuples so routes stay thin.
4. **Service layer is framework-agnostic** — `gd_service.py` has no Flask imports, making it testable and runnable standalone (ported from the original CLI script).
