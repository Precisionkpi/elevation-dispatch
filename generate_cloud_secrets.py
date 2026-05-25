"""Generate the secrets.toml content to paste into Streamlit Community Cloud.

Reads from:
  - .streamlit/secrets.toml  (for FSP_API_KEY, FSP_OPERATOR_ID)
  - oauth-client.json        (for OAuth client_id + client_secret)
  - service-account.json     (for the service account JSON)

Writes to:
  - cloud-secrets.toml       (gitignored; paste into Streamlit Cloud Settings -> Secrets)

The output cookie_secret is freshly generated each run; that's fine — only
needs to be stable per deployment.
"""
import json
import os
import secrets as _secrets
import sys
from pathlib import Path

# Backwards-compat alias for places below that still say `secrets.`
secrets = _secrets

HERE = Path(__file__).parent

def fail(msg):
    print(f"ERROR: {msg}")
    sys.exit(1)


# 1. Read FSP credentials from local secrets.toml
LOCAL_SECRETS = HERE / ".streamlit" / "secrets.toml"
if not LOCAL_SECRETS.exists():
    fail(f"{LOCAL_SECRETS} doesn't exist. Set it up locally first.")

fsp_key = ""
fsp_operator = ""
sheet_id = ""
for line in LOCAL_SECRETS.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line.startswith("FSP_API_KEY"):
        fsp_key = line.split("=", 1)[1].strip().strip('"').strip("'")
    elif line.startswith("FSP_OPERATOR_ID"):
        fsp_operator = line.split("=", 1)[1].strip().strip('"').strip("'")
    elif line.startswith("GOOGLE_SHEET_ID"):
        sheet_id = line.split("=", 1)[1].strip().strip('"').strip("'")

if not fsp_key:
    fail("FSP_API_KEY not found in .streamlit/secrets.toml")
if not fsp_operator:
    fail("FSP_OPERATOR_ID not found in .streamlit/secrets.toml")
if not sheet_id:
    sheet_id = "1f_0gTC1a2ap5uh8H8_1y-Bluq0FYoHFhj_05g5OmS4g"
    print(f"GOOGLE_SHEET_ID not in local secrets.toml; using known value: {sheet_id}")


# 2. Read OAuth client JSON
oauth_path = HERE / "oauth-client.json"
if not oauth_path.exists():
    # Try common alternate names
    for alt in HERE.glob("client_secret*.json"):
        oauth_path = alt
        break
if not oauth_path.exists():
    fail(f"OAuth client JSON not found. Save it to {HERE}/oauth-client.json")

oauth = json.loads(oauth_path.read_text(encoding="utf-8"))
# Google's OAuth client JSON has nesting under "web" or "installed"
oauth_inner = oauth.get("web") or oauth.get("installed") or oauth
client_id = oauth_inner.get("client_id")
client_secret = oauth_inner.get("client_secret")
if not client_id or not client_secret:
    fail(f"OAuth JSON missing client_id/client_secret. Read: {list(oauth_inner.keys())}")


# 3. Read service account JSON
sa_path = HERE / "service-account.json"
if not sa_path.exists():
    for alt in HERE.glob("*service-account*.json"):
        sa_path = alt
        break
    for alt in HERE.glob("*.iam.gserviceaccount.com*.json"):
        sa_path = alt
        break
if not sa_path.exists():
    fail(f"Service-account JSON not found. Save it to {HERE}/service-account.json")

sa = json.loads(sa_path.read_text(encoding="utf-8"))
required = ["type", "project_id", "private_key_id", "private_key", "client_email", "client_id"]
for k in required:
    if k not in sa:
        fail(f"Service-account JSON missing key: {k}")


# 4. Generate a cookie secret (hex, no special chars)
cookie_secret = secrets.token_hex(48)


# 5. Compose the TOML output
def toml_str(value):
    """Escape a Python string as a TOML basic string."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return f'"{escaped}"'


REDIRECT_URI = "https://elevation-dispatch.streamlit.app/oauth2callback"

out = []
out.append("# Streamlit Community Cloud secrets — paste this into Settings -> Secrets")
out.append("# (Do not commit this file. It is gitignored.)")
out.append("")
out.append(f"FSP_API_KEY = {toml_str(fsp_key)}")
out.append(f"FSP_OPERATOR_ID = {toml_str(fsp_operator)}")
out.append("")
out.append(f"GOOGLE_SHEET_ID = {toml_str(sheet_id)}")
out.append('GOOGLE_SHEET_WORKSHEET = "Dispatches"')
out.append("")
out.append("[auth]")
out.append(f"redirect_uri = {toml_str(REDIRECT_URI)}")
out.append(f"cookie_secret = {toml_str(cookie_secret)}")
out.append("")
out.append("[auth.google]")
out.append(f"client_id = {toml_str(client_id)}")
out.append(f"client_secret = {toml_str(client_secret)}")
out.append('server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"')
out.append("")
out.append("[gcp_service_account]")
for k in ["type", "project_id", "private_key_id", "private_key", "client_email",
          "client_id", "auth_uri", "token_uri",
          "auth_provider_x509_cert_url", "client_x509_cert_url",
          "universe_domain"]:
    if k in sa:
        out.append(f"{k} = {toml_str(sa[k])}")

result = "\n".join(out) + "\n"

# 6. Write to file
output_path = HERE / "cloud-secrets.toml"
output_path.write_text(result, encoding="utf-8")
os.chmod(output_path, 0o600) if hasattr(os, "chmod") else None

print()
print(f"Wrote {output_path}")
print(f"Size: {len(result)} bytes")
print(f"Redirect URI used: {REDIRECT_URI}")
print()
print("Next step: paste the contents of cloud-secrets.toml into")
print("Streamlit Cloud -> your app -> Settings -> Secrets")
print()
print("If the deployed app URL ends up different from")
print(f"  {REDIRECT_URI}")
print("update both:")
print(f"  - this file's redirect_uri line")
print(f"  - the OAuth client's Authorized redirect URIs in Google Cloud Console")
