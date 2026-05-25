"""SQLite storage + PDF export for dispatch submissions."""
import json
import os
import sqlite3
from datetime import datetime

import config


DDL = """
CREATE TABLE IF NOT EXISTS dispatches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    pilot_name TEXT,
    pilot_email TEXT,
    flight_date TEXT,
    block_time TEXT,
    instructor TEXT,
    aircraft TEXT,
    flight_type TEXT,
    route TEXT,
    wb_image_path TEXT,
    weather_image_path TEXT,
    notams_tfr_checked INTEGER,
    flight_plans TEXT,
    tach_until_mx TEXT,
    days_until_inspection TEXT,
    open_squawks TEXT,
    squawks_acknowledged INTEGER,
    fsp_aircraft_id TEXT
);
"""


def init_db():
    os.makedirs(config.UPLOADS_DIR, exist_ok=True)
    with sqlite3.connect(config.DB_FILE) as conn:
        conn.executescript(DDL)
        conn.commit()


def save_dispatch(record):
    init_db()
    record = {**record, "created_at": datetime.now().isoformat(timespec="seconds")}
    cols = list(record.keys())
    with sqlite3.connect(config.DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO dispatches ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
            tuple(record.values()),
        )
        conn.commit()
        return cur.lastrowid


def save_upload(dispatch_id, label, uploaded_file):
    if uploaded_file is None:
        return None
    ext = os.path.splitext(uploaded_file.name)[1].lower() or ".bin"
    folder = os.path.join(config.UPLOADS_DIR, str(dispatch_id))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{label}{ext}")
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return path


def attach_uploads(dispatch_id, wb_path, weather_path):
    with sqlite3.connect(config.DB_FILE) as conn:
        conn.execute(
            "UPDATE dispatches SET wb_image_path = ?, weather_image_path = ? WHERE id = ?",
            (wb_path, weather_path, dispatch_id),
        )
        conn.commit()


def get_dispatch(dispatch_id):
    with sqlite3.connect(config.DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM dispatches WHERE id = ?", (dispatch_id,)
        ).fetchone()
    return dict(row) if row else None


def generate_pdf(dispatch_id):
    from fpdf import FPDF

    row = get_dispatch(dispatch_id)
    if not row:
        return None

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(15, 31, 58)
    pdf.cell(0, 12, f"{config.COMPANY_NAME} Dispatch #{dispatch_id}", ln=1)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(0, 5, f"Submitted: {row.get('created_at', '')}", ln=1)
    pdf.ln(6)

    def _kv(label, value):
        # Label on one line, value (possibly long) on the next — avoids fpdf2's
        # "not enough horizontal space" error when the cursor is offset.
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 4, label.upper(), ln=1)
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(15, 31, 58)
        try:
            pdf.multi_cell(0, 6, str(value if value not in (None, "") else "—"))
        except Exception:
            # Fallback: truncate hard if a value still won't fit
            text = str(value or "—")[:200]
            pdf.cell(0, 6, text, ln=1)
        pdf.ln(1)

    fields = [
        ("Pilot", row.get("pilot_name")),
        ("Date", row.get("flight_date")),
        ("Block Time", row.get("block_time")),
        ("Instructor", row.get("instructor")),
        ("Aircraft", row.get("aircraft")),
        ("Flight Type", row.get("flight_type")),
        ("Route", row.get("route")),
        ("NOTAMs / TFRs Checked", "Yes" if row.get("notams_tfr_checked") else "No"),
        ("Flight Plans Filed", row.get("flight_plans")),
        ("Tach hours until next MX", row.get("tach_until_mx")),
        ("Days until next Inspection", row.get("days_until_inspection")),
        ("Squawks Acknowledged", "Yes" if row.get("squawks_acknowledged") else "No"),
    ]
    for label, value in fields:
        _kv(label, value)

    if row.get("open_squawks"):
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(15, 31, 58)
        pdf.cell(0, 7, "Open Squawks at Dispatch", ln=1)
        pdf.set_font("Helvetica", "", 10)
        try:
            squawks = json.loads(row["open_squawks"])
            if not squawks:
                pdf.cell(0, 5, "None.", ln=1)
            for s in squawks:
                desc = (s.get("description") or "(no description)").strip()
                rep = (s.get("reported_date") or "")[:10] if s.get("reported_date") else "?"
                try:
                    pdf.multi_cell(0, 5, f"- {desc}  (reported {rep})")
                except Exception:
                    pdf.cell(0, 5, f"- {desc[:120]}", ln=1)
        except (json.JSONDecodeError, TypeError):
            try:
                pdf.multi_cell(0, 5, str(row["open_squawks"])[:500])
            except Exception:
                pass

    for label, path in [
        ("Weight & Balance", row.get("wb_image_path")),
        ("Weather Briefing", row.get("weather_image_path")),
    ]:
        if path and os.path.exists(path):
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 14)
            pdf.set_text_color(15, 31, 58)
            pdf.cell(0, 8, label, ln=1)
            pdf.ln(2)
            ext = os.path.splitext(path)[1].lower()
            if ext in (".png", ".jpg", ".jpeg"):
                try:
                    pdf.image(path, w=180)
                except Exception as e:
                    pdf.set_font("Helvetica", "", 10)
                    pdf.cell(0, 5, f"(could not embed image: {e})", ln=1)
            else:
                pdf.set_font("Helvetica", "", 10)
                pdf.cell(0, 5, f"(attached file: {os.path.basename(path)})", ln=1)

    return bytes(pdf.output())
