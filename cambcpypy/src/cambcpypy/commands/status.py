"""cambc status — show current team, latest submission, and ladder rank."""

import click
from rich.console import Console

from cambcpypy.api import api_get
from cambcpypy.auth import load_credentials

console = Console()


def _get_rank_tier(rating: float, matches_played: int) -> str:
    """Return rank tier name based on rating and matches played.

    Keep in sync with shared/src/ranks.ts.
    """
    if matches_played < 100:
        return "Unranked"
    tiers = [
        (2400, "Grandmaster"),
        (2200, "Master"),
        (2000, "Candidate Master"),
        (1800, "Diamond"),
        (1600, "Emerald"),
        (1500, "Gold"),
        (1400, "Silver"),
    ]
    for threshold, name in tiers:
        if rating >= threshold:
            return name
    return "Bronze"


@click.command()
def status() -> None:
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
        console.print("  [dim](Could not fetch live data)[/dim]")
        console.print()
        return

    team_info = data.get("team", {})
    rating = data.get("rating")
    members = data.get("members", [])

    console.print(
        f"  Team: [bold]{team_info.get('name', '?')}[/bold] ({team_info.get('category', '?')})"
    )

    if rating:
        r = rating.get("rating", 0)
        mp = rating.get("matchesPlayed", 0)
        tier = _get_rank_tier(r, mp)
        console.print(f"  Rating: {r:.0f} ({tier}) — {mp} matches played")
    else:
        console.print("  Rating: [dim]unrated[/dim]")

    # Show ladder rank position
    try:
        ladder_data = api_get("/api/ladder")
        rankings = (
            ladder_data
            if isinstance(ladder_data, list)
            else ladder_data.get("rankings", [])
        )
        my_rank = next(
            (i + 1 for i, r in enumerate(rankings) if r.get("teamId") == team["id"]),
            None,
        )
        if my_rank:
            console.print(f"  Rank: #{my_rank} of {len(rankings)}")
    except SystemExit:
        pass

    # Show active submission
    try:
        sub_data = api_get("/api/submissions")
        subs = sub_data.get("submissions", [])
        active = next((s for s in subs if s.get("isActive")), None)
        if active:
            name_part = f" ({active['name']})" if active.get("name") else ""
            console.print(f"  Active bot: v{active.get('version', '?')}{name_part}")
        elif subs:
            console.print("  Active bot: [dim]none (no ready submission)[/dim]")
        else:
            console.print("  Active bot: [dim]no submissions yet[/dim]")
    except SystemExit:
        pass

    # Show recent match record
    try:
        match_data = api_get("/api/matches", {"teamIds": team["id"], "limit": "10"})
        recent = match_data.get("matches", [])
        if recent:
            wins = sum(1 for m in recent if m.get("winnerId") == team["id"])
            losses = sum(
                1
                for m in recent
                if m.get("winnerId") and m.get("winnerId") != team["id"]
            )
            console.print(f"  Last 10: {wins}W {losses}L")
    except SystemExit:
        pass

    console.print(f"  Members: {', '.join(m.get('userName', '?') for m in members)}")
    console.print()
