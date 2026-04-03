"""cambc test-run — run a remote test match with local bots and TLE enforcement."""

import io
import os
import zipfile
from pathlib import Path

import click
from rich.console import Console

from cambc.api import api_post_multipart
from cambc.config import find_config

console = Console()


def _zip_bot(bot_path: str, bots_dir: Path) -> bytes:
    """Resolve a bot path and return it as a zip in memory."""
    p = Path(bot_path)
    if not p.exists() and not p.is_absolute():
        candidate = bots_dir / bot_path
        if candidate.exists():
            p = candidate

    if p.is_dir():
        main_py = p / "main.py"
        if not main_py.is_file():
            raise click.BadParameter(f"Directory '{bot_path}' does not contain main.py")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(p):
                for f in files:
                    full = Path(root) / f
                    arcname = str(full.relative_to(p))
                    zf.write(full, arcname)
        return buf.getvalue()

    if p.is_file() and p.name == "main.py":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(p, "main.py")
        return buf.getvalue()

    if p.is_file() and p.suffix == ".zip":
        return p.read_bytes()

    raise click.BadParameter(f"Bot not found or invalid: '{bot_path}'")


@click.command("test-run")
@click.argument("bot_a")
@click.argument("bot_b")
@click.argument("map_path", required=False, default=None)
def test_run(bot_a: str, bot_b: str, map_path: str | None):
    """Run a remote test match between two local bots with TLE enforcement.

    \b
    BOT_A and BOT_B can be directories (containing main.py), single .py files,
    or .zip archives — same as `cambc run`.
    MAP_PATH is optional — a .map26 file to use for all games.

    \b
    Examples:
      cambc test-run starter starter
      cambc test-run bot_a bot_b maps/default_small1.map26
    """
    config, project_root = find_config()
    bots_dir = (project_root / config.bots_dir).resolve()

    console.print("[bold]Packaging bots...[/bold]")
    try:
        zip_a = _zip_bot(bot_a, bots_dir)
        zip_b = _zip_bot(bot_b, bots_dir)
    except click.BadParameter as e:
        console.print(f"[red]{e.format_message()}[/red]")
        raise SystemExit(1)

    files: dict[str, tuple[str, bytes, str]] = {
        "bot_a": ("bot_a.zip", zip_a, "application/zip"),
        "bot_b": ("bot_b.zip", zip_b, "application/zip"),
    }
    text_fields: dict[str, str] = {
        "bot_a_name": Path(bot_a).stem,
        "bot_b_name": Path(bot_b).stem,
    }

    if map_path:
        mp = Path(map_path)
        if not mp.exists() and not mp.is_absolute():
            candidate = project_root / config.maps_dir / map_path
            if candidate.exists():
                mp = candidate
        if not mp.is_file():
            console.print(f"[red]Map file not found: {map_path}[/red]")
            raise SystemExit(1)
        files["map"] = (mp.name, mp.read_bytes(), "application/octet-stream")

    console.print("[bold]Uploading and submitting test run...[/bold]")
    data = api_post_multipart("/api/matches/test-run", files, text_fields)

    match_id = data.get("matchId")
    if not match_id:
        console.print("[red]Unexpected response from server.[/red]")
        raise SystemExit(1)

    console.print(f"[green]Test run queued![/green] Match ID: {match_id}")
    console.print(f"  Check status: cambc test-matches")
