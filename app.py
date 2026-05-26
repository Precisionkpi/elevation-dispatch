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


# ── Custom CSS — dark theme matching elevationflight.com ───
st.markdown("""
<style>
  /* Brand font */
  @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&display=swap');

  html, body, [class^="css"], [class*=" css"] {
    font-family: 'Outfit', system-ui, -apple-system, BlinkMacSystemFont, sans-serif !important;
  }

  /* Dark page background with subtle sky-blue glow */
  [data-testid="stAppViewContainer"] {
    background:
      radial-gradient(ellipse 1000px 600px at 20% 10%, rgba(74, 154, 219, 0.10) 0%, transparent 60%),
      radial-gradient(ellipse 800px 500px at 90% 90%, rgba(27, 103, 159, 0.08) 0%, transparent 60%),
      linear-gradient(180deg, #0b0d11 0%, #111318 100%);
    background-attachment: fixed;
    color: #f5f3ec;
  }

  /* Main form container as an elevated dark card */
  .block-container {
    padding-top: 4.5rem;
    padding-bottom: 4rem;
    max-width: 780px;
  }
  .block-container > div:first-child {
    background: #1a1d23;
    border-radius: 16px;
    padding: 28px 36px 32px 36px;
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.45), 0 2px 6px rgba(0, 0, 0, 0.25);
    border: 1px solid rgba(255, 255, 255, 0.06);
  }

  /* Logo block — invert the dark logo so it shows in cream on dark */
  .logo-wrap {
    text-align: center;
    padding: 8px 0 16px 0;
    position: relative;
  }
  .logo-wrap img {
    max-width: 380px;
    width: 85%;
    height: auto;
    filter: invert(1) brightness(1.05);
    mix-blend-mode: screen;
  }
  @media (max-width: 640px) {
    .logo-wrap img { width: 88%; }
    .block-container > div:first-child { padding: 20px 18px 24px 18px; }
  }

  /* Title — cream text, with a sky-blue airplane sitting just to the right */
  h1 {
    color: #fbfaf7 !important;
    font-weight: 800 !important;
    letter-spacing: -0.02em !important;
  }
  h1::after {
    content: "";
    display: inline-block;
    width: 0.85em;
    height: 0.85em;
    margin-left: 0.15em;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%239bd5f5'><path d='M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z'/></svg>");
    background-repeat: no-repeat;
    background-size: contain;
    background-position: center;
    vertical-align: middle;
    transform: rotate(45deg);
    opacity: 0.25;
  }

  /* Subtitle / hint text */
  h1 + div p strong { color: #d2ecfc; font-weight: 500; }

  /* Section header with sky-blue accent bar */
  .section-header {
    position: relative;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    color: #9bd5f5;
    text-transform: uppercase;
    margin: 2rem 0 1rem 0;
    padding-left: 14px;
    border-bottom: 1px solid rgba(155, 213, 245, 0.15);
    padding-bottom: 6px;
  }
  .section-header::before {
    content: "";
    position: absolute;
    left: 0;
    top: 2px;
    bottom: 8px;
    width: 4px;
    background: linear-gradient(180deg, #9bd5f5, #1b679f);
    border-radius: 3px;
  }

  /* Form labels */
  label[data-testid="stWidgetLabel"] p {
    font-weight: 600;
    color: #f5f3ec;
    font-size: 0.92rem;
  }

  /* Inputs — dark with subtle border */
  div[data-baseweb="input"] > div,
  div[data-baseweb="select"] > div,
  div[data-baseweb="textarea"] > div {
    border-radius: 10px !important;
    border: 1px solid rgba(255, 255, 255, 0.10) !important;
    background: #262a32 !important;
    color: #f5f3ec !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
  }
  div[data-baseweb="input"]:focus-within > div,
  div[data-baseweb="select"]:focus-within > div {
    border-color: #4a9adb !important;
    box-shadow: 0 0 0 3px rgba(74, 154, 219, 0.18) !important;
  }
  /* Input text */
  div[data-baseweb="input"] input,
  div[data-baseweb="select"] input { color: #f5f3ec !important; }

  /* File uploader */
  [data-testid="stFileUploader"] section {
    border-radius: 10px;
    border: 2px dashed rgba(155, 213, 245, 0.25);
    background: #1f232a;
  }
  [data-testid="stFileUploader"] section:hover {
    border-color: #4a9adb;
    background: #262a32;
  }

  /* Primary button — sky-blue gradient (like website's CONTACT button) */
  div[data-testid="stButton"] > button[kind="primary"] {
    width: 100%;
    border-radius: 12px;
    padding: 0.9rem 2rem;
    font-weight: 700;
    font-size: 1.02rem;
    background: linear-gradient(135deg, #6eb8ec 0%, #1b679f 100%) !important;
    border: none !important;
    color: #ffffff !important;
    box-shadow: 0 4px 14px rgba(27, 103, 159, 0.40);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }
  div[data-testid="stButton"] > button[kind="primary"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 8px 22px rgba(27, 103, 159, 0.55);
  }

  /* Secondary buttons */
  div[data-testid="stButton"] > button:not([kind="primary"]) {
    background: #262a32 !important;
    color: #f5f3ec !important;
    border: 1px solid rgba(255, 255, 255, 0.10) !important;
  }

  /* Alerts — dark variants */
  div[data-testid="stAlert"] { border-radius: 10px; }

  /* Stat block — dark with sky accent label */
  .stat {
    padding: 14px 16px;
    border-radius: 12px;
    background: linear-gradient(135deg, #1f232a 0%, #262a32 100%);
    border: 1px solid rgba(155, 213, 245, 0.12);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.30);
    min-height: 100px;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }
  .stat:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 14px rgba(27, 103, 159, 0.30);
  }
  .stat-label {
    font-size: 0.72rem;
    color: #9bd5f5;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  .stat-value {
    font-size: 1.7rem;
    font-weight: 800;
    color: #fbfaf7;
    line-height: 1.2;
    margin-top: 6px;
  }
  .stat-value.ok { color: #4ade80; }
  .stat-value.warn { color: #fbbf24; }
  .stat-value.danger { color: #f87171; }
  .stat-detail {
    font-size: 0.76rem;
    color: #9ca3af;
    margin-top: 4px;
    white-space: normal;
  }

  /* Identity banner — sky-blue gradient (matches website's CONTACT) */
  .ac-banner {
    background: linear-gradient(135deg, #1b679f, #0c1629);
    color: #ffffff;
    padding: 16px 22px;
    border-radius: 12px;
    margin: 6px 0 14px 0;
    box-shadow: 0 4px 14px rgba(27, 103, 159, 0.30);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .ac-banner .ac-tail { font-size: 1.5rem; font-weight: 800; letter-spacing: -0.01em; }
  .ac-banner .ac-model { font-size: 0.92rem; opacity: 0.85; margin-top: 2px; }
  .ac-banner .ac-status {
    background: rgba(155, 213, 245, 0.25);
    color: #d2ecfc;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.04em;
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
  .status-ok { background: rgba(74, 222, 128, 0.18); color: #4ade80; }
  .status-warn { background: rgba(251, 191, 36, 0.18); color: #fbbf24; }
  .status-danger { background: rgba(248, 113, 113, 0.18); color: #f87171; }

  /* Sidebar */
  [data-testid="stSidebar"] { background: #0c1629 !important; }

  /* Dividers */
  hr { border-color: rgba(255, 255, 255, 0.08) !important; }

  /* Hide chrome inside the iframe */
  footer, #MainMenu { display: none !important; }
  .stDeployButton { display: none !important; }
  header[data-testid="stHeader"] { background: transparent !important; }

  /* Hide Streamlit's auto-generated heading anchor links (the chain icon
     that appears on hover next to h1/h2/h3 titles) */
  h1 > a, h2 > a, h3 > a, h4 > a, h5 > a, h6 > a,
  [data-testid="stHeadingActionElements"],
  [data-testid="stHeadingAnchor"],
  .stMarkdown a[class*="anchor"],
  a[class*="anchor-link"] {
    display: none !important;
  }
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


@st.cache_data(ttl=300)
def cached_pilots():
    return _client().list_pilots()


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
    """Tach hours remaining: red < 5, orange < 10, else green."""
    if hours is None:
        return "ok"
    return "danger" if hours < 5 else "warn" if hours < 10 else "ok"


def _days_status(days):
    """Days until inspection: red < 3, orange < 14, else green."""
    if days is None:
        return "ok"
    return "danger" if days < 3 else "warn" if days < 14 else "ok"


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


# ── Sidebar ────────────────────────────────────────────────
debug_mode = False  # debug expander hidden in production
with st.sidebar:
    if AUTH_ENABLED and user_email:
        st.markdown(f"**Signed in as**  \n{user_name_from_auth}  \n`{user_email}`")
        if st.button("Sign out", use_container_width=True):
            custom_auth.logout()
            st.rerun()


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
        student_list = cached_pilots()
    except FSPError as e:
        fsp_errors.append(f"People: {e}")
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
    # Match logged-in Google email to an FSP person record. Apply any alias
    # from secrets first (lets people log in with one email and match against
    # a different email in FSP).
    lookup_email = config.EMAIL_ALIASES.get(user_email, user_email)
    matched = None
    if student_list and lookup_email:
        matched = next(
            (s for s in student_list if (s.get("email") or "").lower() == lookup_email),
            None,
        )
    if matched:
        selected_student = matched
        name = selected_student["name"]
        role_label = (matched.get("primary_role") or "PILOT").upper()
        st.markdown(
            f'<div class="ac-banner"><div><div class="ac-tail">{name}</div>'
            f'<div class="ac-model">{user_email}</div></div>'
            f'<div class="ac-status">{role_label}</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.error(
            f"Hi {user_name_from_auth or user_email}! Your Google login email "
            f"**{user_email}** isn't matching any FSP record. Two fixes:\n\n"
            f"1. Update your FSP profile email to **{user_email}** (easiest), or\n"
            f"2. Sign in with the Google account that matches your FSP email."
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

# ── Flying with (shown for Instructor / Renter / Owner) ────
# Covers dual-instruction students, another instructor for currency /
# requalification flights, passengers, or any other non-self pilot on the
# reservation. Auto-filled from reservation.pilots[] with the signed-in
# user's own name removed.
student_on_flight = ""
matched_role = (selected_student or {}).get("primary_role")
if matched_role in ("Instructor", "Renter", "Owner"):
    default_other_pilot = ""
    if reservation and reservation.get("pilot_names"):
        my_name_lc = (selected_student.get("name") or "").lower()
        others = [
            n for n in reservation["pilot_names"]
            if n and n.lower() != my_name_lc
        ]
        default_other_pilot = ", ".join(others)
    student_on_flight = st.text_input(
        "Flying with (passenger, student, or co-pilot)",
        value=default_other_pilot,
        help=(
            "Auto-filled from your FSP reservation (excluding yourself). "
            "Works for dual students, a co-instructor (currency / requalification), "
            "or a passenger. Type a name if they're not in FSP. "
            "Leave blank for solo / personal time."
        ),
    )

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

# Route of Flight — single title with the Practice Area checkbox and optional
# free-text field grouped underneath. (colors are inherited from the dark theme)
st.markdown(
    '<div style="font-weight:600;color:#f5f3ec;font-size:0.92rem;'
    'margin:0.5rem 0 0.1rem 0">Route of Flight *</div>'
    '<div style="font-size:0.82rem;color:#b0d9f5;'
    'margin-bottom:0.4rem">Check the Practice Area box if that\'s where '
    'you\'re going. Otherwise, type the route in the field below.</div>',
    unsafe_allow_html=True,
)
practice_area = st.checkbox("Practice Area", value=False)
if practice_area:
    route = "Practice Area"
else:
    route = st.text_input(
        "route_typed",
        placeholder="e.g. KHEF KCJR KHEF",
        label_visibility="collapsed",
        help="Type the route, or check the Practice Area box above.",
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

# Tach until MX — stat block above, blank input below (pilot must type it)
if maint and maint.get("tach_until_mx"):
    name_t, hours_t = maint["tach_until_mx"]
    _stat_block("Tach until MX (from FSP)", f"{hours_t:.1f} hrs", name_t, _hours_status(hours_t))
    st.markdown("")
tach_until_mx = st.text_input(
    "Tach hours until next MX *",
    value="",
    help="Reference the FSP value shown above and type it in here (forces a conscious check).",
)

# Days until Inspection — same pattern
if maint and maint.get("days_until_inspection"):
    name_d, days_d = maint["days_until_inspection"]
    _stat_block("Days until Inspection (from FSP)", f"{days_d} days", name_d, _days_status(days_d))
    st.markdown("")
days_until_inspection = st.text_input(
    "Days until next Inspection *",
    value="",
    help="Reference the FSP value shown above and type it in here (forces a conscious check).",
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
            "student_on_flight": student_on_flight.strip() if student_on_flight else "",
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
                    reservation_number=str(reservation.get("number")) if reservation and reservation.get("number") else "",
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
