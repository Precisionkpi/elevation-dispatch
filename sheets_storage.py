"""Append dispatch submissions to a Google Sheet.

Uses a Google Cloud service account (credentials in st.secrets) to write
rows to a Sheet identified by GOOGLE_SHEET_ID. The Sheet must be shared
with the service-account email (Editor permission).

Designed to be opt-in: callers should check ``enabled()`` before using.
"""
from datetime import datetime
from typing import Optional

import config


HEADER_ROW = [
    "Submitted At",
    "Pilot Email",
    "Pilot Name",
    "Flight Date",
    "Block Time",
    "Instructor",
    "Aircraft",
    "Flight Type",
    "Route",
    "Hobbs",
    "Tach",
    "Tach hrs until next MX",
    "Days until next Inspection",
    "NOTAMs / TFRs Checked",
    "Flight Plans Filed",
    "Open Squawks Count",
    "Squawks Acknowledged",
    "Grounded Aircraft Flag",
    "W&B Image (filename)",
    "Weather Image (filename)",
    "FSP Reservation #",
    "FSP Aircraft ID",
    "Flying With (if Instructor)",  # appended last to preserve column order
]


def enabled() -> bool:
    """Return True if both the sheet ID and service-account secrets are configured."""
    if not config.GOOGLE_SHEET_ID:
        return False
    try:
        import streamlit as st
        return "gcp_service_account" in st.secrets
    except Exception:
        return False


def _creds_info():
    import streamlit as st
    creds_info = dict(st.secrets["gcp_service_account"])
    if "\\n" in creds_info.get("private_key", ""):
        creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
    return creds_info


def _client():
    """Return a gspread client authorized via the service account in st.secrets."""
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(_creds_info(), scopes=scopes)
    return gspread.authorize(creds)


def _drive_service():
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_service_account_info(
        _creds_info(),
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


_subfolder_cache: dict = {}


def _get_or_create_subfolder(service, parent_id: str, name: str) -> str:
    """Look up <name> subfolder under <parent_id>; create it if missing. Cached."""
    key = (parent_id, name)
    if key in _subfolder_cache:
        return _subfolder_cache[key]

    # Drive search — escape single quotes in the folder name
    safe_name = name.replace("'", "\\'")
    query = (
        f"name = '{safe_name}' "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and '{parent_id}' in parents "
        f"and trashed = false"
    )
    res = service.files().list(
        q=query,
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        spaces="drive",
    ).execute()
    folders = res.get("files", [])
    if folders:
        folder_id = folders[0]["id"]
    else:
        created = service.files().create(
            body={
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            },
            fields="id",
            supportsAllDrives=True,
        ).execute()
        folder_id = created["id"]

    _subfolder_cache[key] = folder_id
    return folder_id


def upload_to_drive(file_bytes: bytes, filename: str, mimetype: str = "application/octet-stream") -> str:
    """Upload bytes to Drive via Apps Script bridge (preferred) or direct API.

    Apps Script bridge bypasses Google's restriction that service accounts have
    no personal storage quota — the script runs as the user who deployed it.
    Configure APPS_SCRIPT_UPLOAD_URL in secrets and follow SETUP.md to deploy
    the script.
    """
    if config.APPS_SCRIPT_UPLOAD_URL:
        return _upload_via_apps_script(file_bytes, filename, mimetype)

    if not config.GOOGLE_DRIVE_FOLDER_ID:
        raise RuntimeError("No upload destination configured.")

    # Direct Drive API path (works with Shared Drives)
    import io
    from googleapiclient.http import MediaIoBaseUpload

    service = _drive_service()

    # Drop into a Photos subfolder if configured (auto-created)
    target_folder = config.GOOGLE_DRIVE_FOLDER_ID
    if config.GOOGLE_DRIVE_PHOTOS_SUBFOLDER:
        try:
            target_folder = _get_or_create_subfolder(
                service,
                config.GOOGLE_DRIVE_FOLDER_ID,
                config.GOOGLE_DRIVE_PHOTOS_SUBFOLDER,
            )
        except Exception:
            # Fall back to the root folder if subfolder lookup/create fails
            target_folder = config.GOOGLE_DRIVE_FOLDER_ID

    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mimetype, resumable=False)
    created = service.files().create(
        body={"name": filename, "parents": [target_folder]},
        media_body=media,
        fields="id, webViewLink",
        supportsAllDrives=True,
    ).execute()
    file_id = created["id"]
    try:
        service.permissions().create(
            fileId=file_id,
            body={"role": "reader", "type": "anyone"},
            fields="id",
            supportsAllDrives=True,
        ).execute()
    except Exception:
        pass
    return created.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"


def _upload_via_apps_script(file_bytes: bytes, filename: str, mimetype: str) -> str:
    """POST the file (base64-encoded) to the Apps Script bridge, get a Drive URL back."""
    import base64
    import requests

    payload = {
        "filename": filename,
        "mimetype": mimetype,
        "folderId": config.GOOGLE_DRIVE_FOLDER_ID,
        "content_b64": base64.b64encode(file_bytes).decode("ascii"),
    }
    r = requests.post(
        config.APPS_SCRIPT_UPLOAD_URL, json=payload, timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"Apps Script returned {r.status_code}: {r.text[:200]}")
    try:
        data = r.json()
    except ValueError as e:
        raise RuntimeError(f"Apps Script returned non-JSON: {r.text[:200]}") from e
    if data.get("error"):
        raise RuntimeError(f"Apps Script error: {data['error']}")
    url = data.get("url")
    if not url:
        raise RuntimeError(f"Apps Script returned no URL: {data}")
    return url


def _hyperlink(url: str, label: str) -> str:
    """Wrap a URL as a Sheet HYPERLINK formula. value_input_option=USER_ENTERED parses it."""
    if not url:
        return ""
    safe_url = url.replace('"', '%22')
    safe_label = (label or "Open").replace('"', "'")
    return f'=HYPERLINK("{safe_url}", "{safe_label}")'


def _open_worksheet():
    gc = _client()
    sh = gc.open_by_key(config.GOOGLE_SHEET_ID)
    try:
        ws = sh.worksheet(config.GOOGLE_SHEET_WORKSHEET)
    except Exception:
        # Worksheet doesn't exist yet — create it with the header row.
        ws = sh.add_worksheet(
            title=config.GOOGLE_SHEET_WORKSHEET, rows=1000, cols=len(HEADER_ROW),
        )
        ws.append_row(HEADER_ROW)
        return ws
    # Ensure header row exists
    try:
        existing = ws.row_values(1)
    except Exception:
        existing = []
    if not existing:
        ws.append_row(HEADER_ROW)
    return ws


def append_dispatch(record: dict, *, pilot_email: str = "", squawks_count: int = 0,
                    grounded: bool = False, hobbs: Optional[float] = None,
                    tach: Optional[float] = None,
                    wb_url: str = "", weather_url: str = "",
                    wb_filename: str = "", weather_filename: str = "") -> Optional[int]:
    """Append a dispatch record as a new row.

    If wb_url / weather_url are provided (Drive links), they're written as
    HYPERLINK formulas so the Sheet shows clickable "View W&B" / "View Weather"
    cells. Falls back to filename text if URL not given.
    """
    if not enabled():
        return None
    ws = _open_worksheet()
    submitted = record.get("created_at") or datetime.now().isoformat(timespec="seconds")
    wb_cell = _hyperlink(wb_url, f"View W&B ({wb_filename})") if wb_url else wb_filename
    weather_cell = _hyperlink(weather_url, f"View Weather ({weather_filename})") if weather_url else weather_filename
    row = [
        submitted,
        pilot_email,
        record.get("pilot_name", ""),
        record.get("flight_date", ""),
        record.get("block_time", ""),
        record.get("instructor", ""),
        record.get("aircraft", ""),
        record.get("flight_type", ""),
        record.get("route", ""),
        f"{hobbs:.1f}" if hobbs is not None else "",
        f"{tach:.1f}" if tach is not None else "",
        record.get("tach_until_mx", ""),
        record.get("days_until_inspection", ""),
        "Yes" if record.get("notams_tfr_checked") else "No",
        record.get("flight_plans", ""),
        squawks_count,
        "Yes" if record.get("squawks_acknowledged") else "No",
        "Yes" if grounded else "No",
        wb_cell,
        weather_cell,
        "",  # Reservation # placeholder
        record.get("fsp_aircraft_id", ""),
        record.get("student_on_flight", ""),  # appended last
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    try:
        return len(ws.get_all_values())
    except Exception:
        return -1
