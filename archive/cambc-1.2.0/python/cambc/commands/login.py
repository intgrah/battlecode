"""cambc login — authenticate via browser-based flow."""

import json
import secrets
import urllib.request
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import click
from rich.console import Console

from cambc.auth import get_api_url, save_credentials, load_credentials

console = Console()


class _CallbackHandler(BaseHTTPRequestHandler):
    """Handles the localhost callback from the browser."""

    code: str | None = None
    state: str | None = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        self.server._code = params.get("code", [None])[0]
        self.server._state = params.get("state", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<html><body style='font-family:system-ui;display:flex;justify-content:center;"
            b"align-items:center;height:100vh;margin:0;background:#0a0a0a;color:#fafafa'>"
            b"<div style='text-align:center'>"
            b"<h2>Authorized</h2>"
            b"<p>You can close this tab and return to your terminal.</p>"
            b"</div></body></html>"
        )

    def log_message(self, format, *args):
        pass  # Suppress request logging


@click.command()
def login():
    """Authenticate with the Cambridge Battlecode platform."""
    existing = load_credentials()
    if existing:
        user = existing.get("user", {})
        console.print(
            f"Already logged in as [bold]{user.get('name', '?')}[/bold] ({user.get('email', '?')})"
        )
        if not click.confirm("Log in again?", default=False):
            return

    api_url = get_api_url()
    state = secrets.token_urlsafe(32)

    # Start a local server to receive the callback
    server = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    port = server.server_address[1]

    auth_url = f"{api_url}/cli/auth?port={port}&state={state}"

    console.print(f"Opening browser to authenticate...")
    console.print(f"If the browser doesn't open, visit: [link={auth_url}]{auth_url}[/link]")

    webbrowser.open(auth_url)

    # Wait for the callback (with timeout)
    server.timeout = 120
    server._code = None
    server._state = None

    console.print("Waiting for authorization...", style="dim")
    while server._code is None:
        server.handle_request()
        if server._code is None and server._state is None:
            # Timeout or unexpected request
            break

    server.server_close()

    if not server._code:
        console.print("[red]Authorization timed out or was cancelled.[/red]")
        raise SystemExit(1)

    if server._state != state:
        console.print("[red]State mismatch — possible CSRF attack. Aborting.[/red]")
        raise SystemExit(1)

    # Exchange the code for a session token
    console.print("Exchanging authorization code...", style="dim")
    try:
        payload = json.dumps({"code": server._code}).encode()
        req = urllib.request.Request(
            f"{api_url}/api/cli/exchange",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
            msg = body.get("error", str(e))
        except Exception:
            msg = str(e)
        console.print(f"[red]Authentication failed: {msg}[/red]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]Authentication failed: {e}[/red]")
        raise SystemExit(1)

    token = data.get("token")
    if not token:
        console.print("[red]Invalid response from server.[/red]")
        raise SystemExit(1)

    save_credentials(
        token=token,
        expires_at=data.get("expires_at", ""),
        user=data.get("user", {}),
        team=data.get("team"),
    )

    user = data.get("user", {})
    team = data.get("team")
    console.print(f"\n[green]Logged in as [bold]{user.get('name', '?')}[/bold][/green] ({user.get('email', '?')})")
    if team:
        console.print(f"  Team: [bold]{team.get('name', '?')}[/bold]")
