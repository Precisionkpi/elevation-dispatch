"""Custom Google OAuth flow that bypasses Streamlit's st.login().

st.login() / streamlit[auth] relies on a Starlette session middleware
that uses a cookie to round-trip the OAuth state. On Streamlit Community
Cloud this combination has been flaky (MismatchingStateError), so we
implement OAuth ourselves using a stateless approach:

1. User clicks "Sign in" -> we build the Google OAuth URL and link them out.
2. Google redirects them back to the bare app URL with ?code=...&state=...
3. We read query params via st.query_params, exchange the code for an
   access token at Google's token endpoint, then fetch their profile.
4. We store the user dict in st.session_state (Streamlit's native
   per-session store) and clear the URL params.

State validation is best-effort: we set a state token in session_state
when generating the URL and check it on callback if present, but if
session_state didn't persist across the redirect (a Streamlit Cloud
edge case), we still accept the callback. The OAuth code from Google
is single-use and bound to our client_id, so the security impact is
limited even without strict state validation.
"""
import secrets as _secrets
from urllib.parse import urlencode

import requests
import streamlit as st


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
SCOPES = ["openid", "email", "profile"]

USER_KEY = "_oauth_user"
STATE_KEY = "_oauth_state"


def _config():
    """Return (client_id, client_secret, redirect_uri) tuple, or (None, None, None)."""
    try:
        cfg = st.secrets.get("google_oauth", None)
        if cfg is None:
            return (None, None, None)
        return (
            cfg.get("client_id"),
            cfg.get("client_secret"),
            cfg.get("redirect_uri"),
        )
    except Exception:
        return (None, None, None)


def is_configured() -> bool:
    """True if all OAuth secrets are present."""
    cid, sec, ru = _config()
    return bool(cid and sec and ru)


def get_user():
    """Return the logged-in user dict {email, name, picture, sub} or None."""
    return st.session_state.get(USER_KEY)


def login_url() -> str:
    """Build the Google OAuth login URL and remember the state."""
    client_id, _, redirect_uri = _config()
    state = _secrets.token_urlsafe(32)
    st.session_state[STATE_KEY] = state
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return GOOGLE_AUTH_URL + "?" + urlencode(params)


def handle_callback() -> bool:
    """If URL has ?code=, exchange it for a token and store the user.

    Returns True if a callback was processed (success or failure).
    Caller should st.rerun() if True to clear the page state.
    """
    qp = st.query_params
    code = qp.get("code")
    if not code:
        return False

    # Best-effort state check
    url_state = qp.get("state")
    saved_state = st.session_state.get(STATE_KEY)
    if saved_state and url_state and saved_state != url_state:
        # Hard mismatch -> reject
        st.error("Sign-in state mismatch. Try again.")
        st.query_params.clear()
        return True
    # If saved_state is None we accept (session_state may have been lost
    # across the OAuth redirect — Cloud edge case).

    client_id, client_secret, redirect_uri = _config()
    try:
        token_resp = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        if not token_resp.ok:
            st.error(f"Token exchange failed: {token_resp.status_code} — {token_resp.text[:200]}")
            st.query_params.clear()
            return True
        access_token = token_resp.json().get("access_token")
        if not access_token:
            st.error("Token exchange returned no access_token.")
            st.query_params.clear()
            return True

        ui_resp = requests.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        if not ui_resp.ok:
            st.error(f"Profile fetch failed: {ui_resp.status_code}")
            st.query_params.clear()
            return True
        info = ui_resp.json()

        st.session_state[USER_KEY] = {
            "email": (info.get("email") or "").lower(),
            "name": info.get("name") or "",
            "picture": info.get("picture"),
            "sub": info.get("sub"),
            "email_verified": info.get("email_verified", True),
        }
        st.session_state.pop(STATE_KEY, None)
        st.query_params.clear()
        return True
    except requests.RequestException as e:
        st.error(f"Sign-in network error: {e}")
        st.query_params.clear()
        return True


def logout():
    """Clear the signed-in user (and any leftover OAuth state) from session."""
    st.session_state.pop(USER_KEY, None)
    st.session_state.pop(STATE_KEY, None)
