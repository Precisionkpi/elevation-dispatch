"""Flight Schedule Pro Core API client.

Read-only access to aircraft, instructors, maintenance reminders, and squawks.

Auth: x-subscription-key header (Primary or Secondary key from FSP Settings > API Access).
All endpoints are scoped under /operators/{operatorId}/.

Spec: https://developer.flightschedulepro.com/core/swagger.json

Response shapes (verified against operator 193717):
- Aircraft list: { totalItems, offset, limit, items: [{aircraftId, tailNumber,
    make.name, model.name, status.name, isSimulator, ...}] }
- Instructor list: { totalItems, offset, limit, items: [{userId, firstName,
    lastName, email, instructorStatus.name, ...}] }
- Squawks (with ?resolved=false): list[{squawkId, description, created, resolved,
    groundAircraft, actionTaken, correctiveAction, ...}]  (NOTE: returns a flat
    list when filtered, paginated dict otherwise)
- Maintenance reminders: { items: [{maintenanceReminderId, name, active,
    permanentlyComplied, status.name, dateOptions, timeOptions, cycleOptions}] }
    - dateOptions: { typeStatus.name, message, expirationDate, currentDate }
    - timeOptions: { typeStatus.name, message, expirationHours, currentHours }
"""
from datetime import date, datetime, timedelta

import requests

import config


class FSPError(Exception):
    """Raised for any FSP API issue (auth, network, parse, 4xx/5xx)."""


class FSPClient:
    def __init__(self, api_key=None, operator_id=None, base_url=None,
                 scheduling_base_url=None, reports_base_url=None):
        self.api_key = api_key or config.FSP_API_KEY
        self.operator_id = operator_id or config.FSP_OPERATOR_ID
        self.base_url = (base_url or config.FSP_BASE_URL).rstrip("/")
        self.scheduling_base_url = (scheduling_base_url or config.FSP_SCHEDULING_BASE_URL).rstrip("/")
        self.reports_base_url = (reports_base_url or config.FSP_REPORTS_BASE_URL).rstrip("/")
        if not self.api_key:
            raise FSPError("FSP_API_KEY is not set. Add it to .streamlit/secrets.toml.")
        if not self.operator_id:
            raise FSPError(
                "FSP_OPERATOR_ID is not set. Add your numeric operator ID to "
                ".streamlit/secrets.toml."
            )

    def _headers(self):
        return {"x-subscription-key": self.api_key, "Accept": "application/json"}

    def _get(self, path, params=None, base=None):
        root = (base or self.base_url).rstrip("/")
        url = f"{root}/{path.lstrip('/')}"
        try:
            r = requests.get(url, headers=self._headers(), params=params, timeout=15)
        except requests.RequestException as e:
            raise FSPError(f"Network error talking to FSP: {e}") from e
        if r.status_code == 401:
            raise FSPError("FSP rejected the API key (401). Check FSP_API_KEY.")
        if r.status_code == 400 and "operatorId" in (r.text or ""):
            raise FSPError(
                "FSP says your key is not granted for this operator ID. "
                "Check FSP_OPERATOR_ID matches the operator your key belongs to."
            )
        if r.status_code == 404:
            raise FSPError(f"FSP returned 404 on {path}.")
        if not r.ok:
            raise FSPError(f"FSP {r.status_code} on {path}: {r.text[:300]}")
        try:
            return r.json()
        except ValueError as e:
            raise FSPError(f"FSP returned non-JSON on {path}: {r.text[:200]}") from e

    @staticmethod
    def _items(data):
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("items", "data", "results", "value"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        return []

    @staticmethod
    def _nested_name(obj, key):
        sub = obj.get(key)
        if isinstance(sub, dict):
            n = sub.get("name")
            return n.strip() if isinstance(n, str) else n
        return None

    # ── Aircraft ──────────────────────────────────────────
    def list_aircraft(self):
        data = self._get(
            f"operators/{self.operator_id}/aircraft",
            params={"limit": 200},
        )
        out = []
        seen_ids = set()
        for a in self._items(data):
            if not isinstance(a, dict):
                continue
            aid = a.get("aircraftId")
            if not aid or aid in seen_ids:
                continue
            # Filter deleted aircraft
            status_name = self._nested_name(a, "status")
            if status_name == "Deleted":
                continue
            seen_ids.add(aid)
            make = self._nested_name(a, "make") or ""
            model = self._nested_name(a, "model") or ""
            display_model = f"{make} {model}".strip() or None
            out.append({
                "id": aid,
                "tail_number": a.get("tailNumber"),
                "model": display_model,
                "is_simulator": a.get("isSimulator", False),
                "status": status_name,
                "raw": a,
            })
        # Sort by tail number for predictable dropdown order
        out.sort(key=lambda x: (x["tail_number"] or "").upper())
        return out

    # ── Maintenance reminders ─────────────────────────────
    def get_maintenance_status(self, aircraft_id):
        """Return summary of maintenance reminders for an aircraft."""
        data = self._get(
            f"operators/{self.operator_id}/aircraft/{aircraft_id}/maintenanceReminders",
            params={"limit": 200},
        )
        return self._summarize_maintenance(data)

    @staticmethod
    def _summarize_maintenance(data):
        """Find the soonest-due tach reminder and soonest-due date reminder.

        Each reminder may have a dateOptions block, a timeOptions block, both,
        or neither. We compute hours-remaining from timeOptions and
        days-remaining from dateOptions, ignoring reminders that are inactive
        or permanently complied.
        """
        items = FSPClient._items(data)

        current_tach = None
        tach_remaining = []
        days_remaining = []

        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("permanentlyComplied"):
                continue
            if item.get("active") is False:
                continue
            name = item.get("name") or "Maintenance item"

            t_opts = item.get("timeOptions") or {}
            if isinstance(t_opts, dict):
                exp_hrs = t_opts.get("expirationHours")
                curr_hrs = t_opts.get("currentHours")
                if curr_hrs is not None and current_tach is None:
                    try:
                        current_tach = float(curr_hrs)
                    except (TypeError, ValueError):
                        pass
                if exp_hrs is not None and curr_hrs is not None:
                    try:
                        tach_remaining.append((name, float(exp_hrs) - float(curr_hrs)))
                    except (TypeError, ValueError):
                        pass

            d_opts = item.get("dateOptions") or {}
            if isinstance(d_opts, dict):
                exp_date = d_opts.get("expirationDate") or d_opts.get("dueDate")
                if exp_date:
                    try:
                        d = datetime.fromisoformat(
                            str(exp_date).replace("Z", "+00:00")
                        ).date()
                        days_remaining.append((name, (d - date.today()).days))
                    except (ValueError, TypeError):
                        pass

        return {
            "current_tach": current_tach,
            "tach_until_mx": min(tach_remaining, key=lambda x: x[1]) if tach_remaining else None,
            "days_until_inspection": min(days_remaining, key=lambda x: x[1]) if days_remaining else None,
            "all_tach_items": sorted(tach_remaining, key=lambda x: x[1]),
            "all_date_items": sorted(days_remaining, key=lambda x: x[1]),
            "raw": data,
        }

    # ── Squawks ───────────────────────────────────────────
    def get_open_squawks(self, aircraft_id):
        """Return list of unresolved squawks for an aircraft.

        FSP uses prefix operators for filter values: ``eq:false`` (not just
        ``false``). Other operators (``ne:``) are unsupported on this field.
        """
        data = self._get(
            f"operators/{self.operator_id}/aircraft/{aircraft_id}/squawks",
            params={"resolved": "eq:false", "limit": 200},
        )
        items = self._items(data)
        out = []
        for s in items:
            if not isinstance(s, dict):
                continue
            # Belt-and-suspenders: skip anything marked resolved
            if s.get("resolved") is True:
                continue
            out.append({
                "id": s.get("squawkId"),
                "description": s.get("description") or "(no description)",
                "reported_date": s.get("created"),
                "ground_aircraft": s.get("groundAircraft", False),
                "reference_number": s.get("referenceNumber"),
                "work_order": s.get("workOrderDisplayNumber"),
                "raw": s,
            })
        # Sort so groundAircraft squawks float to the top
        out.sort(key=lambda s: (not s["ground_aircraft"], s.get("reported_date") or ""))
        return out

    def list_active_user_ids(self):
        """Return the set of userIds with status='Active' from /users."""
        data = self._get(
            f"operators/{self.operator_id}/users",
            params={"limit": 500},
        )
        active = set()
        for u in self._items(data):
            if not isinstance(u, dict):
                continue
            status_name = (u.get("status") or {}).get("name") if isinstance(u.get("status"), dict) else None
            if status_name == "Active":
                active.add(u.get("userId"))
        return active

    # ── Pilots (anyone who can fill out a dispatch) ────────
    def list_pilots(self, allowed_roles=(
        "Students", "Instructors", "Administrator", "Renters", "Owners",
    )):
        """Return all people who could file a dispatch.

        Administrators are treated as Instructors (most school admins are also
        CFIs and need the instructor workflow — 'Flying with' field, etc.).
        Filtered client-side from /people (server-side role filter is
        silently ignored).
        """
        data = self._get(
            f"operators/{self.operator_id}/people",
            params={"limit": 500},
        )
        # Cross-reference with /users to skip Inactive / Deleted accounts
        try:
            active_ids = self.list_active_user_ids()
        except FSPError:
            active_ids = None  # fall back to no filtering if /users fails
        allowed = set(allowed_roles)
        # Map FSP role name -> the label we show. Both Instructor & Administrator
        # map to "Instructor" so admins get the instructor experience.
        role_label = {
            "Instructors": "Instructor",
            "Administrator": "Instructor",
            "Students": "Student",
            "Renters": "Renter",
            "Owners": "Owner",
        }
        # Priority for picking the displayed role when a person has multiple.
        priority_order = ("Instructors", "Administrator", "Students", "Renters", "Owners")
        out = []
        for p in self._items(data):
            if not isinstance(p, dict):
                continue
            uid = p.get("userGuidId")
            # Skip if /users says this person is Inactive / Deleted
            if active_ids is not None and uid and uid not in active_ids:
                continue
            role_names = {(r or {}).get("name") for r in (p.get("roles") or []) if r}
            flying_roles = role_names & allowed
            if not flying_roles:
                continue
            first = p.get("firstName") or ""
            last = p.get("lastName") or ""
            name = f"{first} {last}".strip() or p.get("email") or "?"
            primary_role = next(
                (role_label[r] for r in priority_order if r in flying_roles),
                "Pilot",
            )
            out.append({
                "id": uid,
                "name": name,
                "email": p.get("email"),
                "phone": p.get("phone"),
                "primary_role": primary_role,
                "roles": sorted(flying_roles),
                "raw": p,
            })
        out.sort(key=lambda x: x["name"].upper())
        return out

    # ── Students (people with "Students" role) ────────────
    def list_students(self):
        """Return all people whose roles contain 'Students'.

        FSP doesn't support a server-side role filter on /people (the param
        is silently ignored), so we fetch all and filter client-side.
        """
        data = self._get(
            f"operators/{self.operator_id}/people",
            params={"limit": 500},
        )
        out = []
        for p in self._items(data):
            if not isinstance(p, dict):
                continue
            roles = p.get("roles") or []
            if not any((r or {}).get("name") == "Students" for r in roles):
                continue
            first = p.get("firstName") or ""
            last = p.get("lastName") or ""
            name = f"{first} {last}".strip() or p.get("email") or "?"
            out.append({
                "id": p.get("userGuidId"),
                "name": name,
                "email": p.get("email"),
                "phone": p.get("phone"),
                "raw": p,
            })
        out.sort(key=lambda x: x["name"].upper())
        return out

    # ── Reservations (Scheduling API) ─────────────────────
    def get_reservations_for_student_date(self, user_id, day):
        """Return reservations where this user is a pilot, on the given date.

        FSP date filter requires Gte:/Lte: with UTC + Z suffix. We query a
        24-hour UTC window (loose - may catch flights from adjacent days in
        other time zones) and filter client-side to local-date matches.
        """
        if not user_id or not day:
            return []
        # Build a wide UTC window: yesterday midnight UTC to day+2 midnight UTC.
        # We'll filter to the actual local date after.
        start = datetime.combine(day - timedelta(days=1), datetime.min.time())
        end = datetime.combine(day + timedelta(days=2), datetime.min.time())
        params = {
            "startTimeUtc": f"Gte:{start.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            "endTimeUtc": f"Lte:{end.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            "userId": f"eq:{user_id}",
            "limit": 50,
        }
        data = self._get(
            f"operators/{self.operator_id}/reservations",
            params=params,
            base=self.scheduling_base_url,
        )
        out = []
        target_iso = day.isoformat()
        for r in self._items(data):
            if not isinstance(r, dict):
                continue
            # Match by the LOCAL start date (startTime, not startTimeUtc)
            local_start = r.get("startTime") or ""
            if not local_start.startswith(target_iso):
                continue
            out.append(self._normalize_reservation(r))
        out.sort(key=lambda r: r.get("start_time") or "")
        return out

    def get_next_reservation_for_student(self, user_id, lookahead_days=90):
        """Return the soonest reservation that hasn't ended yet, or None.

        A reservation is 'still relevant' if its endTime is in the future,
        i.e., it's either currently active (started but not finished) or
        scheduled to start later. This means an 8 AM block that ends at noon
        is still picked at 8:15 AM (in-window), and a flight that already
        ended at noon won't be picked at 12:30 PM in favour of a later one.
        """
        if not user_id:
            return None
        now = datetime.utcnow()
        # Generous start window (1 week back) to be sure currently-active
        # reservations with early start times are included.
        start_window = datetime.combine(
            date.today() - timedelta(days=7), datetime.min.time()
        )
        params = {
            "startTimeUtc": f"Gte:{start_window.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            "endTimeUtc": f"Gte:{now.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            "userId": f"eq:{user_id}",
            "limit": 100,
        }
        try:
            data = self._get(
                f"operators/{self.operator_id}/reservations",
                params=params,
                base=self.scheduling_base_url,
            )
        except FSPError:
            return None
        items = self._items(data)
        # Sort by local start time, take soonest non-ended
        items.sort(key=lambda r: r.get("startTime") or "9999")
        # Cap lookahead client-side too
        cutoff = (date.today() + timedelta(days=lookahead_days)).isoformat()
        for r in items:
            if not isinstance(r, dict):
                continue
            local_start = (r.get("startTime") or "")[:10]
            if local_start and local_start > cutoff:
                continue
            return self._normalize_reservation(r)
        return None

    @staticmethod
    def _normalize_reservation(r):
        instr = r.get("instructor") or {}
        instr_name = ""
        if isinstance(instr, dict):
            instr_name = f"{instr.get('firstName', '')} {instr.get('lastName', '')}".strip()
        pilots = r.get("pilots") or []
        pilot_names = []
        for p in pilots:
            if isinstance(p, dict):
                pilot_names.append(f"{p.get('firstName', '')} {p.get('lastName', '')}".strip())
        aircraft = r.get("aircraft") or {}
        return {
            "id": r.get("reservationId"),
            "number": r.get("reservationNumber"),
            "start_time": r.get("startTime"),
            "end_time": r.get("endTime"),
            "start_time_utc": r.get("startTimeUtc"),
            "end_time_utc": r.get("endTimeUtc"),
            "type": (r.get("reservationType") or {}).get("name"),
            "instructor_name": instr_name or None,
            "instructor_id": instr.get("userId") if isinstance(instr, dict) else None,
            "pilot_names": pilot_names,
            "aircraft_id": aircraft.get("aircraftId") if isinstance(aircraft, dict) else None,
            "aircraft_tail": aircraft.get("tailNumber") if isinstance(aircraft, dict) else None,
            "raw": r,
        }

    # ── Aircraft meters (Hobbs / Tach) via Reporting API ──
    def list_aircraft_meters(self):
        """Return per-aircraft meter readings from the Reporting API.

        Reporting API exposes Hobbs (airframeHobbs) and Tach (engine1Tach)
        plus billing meter, last-updated, and aircraft TTIS basis. Useful
        for showing current readings right after aircraft selection.
        """
        data = self._get(
            f"operators/{self.operator_id}/aircraft",
            params={"limit": 200},
            base=self.reports_base_url,
        )
        out = []
        for ac in self._items(data):
            if not isinstance(ac, dict):
                continue
            if ac.get("status") == "Deleted":
                continue
            out.append({
                "aircraft_id": ac.get("aircraftId"),
                "tail": ac.get("registrationTail"),
                "hobbs": ac.get("airframeHobbs") if ac.get("airframeHasHobbs") else None,
                "tach": ac.get("engine1Tach") if ac.get("engine1HasTach") else None,
                "billing_meter": ac.get("billingMeter"),
                "ttis": ac.get("airframeTtis"),
                "ttis_based_on": ac.get("airframeTtisBasedOn"),
                "last_updated": ac.get("lastUpdated"),
                "raw": ac,
            })
        return out

    # ── Instructors ───────────────────────────────────────
    def list_instructors(self):
        data = self._get(
            f"operators/{self.operator_id}/instructors",
            params={"limit": 200},
        )
        out = []
        for u in self._items(data):
            if not isinstance(u, dict):
                continue
            status_name = self._nested_name(u, "instructorStatus")
            # Skip Deleted AND Inactive — only show currently-flying instructors
            if status_name in ("Deleted", "Inactive"):
                continue
            first = u.get("firstName") or ""
            last = u.get("lastName") or ""
            name = f"{first} {last}".strip() or u.get("email") or "?"
            out.append({
                "id": u.get("userId"),
                "name": name,
                "email": u.get("email"),
                "raw": u,
            })
        out.sort(key=lambda x: x["name"].upper())
        return out
