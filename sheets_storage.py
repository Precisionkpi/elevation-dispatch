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


def _client():
    """Return a gspread client authorized via the service account in st.secrets."""
    import streamlit as st
    import gspread
    from google.oauth2.service_account import Credentials

    creds_info = dict(st.secrets["gcp_service_account"])
    # Streamlit reads multi-line private_key with literal "\n"; reassemble.
    if "\\n" in creds_info.get("private_key", ""):
        creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    return gspread.authorize(creds)


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
                    wb_filename: str = "", weather_filename: str = "") -> Optional[int]:
    """Append a dispatch record as a new row. Returns 1-indexed row number written, or None."""
    if not enabled():
        return None
    ws = _open_worksheet()
    submitted = record.get("created_at") or datetime.now().isoformat(timespec="seconds")
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
        wb_filename,
        weather_filename,
        "",  # Reservation # will be added by app if known
        record.get("fsp_aircraft_id", ""),
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    # Return current row count (approximate — gspread doesn't give index directly)
    try:
        return len(ws.get_all_values())
    except Exception:
        return -1
