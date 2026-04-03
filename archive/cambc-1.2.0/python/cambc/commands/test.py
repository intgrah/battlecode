"""cambc unrated — request an unrated match against another team."""

import click
from rich.console import Console

from cambc.api import api_post

console = Console()


@click.command("unrated")
@click.argument("opponent_id")
@click.option("--match", "source_match", default=None, help="Use opponent's submission from this match ID")
def unrated(opponent_id: str, source_match: str | None):
    """Request an unrated match against OPPONENT_ID (your team vs theirs).

    Use `cambc teams search` to find team IDs.

    With --match, the opponent uses whichever submission version they had
    in that match, instead of their latest.
    """
    body: dict[str, str] = {"opponentTeamId": opponent_id}
    if source_match:
        body["sourceMatchId"] = source_match

    data = api_post("/api/matches/unrated", body)

    match_id = data.get("matchId")
    if not match_id:
        console.print("[red]Unexpected response from server.[/red]")
        raise SystemExit(1)

    from cambc.auth import get_api_url
    msg = f"[green]Unrated match queued![/green] Match ID: {match_id}"
    if source_match:
        msg += f"\n  Opponent version from match: {source_match}"
    console.print(msg)
    console.print(f"  View at: {get_api_url()}/match/{match_id}")
