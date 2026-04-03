"""cambc status — show current team, latest submission, and ladder rank."""

import click
from rich.console import Console

from cambc.api import api_get
from cambc.auth import load_credentials

console = Console()


@click.command()
def status():
    """Show your team, latest submission, and ladder rank."""
    creds = load_credentials()
    if not creds:
        console.print("[red]Not logged in. Run: cambc login[/red]")
        raise SystemExit(1)

    user = creds.get("user", {})
    team = creds.get("team")

    console.print(f"\n[bold]{user.get('name', '?')}[/bold] ({user.get('email', '?')})")

    if not team:
        console.print("  Team: [dim]none[/dim]")
        console.print()
        return

    try:
        data = api_get(f"/api/teams/{team['id']}")
    except SystemExit:
        console.print(f"  Team: [bold]{team.get('name', '?')}[/bold]")
        console.print(f"  [dim](Could not fetch live data)[/dim]")
        console.print()
        return

    team_info = data.get("team", {})
    rating = data.get("rating")
    members = data.get("members", [])

    console.print(f"  Team: [bold]{team_info.get('name', '?')}[/bold] ({team_info.get('category', '?')})")

    if rating:
        r = rating.get("rating", 0)
        mp = rating.get("matchesPlayed", 0)
        console.print(f"  Rating: {r:.0f} -- {mp} matches played")
    else:
        console.print("  Rating: [dim]unrated[/dim]")

    console.print(f"  Members: {', '.join(m.get('userName', '?') for m in members)}")
    console.print()
