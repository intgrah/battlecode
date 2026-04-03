"""cambc watch — open replay in local or platform visualizer."""

import click
from rich.console import Console

console = Console()


@click.command()
@click.argument("replay_file", required=False, type=click.Path(exists=True))
@click.option("--match", "match_id", type=str, help="Match ID to view on platform")
@click.option("--game", "game_number", type=int, help="Game number within match")
def watch(replay_file: str | None, match_id: str | None, game_number: int | None):
    """Open replay in visualizer.

    \b
    Examples:
      cambc watch replay.replay26        # View local replay file
      cambc watch --match <id>           # Open match on platform
      cambc watch --match <id> --game 3  # Open specific game
    """
    if match_id:
        _open_platform(match_id, game_number)
        return

    if not replay_file:
        console.print("[red]Provide a replay file or use --match <id>[/red]")
        console.print("[dim]  cambc watch replay.replay26[/dim]")
        console.print("[dim]  cambc watch --match <match-id>[/dim]")
        raise SystemExit(1)

    _serve_local(replay_file)


def _open_platform(match_id: str, game_number: int | None) -> None:
    """Open the platform visualiser page in the user's browser."""
    import webbrowser
    from cambc.auth import get_api_url

    base_url = get_api_url()
    url = f"{base_url}/visualiser?matchId={match_id}"
    if game_number is not None:
        url += f"&game={game_number}"

    console.print(f"Opening visualiser: [link={url}]{url}[/link]")
    webbrowser.open(url)


def _find_dist() -> "str | None":
    """Find the visualiser dist directory. Returns dist_path or None."""
    from pathlib import Path

    mono_dist = Path(__file__).parent.parent.parent.parent.parent / "visualiser" / "dist"
    bundled_dist = Path(__file__).parent.parent / "data" / "visualiser"

    if (mono_dist / "index.html").is_file():
        return str(mono_dist.resolve())
    if (bundled_dist / "index.html").is_file():
        return str(bundled_dist.resolve())
    return None


def _serve_local(replay_file: str) -> None:
    """Serve the visualiser locally with a replay file auto-loaded."""
    import http.server
    import threading
    import webbrowser
    from pathlib import Path

    replay_path = Path(replay_file).resolve()

    dist_path = _find_dist()
    if not dist_path:
        console.print(
            "[red]Visualiser not found. "
            "Try reinstalling cambc or use --match <id> to view on the platform.[/red]"
        )
        raise SystemExit(1)

    class ReplayHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=dist_path, **kwargs)

        def do_GET(self):
            if self.path == "/local-replay":
                try:
                    data = replay_path.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except Exception:
                    self.send_error(500, "Failed to read replay file")
                return
            super().do_GET()

        def log_message(self, format, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), ReplayHandler)
    port = server.server_address[1]

    url = f"http://127.0.0.1:{port}/?replayUrl=/local-replay"
    console.print(f"Serving visualiser at [link={url}]{url}[/link]")
    console.print(f"Replay: {replay_path.name}")
    console.print("[dim]Press Ctrl+C to stop[/dim]")

    threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")
        server.shutdown()
