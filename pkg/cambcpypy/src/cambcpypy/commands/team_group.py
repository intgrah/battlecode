"""cambc team — search teams and view team profiles (replaces `teams`)."""

import click
from rich.console import Console
from rich.table import Table

from cambcpypy.api import api_get

console = Console()


@click.group()
def team() -> None:
    """Search teams and view team profiles."""


@team.command()
@click.argument("query")
def search(query: str) -> None:
    """Search for teams by name."""
    from urllib.parse import urlencode

    data = api_get(f"/api/teams/search?{urlencode({'q': query})}")

    results = data.get("teams", [])
    if not results:
        console.print(f"[dim]No teams matching '{query}'.[/dim]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Team ID", style="dim")
    table.add_column("Name")
    table.add_column("Category")
    table.add_column("Rating", justify="right")
    table.add_column("Matches", justify="right")
    table.add_column("Region")

    for t in results:
        rating = f"{t.get('rating', 0):.0f}"
        table.add_row(
            t.get("teamId", "?"),
            t.get("teamName", "?"),
            t.get("category", "?"),
            rating,
            str(t.get("matchesPlayed", 0)),
            t.get("region", "?"),
        )

    console.print(table)


@team.command()
@click.argument("team_id")
def info(team_id: str) -> None:
    """View detailed info for a team by ID."""
    data = api_get(f"/api/teams/{team_id}")

    team_data = data.get("team", {})
    members = data.get("members", [])
    rating = data.get("rating")

    console.print(
        f"\n[bold]{team_data.get('name', '?')}[/bold]  [dim]({team_data.get('id', '?')})[/dim]"
    )
    console.print(f"  Category: {team_data.get('category', '?')}")
    console.print(f"  Region:   {data.get('region', '?')}")

    if rating:
        console.print(f"  Rating:   {rating.get('rating', 0):.0f}")
        console.print(f"  Matches:  {rating.get('matchesPlayed', 0)}")
    else:
        console.print("  Rating:   unrated")

    if members:
        console.print("\n  Members:")
        for m in members:
            role_badge = " [dim](owner)[/dim]" if m.get("role") == "owner" else ""
            region = f" [{m.get('userRegion', '?')}]"
            console.print(f"    - {m.get('userName', '?')}{role_badge}{region}")

    console.print()
