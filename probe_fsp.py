"""Get Hobbs + Tach for ACTIVE aircraft from Reporting API."""
from pathlib import Path
import requests


def load_key():
    for line in (Path(__file__).parent / ".streamlit" / "secrets.toml").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("FSP_API_KEY"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")


KEY = load_key()
OP_ID = "193717"
REPORTS = "https://usc-api.flightschedulepro.com/reports/v1.0"
HEADERS = {"x-subscription-key": KEY, "Accept": "application/json"}

r = requests.get(f"{REPORTS}/operators/{OP_ID}/aircraft", headers=HEADERS, params={"limit": 50}, timeout=15)
data = r.json()
items = data.get("items", []) if isinstance(data, dict) else data
print(f"Total: {data.get('totalItems') if isinstance(data, dict) else len(items)}")

for ac in items:
    if ac.get("status") == "Deleted":
        continue
    tail = ac.get("registrationTail")
    print(f"\n--- {tail} (status={ac.get('status')}) ---")
    print(f"  billingMeter: {ac.get('billingMeter')}")
    print(f"  airframeTtisBasedOn: {ac.get('airframeTtisBasedOn')}")
    print(f"  airframeTtis: {ac.get('airframeTtis')}")
    print(f"  airframeHasHobbs: {ac.get('airframeHasHobbs')}  airframeHobbs: {ac.get('airframeHobbs')}")
    print(f"  engine1HasTach: {ac.get('engine1HasTach')}  engine1Tach: {ac.get('engine1Tach')}")
    print(f"  airframeAirTime: {ac.get('airframeAirTime')}  airframeFlightTime: {ac.get('airframeFlightTime')}")
    print(f"  lastUpdated: {ac.get('lastUpdated')}")
