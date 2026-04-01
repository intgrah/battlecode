#!/usr/bin/env python3
"""Queue unrated matches against nearby ladder opponents.

Usage:
    python tools/challenge.py          # 10 teams above us
    python tools/challenge.py --top    # top 10 (if rank >= 10)
    python tools/challenge.py -n 5     # 5 teams above us
"""

import argparse
import subprocess
import sys

CAMBC = "venv/bin/cambc"


def run_json(args: list[str]) -> str:
    """Run a cambc command and return stdout."""
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def get_ladder(limit: int) -> list[dict]:
    """Parse ladder output into list of {rank, name, rating, team_id}."""
    # Use team search to get IDs — ladder doesn't show them.
    # First get names from ladder.
    out = subprocess.run(
        [CAMBC, "ladder", "--limit", str(limit)],
        capture_output=True, text=True, env={"COLUMNS": "200", "PATH": subprocess.os.environ["PATH"],
                                              "HOME": subprocess.os.environ["HOME"]}
    )
    lines = out.stdout.strip().split("\n")
    teams = []
    for line in lines:
        # Parse table rows: │ rank │ name │ rating │ matches │ category │ region │
        if not line.startswith("│"):
            continue
        parts = [p.strip() for p in line.split("│") if p.strip()]
        if len(parts) < 4:
            continue
        try:
            rank = int(parts[0])
        except ValueError:
            continue
        teams.append({
            "rank": rank,
            "name": parts[1],
            "rating": int(parts[2]),
        })
    return teams


def get_our_rank(teams: list[dict]) -> tuple[int, str]:
    """Find our team in the ladder using --around."""
    out = subprocess.run(
        [CAMBC, "ladder", "--around"],
        capture_output=True, text=True, env={"COLUMNS": "200", "PATH": subprocess.os.environ["PATH"],
                                              "HOME": subprocess.os.environ["HOME"]}
    )
    # Parse our team name from status
    status_out = subprocess.run([CAMBC, "status"], capture_output=True, text=True)
    # Find our team name in status output
    our_name = None
    for line in status_out.stdout.split("\n"):
        if "Team:" in line:
            our_name = line.split("Team:")[1].strip()
            # Strip category suffix like "(main)" or "(novice)"
            if "(" in our_name:
                our_name = our_name[:our_name.index("(")].strip()
            break

    if our_name is None:
        print("Error: could not determine our team name from `cambc status`", file=sys.stderr)
        sys.exit(1)

    for t in teams:
        if t["name"] == our_name:
            return t["rank"], our_name

    # If not in the fetched list, parse --around output
    for line in out.stdout.strip().split("\n"):
        if not line.startswith("│"):
            continue
        parts = [p.strip() for p in line.split("│") if p.strip()]
        if len(parts) < 4:
            continue
        if parts[1] == our_name:
            try:
                return int(parts[0]), our_name
            except ValueError:
                pass

    print(f"Error: could not find our team '{our_name}' in ladder", file=sys.stderr)
    sys.exit(1)


def search_team_id(name: str) -> str | None:
    """Get team ID by exact name search."""
    out = subprocess.run(
        [CAMBC, "team", "search", name],
        capture_output=True, text=True, env={"COLUMNS": "200", "PATH": subprocess.os.environ["PATH"],
                                              "HOME": subprocess.os.environ["HOME"]}
    )
    for line in out.stdout.strip().split("\n"):
        if not line.startswith("│"):
            continue
        parts = [p.strip() for p in line.split("│") if p.strip()]
        if len(parts) >= 2 and parts[1] == name:
            return parts[0]
    return None


def queue_unrated(team_id: str) -> str | None:
    """Queue an unrated match, return match ID or None."""
    out = subprocess.run(
        [CAMBC, "match", "unrated", team_id],
        capture_output=True, text=True
    )
    if out.returncode != 0:
        return None
    for line in out.stdout.split("\n"):
        if "Match ID:" in line:
            return line.split("Match ID:")[1].strip()
    return None


def main():
    parser = argparse.ArgumentParser(description="Queue unrated matches against nearby opponents")
    parser.add_argument("-n", type=int, default=10, help="Number of opponents (default: 10)")
    parser.add_argument("--top", action="store_true", help="Challenge top N instead of N above us")
    args = parser.parse_args()

    n = args.n

    # Fetch enough of the ladder
    ladder = get_ladder(60)
    our_rank, our_name = get_our_rank(ladder)
    print(f"We are: {our_name} (rank {our_rank})")

    if args.top or our_rank <= n:
        # Top n+1 excluding us
        targets = [t for t in ladder if t["name"] != our_name][:n]
    else:
        # n teams directly above us
        above = [t for t in ladder if t["rank"] < our_rank]
        targets = above[-n:]  # last n = closest above

    print(f"Challenging {len(targets)} teams (ranks {targets[0]['rank']}-{targets[-1]['rank']}):\n")

    results = []
    for t in targets:
        team_id = search_team_id(t["name"])
        if team_id is None:
            print(f"  #{t['rank']:>2} {t['name']:<25} — SKIP (team not found)")
            continue
        match_id = queue_unrated(team_id)
        if match_id:
            print(f"  #{t['rank']:>2} {t['name']:<25} — queued ({match_id})")
            results.append({"rank": t["rank"], "name": t["name"], "match_id": match_id})
        else:
            print(f"  #{t['rank']:>2} {t['name']:<25} — FAILED")

    print(f"\n{len(results)}/{len(targets)} matches queued.")


if __name__ == "__main__":
    main()
