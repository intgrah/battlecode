"""cambc test-matches — list your remote test runs."""

import click
from rich.console import Console
from rich.table import Table

from cambc.api import api_get

console = Console()


@click.command("test-matches")
@click.option("--limit", default=20, type=int, help="Number of test runs to show")
def test_matches(limit: int):
    """List your remote test run matches."""
    data = api_get("/api/matches/test-runs")
    match_list = data.get("matches", [])[:limit]

    if not match_list:
        console.print("[dim]No test runs found.[/dim]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Match ID", style="dim")
    table.add_column("Score", justify="center")
    table.add_column("Status")
    table.add_column("Stage", style="dim")
    table.add_column("Date", style="dim")

    for m in match_list:
        score = f"{m.get('scoreA', 0)}-{m.get('scoreB', 0)}"
        status = m.get("status", "?")
        stage = m.get("stage") or ""
        match_id = m.get("id", "?")

        if status == "complete":
            status = f"[green]{status}[/green]"
        elif status == "error":
            status = f"[red]{status}[/red]"
            if m.get("errorMessage"):
                stage = m["errorMessage"][:60]
        elif status == "running":
            status = f"[yellow]{status}[/yellow]"

        date = ""
        raw_date = m.get("completedAt") or m.get("createdAt")
        if raw_date:
            date = raw_date[:16].replace("T", " ")

        table.add_row(match_id, score, status, stage, date)

    console.print(table)
