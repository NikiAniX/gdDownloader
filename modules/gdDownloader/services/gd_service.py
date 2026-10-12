"""Pure-Python Google Drive download-and-delete service.

No Flask imports — this module is framework-agnostic and can be tested
or run standalone (e.g. from the original CLI script).
"""

import os
import io
import pickle
from dataclasses import dataclass, field

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCOPES = ["https://www.googleapis.com/auth/drive"]

GOOGLE_DOC_EXPORT_MAP = {
    "application/vnd.google-apps.document": (
        "application/pdf", ".pdf",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
}


# ---------------------------------------------------------------------------
# Result DTO
# ---------------------------------------------------------------------------

@dataclass
class GdDownloadResult:
    """Outcome of a single download-or-delete attempt."""

    status: str  # "success" | "error"
    logs: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "success"


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _authenticate_drive(
    creds_file: str = "credentials.json",
    token_file: str = "token.pickle",
) -> build:
    """Authenticate and return a Drive v3 service object.

    Creates / refreshes a pickle token so subsequent calls can skip OAuth flow.
    """
    creds = None
    if os.path.exists(token_file):
        with open(token_file, "rb") as token:
            creds = pickle.load(token)  # noqa: S301

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "wb") as token:
            pickle.dump(creds, token)

    return build("drive", "v3", credentials=creds)


# ---------------------------------------------------------------------------
# Core download / delete logic (ported from download_and_delete.py)
# ---------------------------------------------------------------------------

def _download_file(
    service: build,
    file_id: str,
    file_name: str,
    mime_type: str,
    destination_dir: str,
) -> tuple[str | None, str]:
    """Download a single file. Returns ``(destination_path, error_msg)``."""
    os.makedirs(destination_dir, exist_ok=True)
    safe_name = file_name.replace("/", "_")
    destination_path = os.path.join(destination_dir, safe_name)

    try:
        if mime_type in GOOGLE_DOC_EXPORT_MAP:
            export_mime, ext = GOOGLE_DOC_EXPORT_MAP[mime_type]
            destination_path += ext
            request = service.files().export_media(fileId=file_id, mimeType=export_mime)
        else:
            request = service.files().get_media(fileId=file_id)

        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()  # type: ignore[assignment]

        with open(destination_path, "wb") as f:
            f.write(fh.getvalue())

        return (destination_path, "")
    except Exception as exc:
        return (None, str(exc))


def _process_folder(
    service: build,
    folder_id: str,
    current_output_dir: str,
    delete_after: bool,
) -> tuple[bool, list[str]]:
    """Recursively list and download files inside a Drive folder.

    Returns ``(all_ok, logs)``.
    """
    os.makedirs(current_output_dir, exist_ok=True)
    page_token = None
    all_ok = True
    logs: list[str] = []

    while True:
        query = f"'{folder_id}' in parents and trashed = false"
        results = service.files().list(  # type: ignore[union-attr]
            q=query,
            pageSize=100,
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=page_token,
        ).execute()

        items = results.get("files", [])
        for item in items:
            item_id = item["id"]
            item_name = item["name"]
            mime_type = item["mimeType"]

            if mime_type == "application/vnd.google-apps.folder":
                sub_dir = os.path.join(current_output_dir, item_name)
                folder_ok, folder_logs = _process_folder(
                    service, item_id, sub_dir, delete_after,
                )
                logs.extend(folder_logs)
                if not folder_ok:
                    all_ok = False
                else:
                    # Delete the folder from Drive after successful recursion
                    if delete_after:
                        try:
                            service.files().delete(fileId=item_id).execute()
                            logs.append(
                                f"Deleted folder from Google Drive: {item_name} ({item_id})",
                            )
                        except Exception as exc:
                            logs.append(
                                f"Failed to delete folder '{item_name}': {exc}",
                            )
                            all_ok = False
            else:
                dest_path, err = _download_file(
                    service, item_id, item_name, mime_type, current_output_dir,
                )
                if not err:
                    logs.append(f"Successfully downloaded: {dest_path}")
                    if delete_after:
                        try:
                            service.files().delete(fileId=item_id).execute()
                            logs.append(
                                f"Deleted file from Google Drive: {item_name} ({item_id})",
                            )
                        except Exception as exc:
                            logs.append(
                                f"Failed to delete file '{item_name}': {exc}",
                            )
                            all_ok = False
                else:
                    logs.append(f"Error downloading file ID {item_id}: {err}")
                    all_ok = False

        page_token = results.get("nextPageToken")
        if not page_token:
            break

    return (all_ok, logs)


def download_and_delete(
    drive_ids: list[str],
    output_dir: str = "./google_drive_downloaded",
    delete_after: bool = True,
    creds_file: str = "credentials.json",
    token_file: str = "token.pickle",
) -> GdDownloadResult:
    """Orchestrate download (and optional deletion) for a list of Drive IDs.

    Each ID may be a file or a folder (folders are processed recursively).
    Returns a `GdDownloadResult` summarising what happened.
    """
    # Authenticate once, reuse the service object across all IDs
    try:
        service = _authenticate_drive(creds_file, token_file)
    except Exception as exc:
        return GdDownloadResult(status="error", logs=[f"Authentication failed: {exc}"])

    overall_ok = True
    logs: list[str] = []

    for file_id in drive_ids:
        try:
            meta = service.files().get(  # type: ignore[union-attr]
                fileId=file_id, fields="name, mimeType",
            ).execute()
            name = meta["name"]
            mime_type = meta["mimeType"]

            logs.append(f"\nProcessing ID: {file_id} ({name})")

            if mime_type == "application/vnd.google-apps.folder":
                folder_dir = os.path.join(output_dir, name)
                folder_ok, folder_logs = _process_folder(
                    service, file_id, folder_dir, delete_after,
                )
                logs.extend(folder_logs)
                if not folder_ok:
                    overall_ok = False
                elif delete_after:
                    try:
                        service.files().delete(fileId=file_id).execute()
                        logs.append(
                            f"Deleted root folder from Google Drive: {name} ({file_id})",
                        )
                    except Exception as exc:
                        logs.append(f"Failed to delete root folder '{name}': {exc}")
                        overall_ok = False
            else:
                dest_path, err = _download_file(
                    service, file_id, name, mime_type, output_dir,
                )
                if not err:
                    logs.append(f"Successfully downloaded: {dest_path}")
                    if delete_after:
                        try:
                            service.files().delete(fileId=file_id).execute()
                            logs.append(
                                f"Deleted file from Google Drive: {name} ({file_id})",
                            )
                        except Exception as exc:
                            logs.append(f"Failed to delete file '{name}': {exc}")
                            overall_ok = False
                else:
                    logs.append(f"Error downloading file ID {file_id}: {err}")
                    overall_ok = False

        except Exception as exc:
            logs.append(f"Could not process ID {file_id}: {exc}")
            overall_ok = False

    status = "success" if overall_ok else "error"
    return GdDownloadResult(status=status, logs=logs)
