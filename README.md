# Elevation Aviation Dispatch

Streamlit-based dispatch form that replaces the existing Google Form with
data auto-populated from Flight Schedule Pro:

- Aircraft and instructor dropdowns from FSP
- Tach hours until next maintenance, days until next inspection
- Open squawks for the selected aircraft, with a pilot acknowledgement checkbox

## Setup

1. Install Python 3.10+.
2. Create a virtual environment and install dependencies:

   ```powershell
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Copy the secrets template and fill in your FSP API key:

   ```powershell
   copy .streamlit\secrets.toml.example .streamlit\secrets.toml
   notepad .streamlit\secrets.toml
   ```

4. Run the app:

   ```powershell
   streamlit run app.py
   ```

## Flight Schedule Pro API keys

FSP issues a Primary and Secondary key. Put the Primary in `secrets.toml` and
keep the Secondary in a password manager — it lets you rotate without
downtime:

1. Swap Secondary into `secrets.toml`.
2. In FSP, regenerate the Primary key.
3. Swap the new Primary back into `secrets.toml`.

If a key is ever leaked (logs, chat, screenshots), delete both keys in FSP
and regenerate.

## FSP endpoint shapes are best-effort

The endpoint paths in `fsp_client.py` are based on the FSP developer portal
docs but have not been verified against a live response yet. If a request
returns 404 or the auto-fill numbers look wrong:

1. In the sidebar, toggle **Debug FSP responses**.
2. Pick an aircraft. The raw maintenance + squawks JSON will appear in an
   expander on the page.
3. Adjust the field names inside `FSPClient._summarize_maintenance` /
   `_normalize_squawk` / `_normalize_instructor` to match what FSP returns.

The fallback chains (multiple candidate URLs per resource) already try the
most likely shapes before giving up.

## Storage

- Each submission is saved to `dispatch.db` (SQLite, gitignored).
- Uploaded W&B / weather images land in `uploads/<dispatch_id>/`.
- A PDF summary is offered as a download immediately after submission.

## Files

| File | Purpose |
|------|---------|
| `app.py` | Streamlit form (entry point) |
| `fsp_client.py` | Flight Schedule Pro API client |
| `storage.py` | SQLite + PDF generation |
| `config.py` | Secrets / env / default resolution |
| `requirements.txt` | Python dependencies |
| `.streamlit/secrets.toml.example` | Template for secrets file |
