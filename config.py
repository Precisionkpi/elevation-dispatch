"""Configuration for the Elevation Aviation dispatch app.

Values are resolved in this order: Streamlit secrets -> env var -> hardcoded default.
Never put real secrets in this file. Use .streamlit/secrets.toml.
"""
import os

try:
    import streamlit as st
    _HAVE_STREAMLIT = True
except ImportError:
    _HAVE_STREAMLIT = False


def _get(key, default=None):
    if _HAVE_STREAMLIT:
        try:
            if key in st.secrets:
                return st.secrets[key]
        except Exception:
            pass
    return os.environ.get(key, default)


def _csv(val):
    if not val:
        return []
    return [v.strip() for v in val.split(",") if v.strip()]


_HERE = os.path.dirname(os.path.abspath(__file__))

# Branding
COMPANY_NAME = _get("COMPANY_NAME", "Elevation Aviation")
DISPATCH_TITLE = _get("DISPATCH_TITLE", "Dispatch")
DISPATCH_SUBTITLE = _get(
    "DISPATCH_SUBTITLE",
    "Complete Elevation Aviation dispatch form prior to each flight",
)
LOGO_PATH = _get("LOGO_PATH", os.path.join(_HERE, "elevation_logo.png"))

# Flight Schedule Pro API
FSP_API_KEY = _get("FSP_API_KEY", "")
FSP_OPERATOR_ID = _get("FSP_OPERATOR_ID", "")  # numeric operator ID; see FSP web app URL
FSP_BASE_URL = _get("FSP_BASE_URL", "https://usc-api.flightschedulepro.com/core/v1.0")
FSP_SCHEDULING_BASE_URL = _get(
    "FSP_SCHEDULING_BASE_URL",
    "https://usc-api.flightschedulepro.com/scheduling/v1.0",
)
FSP_REPORTS_BASE_URL = _get(
    "FSP_REPORTS_BASE_URL",
    "https://usc-api.flightschedulepro.com/reports/v1.0",
)

# Google Sheets storage (optional). When GOOGLE_SHEET_ID is set AND a
# [gcp_service_account] section exists in secrets.toml, submissions are
# appended to that sheet. Falls back to SQLite-only if either is missing.
GOOGLE_SHEET_ID = _get("GOOGLE_SHEET_ID", "")
GOOGLE_SHEET_WORKSHEET = _get("GOOGLE_SHEET_WORKSHEET", "Dispatches")
# Drive folder to upload W&B + Weather images into.
GOOGLE_DRIVE_FOLDER_ID = _get("GOOGLE_DRIVE_FOLDER_ID", "")
# Optional subfolder inside the Drive folder where uploaded images go.
# Auto-created on first upload. Set to "" to drop files in the root folder.
GOOGLE_DRIVE_PHOTOS_SUBFOLDER = _get("GOOGLE_DRIVE_PHOTOS_SUBFOLDER", "Photos")

# Google Apps Script web-app URL used to upload files. Apps Script runs as
# the user who deployed it, so it bypasses the 'service accounts have no
# storage quota' limitation. Without this URL, image uploads are silently
# skipped and the Sheet just records the filename.
APPS_SCRIPT_UPLOAD_URL = _get("APPS_SCRIPT_UPLOAD_URL", "")

# Storage (local backup; primary in dev, secondary in prod)
DB_FILE = _get("DB_FILE", os.path.join(_HERE, "dispatch.db"))
UPLOADS_DIR = _get("UPLOADS_DIR", os.path.join(_HERE, "uploads"))

# Optional access control (comma-separated emails). Empty = no auth.
ALLOWED_EMAILS = _csv(_get("ALLOWED_EMAILS", ""))


def _get_email_aliases():
    """Return {google_login_email: fsp_email} mapping from secrets [email_aliases].

    Lets people sign in with a Google email that differs from what FSP has,
    by pointing the login email at their FSP-known email."""
    if not _HAVE_STREAMLIT:
        return {}
    try:
        aliases = st.secrets.get("email_aliases", None)
        if aliases is None:
            return {}
        return {str(k).lower(): str(v).lower() for k, v in dict(aliases).items()}
    except Exception:
        return {}


EMAIL_ALIASES = _get_email_aliases()

# Form options
FLIGHT_TYPES = ["Dual Local", "Dual XC", "Local Solo", "XC Solo", "Rental"]
FLIGHT_PLAN_OPTIONS = ["Yes", "N/A - HEF Patterns"]
