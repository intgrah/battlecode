"""cambc test-run — run a remote test match with local bots and TLE enforcement."""

import io
import os
import zipfile
from pathlib import Path

import click
from rich.console import Console

from cambcpypy.api import api_post_multipart
from cambcpypy.config import find_config

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
            msg = f"Directory '{bot_path}' does not contain main.py"
            raise click.BadParameter(msg)
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

    msg = f"Bot not found or invalid: '{bot_path}'"
    raise click.BadParameter(msg)


def _show_test_run(bot_a: str, bot_b: str, maps: tuple[str, ...]) -> None:
    """Core implementation for running a remote test match."""
    config, project_root = find_config()
    bots_dir = (project_root / config.bots_dir).resolve()
    maps_dir = (project_root / config.maps_dir).resolve()

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

    if len(maps) > 5:
        console.print("[red]Maximum 5 maps per test run.[/red]")
        raise SystemExit(1)

    if maps:
        from cambcpypy.commands.run import resolve_map_path

        resolved_maps: list[Path] = []
        for map_arg in maps:
            mp = resolve_map_path(map_arg, maps_dir)
            if not mp.is_file():
                console.print(f"[red]Map file not found: {map_arg}[/red]")
                raise SystemExit(1)
            resolved_maps.append(mp)

        for i, mp in enumerate(resolved_maps):
            files[f"map_{i}"] = (mp.name, mp.read_bytes(), "application/octet-stream")
        text_fields["num_maps"] = str(len(resolved_maps))

        map_names = ", ".join(mp.stem for mp in resolved_maps)
        console.print(
            f"  Maps: {map_names} ({len(resolved_maps)} game{'s' if len(resolved_maps) != 1 else ''})"
        )

    console.print("[bold]Uploading and submitting test run...[/bold]")
    data = api_post_multipart("/api/matches/test-run", files, text_fields)

    match_id = data.get("matchId")
    if not match_id:
        console.print("[red]Unexpected response from server.[/red]")
        raise SystemExit(1)

    console.print(f"[green]Test run queued![/green] Match ID: {match_id}")
    console.print("  Check status: cambc match tests")


@click.command("test-run")
@click.argument("bot_a")
@click.argument("bot_b")
@click.argument("maps", nargs=-1)
def test_run(bot_a: str, bot_b: str, maps: tuple[str, ...]) -> None:
    """Run a remote test match between two local bots with TLE enforcement.

    \b
    BOT_A and BOT_B can be directories (containing main.py), single .py files,
    or .zip archives — same as `cambc run`.
    MAPS are optional .map26 files — one per game. If omitted, 5 random maps.

    \b
    Examples:
      cambc test-run starter starter
      cambc test-run bot_a bot_b arena.map26
      cambc test-run bot_a bot_b arena.map26 canyon.map26 arena.map26
    """
    _show_test_run(bot_a, bot_b, maps)
