"""cambc ladder — view ladder rankings."""

import click
from rich.console import Console
from rich.table import Table

from cambcpypy.api import api_get
from cambcpypy.auth import load_credentials

console = Console()


@click.command()
@click.option("--limit", default=20, type=int, help="Number of teams to show")
@click.option(
    "--category",
    default=None,
    type=click.Choice(["novice", "main"]),
    help="Filter by category",
)
@click.option(
    "--region",
    default=None,
    type=click.Choice(["uk", "international"]),
    help="Filter by region",
)
@click.option("--around", is_flag=True, help="Show rankings around your team (±5)")
def ladder(limit: int, category: str | None, region: str | None, around: bool) -> None:
    """View ladder rankings."""
    data = api_get("/api/ladder")
    rankings = data if isinstance(data, list) else data.get("rankings", data)

    if not rankings:
        console.print("[dim]No teams on the ladder yet.[/dim]")
        return

    # Add rank numbers before filtering (overall ladder position)
    for i, r in enumerate(rankings):
        r["_rank"] = i + 1

    # Apply filters
    if category:
        rankings = [r for r in rankings if r.get("category") == category]
    if region:
        rankings = [r for r in rankings if r.get("region") == region]

    creds = load_credentials()
    my_team_id = None
    if creds and creds.get("team"):
        my_team_id = creds["team"].get("id")

    total_after_filter = len(rankings)

    if around and my_team_id:
        my_idx = next(
            (i for i, r in enumerate(rankings) if r.get("teamId") == my_team_id), None
        )
        if my_idx is not None:
            start = max(0, my_idx - 5)
            end = min(len(rankings), my_idx + 6)
            rankings = rankings[start:end]
        else:
            console.print("[dim]Your team is not on the ladder.[/dim]")
            return
    else:
        rankings = rankings[:limit]

    table = Table(show_header=True, header_style="bold")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Team")
    table.add_column("Rating", justify="right")
    table.add_column("Matches", justify="right")
    table.add_column("Category", style="dim")
    table.add_column("Region", style="dim")

    for r in rankings:
        rank = str(r["_rank"])
        name = r.get("teamName", "?")
        is_mine = my_team_id and r.get("teamId") == my_team_id
        if is_mine:
            name = f"[bold cyan]{name}[/bold cyan]"
            rank = f"[bold cyan]{rank}[/bold cyan]"

        rating = f"{r.get('rating', 0):.0f}"
        matches_played = str(r.get("matchesPlayed", 0))

        table.add_row(
            rank,
            name,
            rating,
            matches_played,
            r.get("category", "?"),
            r.get("region", "?"),
        )

    console.print(table)
    if not around:
        console.print(
            f"\n[dim]Showing {len(rankings)} of {total_after_filter} teams. Use --limit or --around.[/dim]"
        )
