"""Find Chandler's today flight specifically. Show its raw FSP fields."""
from pathlib import Path
import requests
import json


def load_key():
    for line in (Path(__file__).parent / ".streamlit" / "secrets.toml").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("FSP_API_KEY"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")


KEY = load_key()
OP_ID = "193717"
HEADERS = {"x-subscription-key": KEY, "Accept": "application/json"}
ALEX_ID = "869171f5-e828-474c-b82a-6237279a09b2"

# Look at ALL of Alex's reservations starting in the last 2 days
print("=== Filter: startTimeUtc>=2026-06-01, no endTime filter ===")
r = requests.get(
    f"https://usc-api.flightschedulepro.com/scheduling/v1.0/operators/{OP_ID}/reservations",
    headers=HEADERS,
    params={
        "startTimeUtc": "Gte:2026-06-01T00:00:00Z",
        "endTimeUtc": "Lte:2026-06-04T00:00:00Z",
        "userId": f"eq:{ALEX_ID}",
        "limit": 50,
    },
    timeout=15,
)
print(f"HTTP {r.status_code}")
items = r.json().get("items", [])
items.sort(key=lambda x: x.get("startTime") or "9999")
print(f"{len(items)} reservations:")
for it in items:
    pilots = it.get("pilots") or []
    pilot_names = [(p.get("firstName", "") + " " + p.get("lastName", "")).strip() for p in pilots]
    status = (it.get("status") or {}).get("name") if isinstance(it.get("status"), dict) else it.get("status")
    print(f"  #{it.get('reservationNumber')} {it.get('startTime')}->{it.get('endTime')}  utc={it.get('startTimeUtc')}->{it.get('endTimeUtc')}  status={status!r}  pilots={pilot_names}")

# Now print Chandler's today flight raw JSON
print("\n=== Reservation #76534860 (Chandler today) raw fields ===")
for it in items:
    if str(it.get("reservationNumber")) == "76534860":
        print(json.dumps(it, indent=2, default=str)[:2000])
        break
else:
    print("NOT FOUND in the result set above.")
