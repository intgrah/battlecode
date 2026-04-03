"""cambc match — view detailed match info including individual games."""

import click
from rich.console import Console
from rich.table import Table

from cambc.api import api_get

console = Console()

_STAGE_LABELS = {
    "starting": "Starting...",
    "downloading_bots": "Downloading bots...",
    "uploading_replay": "Uploading replay...",
    "processing_result": "Processing...",
}


def _format_stage(stage: str) -> str:
    if stage in _STAGE_LABELS:
        return _STAGE_LABELS[stage]
    if stage.startswith("running_game_"):
        n = stage.split("_")[2]
        return f"Game {n}/5"
    return stage


@click.command("match")
@click.argument("match_id")
def match_detail(match_id: str):
    """View detailed info for a match, including individual games."""
    data = api_get(f"/api/matches/{match_id}")
    m = data.get("match")
    games = data.get("games", [])

    if not m:
        console.print("[red]Match not found.[/red]")
        raise SystemExit(1)

    status = m.get("status", "?")
    triggered = m.get("triggeredBy", "?")
    rated = "rated" if m.get("rated") else "unrated"
    score = f"{m.get('scoreA', 0)}-{m.get('scoreB', 0)}"

    console.print(f"\n[bold]Match {match_id}[/bold]")

    stage = m.get("stage") or ""
    if status == "complete":
        status_display = f"[green]{status}[/green]"
    elif status == "error":
        status_display = f"[red]{status}[/red]"
    elif status == "running":
        stage_label = _format_stage(stage) if stage else ""
        status_display = f"[yellow]{status}[/yellow]"
        if stage_label:
            status_display += f" ({stage_label})"
    elif status == "queued":
        status_display = f"[dim]{status}[/dim]"
    else:
        status_display = status
    console.print(f"  Status:  {status_display}")
    console.print(f"  Type:    {triggered} ({rated})")

    team_a = m.get("teamAName") or "Bot A"
    team_b = m.get("teamBName") or "Bot B"
    team_a_id = m.get("teamAId")
    team_b_id = m.get("teamBId")
    winner_id = m.get("winnerId")

    score_a = m.get("scoreA", 0)
    score_b = m.get("scoreB", 0)
    a_is_winner = (winner_id and winner_id == team_a_id) or (not winner_id and score_a > score_b)
    b_is_winner = (winner_id and winner_id == team_b_id) or (not winner_id and score_b > score_a)

    a_id_display = f" ({team_a_id})" if team_a_id else ""
    a_line = f"  Team A:  [bold]{team_a}[/bold]{a_id_display}"
    if a_is_winner:
        a_line += " [green]<- winner[/green]"
    source_a = m.get("sourceMatchAId")
    if source_a:
        a_line += f"\n           [dim]submission from match {source_a}[/dim]"

    b_id_display = f" ({team_b_id})" if team_b_id else ""
    b_line = f"  Team B:  [bold]{team_b}[/bold]{b_id_display}"
    if b_is_winner:
        b_line += " [green]<- winner[/green]"
    source_b = m.get("sourceMatchBId")
    if source_b:
        b_line += f"\n           [dim]submission from match {source_b}[/dim]"

    console.print(a_line)
    console.print(b_line)
    console.print(f"  Score:   [bold]{score}[/bold]")

    elo_a = m.get("eloDeltaA")
    elo_b = m.get("eloDeltaB")
    if elo_a is not None and elo_b is not None:
        sign_a = "+" if elo_a >= 0 else ""
        sign_b = "+" if elo_b >= 0 else ""
        console.print(f"  ELO:     A: {sign_a}{elo_a:.1f}  B: {sign_b}{elo_b:.1f}")

    created = m.get("createdAt", "")
    if created:
        console.print(f"  Created: {created[:19].replace('T', ' ')}")
    completed = m.get("completedAt", "")
    if completed:
        console.print(f"  Done:    {completed[:19].replace('T', ' ')}")

    error_msg = m.get("errorMessage")
    if status == "error" and error_msg:
        # Decode escaped newlines/tabs from the stored error string
        rendered = error_msg.replace("\\n", "\n").replace("\\t", "\t")
        console.print()
        console.print("[red]Error:[/red]")
        for line in rendered.splitlines():
            console.print(f"  [red]{line}[/red]")

    if not games:
        if status == "queued":
            console.print("\n  [dim]Match is queued — waiting for a runner...[/dim]\n")
        elif status == "running":
            console.print("\n  [dim]Match is running...[/dim]\n")
        else:
            console.print("\n  [dim]No game data.[/dim]\n")
        return

    console.print()
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Map")
    table.add_column("Winner", justify="center")
    table.add_column("Condition")
    table.add_column("Turns", justify="right")

    for g in games:
        game_num = str(g.get("gameNumber", "?"))
        map_name = g.get("mapName", "?")
        g_winner = g.get("winnerId")

        if g_winner and g_winner == team_a_id:
            winner = f"[green]A ({team_a})[/green]"
        elif g_winner and g_winner == team_b_id:
            winner = f"[green]B ({team_b})[/green]"
        else:
            winner = "[dim]--[/dim]"

        condition = g.get("winCondition", "?")
        turns = str(g.get("turnsPlayed", "?"))
        table.add_row(game_num, map_name, winner, condition, turns)

    console.print(table)
    console.print()
