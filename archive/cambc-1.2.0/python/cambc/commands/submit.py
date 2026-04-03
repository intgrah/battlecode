"""cambc submit — upload a bot to the platform."""

import io
import os
import zipfile
from pathlib import Path

import click
from rich.console import Console

from cambc.api import api_post_multipart

console = Console()


def _make_zip(bot_path: Path) -> bytes:
    """Create a zip from a directory or single file."""
    if bot_path.is_dir():
        main_py = bot_path / "main.py"
        if not main_py.is_file():
            raise click.BadParameter(f"Directory '{bot_path}' does not contain main.py")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(bot_path):
                for f in files:
                    full = Path(root) / f
                    arcname = str(full.relative_to(bot_path))
                    zf.write(full, arcname)
        return buf.getvalue()

    if bot_path.suffix == ".zip":
        return bot_path.read_bytes()

    if bot_path.suffix == ".py":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(bot_path, "main.py")
        return buf.getvalue()

    raise click.BadParameter(f"Expected a directory, .py file, or .zip: '{bot_path}'")


@click.command()
@click.argument("path", type=click.Path(exists=True))
def submit(path: str):
    """Upload a bot to the platform.

    PATH can be a directory (containing main.py), a single .py file,
    or a .zip archive.
    """
    bot_path = Path(path).resolve()
    console.print(f"[bold]Packaging {bot_path.name}...[/bold]")

    try:
        zip_bytes = _make_zip(bot_path)
    except click.BadParameter as e:
        console.print(f"[red]{e.format_message()}[/red]")
        raise SystemExit(1)

    size_kb = len(zip_bytes) / 1024
    console.print(f"  Zip size: {size_kb:.1f} KB")
    console.print("[bold]Uploading...[/bold]")

    data = api_post_multipart(
        "/api/submissions/upload",
        files={"file": ("bot.zip", zip_bytes, "application/zip")},
    )

    sub = data.get("submission", {})
    console.print(
        f"[green]Submitted![/green] Version {sub.get('version', '?')} (ID: {sub.get('id', '?')})"
    )
