#!/usr/bin/env python3
"""Interactive helper to obtain Strava OAuth tokens.

This script starts a local HTTP server, opens the Strava authorization URL
in your browser, receives the redirect with the authorization code, exchanges
the code for access and refresh tokens, and saves them to
`~/.aitrainer/strava_tokens.json` along with your client id/secret.

Usage:
  python src/data/get_strava_tokens.py --client-id 12345 --client-secret abcd

Make sure the redirect URI you register in your Strava app matches the
`--redirect-uri` value (default: http://localhost:5000/callback).
"""
from __future__ import annotations

import argparse
import json
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional

import requests


class OAuthHandler(BaseHTTPRequestHandler):
    server_version = "StravaOAuth/1.0"

    def do_GET(self):
        # Parse code from query string
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
        error = qs.get("error", [None])[0]

        if error:
            body = f"Authorization failed: {error}. You may close this tab."
            self.send_response(400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body.encode())
            self.server.code = None
            return

        if code:
            body = "Authorization successful. You may close this tab.".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            # Store the code on the server object for retrieval
            self.server.code = code
            # Shutdown server in a separate thread to avoid deadlock
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return

        # No code present
        body = "No authorization code found. You may close this tab.".encode()
        self.send_response(400)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def find_free_port() -> int:
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def exchange_code_for_tokens(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    resp = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def save_tokens(tokens: dict, client_id: str, client_secret: str) -> Path:
    token_file = Path.home() / ".aitrainer" / "strava_tokens.json"
    token_file.parent.mkdir(parents=True, exist_ok=True)
    # include client id/secret for automatic refresh
    tokens_to_save = dict(tokens)
    tokens_to_save["strava_client_id"] = client_id
    tokens_to_save["strava_client_secret"] = client_secret
    with open(token_file, "w", encoding="utf-8") as f:
        json.dump(tokens_to_save, f, indent=2)
    return token_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Obtain Strava OAuth tokens interactively.")
    parser.add_argument("--client-id", required=True, help="Strava client id from developers.strava.com")
    parser.add_argument("--client-secret", required=True, help="Strava client secret from developers.strava.com")
    parser.add_argument("--port", type=int, default=5000, help="Local port to listen on (default: 5000)")
    parser.add_argument("--redirect-path", default="/callback", help="Redirect path (default: /callback)")
    args = parser.parse_args()

    redirect_uri = f"http://localhost:{args.port}{args.redirect_path}"

    # Construct authorization URL
    auth_url = (
        "https://www.strava.com/oauth/authorize"
        f"?client_id={args.client_id}"
        "&response_type=code"
        f"&redirect_uri={redirect_uri}"
        "&scope=activity:read_all"
        "&approval_prompt=auto"
    )

    print("Opening browser for Strava authorization...")
    print("If the browser does not open, visit this URL manually:\n", auth_url)
    webbrowser.open(auth_url)

    server_address = ("", args.port)
    httpd = HTTPServer(server_address, OAuthHandler)
    # Attach a place to store the code
    httpd.code = None

    try:
        print(f"Listening for redirect at {redirect_uri} ...")
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Interrupted by user, exiting.")
        return

    code: Optional[str] = getattr(httpd, "code", None)
    if not code:
        print("No code received. Exiting.")
        return

    print("Received authorization code, exchanging for tokens...")
    try:
        tokens = exchange_code_for_tokens(args.client_id, args.client_secret, code, redirect_uri)
    except Exception as e:
        print("Failed to exchange code for tokens:", e)
        return

    token_path = save_tokens(tokens, args.client_id, args.client_secret)
    print(f"Tokens saved to: {token_path}")
    print("Done.")


if __name__ == "__main__":
    main()
