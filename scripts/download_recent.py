"""Download the N most recently completed matches (all games in each).

Usage: uv run --no-project python scripts/download_recent.py [N] [--include-team name]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from cambc.api import api_get  # type: ignore[import-not-found]
from cambc.auth import get_token  # type: ignore[import-not-found]

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "replays_all"
INDEX_PATH = OUT_DIR / "index.json"
EXCLUDE_TEAMS = {"pyjail", "jailctf"}


def fetch_recent(n: int, require_team: str | None) -> list[dict]:
    matches: list[dict] = []
    cursor: str | None = None
    while len(matches) < n:
        params: dict[str, str] = {"limit": "50"}
        if cursor:
            params["cursor"] = cursor
        data = api_get("/api/matches", params=params)
        batch = data.get("matches", [])
        if not batch:
            break
        for m in batch:
            if m.get("status") != "complete":
                continue
            a = m.get("teamAName", "")
            b = m.get("teamBName", "")
            if a in EXCLUDE_TEAMS or b in EXCLUDE_TEAMS:
                continue
            if require_team is not None and require_team not in (a, b):
                continue
            matches.append(m)
            if len(matches) >= n:
                break
        cursor = data.get("nextCursor")
        if not cursor:
            break
    return matches


def download_game(token: str, match_id: str, game_num: int, out_path: Path) -> bool:
    url = f"https://game.battlecode.cam/api/matches/replay?matchId={match_id}&game={game_num}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            s3_url = json.loads(resp.read())["url"]
        data = urllib.request.urlopen(s3_url, timeout=60).read()
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as e:
        print(f"  FAILED {out_path.name}: {e}", file=sys.stderr)
        return False
    out_path.write_bytes(data)
    return True


def load_index() -> dict:
    if INDEX_PATH.exists():
        return json.loads(INDEX_PATH.read_text())
    return {}


def save_index(index: dict) -> None:
    INDEX_PATH.write_text(json.dumps(index, separators=(",", ":")))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("n", type=int, nargs="?", default=20, help="number of recent matches")
    ap.add_argument("--include-team", default=None, help="only matches involving this team")
    ap.add_argument("-j", type=int, default=20)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index = load_index()

    matches = fetch_recent(args.n, args.include_team)
    print(f"selected {len(matches)} matches")
    for m in matches[:5]:
        print(f"  {m.get('completedAt','?')}  {m.get('teamAName','?')} {m.get('scoreA',0)}-{m.get('scoreB',0)} {m.get('teamBName','?')}")
    if len(matches) > 5:
        print(f"  ... and {len(matches) - 5} more")

    token = get_token()
    if token is None:
        print("No auth token")
        sys.exit(1)

    tasks: list[tuple[dict, int, Path]] = []
    for m in matches:
        total = (m.get("scoreA", 0) or 0) + (m.get("scoreB", 0) or 0)
        for g in range(1, total + 1):
            out = OUT_DIR / f"{m['id']}_g{g}.replay26"
            if out.exists():
                continue
            tasks.append((m, g, out))
    print(f"downloading {len(tasks)} replays")

    done = failed = 0
    with ThreadPoolExecutor(max_workers=args.j) as pool:
        futures = {pool.submit(download_game, token, m["id"], g, p): (m, g) for (m, g, p) in tasks}
        for fut in as_completed(futures):
            m, g = futures[fut]
            ok = fut.result()
            if ok:
                done += 1
                index[f"{m['id']}_g{g}"] = {
                    "matchId": m["id"],
                    "game": g,
                    "teamA": m.get("teamAName", ""),
                    "teamB": m.get("teamBName", ""),
                    "scoreA": m.get("scoreA", 0),
                    "scoreB": m.get("scoreB", 0),
                    "completedAt": m.get("completedAt", ""),
                }
            else:
                failed += 1
    save_index(index)
    print(f"done={done} failed={failed}")


if __name__ == "__main__":
    main()
