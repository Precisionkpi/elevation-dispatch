"""Elevation Aviation Dispatch Form.

Streamlit replacement for the Google dispatch form, auto-populated from
Flight Schedule Pro (aircraft list, instructors, maintenance status, squawks).
"""
import json
import os
from datetime import date as date_cls, datetime

import streamlit as st

import config
import custom_auth
import sheets_storage
import storage
from fsp_client import FSPClient, FSPError


st.set_page_config(page_title=f"{config.COMPANY_NAME} Dispatch", page_icon="airplane", layout="centered")


# ── Custom CSS — aviation theme (sky gradient + clouds) ────
st.markdown("""
<style>
  /* Sky gradient page background with soft cloud blurs */
  [data-testid="stAppViewContainer"] {
    background:
      radial-gradient(ellipse 800px 400px at 15% 10%, rgba(255,255,255,0.9) 0%, transparent 60%),
      radial-gradient(ellipse 600px 300px at 85% 20%, rgba(255,255,255,0.7) 0%, transparent 60%),
      radial-gradient(ellipse 700px 350px at 50% 80%, rgba(255,255,255,0.6) 0%, transparent 70%),
      linear-gradient(180deg, #7cc6f0 0%, #b8def0 35%, #e0f2fa 70%, #f4fbff 100%);
    background-attachment: fixed;
  }

  /* Make the main form container a "card" floating on the sky */
  .block-container {
    padding-top: 4.5rem;
    padding-bottom: 4rem;
    max-width: 780px;
  }
  .block-container > div:first-child {
    background: rgba(255, 255, 255, 0.94);
    backdrop-filter: blur(8px);
    border-radius: 18px;
    padding: 28px 36px 32px 36px;
    box-shadow: 0 8px 30px rgba(15, 23, 42, 0.12), 0 2px 6px rgba(15, 23, 42, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.6);
  }

  /* Logo block */
  .logo-wrap {
    text-align: center;
    padding: 8px 0 16px 0;
    position: relative;
  }
  .logo-wrap img { max-width: 380px; width: 85%; height: auto; }
  /* Decorative airplane silhouette top-right */
  .logo-wrap::after {
    content: "";
    position: absolute;
    top: 6px;
    right: 0;
    width: 56px;
    height: 56px;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%231f3a5f'><path d='M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z'/></svg>");
    background-repeat: no-repeat;
    background-size: contain;
    opacity: 0.15;
    transform: rotate(45deg);
  }

  /* Title - aviation navy */
  h1 {
    color: #0c2340 !important;
    font-weight: 800 !important;
    letter-spacing: -0.01em !important;
  }

  /* Section header with airplane accent */
  .section-header {
    position: relative;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    color: #1f3a5f;
    text-transform: uppercase;
    margin: 2rem 0 1rem 0;
    padding-left: 14px;
    border-bottom: 2px solid #cfe8f7;
    padding-bottom: 6px;
  }
  .section-header::before {
    content: "";
    position: absolute;
    left: 0;
    top: 2px;
    bottom: 8px;
    width: 4px;
    background: linear-gradient(180deg, #1f6fb5, #0c2340);
    border-radius: 3px;
  }

  /* Form labels */
  label[data-testid="stWidgetLabel"] p {
    font-weight: 600;
    color: #0c2340;
    font-size: 0.95rem;
  }

  /* Inputs */
  div[data-baseweb="input"] > div,
  div[data-baseweb="select"] > div,
  div[data-baseweb="textarea"] > div {
    border-radius: 8px !important;
    border: 1px solid #c8e0ef !important;
    background: #ffffff !important;
  }
  div[data-baseweb="input"]:focus-within > div,
  div[data-baseweb="select"]:focus-within > div {
    border-color: #1f6fb5 !important;
    box-shadow: 0 0 0 3px rgba(31, 111, 181, 0.15) !important;
  }

  /* File uploader */
  [data-testid="stFileUploader"] section {
    border-radius: 10px;
    border: 2px dashed #9fcaea;
    background: #f0f9ff;
  }

  /* Primary button - sky gradient */
  div[data-testid="stButton"] > button[kind="primary"] {
    width: 100%;
    border-radius: 12px;
    padding: 0.9rem 2rem;
    font-weight: 700;
    font-size: 1.05rem;
    background: linear-gradient(135deg, #1f6fb5 0%, #0c2340 100%) !important;
    border: none !important;
    box-shadow: 0 4px 14px rgba(12, 35, 64, 0.3);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }
  div[data-testid="stButton"] > button[kind="primary"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 22px rgba(12, 35, 64, 0.4);
  }

  /* Alerts */
  div[data-testid="stAlert"] { border-radius: 10px; }

  /* Stat block — sky theme */
  .stat {
    padding: 14px 16px;
    border-radius: 12px;
    background: linear-gradient(135deg, #f4fbff 0%, #e0f2fa 100%);
    border: 1px solid #c8e0ef;
    box-shadow: 0 2px 6px rgba(31, 111, 181, 0.08);
    min-height: 100px;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }
  .stat:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 14px rgba(31, 111, 181, 0.18);
  }
  .stat-label {
    font-size: 0.72rem;
    color: #1f6fb5;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  .stat-value {
    font-size: 1.7rem;
    font-weight: 800;
    color: #0c2340;
    line-height: 1.2;
    margin-top: 6px;
  }
  .stat-value.ok { color: #16a34a; }
  .stat-value.warn { color: #d97706; }
  .stat-value.danger { color: #dc2626; }
  .stat-detail {
    font-size: 0.76rem;
    color: #475569;
    margin-top: 4px;
    white-space: normal;
  }

  /* Status pills */
  .status-pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    margin-left: 8px;
  }
  .status-ok { background: #def7e5; color: #1a7a3a; }
  .status-warn { background: #fef3c7; color: #92400e; }
  .status-danger { background: #fee2e2; color: #991b1b; }

  /* Hide Streamlit chrome */
  footer { visibility: hidden; }
  #MainMenu { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


def _section(title):
    st.markdown(f'<div class="section-header">{title}</div>', unsafe_allow_html=True)


# ── Cached FSP wrappers ────────────────────────────────────
@st.cache_resource
def _client():
    return FSPClient()


@st.cache_data(ttl=300)
def cached_aircraft():
    return _client().list_aircraft()


@st.cache_data(ttl=300)
def cached_instructors():
    return _client().list_instructors()


@st.cache_data(ttl=60)
def cached_maintenance(aircraft_id):
    return _client().get_maintenance_status(aircraft_id)


@st.cache_data(ttl=60)
def cached_squawks(aircraft_id):
    return _client().get_open_squawks(aircraft_id)


@st.cache_data(ttl=300)
def cached_students():
    return _client().list_students()


@st.cache_data(ttl=120)
def cached_aircraft_meters():
    return _client().list_aircraft_meters()


@st.cache_data(ttl=60)
def cached_reservations(student_id, day_iso):
    return _client().get_reservations_for_student_date(
        student_id, date_cls.fromisoformat(day_iso)
    )


@st.cache_data(ttl=120)
def cached_next_reservation(student_id):
    return _client().get_next_reservation_for_student(student_id)


def _fmt_pair(pair, suffix):
    if not pair:
        return "—"
    name, value = pair
    if isinstance(value, float):
        return f"{value:.1f} {suffix} ({name})"
    return f"{value} {suffix} ({name})"


def _stat_block(label, value, detail=None, status="ok"):
    """Render a stat box that wraps cleanly without truncation."""
    value_str = value if value not in (None, "") else "—"
    detail_html = f'<div class="stat-detail">{detail}</div>' if detail else ""
    st.markdown(
        f'<div class="stat">'
        f'<div class="stat-label">{label}</div>'
        f'<div class="stat-value {status}">{value_str}</div>'
        f'{detail_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _hours_status(hours):
    if hours is None:
        return "ok"
    return "danger" if hours < 10 else "warn" if hours < 25 else "ok"


def _days_status(days):
    if days is None:
        return "ok"
    return "danger" if days < 7 else "warn" if days < 30 else "ok"


# ── AUTH GATE (custom Google OAuth — bypasses st.login) ───
AUTH_ENABLED = custom_auth.is_configured()


def _render_logo():
    if os.path.exists(config.LOGO_PATH):
        import base64
        with open(config.LOGO_PATH, "rb") as _f:
            b64 = base64.b64encode(_f.read()).decode()
        st.markdown(
            f'<div class="logo-wrap"><img src="data:image/png;base64,{b64}" alt="logo"/></div>',
            unsafe_allow_html=True,
        )


user_email = ""
user_name_from_auth = ""
if AUTH_ENABLED:
    # If we just came back from Google with ?code=, process it.
    if custom_auth.handle_callback():
        st.rerun()
    user = custom_auth.get_user()
    if not user:
        _render_logo()
        st.title(config.DISPATCH_TITLE)
        st.markdown(f"**{config.DISPATCH_SUBTITLE}**")
        st.markdown("")
        st.info("Please sign in with your school Google account to continue.")
        st.link_button("Sign in with Google", custom_auth.login_url(), type="primary")
        st.stop()
    user_email = user["email"]
    user_name_from_auth = user["name"]


# ── Sidebar: identity + status ─────────────────────────────
with st.sidebar:
    if AUTH_ENABLED and user_email:
        st.markdown(f"**Signed in as**  \n{user_name_from_auth}  \n`{user_email}`")
        if st.button("Sign out", use_container_width=True):
            custom_auth.logout()
            st.rerun()
        st.divider()
    st.header("Settings")
    debug_mode = st.checkbox("Debug FSP responses", value=False,
                             help="Show raw API responses to help diagnose endpoint shapes")
    if config.FSP_API_KEY:
        st.success("FSP key loaded")
    else:
        st.error("FSP_API_KEY missing")
    if config.FSP_OPERATOR_ID:
        st.success(f"Operator: {config.FSP_OPERATOR_ID}")
    else:
        st.error("FSP_OPERATOR_ID missing")
    if sheets_storage.enabled():
        st.success("Google Sheet: connected")
    elif config.GOOGLE_SHEET_ID:
        st.warning("Sheet ID set but service account missing")
    if AUTH_ENABLED:
        st.success("Auth: enabled")
    else:
        st.warning("Auth: not configured (anonymous mode)")
    st.caption(f"Base: `{config.FSP_BASE_URL}`")


# ── Header ─────────────────────────────────────────────────
_render_logo()
st.title(config.DISPATCH_TITLE)
st.markdown(f"**{config.DISPATCH_SUBTITLE}**")
st.caption("\\* Indicates required question")
st.divider()


# ── Try to load FSP catalog data ───────────────────────────
aircraft_list = []
instructor_list = []
student_list = []
fsp_errors = []

if config.FSP_API_KEY:
    try:
        aircraft_list = cached_aircraft()
    except FSPError as e:
        fsp_errors.append(f"Aircraft: {e}")
    try:
        instructor_list = cached_instructors()
    except FSPError as e:
        fsp_errors.append(f"Instructors: {e}")
    try:
        student_list = cached_students()
    except FSPError as e:
        fsp_errors.append(f"Students: {e}")
else:
    st.warning(
        "Flight Schedule Pro API key not configured. The form will still work, "
        "but aircraft/instructor lists and maintenance data won't auto-populate. "
        "Add `FSP_API_KEY` to `.streamlit/secrets.toml`."
    )

for err in fsp_errors:
    st.warning(err)


_section("Pilot & Date")

# ── Name: auto-matched from Google login when auth is on ───
selected_student = None
name = ""
if AUTH_ENABLED:
    # Match logged-in Google email to an FSP student record
    matched = None
    if student_list and user_email:
        matched = next(
            (s for s in student_list if (s.get("email") or "").lower() == user_email),
            None,
        )
    if matched:
        selected_student = matched
        name = selected_student["name"]
        st.markdown(
            f'<div class="ac-banner"><div><div class="ac-tail">{name}</div>'
            f'<div class="ac-model">{user_email}</div></div>'
            f'<div class="ac-status">STUDENT</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.error(
            f"Hi {user_name_from_auth or user_email}! Your Google account email "
            f"**{user_email}** is not registered as a student in Flight Schedule Pro. "
            "Please contact the school admin to be added as a student."
        )
        st.stop()
elif student_list:
    student_names = [s["name"] for s in student_list]
    name_idx = st.selectbox(
        "Name *",
        options=range(len(student_names) + 1),
        format_func=lambda i: "— Choose —" if i == 0 else student_names[i - 1],
    )
    if name_idx > 0:
        selected_student = student_list[name_idx - 1]
        name = selected_student["name"]
else:
    name = st.text_input("Name *",
                         help="FSP student list unavailable; enter manually")

# ── Date (default to student's next upcoming reservation) ──
default_date = date_cls.today()
if selected_student:
    try:
        next_res = cached_next_reservation(selected_student["id"])
        if next_res and next_res.get("start_time"):
            try:
                res_date = datetime.fromisoformat(next_res["start_time"]).date()
                if res_date >= date_cls.today():
                    default_date = res_date
            except ValueError:
                pass
    except FSPError:
        pass
flight_date = st.date_input(
    "Date *",
    value=default_date,
    help=("Defaults to your next upcoming reservation in FSP. "
          "Change to any date to override."),
)

# ── Reservation lookup (student + date) ────────────────────
reservation = None
reservation_error = None
if selected_student and flight_date:
    try:
        reservations = cached_reservations(selected_student["id"], flight_date.isoformat())
    except FSPError as e:
        reservation_error = str(e)
        reservations = []
    if reservations:
        if len(reservations) == 1:
            reservation = reservations[0]
        else:
            res_options = [
                f"#{r['number']}  {r['start_time'][11:16]}–{r['end_time'][11:16]}  "
                f"{r.get('type') or '?'}  ({r.get('aircraft_tail') or 'no AC'})"
                for r in reservations
            ]
            pick = st.selectbox(
                "Multiple reservations on this date — pick one:",
                options=range(len(res_options)),
                format_func=lambda i: res_options[i],
            )
            reservation = reservations[pick]
        st.success(
            f"Auto-filled from FSP reservation #{reservation['number']} "
            f"({reservation.get('type') or 'flight'})"
        )
    elif reservation_error:
        st.warning(f"Could not look up reservations: {reservation_error}")
    else:
        st.info(f"No FSP reservation found for {selected_student['name']} on {flight_date}.")

_section("Flight Details")

# ── Block Time (default from reservation) ──────────────────
default_block = None
if reservation and reservation.get("start_time"):
    try:
        default_block = datetime.fromisoformat(reservation["start_time"]).time()
    except ValueError:
        pass
block_time = st.time_input("Block Time *", value=default_block, help="Flight start time")

# ── Instructor (default from reservation) ──────────────────
NO_INSTRUCTOR = "N/A-Solo"
if instructor_list:
    instructor_names = sorted([i["name"] for i in instructor_list if i["name"]])
    instr_options = ["— Choose —", NO_INSTRUCTOR] + instructor_names
    default_instr_idx = 0
    if reservation:
        res_instr = (reservation.get("instructor_name") or "").strip()
        if res_instr and res_instr in instr_options:
            default_instr_idx = instr_options.index(res_instr)
        elif not res_instr:
            # Reservation has no instructor (solo / rental)
            default_instr_idx = 1
    instructor = st.selectbox(
        "Instructor *",
        options=instr_options,
        index=default_instr_idx,
        help="Pick 'N/A-Solo' for solo or rental flights.",
    )
else:
    instructor = st.text_input(
        "Instructor *",
        value=(reservation["instructor_name"] if reservation and reservation.get("instructor_name") else ""),
        help="FSP instructor list unavailable; enter manually (or type 'N/A' for solo/rental)",
    )

# ── Aircraft (default from reservation) ────────────────────
selected_aircraft_id = None
selected_aircraft_label = None
if aircraft_list:
    options = [(a["id"], f"{a['tail_number'] or '?'} - {a['model'] or '?'}") for a in aircraft_list]
    options.sort(key=lambda x: x[1])
    labels = ["— Choose —"] + [lbl for _, lbl in options]
    default_ac_idx = 0
    if reservation and reservation.get("aircraft_tail"):
        target_tail = reservation["aircraft_tail"]
        for i, (aid, _lbl) in enumerate(options):
            matched = next((a for a in aircraft_list if a["id"] == aid), None)
            if matched and matched["tail_number"] == target_tail:
                default_ac_idx = i + 1
                break
    idx = st.selectbox(
        "Aircraft *",
        options=range(len(labels)),
        format_func=lambda i: labels[i],
        index=default_ac_idx,
    )
    if idx > 0:
        selected_aircraft_id = options[idx - 1][0]
        selected_aircraft_label = options[idx - 1][1]
else:
    selected_aircraft_label = st.text_input(
        "Aircraft *",
        value=(reservation["aircraft_tail"] if reservation and reservation.get("aircraft_tail") else ""),
        help="FSP aircraft list unavailable; enter manually",
    )


if selected_aircraft_id:
    _section("Aircraft Status")

# ── Aircraft meters (Hobbs / Tach) ─────────────────────────
ac_meter = None
if selected_aircraft_id:
    try:
        meters = cached_aircraft_meters()
        ac_meter = next((m for m in meters if m["aircraft_id"] == selected_aircraft_id), None)
    except FSPError as e:
        st.warning(f"Meter readings unavailable: {e}")

    if ac_meter:
        mc1, mc2 = st.columns(2)
        with mc1:
            hobbs = ac_meter.get("hobbs")
            _stat_block(
                "Hobbs",
                f"{hobbs:.1f}" if hobbs is not None else None,
                "hours",
            )
        with mc2:
            tach = ac_meter.get("tach")
            _stat_block(
                "Tach",
                f"{tach:.1f}" if tach is not None else None,
                "hours",
            )
        if ac_meter.get("last_updated"):
            st.caption(f"Meters last updated: {str(ac_meter['last_updated'])[:10]}")
        st.markdown("")


# ── Aircraft-driven info (maintenance, squawks) ────────────
maint = None
squawks = []
squawks_error = None
if selected_aircraft_id:
    with st.spinner("Loading aircraft data from FSP..."):
        try:
            maint = cached_maintenance(selected_aircraft_id)
        except FSPError as e:
            st.warning(f"Maintenance unavailable: {e}")
        try:
            squawks = cached_squawks(selected_aircraft_id)
        except FSPError as e:
            squawks_error = str(e)
            st.warning(f"Squawks unavailable: {e}")

    st.markdown("### Open Squawks")
    if squawks_error:
        st.info("Could not retrieve squawks from FSP — review them manually before dispatch.")
    elif not squawks:
        st.success("No open squawks for this aircraft.")
    else:
        # Flag grounded aircraft at the top
        grounded = [s for s in squawks if s.get("ground_aircraft")]
        if grounded:
            st.error(
                f"AIRCRAFT GROUNDED by {len(grounded)} squawk(s). Do not dispatch."
            )
        for s in squawks:
            with st.container(border=True):
                title = s.get("description") or "Squawk"
                if s.get("ground_aircraft"):
                    st.markdown(f"**{title}**  &nbsp; :red[GROUNDS AIRCRAFT]")
                else:
                    st.markdown(f"**{title}**")
                meta = []
                if s.get("reported_date"):
                    meta.append(f"Reported: {str(s['reported_date'])[:10]}")
                if s.get("reference_number"):
                    meta.append(f"Ref: {s['reference_number']}")
                if s.get("work_order"):
                    meta.append(f"WO: {s['work_order']}")
                if meta:
                    st.caption(" · ".join(meta))

    if debug_mode:
        with st.expander("Raw FSP responses (debug)"):
            st.markdown("**Maintenance:**")
            st.json(maint.get("raw") if maint else {"error": "not loaded"})
            st.markdown("**Squawks:**")
            st.json([s["raw"] for s in squawks])

st.divider()


_section("Pre-flight Briefing")

# ── Remaining form fields ──────────────────────────────────
flight_type = st.radio("Flight Type *", options=config.FLIGHT_TYPES, index=None)

# Route of Flight — default to Practice Area, only collect a typed value when
# the pilot un-checks the box. Stops people leaving 'Practice Area' on
# autopilot for non-practice flights.
practice_area = st.checkbox(
    "Flight to **Practice Area** (uncheck to type a different route)",
    value=True,
)
if practice_area:
    route = "Practice Area"
else:
    route = st.text_input(
        "Route of Flight *",
        placeholder="e.g. KHEF - Practice Area - KHEF, or KHEF KCJR KHEF",
        help="Type the route since this flight isn't going to the practice area.",
    )

wb_file = st.file_uploader(
    "Weight and Balance *",
    type=["png", "jpg", "jpeg", "pdf"],
    help="Insert screen shot of W+B from foreflight (max 10 MB)",
)
weather_file = st.file_uploader(
    "Weather Briefing *",
    type=["png", "jpg", "jpeg", "pdf"],
    help="Insert screenshot of weather along route from foreflight, AWC, or Leidos (at least 3 airports)",
)

notams_checked = st.checkbox("NOTAMs and TFRs Checked *")
flight_plans = st.radio("Exit and return flight plans filed? *",
                        options=config.FLIGHT_PLAN_OPTIONS, index=None)

_section("Maintenance Confirmation")

# Auto-fill tach/inspection numbers from FSP if available
default_tach = ""
default_days = ""
if maint:
    if maint.get("tach_until_mx"):
        default_tach = f"{maint['tach_until_mx'][1]:.1f}"
    if maint.get("days_until_inspection"):
        default_days = str(maint["days_until_inspection"][1])

# Tach until MX — stat block + confirmation input
if maint and maint.get("tach_until_mx"):
    name_t, hours_t = maint["tach_until_mx"]
    _stat_block("Tach until MX (from FSP)", f"{hours_t:.1f} hrs", name_t, _hours_status(hours_t))
    st.markdown("")
tach_until_mx = st.text_input(
    "Tach hours until next MX *",
    value=default_tach,
    help="Use whatever MX action is soonest measured by tach time (auto-filled from FSP when aircraft selected).",
)

# Days until Inspection — stat block + confirmation input
if maint and maint.get("days_until_inspection"):
    name_d, days_d = maint["days_until_inspection"]
    _stat_block("Days until Inspection (from FSP)", f"{days_d} days", name_d, _days_status(days_d))
    st.markdown("")
days_until_inspection = st.text_input(
    "Days until next Inspection *",
    value=default_days,
    help="Use whatever Inspection is soonest based on date (auto-filled from FSP when aircraft selected).",
)

squawks_ack = False
if squawks:
    squawks_ack = st.checkbox(f"I have reviewed all {len(squawks)} open squawks *")

st.divider()


# ── Submit ─────────────────────────────────────────────────
if st.button("Submit Dispatch", type="primary"):
    errors = []
    if not name.strip():
        errors.append("Name is required")
    if not instructor or instructor == "— Choose —":
        errors.append("Instructor (or 'N/A-Solo') is required")
    if not selected_aircraft_label:
        errors.append("Aircraft is required")
    if not flight_type:
        errors.append("Flight Type is required")
    if not route.strip():
        errors.append("Route of Flight is required")
    if not wb_file:
        errors.append("Weight and Balance image is required")
    if not weather_file:
        errors.append("Weather Briefing image is required")
    if not notams_checked:
        errors.append("NOTAMs and TFRs must be checked")
    if not flight_plans:
        errors.append("Flight plans question is required")
    if not tach_until_mx.strip():
        errors.append("Tach hours until next MX is required")
    if not days_until_inspection.strip():
        errors.append("Days until next Inspection is required")
    if squawks and not squawks_ack:
        errors.append("Please acknowledge the open squawks")

    if errors:
        for e in errors:
            st.error(e)
    else:
        record = {
            "pilot_name": name.strip(),
            "pilot_email": user_email,
            "flight_date": flight_date.isoformat(),
            "block_time": block_time.isoformat() if block_time else "",
            "instructor": instructor,
            "aircraft": selected_aircraft_label,
            "flight_type": flight_type,
            "route": route.strip(),
            "wb_image_path": None,
            "weather_image_path": None,
            "notams_tfr_checked": int(notams_checked),
            "flight_plans": flight_plans,
            "tach_until_mx": tach_until_mx.strip(),
            "days_until_inspection": days_until_inspection.strip(),
            "open_squawks": json.dumps([
                {
                    "description": s.get("description"),
                    "reported_date": s.get("reported_date"),
                    "ground_aircraft": s.get("ground_aircraft", False),
                    "reference_number": s.get("reference_number"),
                }
                for s in squawks
            ]),
            "squawks_acknowledged": int(squawks_ack),
            "fsp_aircraft_id": selected_aircraft_id or "",
        }
        dispatch_id = storage.save_dispatch(record)
        wb_path = storage.save_upload(dispatch_id, "wb", wb_file)
        wx_path = storage.save_upload(dispatch_id, "weather", weather_file)
        storage.attach_uploads(dispatch_id, wb_path, wx_path)

        # Also append to Google Sheet if configured
        sheet_msg = ""
        if sheets_storage.enabled():
            grounded_flag = any(s.get("ground_aircraft") for s in squawks)

            # Upload images to Drive (clickable links go into the Sheet)
            wb_url = ""
            weather_url = ""

            def _mime(name):
                lname = (name or "").lower()
                if lname.endswith(".png"):
                    return "image/png"
                if lname.endswith(".jpg") or lname.endswith(".jpeg"):
                    return "image/jpeg"
                if lname.endswith(".pdf"):
                    return "application/pdf"
                return "application/octet-stream"

            # Attempt upload if either route is configured (Apps Script bridge
            # OR a Shared Drive folder where the service account is a member).
            upload_configured = bool(
                config.APPS_SCRIPT_UPLOAD_URL or config.GOOGLE_DRIVE_FOLDER_ID
            )
            upload_errors = []
            if upload_configured:
                with st.spinner("Uploading attachments..."):
                    if wb_file:
                        try:
                            wb_url = sheets_storage.upload_to_drive(
                                wb_file.getvalue(),
                                f"dispatch-{dispatch_id}-wb-{wb_file.name}",
                                _mime(wb_file.name),
                            )
                        except Exception as e:
                            upload_errors.append(f"W&B: {str(e)[:140]}")
                    if weather_file:
                        try:
                            weather_url = sheets_storage.upload_to_drive(
                                weather_file.getvalue(),
                                f"dispatch-{dispatch_id}-weather-{weather_file.name}",
                                _mime(weather_file.name),
                            )
                        except Exception as e:
                            upload_errors.append(f"Weather: {str(e)[:140]}")
            for ue in upload_errors:
                st.info(f"Image upload skipped — {ue}")

            try:
                sheets_storage.append_dispatch(
                    record,
                    pilot_email=user_email,
                    squawks_count=len(squawks),
                    grounded=grounded_flag,
                    hobbs=(ac_meter or {}).get("hobbs") if ac_meter else None,
                    tach=(ac_meter or {}).get("tach") if ac_meter else None,
                    wb_url=wb_url,
                    weather_url=weather_url,
                    wb_filename=(wb_file.name if wb_file else ""),
                    weather_filename=(weather_file.name if weather_file else ""),
                )
                sheet_msg = " · logged to Google Sheet"
            except Exception as e:
                st.warning(f"Google Sheet write failed (saved locally): {e}")

        st.success(f"Dispatch #{dispatch_id} submitted{sheet_msg}.")
        try:
            pdf_bytes = storage.generate_pdf(dispatch_id)
            if pdf_bytes:
                st.download_button(
                    "Download PDF",
                    data=pdf_bytes,
                    file_name=f"dispatch-{dispatch_id}.pdf",
                    mime="application/pdf",
                )
        except Exception as e:
            st.warning(f"PDF generation failed: {e}")
