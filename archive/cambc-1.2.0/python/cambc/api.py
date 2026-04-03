"""HTTP client helpers for cambc CLI — handles auth, errors, multipart."""

import json
import urllib.request
import urllib.error
from pathlib import Path

from rich.console import Console

from cambc.auth import get_api_url, get_token

console = Console()


class ApiError(Exception):
    def __init__(self, message: str, status: int = 0):
        self.message = message
        self.status = status
        super().__init__(message)


def _require_token() -> str:
    token = get_token()
    if not token:
        console.print("[red]Not logged in. Run: cambc login[/red]")
        raise SystemExit(1)
    return token


def _handle_error(e: urllib.error.HTTPError) -> None:
    try:
        body = json.loads(e.read())
        msg = body.get("error", str(e))
    except Exception:
        msg = str(e)

    if e.code == 401:
        console.print("[red]Session expired. Run: cambc login[/red]")
    elif e.code == 429:
        console.print(f"[yellow]Rate limited: {msg}[/yellow]")
    elif e.code == 404:
        console.print(f"[red]Not found: {msg}[/red]")
    else:
        console.print(f"[red]Error: {msg}[/red]")
    raise SystemExit(1)


def api_get(path: str, params: dict[str, str] | None = None) -> dict:
    """Authenticated GET request. Returns parsed JSON."""
    from urllib.parse import urlencode

    token = _require_token()
    api_url = get_api_url()
    url = f"{api_url}{path}"
    if params:
        url += f"?{urlencode(params)}"

    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        _handle_error(e)
        raise  # unreachable but satisfies type checker
    except Exception as e:
        console.print(f"[red]Request failed: {e}[/red]")
        raise SystemExit(1)


def api_post(path: str, body: dict) -> dict:
    """Authenticated POST request with JSON body. Returns parsed JSON."""
    token = _require_token()
    api_url = get_api_url()

    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{api_url}{path}",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        _handle_error(e)
        raise
    except Exception as e:
        console.print(f"[red]Request failed: {e}[/red]")
        raise SystemExit(1)


def api_post_multipart(
    path: str,
    files: dict[str, tuple[str, bytes, str]],
    text_fields: dict[str, str] | None = None,
    timeout: int = 60,
) -> dict:
    """Authenticated POST with multipart/form-data. Returns parsed JSON."""
    token = _require_token()
    api_url = get_api_url()

    boundary = "----CambcBoundary"
    parts: list[bytes] = []
    if text_fields:
        for name, value in text_fields.items():
            parts.append(f"--{boundary}\r\n".encode())
            parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
            parts.append(value.encode())
            parts.append(b"\r\n")
    for name, (filename, data, content_type) in files.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        )
        parts.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        parts.append(data)
        parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)

    req = urllib.request.Request(
        f"{api_url}{path}",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        _handle_error(e)
        raise
    except Exception as e:
        console.print(f"[red]Upload failed: {e}[/red]")
        raise SystemExit(1)
