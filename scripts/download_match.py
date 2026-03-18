import json
import sys
import urllib.request
from pathlib import Path

from cambc.api import api_get
from cambc.auth import get_token

ROOT = Path(__file__).resolve().parent.parent


def download_match(match_id: str, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    token = get_token()
    data = api_get(f"/api/matches/{match_id}")
    m = data["match"]
    games = data.get("games", [])

    team_a = m.get("teamAName", "A").replace(" ", "_")
    team_b = m.get("teamBName", "B").replace(" ", "_")
    print(f"{team_a} vs {team_b}  ({m.get('scoreA', 0)}-{m.get('scoreB', 0)})")

    paths = []
    for g in games:
        game_num = g["gameNumber"]
        url = f"https://game.battlecode.cam/api/matches/replay?matchId={match_id}&game={game_num}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_data = json.loads(resp.read())

        s3_url = resp_data["url"]
        replay_data = urllib.request.urlopen(s3_url, timeout=60).read()
        filename = f"{team_a}_vs_{team_b}_g{game_num}.replay26"
        path = out_dir / filename
        path.write_bytes(replay_data)
        print(
            f"  Game {game_num}: {g.get('mapName', '?')} ({len(replay_data)} bytes) -> {filename}",
        )
        paths.append(path)

    return paths


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: download_match.py <match_id> [out_dir]")
        return
    match_id = sys.argv[1]
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "replays_remote"
    paths = download_match(match_id, out_dir)
    print(f"\nDownloaded {len(paths)} replays to {out_dir}")


if __name__ == "__main__":
    main()
