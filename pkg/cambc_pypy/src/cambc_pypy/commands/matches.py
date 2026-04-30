"""cambc matches — list and filter matches."""

import click
from rich.console import Console
from rich.table import Table

from cambc_pypy.api import api_get
from cambc_pypy.auth import load_credentials

console = Console()


def _show_matches(
    match_type: str | None,
    team: str | None,
    limit: int,
    cursor: str | None,
    mine: bool = False,
) -> None:
    """Core implementation for listing matches."""
    params: dict[str, str | list[str]] = {"limit": str(min(limit, 100))}
    if match_type:
        params["type"] = match_type
    if mine and not team:
        creds = load_credentials()
        if creds and creds.get("team"):
            params["teamIds"] = creds["team"]["id"]
        else:
            console.print("[red]Not on a team. Use --team instead.[/red]")
            raise SystemExit(1)
    elif team:
        # Try to resolve team name to ID via search
        search_data = api_get("/api/teams/search", {"q": team})
        search_results = search_data.get("teams", [])
        # Check for exact match first, then fall back to first result
        exact = [t for t in search_results if t["teamName"].lower() == team.lower()]
        if exact:
            params["teamIds"] = exact[0]["teamId"]
        elif search_results:
            params["teamIds"] = search_results[0]["teamId"]
        else:
            # Maybe it's already a team ID
            params["teamIds"] = team
    if cursor:
        params["cursor"] = cursor

    data = api_get("/api/matches", params)
    match_list = data.get("matches", [])
    next_cursor = data.get("nextCursor")

    if not match_list:
        label = match_type or "all"
        console.print(f"[dim]No {label} matches found.[/dim]")
        return

    creds = load_credentials()
    my_team_id = None
    if creds and creds.get("team"):
        my_team_id = creds["team"].get("id")

    show_type = match_type is None

    table = Table(show_header=True, header_style="bold")
    table.add_column("Match ID", style="dim")
    if show_type:
        table.add_column("Type", style="dim")
    table.add_column("Team A")
    table.add_column("Score", justify="center")
    table.add_column("Team B")
    table.add_column("Status")
    table.add_column("Date", style="dim")

    for m in match_list:
        team_a_name = m.get("teamAName", "?")
        team_b_name = m.get("teamBName", "?")
        team_a_id = m.get("teamAId", "")
        team_b_id = m.get("teamBId", "")

        if m.get("sourceMatchAId"):
            team_a_name += " [dim](OLD)[/dim]"
        if m.get("sourceMatchBId"):
            team_b_name += " [dim](OLD)[/dim]"

        if my_team_id and team_a_id == my_team_id:
            team_a_name = f"[bold]{team_a_name}[/bold]"
        if my_team_id and team_b_id == my_team_id:
            team_b_name = f"[bold]{team_b_name}[/bold]"

        winner_id = m.get("winnerId")
        if winner_id == team_a_id:
            team_a_name = f"[green]{team_a_name}[/green]"
            team_b_name = f"[red]{team_b_name}[/red]"
        elif winner_id == team_b_id:
            team_a_name = f"[red]{team_a_name}[/red]"
            team_b_name = f"[green]{team_b_name}[/green]"

        score = f"{m.get('scoreA', 0)}-{m.get('scoreB', 0)}"
        status = m.get("status", "?")
        match_id = m.get("id", "?")

        date = ""
        raw_date = m.get("completedAt") or m.get("createdAt")
        if raw_date:
            date = raw_date[:16].replace("T", " ")

        row: list[str] = [match_id]
        if show_type:
            triggered = m.get("triggeredBy", "?")
            row.append("UR" if triggered == "unrated" else triggered)
        row.extend([team_a_name, score, team_b_name, status, date])
        table.add_row(*row)

    console.print(table)

    if next_cursor:
        console.print(
            f"\n[dim]More results available. Use --cursor '{next_cursor}'[/dim]"
        )


@click.command()
@click.option(
    "--type",
    "match_type",
    default=None,
    type=click.Choice(["ladder", "unrated"]),
    help="Filter by match type (shows all if omitted)",
)
@click.option("--team", default=None, help="Filter by team name or team ID")
@click.option("--mine", is_flag=True, help="Show only your team's matches")
@click.option(
    "--limit", default=20, type=int, help="Number of matches to show (max 100)"
)
@click.option("--cursor", default=None, help="Pagination cursor (from previous page)")
def matches(
    match_type: str | None, team: str | None, mine: bool, limit: int, cursor: str | None
) -> None:
    """List recent matches. Use --type to filter by ladder or unrated."""
    _show_matches(match_type, team, limit, cursor, mine=mine)
