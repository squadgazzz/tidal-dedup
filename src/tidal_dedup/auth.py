# src/tidal_dedup/auth.py
import sys
import webbrowser

import requests.exceptions
import tidalapi
import yaml


def open_tidal_session() -> tidalapi.Session:
    """Open a Tidal session, reusing a saved token if available."""
    try:
        with open(".session.yml", "r") as f:
            previous_session = yaml.safe_load(f)
    except OSError:
        previous_session = None

    session = tidalapi.Session()

    if previous_session:
        try:
            if session.load_oauth_session(
                token_type=previous_session["token_type"],
                access_token=previous_session["access_token"],
                refresh_token=previous_session["refresh_token"],
            ):
                return session
        except requests.exceptions.ConnectionError as e:
            sys.exit(f"Network error connecting to Tidal: {e}")
        except Exception as e:
            print(f"Error loading previous Tidal session: {e}")

    login, future = session.login_oauth()
    print("Login with the web browser: " + login.verification_uri_complete)
    url = login.verification_uri_complete
    if not url.startswith("https://"):
        url = "https://" + url
    webbrowser.open(url)
    future.result()

    with open(".session.yml", "w") as f:
        yaml.dump(
            {
                "session_id": session.session_id,
                "token_type": session.token_type,
                "access_token": session.access_token,
                "refresh_token": session.refresh_token,
            },
            f,
        )
    return session
