"""cambc match — view, list, and manage matches."""

import click
from rich.console import Console

from cambcpypy.compat import SmartGroup

console = Console()


@click.group(cls=SmartGroup, default_cmd="info")
def match() -> None:
    """View, list, and manage matches."""


# --- info (default subcommand) ---
from cambcpypy.commands.match_detail import _show_match_detail


@match.command()
@click.argument("match_id")
def info(match_id: str) -> None:
    """View detailed info for a match, including individual games."""
    _show_match_detail(match_id)


# --- list ---
from cambcpypy.commands.matches import _show_matches


@match.command("list")
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
def list_matches(match_type, team, mine, limit, cursor) -> None:
    """List recent matches. Use --type to filter by ladder or unrated."""
    _show_matches(match_type, team, limit, cursor, mine=mine)


# --- unrated ---
from cambcpypy.commands.test import _show_unrated


@match.command()
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
    """Request an unrated match against OPPONENT_ID.

    Use `cambc team search` to find team IDs.

    With --map, specify which maps to play (up to 5). Omit for random selection.
    Example: cambc match unrated <id> --map arena --map fortress
    """
    _show_unrated(opponent_id, source_match, maps or None)


# --- test ---
from cambcpypy.commands.test_run import _show_test_run


@match.command("test")
@click.argument("bot_a")
@click.argument("bot_b")
@click.argument("maps", nargs=-1)
def test(bot_a: str, bot_b: str, maps: tuple[str, ...]) -> None:
    """Run a remote test match between two local bots with TLE enforcement.

    \b
    BOT_A and BOT_B can be directories (containing main.py), single .py files,
    or .zip archives.
    MAPS are optional .map26 files — one per game. If omitted, 5 random maps.
    """
    _show_test_run(bot_a, bot_b, maps)


# --- replay ---


@match.command()
@click.argument("match_id")
@click.option(
    "--game",
    "-g",
    default=None,
    type=int,
    help="Game number (1-5). Downloads all if omitted.",
)
@click.option(
    "--output",
    "-o",
    default=None,
    help="Output file path (default: <matchId>_game_<N>.replay26)",
)
def replay(match_id: str, game: int | None, output: str | None) -> None:
    """Download replay file(s) for a match.

    Downloads .replay26 files locally for offline viewing with `cambc watch`.
    """
    import urllib.request

    from cambcpypy.api import api_get

    # Get match games to know how many there are
    data = api_get(f"/api/matches/{match_id}")
    games = data.get("games", [])

    if not games:
        console.print(
            "[red]No games found for this match (match may still be running).[/red]"
        )
        raise SystemExit(1)

    if game is not None:
        targets = [g for g in games if g.get("gameNumber") == game]
        if not targets:
            console.print(
                f"[red]Game {game} not found. Match has games 1-{len(games)}.[/red]"
            )
            raise SystemExit(1)
    else:
        targets = games

    for g in targets:
        gn = g.get("gameNumber", 0)
        replay_data = api_get(
            "/api/matches/replay", {"matchId": match_id, "game": str(gn)}
        )
        url = replay_data.get("url")
        if not url:
            console.print(f"  [yellow]Game {gn}: no replay available[/yellow]")
            continue

        if output and len(targets) == 1:
            out_path = output
        else:
            out_path = f"{match_id}_game_{gn}.replay26"

        urllib.request.urlretrieve(url, out_path)
        console.print(f"  [green]Game {gn}:[/green] {out_path}")

    console.print("\n[dim]View with: cambc watch <file>[/dim]")


# --- watch ---


@match.command("watch")
@click.argument("match_id")
@click.option("--game", "-g", default=None, type=int, help="Game number within match")
def watch(match_id: str, game: int | None) -> None:
    """Open a match replay in the visualizer (browser).

    Shortcut for `cambc watch --match <id>`.
    """
    import webbrowser

    from cambcpypy.auth import get_api_url

    url = f"{get_api_url()}/visualiser?matchId={match_id}"
    if game is not None:
        url += f"&game={game}"
    webbrowser.open(url)


# --- tests ---
from cambcpypy.commands.test_matches import _show_test_matches


@match.command("tests")
@click.option("--limit", default=20, type=int, help="Number of test runs to show")
def tests(limit: int) -> None:
    """List your remote test run matches."""
    _show_test_matches(limit)
