# Elevation Aviation Dispatch — Setup & Deployment Guide

This is the **operator's runbook** for getting the dispatch app online and
handed off to the flight school. Follow the sections in order. Time: ~60–90 min
the first time.

What the school gets at the end:
- A stable URL (e.g. `https://elevation-dispatch.streamlit.app`)
- Students sign in with Google → form auto-fills their name + reservation
- Each submission appears as a new row in a Google Sheet in the school's Drive
- New students are added the same way they already are: in Flight Schedule Pro

What stays free: hosting, auth, the Sheet, the Postgres backup.
What costs: just your existing FSP API subscription.

---

## 1. Pre-flight checklist (you already have these)

- [x] Flight Schedule Pro **API Primary Key** (Settings → API Access)
- [x] FSP **Operator ID** (e.g. `193717`)
- [ ] A Google account you can use to create the GitHub repo, GCP project, and Sheet
- [ ] [Git for Windows](https://git-scm.com/download/win) installed
- [ ] A GitHub account ([github.com](https://github.com) — free)

---

## 2. Push the project to GitHub

The dispatch project is currently in `C:\Users\Ben\Desktop\dispatch`. Get it onto GitHub
so Streamlit Cloud can deploy from it.

1. On [github.com](https://github.com), click the **+** in the top right → **New repository**.
2. Owner: your account. Name: `elevation-dispatch`. **Private**. Don't initialize with anything.
3. Click **Create repository**. Leave the next page open — you'll need the URL.

4. Open PowerShell and run:

   ```powershell
   cd C:\Users\Ben\Desktop\dispatch
   git init
   git add .
   git status
   ```

5. **Look at the `git status` output very carefully.** The files listed under
   "Changes to be committed" should NOT include any of these:
   - `.streamlit/secrets.toml`
   - `dispatch.db`
   - `uploads/`
   - `__pycache__/`
   - `.venv/`

   They're in `.gitignore`, so they shouldn't be there. If any of them ARE, stop
   and tell me — we have a leak to fix before committing.

6. Commit and push:

   ```powershell
   git commit -m "Initial dispatch app"
   git branch -M main
   git remote add origin https://github.com/<YOUR-USERNAME>/elevation-dispatch.git
   git push -u origin main
   ```

   GitHub will prompt for credentials (use a [personal access token](https://github.com/settings/tokens)
   as the password — generate one with `repo` scope).

7. Refresh the GitHub repo page — you should see all the files (without secrets).

---

## 3. Google Cloud project (one project hosts both OAuth and the Sheets service account)

1. Go to [console.cloud.google.com](https://console.cloud.google.com).
2. Top bar → project dropdown → **New Project**.
   - Name: `Elevation Dispatch`
   - Organization: skip if none
   - Click **Create**, then make sure it's selected in the project dropdown.

### 3a. Enable APIs

3. Left menu → **APIs & Services** → **Library**.
4. Search and **Enable** each of these:
   - Google Sheets API
   - Google Drive API
   - Google People API (Streamlit's OAuth uses this for the user's name/email)

### 3b. OAuth consent screen (one-time)

5. Left menu → **APIs & Services** → **OAuth consent screen**.
6. User type: **External**. Click **Create**.
7. Fill in:
   - App name: `Elevation Aviation Dispatch`
   - User support email: your email
   - Developer contact email: your email
8. **Save and continue** through Scopes (skip — Streamlit handles it), Test users.
9. **Test users**: add the Google emails of anyone who needs to try it during
   testing (you, the school admin, a couple of students). Up to 100.
10. Save. The app stays in "Testing" mode — only added emails can sign in until
    you publish it (Section 6).

### 3c. OAuth credentials

11. Left menu → **APIs & Services** → **Credentials** → **+ Create credentials** → **OAuth client ID**.
12. Application type: **Web application**. Name: `Streamlit Dispatch`.
13. Authorized redirect URIs — **add both**:
    - `http://localhost:8502/oauth2callback` (local dev)
    - `https://elevation-dispatch.streamlit.app/oauth2callback` (will adjust later if your Streamlit URL is different)
14. Click **Create**. A dialog shows:
    - **Client ID** (`....apps.googleusercontent.com`)
    - **Client secret** (`GOCSPX-...`)

    Copy both — you'll paste them into Streamlit Cloud secrets later. Keep them
    safe; treat them like passwords.

### 3d. Service account for Google Sheets

15. Left menu → **IAM & Admin** → **Service Accounts** → **+ Create service account**.
16. Name: `dispatch-sheet-writer`. Click **Create and continue**.
17. Grant role: **Editor** is fine for simplicity. Click **Continue**, then **Done**.
18. Click the service account row → **Keys** tab → **Add key** → **Create new key** → **JSON**.
19. A `.json` file downloads. **Keep this file safe** — you'll paste its contents into Streamlit Cloud secrets.

---

## 4. The Google Sheet

1. In your browser, go to [sheets.google.com](https://sheets.google.com) → **Blank**.
2. Rename it to `Elevation Dispatch Submissions`.
3. Rename the default tab (bottom left) to `Dispatches`.
4. From the URL, copy the long ID between `/d/` and `/edit`:

   `https://docs.google.com/spreadsheets/d/`**`1aBc...xYz`**`/edit#gid=0`

   That's your **Sheet ID**.

5. **Share the Sheet with the service account.** Click **Share** (top right).
   - Paste the service account email (from the JSON file, the `client_email` field — it ends in `iam.gserviceaccount.com`).
   - Permission: **Editor**.
   - Uncheck "Notify people".
   - Click **Share**.

   Without this step, the app will get a 403 when writing.

---

## 5. Deploy to Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io). Sign in with the
   GitHub account that owns the repo.

2. Click **New app** → **Deploy a public app from GitHub**.
   - Repository: `<your-username>/elevation-dispatch`
   - Branch: `main`
   - Main file path: `app.py`
   - App URL: pick a name (e.g. `elevation-dispatch`) — this becomes
     `https://elevation-dispatch.streamlit.app`

3. Click **Advanced settings**.
   - Python version: 3.11 (or 3.12)
   - **Secrets**: paste the following, filling in the placeholders. Note the
     formatting carefully — TOML is whitespace-sensitive.

   ```toml
   FSP_API_KEY = "<your FSP primary key>"
   FSP_OPERATOR_ID = "193717"

   GOOGLE_SHEET_ID = "<the Sheet ID from step 4>"
   GOOGLE_SHEET_WORKSHEET = "Dispatches"

   [auth]
   redirect_uri = "https://elevation-dispatch.streamlit.app/oauth2callback"
   cookie_secret = "<paste a long random string here>"
   client_id = "<OAuth client ID from step 3c>"
   client_secret = "<OAuth client secret from step 3c>"
   server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

   [gcp_service_account]
   # paste each field from your downloaded service-account JSON here, e.g.:
   type = "service_account"
   project_id = "<...>"
   private_key_id = "<...>"
   private_key = "-----BEGIN PRIVATE KEY-----\n<...>\n-----END PRIVATE KEY-----\n"
   client_email = "<...>@<...>.iam.gserviceaccount.com"
   client_id = "<...>"
   auth_uri = "https://accounts.google.com/o/oauth2/auth"
   token_uri = "https://oauth2.googleapis.com/token"
   auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
   client_x509_cert_url = "<...>"
   ```

   Tips:
   - For `cookie_secret`, paste any long random string. In PowerShell, generate one with:
     ```powershell
     [Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Maximum 256 }))
     ```
   - The `private_key` value spans multiple lines in the JSON. Keep the `\n`
     escapes literal in TOML — Streamlit will read them correctly.

4. Click **Deploy**. First boot takes 2–3 minutes (pip install).

5. When the app shows the "Sign in with Google" screen, **the URL is now live**.
   Note it down — that's what you give to the school.

---

## 6. Test before handing off

Run through this checklist as a test user (one of the emails you added in step 3b step 9):

- [ ] App URL loads → "Sign in with Google" screen
- [ ] Sign in → no "not authorized" if your email is in FSP students
- [ ] If not in FSP, see the "not registered as a student" message
- [ ] Sidebar shows "Signed in as <your name>"
- [ ] Name auto-populates as your FSP student record
- [ ] Pick today's date → reservation auto-fills time/instructor/aircraft (if you have one)
- [ ] Aircraft selection shows Hobbs + Tach + maintenance + squawks
- [ ] Solo flight → instructor dropdown lets you pick "N/A-Solo"
- [ ] Submit a test dispatch → green "submitted · logged to Google Sheet"
- [ ] Open the Sheet → see a new row with all the data
- [ ] Sign out → returns to login screen

---

## 7. Publish (remove the "test user" limit)

While the OAuth consent screen is in **Testing** mode, only the test users you
added can sign in. To allow all school students:

1. GCP Console → **APIs & Services** → **OAuth consent screen**.
2. Click **PUBLISH APP** → confirm.
3. Status changes to "In production". Anyone with a Google account can now
   sign in. (Only students registered in FSP can actually submit, because of the
   FSP email match.)

   Note: Google may show a "this app isn't verified" warning until you go
   through their verification flow. For an internal-style app with < 100 users,
   it's harmless — users click **Advanced** → **Continue**. You can submit
   for verification later if needed.

---

## 8. Hand the app to the school

Send the school admin a short email like:

> Hi <admin>, the new dispatch form is live at `https://elevation-dispatch.streamlit.app`.
>
> Students sign in with their own Google account. The app auto-populates their
> name and today's reservation from Flight Schedule Pro. Each submission appears
> as a new row in this Google Sheet: <link>
>
> Adding a new student: register them in FSP under the **Students** role with
> their Google email. They can immediately sign in to the dispatch app.
>
> If anything stops working, contact <you>.

Optional: bookmark the Sheet for them in their Drive, or move the Sheet into
a shared "Elevation Aviation" Drive folder.

---

## 9. Ongoing maintenance (low burden)

| Task | Frequency | Who |
|---|---|---|
| Rotate FSP API keys | Every 6–12 months, or after any suspected leak | You or school admin (FSP UI) |
| Add new student | When enrolled | School admin (FSP UI) |
| Remove a student | When they leave | School admin (FSP UI) |
| Check Streamlit Cloud limits | Monthly | You — Streamlit Cloud dashboard shows usage |
| Bump dependencies | Annually | You — `pip-compile requirements.txt`, push to GitHub, Streamlit redeploys |

### Key rotation procedure

FSP gives you Primary + Secondary keys for zero-downtime rotation:
1. In Streamlit Cloud → **Settings** → **Secrets**, change `FSP_API_KEY` to the **Secondary** key.
2. Save (the app reloads automatically).
3. In FSP, regenerate the **Primary** key.
4. Update `FSP_API_KEY` in Streamlit Cloud back to the new Primary.

---

## 10. Eventual handoff to the school (when ready)

Right now everything is under your accounts. To transfer:

1. **GitHub**: Settings → Transfer ownership → enter the school's GitHub org.
2. **Streamlit Cloud**: have the school sign up with their GitHub account, fork
   or move the repo, redeploy. They'll need to re-enter all the secrets.
3. **Google Cloud project**: IAM → grant their admin Owner role, then they can
   demote you. Or rebuild from scratch under their Google Workspace.
4. **Google Sheet**: Share → transfer ownership to school admin's email.

Until handoff, you remain the maintainer. After handoff, deploys/secrets are
the school's responsibility.

---

## Troubleshooting

**"Your Google account email is not registered as a student"**
- The signed-in email doesn't match any FSP `/people` record with the **Students** role.
- Fix: in FSP, find the student → set their email to the one they sign in with → set role to Students.

**"FSP rejected the API key (401)"**
- Key was deleted or rotated in FSP without updating Streamlit Cloud secrets.
- Fix: regenerate key in FSP, paste into Streamlit Cloud secrets.

**"FSP says your key is not granted for this operator ID"**
- `FSP_OPERATOR_ID` doesn't match the operator the key was issued for.
- Fix: confirm operator ID with FSP support; update in secrets.

**Google Sheet writes fail with 403 Forbidden**
- The service account isn't shared on the Sheet, or shared with viewer-only access.
- Fix: Sheet → Share → add the service account `client_email` with **Editor** permission.

**Logo doesn't show**
- `elevation_logo.png` is gitignored (we don't commit your specific logo to a public-ish repo by default).
- Fix: either commit it (remove from `.gitignore`), or upload it manually after deploy by
  adding it to the repo intentionally. Or set `LOGO_PATH` to a URL in secrets.

**"redirect_uri_mismatch" on sign-in**
- The Streamlit Cloud URL doesn't match what you registered in Google Cloud Console.
- Fix: GCP Console → Credentials → your OAuth client → Authorized redirect URIs →
  add `https://<your-actual-streamlit-url>/oauth2callback`.

---

## File-by-file summary

| File | Purpose |
|---|---|
| `app.py` | Streamlit form (entry point) |
| `fsp_client.py` | Flight Schedule Pro API client (aircraft, students, reservations, etc.) |
| `storage.py` | Local SQLite save + PDF generation |
| `sheets_storage.py` | Google Sheets append for school visibility |
| `config.py` | Config resolved from secrets / env / defaults |
| `requirements.txt` | Python dependencies |
| `.streamlit/secrets.toml.example` | Template for the secrets file |
| `.streamlit/config.toml` | Streamlit theme + server settings |
| `.gitignore` | Keeps secrets, DB, uploads out of git |
| `SETUP.md` | This file |
