"""One-shot Google OAuth flow. Writes token.pickle in the repo root."""

from __future__ import annotations

import pickle
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

ROOT = Path(__file__).parent
CLIENT_SECRET = ROOT / "client_secret.json"
TOKEN_PATH = ROOT / "token.pickle"
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def get_credentials():
    creds = load_cached_credentials()
    if creds is not None:
        return creds
    if not CLIENT_SECRET.exists():
        raise RuntimeError(
            f"{CLIENT_SECRET.name} not found — cannot start the OAuth flow"
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0)
    with TOKEN_PATH.open("wb") as fh:
        pickle.dump(creds, fh)
    return creds


def load_cached_credentials():
    """Return usable credentials from the cached token, or None.

    Never prompts and never opens a browser — safe to call from the watcher,
    where a missing token must degrade to the credential-free RSS path rather
    than blocking on an interactive sign-in.
    """
    if not TOKEN_PATH.exists():
        return None
    try:
        with TOKEN_PATH.open("rb") as fh:
            creds = pickle.load(fh)
    except Exception:
        return None
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            return None
        with TOKEN_PATH.open("wb") as fh:
            pickle.dump(creds, fh)
        return creds
    return None


if __name__ == "__main__":
    creds = get_credentials()
    print(f"Signed in. Token saved to {TOKEN_PATH}")
