from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from cambc.api import api_get
from cambc.auth import get_token

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "replays_all"
INDEX_PATH = OUT_DIR / "index.json"

EXCLUDE_TEAMS = {"pyjail", "jailctf"}
CONCURRENCY = 20


def load_index() -> dict[str, dict]:
    if INDEX_PATH.exists():
        return json.loads(INDEX_PATH.read_text())
    return {}


def save_index(index: dict[str, dict]) -> None:
    INDEX_PATH.write_text(json.dumps(index, separators=(",", ":")))


def fetch_all_matches(since: str | None) -> list[dict]:
    matches = []
    cursor = None
    pages = 0
    while True:
        params: dict[str, str] = {"limit": "100"}
        if cursor:
            params["cursor"] = cursor
        data = api_get("/api/matches", params=params)
        batch = data.get("matches", [])
        for m in batch:
            if since and m.get("completedAt", "") <= since:
                return matches
            if m.get("status") != "complete":
                continue
            a = m.get("teamAName", "")
            b = m.get("teamBName", "")
            if a in EXCLUDE_TEAMS or b in EXCLUDE_TEAMS:
                continue
            matches.append(m)
        pages += 1
        cursor = data.get("nextCursor")
        if not cursor or not batch:
            break
        if pages % 20 == 0:
            print(f"  scanned {pages * 100} matches, {len(matches)} valid so far...")
    return matches


def download_game(
    token: str,
    match_id: str,
    game_num: int,
    out_path: Path,
) -> bool:
    url = f"https://game.battlecode.cam/api/matches/replay?matchId={match_id}&game={game_num}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            s3_url = json.loads(resp.read())["url"]
        data = urllib.request.urlopen(s3_url, timeout=60).read()
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as e:
        print(f"  FAILED {out_path.name}: {e}", file=sys.stderr)
        return False
    else:
        out_path.write_bytes(data)
        return True


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index = load_index()

    since = None
    if index:
        since = max(e["completedAt"] for e in index.values() if "completedAt" in e)
        print(f"Incremental mode: fetching matches after {since}")
    else:
        print("Full download: fetching all matches")

    print("Scanning matches...")
    matches = fetch_all_matches(since)
    print(f"Found {len(matches)} new matches")

    if not matches:
        print("Nothing to download.")
        return

    token_val = get_token()
    if token_val is None:
        print("No auth token found.")
        return
    token: str = token_val
    tasks: list[tuple[dict, int, Path]] = []
    for m in matches:
        mid = m["id"]
        score_a = m.get("scoreA", 0)
        score_b = m.get("scoreB", 0)
        total_games = score_a + score_b
        for g in range(1, total_games + 1):
            out_path = OUT_DIR / f"{mid}_g{g}.replay26"
            if out_path.exists():
                continue
            tasks.append((m, g, out_path))

    print(f"Downloading {len(tasks)} replays ({CONCURRENCY} threads)...")
    t0 = time.time()
    done = 0
    failed = 0

    def do_download(
        task: tuple[dict[str, str], int, Path],
    ) -> tuple[dict[str, str], int, bool]:
        m, g, out_path = task
        match_id: str = m["id"]
        ok = download_game(token, match_id, g, out_path)
        return m, g, ok

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = {pool.submit(do_download, t): t for t in tasks}
        for future in as_completed(futures):
            m, g, ok = future.result()
            if ok:
                done += 1
                key = f"{m['id']}_g{g}"
                index[key] = {
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
            total = done + failed
            elapsed = time.time() - t0
            rate = total / elapsed if elapsed > 0 else 0
            eta = (len(tasks) - total) / rate if rate > 0 else 0
            pct = total * 100 // len(tasks)
            bar = f"[{'#' * (pct // 2)}{'-' * (50 - pct // 2)}]"
            print(
                f"\r  {bar} {pct}%  {total}/{len(tasks)}  {rate:.0f}/s  ETA {eta:.0f}s  ({failed} fail)",
                end="",
                flush=True,
            )
            if total % 500 == 0:
                save_index(index)

    print()
    save_index(index)
    elapsed = time.time() - t0
    print(f"Done: {done} downloaded, {failed} failed in {elapsed:.0f}s")
    print(f"Index: {len(index)} total games in {INDEX_PATH}")


if __name__ == "__main__":
    main()
