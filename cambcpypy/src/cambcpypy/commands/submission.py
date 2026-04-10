"""cambc submission — manage bot submissions (upload, list, activate, rename)."""

import io
import os
import zipfile
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from cambcpypy.api import api_get, api_post, api_post_multipart

console = Console()


_JUNK_DIRS = {
    "__pycache__",
    ".git",
    ".svn",
    ".hg",
    ".idea",
    ".vscode",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__MACOSX",
    ".tox",
    ".eggs",
    ".nox",
}

_JUNK_FILES = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    ".thumbs",
    "ehthumbs.db",
    "ehthumbs_vista.db",
    ".Spotlight-V100",
    ".Trashes",
    ".directory",
}

_JUNK_EXTENSIONS = {".pyc", ".pyo"}


def _is_junk(path: Path) -> bool:
    if path.name in _JUNK_FILES or path.name.startswith("._"):
        return True
    if path.suffix in _JUNK_EXTENSIONS:
        return True
    return any(part in _JUNK_DIRS for part in path.parts)


def _make_zip(bot_path: Path) -> bytes:
    """Create a zip from a directory or single file."""
    if bot_path.is_dir():
        main_py = bot_path / "main.py"
        if not main_py.is_file():
            msg = f"Directory '{bot_path}' does not contain main.py"
            raise click.BadParameter(msg)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(bot_path):
                dirs[:] = [d for d in dirs if d not in _JUNK_DIRS]
                for f in files:
                    full = Path(root) / f
                    if _is_junk(full.relative_to(bot_path)):
                        continue
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

    msg = f"Expected a directory, .py file, or .zip: '{bot_path}'"
    raise click.BadParameter(msg)


@click.group()
def submission() -> None:
    """Manage bot submissions (upload, list, activate, rename)."""


@submission.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--name", "-n", default=None, help="Optional name for this submission")
def upload(path: str, name: str | None) -> None:
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

    text_fields: dict[str, str] = {}
    if name:
        text_fields["name"] = name

    data = api_post_multipart(
        "/api/submissions/upload",
        files={"file": ("bot.zip", zip_bytes, "application/zip")},
        text_fields=text_fields or None,
    )

    sub = data.get("submission", {})
    msg = f"[green]Submitted![/green] Version {sub.get('version', '?')} (ID: {sub.get('id', '?')})"
    if name:
        msg += f" — {name}"
    console.print(msg)


@submission.command("list")
def list_submissions() -> None:
    """List all submissions for your team."""
    data = api_get("/api/submissions")
    subs = data.get("submissions", [])

    if not subs:
        console.print("[dim]No submissions yet.[/dim]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Version", justify="right")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Active", justify="center")
    table.add_column("Uploaded By")
    table.add_column("Date", style="dim")

    for s in subs:
        version = f"v{s.get('version', '?')}"
        name_display = s.get("name") or "[dim]—[/dim]"
        status = s.get("status", "?")
        if status == "ready":
            status = f"[green]{status}[/green]"
        elif status == "error":
            status = f"[red]{status}[/red]"

        active = "[green]Yes[/green]" if s.get("isActive") else "[dim]—[/dim]"
        uploaded_by = s.get("submittedByName") or "[dim]—[/dim]"

        date = ""
        raw = s.get("uploadedAt")
        if raw:
            date = raw[:16].replace("T", " ")

        table.add_row(version, name_display, status, active, uploaded_by, date)

    console.print(table)


@submission.command()
@click.argument("version", type=int)
def activate(version: int) -> None:
    """Set a submission as the active one used for ladder matches.

    VERSION is the submission version number (e.g. 3).
    """
    # First, list submissions to find the ID for this version
    data = api_get("/api/submissions")
    subs = data.get("submissions", [])

    target = next((s for s in subs if s.get("version") == version), None)
    if not target:
        console.print(f"[red]No submission found with version {version}.[/red]")
        raise SystemExit(1)

    if target.get("status") != "ready":
        console.print(
            f"[red]Version {version} has status '{target.get('status')}' — only ready submissions can be activated.[/red]"
        )
        raise SystemExit(1)

    if target.get("isActive"):
        console.print(f"[dim]Version {version} is already active.[/dim]")
        return

    api_post("/api/submissions/activate", {"submissionId": target["id"]})
    console.print(f"[green]Version {version} is now the active submission.[/green]")


@submission.command()
@click.argument("version", type=int)
@click.argument("name")
def rename(version: int, name: str) -> None:
    """Rename a submission.

    VERSION is the submission version number (e.g. 3).
    NAME is the new name for the submission.
    """
    data = api_get("/api/submissions")
    subs = data.get("submissions", [])

    target = next((s for s in subs if s.get("version") == version), None)
    if not target:
        console.print(f"[red]No submission found with version {version}.[/red]")
        raise SystemExit(1)

    api_post("/api/submissions/rename", {"submissionId": target["id"], "name": name})
    console.print(f"[green]Version {version} renamed to '{name}'.[/green]")


@submission.command()
@click.argument("version", required=False, default=None, type=int)
@click.option(
    "--output", "-o", default=None, help="Output file path (default: v<VERSION>.zip)"
)
def download(version: int | None, output: str | None) -> None:
    """Download a submission zip file.

    VERSION is the submission version number. Defaults to the active submission.
    """
    import urllib.request

    data = api_get("/api/submissions")
    subs = data.get("submissions", [])

    if not subs:
        console.print("[red]No submissions found.[/red]")
        raise SystemExit(1)

    if version is not None:
        target = next((s for s in subs if s.get("version") == version), None)
        if not target:
            console.print(f"[red]No submission found with version {version}.[/red]")
            raise SystemExit(1)
    else:
        target = next((s for s in subs if s.get("isActive")), None)
        if not target:
            target = next((s for s in subs if s.get("status") == "ready"), None)
        if not target:
            console.print("[red]No ready submission to download.[/red]")
            raise SystemExit(1)
        version = target.get("version", 0)

    dl_data = api_get("/api/submissions/download", {"submissionId": target["id"]})
    url = dl_data.get("url")
    if not url:
        console.print("[red]Could not get download URL.[/red]")
        raise SystemExit(1)

    out_path = output or f"v{version}.zip"
    urllib.request.urlretrieve(url, out_path)
    name_part = f" ({target['name']})" if target.get("name") else ""
    console.print(f"[green]Downloaded v{version}{name_part} to {out_path}[/green]")
