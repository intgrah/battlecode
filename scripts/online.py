import subprocess
import sys
from datetime import UTC, datetime


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout


def parse_matches(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    lines = text.strip().splitlines()
    for line in lines:
        if not line.startswith("│"):
            continue
        cells = [c.strip() for c in line.split("│")[1:-1]]
        if len(cells) < 6:
            continue
        match_id, team_a, score, team_b, status, date = cells
        if not match_id and rows:
            for k, v in [("team_a", team_a), ("team_b", team_b), ("date", date)]:
                if v:
                    rows[-1][k] = (rows[-1].get(k, "") + " " + v).strip()
            continue
        if not match_id:
            continue
        rows.append(
            {
                "match_id": match_id,
                "team_a": team_a,
                "team_b": team_b,
                "score": score,
                "status": status,
                "date": date,
            },
        )
    return rows


def parse_team_search(text: str) -> dict[str, tuple[str, int, int]]:
    results: dict[str, tuple[str, int, int]] = {}
    last_entry: list | None = None
    lines = text.strip().splitlines()
    for line in lines:
        if not line.startswith("│"):
            continue
        cells = [c.strip() for c in line.split("│")[1:-1]]
        if len(cells) < 6:
            continue
        team_id, name, _cat, rating, matches, _region = cells
        if not team_id:
            if last_entry and name:
                last_entry[1] = (last_entry[1] + " " + name).strip()
            continue
        if not rating.isdigit():
            continue
        last_entry = [team_id, name, int(rating), int(matches)]
        results[name] = (team_id, int(rating), int(matches))
    if last_entry and last_entry[1] not in results:
        results[last_entry[1]] = (last_entry[0], last_entry[2], last_entry[3])
    return results


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    text = run(["cambc", "matches", "--type", "unrated", "--limit", str(limit)])
    matches = parse_matches(text)

    seen: dict[str, str] = {}
    for m in matches:
        name = m["team_a"]
        if name not in seen:
            seen[name] = m["date"]

    if not seen:
        print("No recent unrated matches found.")
        return

    team_info: dict[str, tuple[int, int]] = {}
    for name in seen:
        query = name.rstrip("…")
        out = run(["cambc", "teams", "search", query])
        teams = parse_team_search(out)
        if name in teams:
            _, rating, match_count = teams[name]
            team_info[name] = (rating, match_count)
        elif name.endswith("…"):
            for tname, (_, rating, match_count) in teams.items():
                if tname.startswith(query):
                    team_info[name] = (rating, match_count)
                    break

    now = datetime.now(UTC)

    def fmt_ago(date_str: str) -> str:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
        delta = now - dt
        mins = int(delta.total_seconds() // 60)
        if mins < 1:
            return "just now"
        if mins < 60:
            return f"{mins}m ago"
        hours = mins // 60
        if hours < 24:
            return f"{hours}h {mins % 60}m ago"
        days = hours // 24
        return f"{days}d {hours % 24}h ago"

    print(f"{'Team':<25} {'Elo':>6} {'Matches':>8}  {'Last seen':>12}")
    print("-" * 60)
    for name, date in seen.items():
        ago = fmt_ago(date)
        if name in team_info:
            rating, match_count = team_info[name]
            print(f"{name:<25} {rating:>6} {match_count:>8}  {ago:>12}")
        else:
            print(f"{name:<25} {'?':>6} {'?':>8}  {ago:>12}")


if __name__ == "__main__":
    main()
