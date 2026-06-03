"""Probe Alex's reservations through FSP using the exact filter the app sends."""
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

import requests


def load_key():
    for line in (Path(__file__).parent / ".streamlit" / "secrets.toml").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("FSP_API_KEY"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")


KEY = load_key()
OP_ID = "193717"
HEADERS = {"x-subscription-key": KEY, "Accept": "application/json"}
ALEX_ID = "869171f5-e828-474c-b82a-6237279a09b2"

now_utc = datetime.utcnow()
now_aware = datetime.now(timezone.utc)
est = timezone(timedelta(hours=-4))
now_est = datetime.now(est)

print(f"now UTC : {now_aware.isoformat()}")
print(f"now EDT : {now_est.isoformat()}")
print()

start_window = datetime.combine(date.today() - timedelta(days=7), datetime.min.time())
params = {
    "startTimeUtc": f"Gte:{start_window.strftime('%Y-%m-%dT%H:%M:%SZ')}",
    "endTimeUtc": f"Gte:{now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}",
    "userId": f"eq:{ALEX_ID}",
    "limit": 20,
}
print("Filter:", params)
print()

r = requests.get(
    f"https://usc-api.flightschedulepro.com/scheduling/v1.0/operators/{OP_ID}/reservations",
    headers=HEADERS, params=params, timeout=15,
)
print(f"HTTP {r.status_code}")
items = r.json().get("items", [])
items.sort(key=lambda x: x.get("startTime") or "9999")
print(f"\n{len(items)} non-ended reservations for Alex:")
for it in items[:8]:
    pilots = it.get("pilots") or []
    pilot_names = [(p.get("firstName", "") + " " + p.get("lastName", "")).strip() for p in pilots]
    print(f"  #{it.get('reservationNumber')}")
    print(f"    startLocal={it.get('startTime')}  endLocal={it.get('endTime')}")
    print(f"    startUtc  ={it.get('startTimeUtc')}  endUtc  ={it.get('endTimeUtc')}")
    print(f"    pilots={pilot_names}")
    print()
