"""cambc unrated — request an unrated match against another team."""

import click
from rich.console import Console

from cambcpypy.api import api_post

console = Console()


def _show_unrated(
    opponent_id: str, source_match: str | None, maps: tuple[str, ...] | None
) -> None:
    """Core implementation for requesting an unrated match."""
    body: dict = {"opponentTeamId": opponent_id}
    if source_match:
        body["sourceMatchId"] = source_match
    if maps:
        body["mapNames"] = list(maps[:5])

    data = api_post("/api/matches/unrated", body)

    match_id = data.get("matchId")
    if not match_id:
        console.print("[red]Unexpected response from server.[/red]")
        raise SystemExit(1)

    from cambcpypy.auth import get_api_url

    msg = f"[green]Unrated match queued![/green] Match ID: {match_id}"
    if source_match:
        msg += f"\n  Opponent version from match: {source_match}"
    if maps:
        msg += f"\n  Maps: {', '.join(maps[:5])}"
    console.print(msg)
    console.print(f"  View at: {get_api_url()}/match/{match_id}")


@click.command("unrated")
@click.argument("opponent_id")
@click.option(
    "--match",
    "source_match",
    default=None,
    help="Use opponent's submission from this match ID",
)
@click.option(
    "--map",
    "maps",
    multiple=True,
    help="Map name (repeatable, up to 5). Omit for random.",
)
def unrated(opponent_id: str, source_match: str | None, maps: tuple[str, ...]) -> None:
    """Request an unrated match against OPPONENT_ID (your team vs theirs).

    Use `cambc team search` to find team IDs.

    With --match, the opponent uses whichever submission version they had
    in that match, instead of their latest.

    With --map, specify which maps to play (up to 5). Omit for random selection.
    Example: cambc unrated <id> --map arena --map fortress --map galaxy
    """
    _show_unrated(opponent_id, source_match, maps or None)
