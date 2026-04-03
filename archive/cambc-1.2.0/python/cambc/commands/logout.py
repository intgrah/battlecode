"""cambc logout — clear stored credentials."""

import click
from rich.console import Console

from cambc.auth import clear_credentials, load_credentials

console = Console()


@click.command()
def logout():
    """Clear stored authentication credentials."""
    existing = load_credentials()
    if not existing:
        console.print("Not currently logged in.")
        return

    clear_credentials()
    user = existing.get("user", {})
    console.print(f"Logged out (was [bold]{user.get('name', '?')}[/bold]).")
