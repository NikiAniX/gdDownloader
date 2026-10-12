"""Input validation for the /gdDownloader POST route.

Validators follow the `(ok, messages)` convention — they never raise.
"""


def validate_form_inputs(merged: dict) -> tuple[bool, list[str]]:
    """Validate merged form + file upload data.

    Both ``request.form`` and ``request.files`` have been merged into a
    single dict before calling this function.  Only the ``form`` keys are
    inspected (the merged `files` entries won't clash since this route
    accepts no file uploads).

    Expected keys in *merged*: ``drive_ids``, ``output_dir``, ``delete_after``.

    Returns ``(ok, messages)``.
    """
    errors: list[str] = []

    # --- drive_ids (required, comma-separated or JSON array in a single field) ---
    raw_ids = merged.get("drive_ids", "").strip()
    if not raw_ids:
        errors.append("'drive_ids' is required (comma-separated IDs).")
    else:
        # Accept "id1,id2,id3" format
        ids = [sid.strip() for sid in raw_ids.split(",") if sid.strip()]
        if not ids:
            errors.append("'drive_ids' contains no valid entries.")

    # --- output_dir (optional, defaults to './google_drive_downloaded') ---
    output_dir = merged.get("output_dir", "").strip()
    if output_dir and ".." in output_dir:
        errors.append("'output_dir' must not contain '..'.")

    # --- delete_after (optional, boolean-like) ---
    delete_raw = merged.get("delete_after", "true").strip().lower()
    if delete_raw not in ("true", "false"):
        errors.append("'delete_after' must be 'true' or 'false'.")

    return (len(errors) == 0, errors)
