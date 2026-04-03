"""cambc map-editor — open map editor locally or on platform."""

import click
from rich.console import Console

console = Console()


@click.command("map-editor")
@click.option("--platform", "use_platform", is_flag=True, help="Open map editor on platform instead of locally")
def map_editor(use_platform: bool):
    """Open the map editor.

    \b
    Examples:
      cambc map-editor              # Open map editor locally
      cambc map-editor --platform   # Open on platform
    """
    if use_platform:
        _open_platform()
    else:
        _serve_local()


def _open_platform() -> None:
    """Open the platform map editor page in the user's browser."""
    import webbrowser
    from cambc.auth import get_api_url

    base_url = get_api_url()
    url = f"{base_url}/map-editor"

    console.print(f"Opening map editor: [link={url}]{url}[/link]")
    webbrowser.open(url)


def _serve_local() -> None:
    """Serve the map editor locally."""
    import http.server
    import threading
    import webbrowser
    from pathlib import Path

    mono_dist = Path(__file__).parent.parent.parent.parent.parent / "visualiser" / "dist"
    bundled_dist = Path(__file__).parent.parent / "data" / "visualiser"

    if (mono_dist / "map-editor.html").is_file():
        dist_path = str(mono_dist.resolve())
    elif (bundled_dist / "map-editor.html").is_file():
        dist_path = str(bundled_dist.resolve())
    else:
        console.print(
            "[red]Map editor not found. "
            "Try reinstalling cambc or use --platform to open on the platform.[/red]"
        )
        raise SystemExit(1)

    class EditorHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=dist_path, **kwargs)

        def do_GET(self):
            if self.path == "/" or self.path.startswith("/?"):
                self.path = "/map-editor.html"
            super().do_GET()

        def log_message(self, format, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), EditorHandler)
    port = server.server_address[1]

    url = f"http://127.0.0.1:{port}/"
    console.print(f"Serving map editor at [link={url}]{url}[/link]")
    console.print("[dim]Press Ctrl+C to stop[/dim]")

    threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")
        server.shutdown()
