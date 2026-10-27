"""Reauthorize the local Google Drive connection without printing credentials."""

import json
import secrets
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from dotenv import dotenv_values, set_key
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from config import SCOPES


ENV_FILE = Path(__file__).with_name(".env")


class SetupError(Exception):
    pass


def load_oauth_settings():
    values = dotenv_values(ENV_FILE)
    client_json = values.get("GOOGLE_CLIENT_SECRET_JSON")
    redirect_uri = values.get("REDIRECT_URI")
    if not client_json or not redirect_uri:
        raise SetupError("Lipsesc GOOGLE_CLIENT_SECRET_JSON sau REDIRECT_URI din .env.")

    client_config = json.loads(client_json)
    if "web" not in client_config:
        raise SetupError("GOOGLE_CLIENT_SECRET_JSON trebuie să fie un client OAuth web.")

    if redirect_uri not in client_config["web"].get("redirect_uris", []):
        raise SetupError(
            "REDIRECT_URI din .env nu apare în adresele autorizate ale clientului Google."
        )

    redirect = urlsplit(redirect_uri)
    if (
        redirect.scheme != "http"
        or redirect.hostname not in ("localhost", "127.0.0.1")
        or redirect.path != "/auth/callback"
        or redirect.port is None
        or redirect.query
        or redirect.fragment
    ):
        raise SetupError("REDIRECT_URI trebuie să fie un URL local /auth/callback cu port.")

    return client_config, redirect_uri, redirect


def wait_for_google_callback(
    redirect, expected_state: str, authorization_url: str, timeout_seconds=600
):
    result = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path != redirect.path:
                self.send_error(404)
                return

            params = parse_qs(parsed.query)
            state = params.get("state", [""])[0]
            if not secrets.compare_digest(state, expected_state):
                self.send_error(400, "Invalid authorization state")
                return

            if params.get("error"):
                result["error"] = "Autorizarea a fost refuzată în browser."
            elif params.get("code"):
                result["code"] = params["code"][0]
            else:
                result["error"] = "Google nu a trimis un cod de autorizare."

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(
                b"<p>Raspunsul Google a fost primit. Verifica rezultatul in PowerShell.</p>"
            )

        def log_message(self, format, *args):
            # The callback URL contains a one-time authorization code.
            pass

    try:
        server = HTTPServer((redirect.hostname, redirect.port), CallbackHandler)
    except OSError as exc:
        raise SetupError(
            f"Portul {redirect.port} este ocupat. Oprește Uvicorn cu Ctrl+C și reîncearcă."
        ) from exc

    with server:
        server.timeout = 1
        if not webbrowser.open(authorization_url):
            print("Browserul nu s-a deschis. Deschide acest link în browser:")
            print(authorization_url)
        deadline = time.monotonic() + timeout_seconds
        while not result and time.monotonic() < deadline:
            server.handle_request()

    if not result:
        raise SetupError("Autorizarea nu a fost finalizată în 10 minute.")
    if "error" in result:
        raise SetupError(result["error"])
    return result["code"]


def main():
    client_config, redirect_uri, redirect = load_oauth_settings()
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )

    print("Se deschide autentificarea Google. Alege contul care deține fotografiile.")
    authorization_code = wait_for_google_callback(
        redirect, state, authorization_url
    )

    # The callback state was checked above. Exchanging the code directly keeps
    # OAuthLib's HTTPS enforcement for its request to Google's token endpoint.
    flow.fetch_token(code=authorization_code)
    credentials = flow.credentials
    if not credentials.refresh_token:
        raise SetupError("Google nu a furnizat un token de reînnoire. Reîncearcă autorizarea.")

    # Verify the selected account can access Drive before replacing the old token.
    drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
    drive.files().list(pageSize=1, fields="files(id)").execute()

    set_key(str(ENV_FILE), "GOOGLE_DRIVE_TOKEN_JSON", credentials.to_json(), quote_mode="always")
    print("Google Drive a fost reautorizat. Repornește Uvicorn.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        if isinstance(exc, SetupError):
            print(str(exc))
        else:
            print(f"Autorizarea nu s-a finalizat ({type(exc).__name__}).")
        sys.exit(1)
