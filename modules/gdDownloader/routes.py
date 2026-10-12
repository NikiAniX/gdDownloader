"""HTTP layer for Google Drive download-and-delete.

Thin Flask routes — validation → service delegate → JSON response.
Blueprint is defined here; __init__.py re-exports it.
"""

from flask import Blueprint, request, jsonify

from .services import download_and_delete
from .validators.inputs import validate_form_inputs

gdDownloader_bp = Blueprint("gdDownloader_bp", __name__, url_prefix="/gdDownloader")


@gdDownloader_bp.route("", methods=["POST"])
def trigger_download():
    """POST /gdDownloader — download files/folders from Google Drive.

    Form fields:
        drive_ids   (required)  comma-separated Drive file/folder IDs
        output_dir  (optional)  local directory to save files into
        delete_after(optional, 'true'|'false') delete from Drive after download

    Returns JSON with ``status`` and ``logs``.
    """
    # Merge form + files into one dict (per project convention)
    data = {**request.form.to_dict(flat=True), **request.files.to_dict(flat=True)}

    ok, messages = validate_form_inputs(data)
    if not ok:
        return jsonify({"status": "error", "logs": messages}), 400

    drive_ids = [sid.strip() for sid in request.form.get("drive_ids", "").split(",") if sid.strip()]
    output_dir = (request.form.get("output_dir") or "./google_drive_downloaded").strip() or "./google_drive_downloaded"
    delete_after_raw = (request.form.get("delete_after") or "true").strip().lower()
    delete_after = delete_after_raw == "true"

    result = download_and_delete(
        drive_ids=drive_ids,
        output_dir=output_dir,
        delete_after=delete_after,
    )

    return jsonify({"status": result.status, "logs": result.logs})
