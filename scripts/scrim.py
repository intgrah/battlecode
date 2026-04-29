"""Auto-scrim driver: continuously queues unrated matches against a curated
list of opponents, attributes every match (ladder + unrated) to a specific
submission version, and shares state across teammates via a dedicated git
branch.

============================================================================
HOW IT WORKS
============================================================================

1. Tracked opponents
--------------------
A small SQLite DB at `scripts/scrim.db` stores the team_ids we care about
(`opponents` table). Manage them with:

    scrim ladder --region uk --limit 20    # browse, copy team_ids
    scrim add <team_id> [--name LABEL]
    scrim remove <team_id>
    scrim list

We picked a curated set: top-N UK teams within ±200 rating (qualifier
prep) plus international teams within +200 of us (calibration). Avoid
auto-add — it's noisy.

2. Submitting matches
---------------------
    scrim run --forever --async

Loops indefinitely, in each iteration:
  - sync /api/matches and /api/submissions to refresh local DB
  - pick the opponent we've queued least recently (oldest `requested_at`
    in the `matches` table)
  - pick 5 maps least-recently-queued against that opponent (using both
    completed games and in-flight `map_names` so we don't re-queue the
    same maps before the previous match completes)
  - block until we have a free slot in the rate-limit window:
      ** Server enforces 5 unrated requests per 10 minutes PER USER **
      (not per opponent, not per team — confirmed via 429). Teammates
      each have their own slot.
  - POST /api/matches/unrated with opponentTeamId + 5 maps; record the
    `match_id` immediately (status='requested')
  - move on (`--async` skips waiting for completion; `poll` later updates)

The unrated endpoint plays whichever submission is currently `isActive`
on the ladder for both teams — we never specify a version. Match results
record `teamAVersion` / `teamBVersion` server-side so attribution stays
correct even after we upload a newer build.

3. Submitting bots
------------------
    scrim submit <bot_path> [-n NAME]

Wraps `cambc submission upload`. By default the submission's `name` is
set to `<bot_path> (<git_short_sha>)` (e.g. `intgrah/v54.7.9 (bb45e58)`)
so any submission can be traced back to source. After upload we re-sync
so `status --bot intgrah/v54.7.9` immediately works.

4. Reading results
------------------
    scrim status                            # all opponents, all versions
    scrim status --bot intgrah/v54.7.9      # filter by submission name
    scrim status --version 196              # filter by version number
    scrim status --team <team_id>           # one opponent
    scrim status --by-map                   # per-map breakdown (lazy-fetches games)
    scrim queued                            # in-flight matches (status != complete/error)

Match-level W/L is derived from `score_a` / `score_b` directly — no extra
API calls. Per-map breakdown lazy-fetches `/api/matches/<id>` to populate
the `games` table only for matches in scope.

5. Coordinating with teammates
------------------------------
The shared scrim DB lives on an orphan `scrim-db` branch at origin (no
shared history with master, only `scrim.db`). Push/pull goes through git
plumbing (`hash-object` / `commit-tree` / `update-ref`) so neither
operation checks out anything or touches the master working tree:

    scrim pull-state    # fetch origin/scrim-db, overwrite local scrim.db,
                        # then sync from /api to recover any new local
                        # state (idempotent)
    scrim push-state    # snapshot local scrim.db to origin/scrim-db

Suggested flow when running concurrently: pull-state → run-batch →
push-state. The map picker reads in-flight `map_names` rows so a
teammate's recent submissions feed into our next picks (no duplicate
maps queued).

6. Match attribution
--------------------
Every match in the `matches` table carries:
    our_version, their_version, triggered_by ('ladder' | 'unrated'),
    our_side ('A' | 'B'), team_b_id/name, our_rating_before, elo_delta
plus the raw API blob. So historical W/L queries by version work after
arbitrarily many submissions.

============================================================================
SUBCOMMAND REFERENCE
============================================================================

  add <team_id> [--name LABEL]              track an opponent
  remove <team_id>                          stop tracking
  list                                      show tracked
  ladder [--region] [--category] [--limit] [--around]
                                            print ladder w/ team_ids
  search <query>                            cambc team search

  submit <bot> [-n NAME]                    upload (auto-named with git sha)
  sync [--full]                             pull subs + matches from API

  run [--team T] [--rounds N | --forever] [--maps M] [--async]
                                            submit unrated matches
  queued                                    show in-flight requests
  poll                                      refresh stale 'requested' rows

  status [--team T] [--bot N | --version V] [--by-map]
                                            W/L summary

  pull-state                                pull shared scrim.db (orphan branch)
  push-state                                push local scrim.db (orphan branch)

  replays <match_id> [--out DIR]            download replay files
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import subprocess
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from shutil import which
from typing import Any

from cambc.api import api_get, api_post
from cambc.auth import get_api_url, get_token, load_credentials

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "scripts" / "scrim.db"
MAPS_DIR = ROOT / "maps"
POLL_INTERVAL_S = 5
POLL_TIMEOUT_S = 600
# Server-side limit on `/api/matches/unrated`: at most
# `RATE_LIMIT_MAX_REQUESTS` requests per `RATE_LIMIT_WINDOW_S` per *user*
# (not per opponent, not per team — confirmed via 429 message
# "max 5 test/unrated matches per 10 minutes"). One match request bundles
# up to 5 maps (= 5 games). With 4 teammates each having their own
# 5-per-10-min slot, a 5-person team can fire 25 requests = 125 games per
# 10 min collectively if they coordinate via the shared scrim-db branch.
RATE_LIMIT_MAX_REQUESTS = 5
RATE_LIMIT_WINDOW_S = 600

# Branch on `origin` storing the shared scrim.db snapshot. Orphan branch
# (no shared history with master) — push/pull goes through git plumbing
# (`hash-object` / `commit-tree` / `update-ref`) so neither operation
# checks out anything or touches the master working tree.
SCRIM_DB_BRANCH = "scrim-db"
SCRIM_DB_FILENAME_IN_BRANCH = "scrim.db"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _our_team_id() -> str:
    creds = load_credentials()
    if not creds or not creds.get("team"):
        msg = "not logged in or no team — run `cambc login`"
        raise SystemExit(msg)
    return creds["team"]["id"]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS opponents (
            team_id    TEXT PRIMARY KEY,
            team_name  TEXT,
            added_at   TEXT
        );
        CREATE TABLE IF NOT EXISTS matches (
            match_id      TEXT PRIMARY KEY,
            team_id       TEXT NOT NULL,
            map_names     TEXT,
            requested_at  TEXT,
            completed_at  TEXT,
            score_a       INTEGER,
            score_b       INTEGER,
            status        TEXT,
            raw           TEXT
        );
        CREATE TABLE IF NOT EXISTS games (
            match_id        TEXT NOT NULL,
            game_number     INTEGER NOT NULL,
            map_name        TEXT,
            winner          TEXT,
            win_condition   TEXT,
            turns           INTEGER,
            PRIMARY KEY (match_id, game_number)
        );
        CREATE TABLE IF NOT EXISTS submissions (
            version       INTEGER PRIMARY KEY,
            submission_id TEXT UNIQUE,
            name          TEXT,
            uploaded_at   TEXT,
            is_active     INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS matches_team_idx ON matches(team_id);
        CREATE INDEX IF NOT EXISTS games_match_idx ON games(match_id);
        """,
    )
    # Additive columns on matches — `ADD COLUMN IF NOT EXISTS` is sqlite 3.35+
    # but we use the older "introspect first" pattern for portability.
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(matches)")}
    for col, ddl in (
        ("our_version", "INTEGER"),
        ("their_version", "INTEGER"),
        ("triggered_by", "TEXT"),
        ("our_side", "TEXT"),
        ("team_a_id", "TEXT"),
        ("team_b_id", "TEXT"),
        ("team_b_name", "TEXT"),
        ("our_rating_before", "REAL"),
        ("elo_delta", "REAL"),
    ):
        if col not in existing:
            conn.execute(f"ALTER TABLE matches ADD COLUMN {col} {ddl}")
    # Now that the column exists, create its index.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS matches_version_idx "
        "ON matches(our_version) WHERE our_version IS NOT NULL",
    )
    conn.commit()


def _all_maps() -> list[str]:
    return sorted(p.stem for p in MAPS_DIR.glob("*.map26"))


def _pick_maps_for_opponent(
    conn: sqlite3.Connection, team_id: str, n: int = 5
) -> list[str]:
    """Pick `n` maps for a fresh match — least-recently-played wins ties.

    "Recently played" includes in-flight requested matches whose `games`
    rows don't exist yet — otherwise after submitting match X the rate
    limit expires 10 min later and we'd happily pick the same 5 maps
    again before X has had a chance to complete and populate `games`.
    """
    pool = _all_maps()
    if not pool:
        msg = f"No maps in {MAPS_DIR}"
        raise RuntimeError(msg)
    last_played: dict[str, str] = {}
    # Completed matches via the games table (gives accurate per-map history).
    for r in conn.execute(
        """
        SELECT g.map_name, MAX(m.requested_at) AS last_played
        FROM games g JOIN matches m ON g.match_id = m.match_id
        WHERE m.team_id = ?
        GROUP BY g.map_name
        """,
        (team_id,),
    ):
        last_played[r["map_name"]] = max(
            last_played.get(r["map_name"], ""), r["last_played"] or ""
        )
    # In-flight or unsynced matches via the requested-time map_names column.
    for r in conn.execute(
        """
        SELECT map_names, requested_at FROM matches
        WHERE team_id = ? AND map_names IS NOT NULL AND requested_at IS NOT NULL
        """,
        (team_id,),
    ):
        try:
            for mn in json.loads(r["map_names"]):
                last_played[mn] = max(last_played.get(mn, ""), r["requested_at"] or "")
        except (json.JSONDecodeError, TypeError):
            continue
    random.shuffle(pool)
    pool.sort(key=lambda m: last_played.get(m, ""))
    return pool[:n]


def _wait_for_rate_slot(conn: sqlite3.Connection) -> None:
    """Block until we have a free slot in the global rate-limit window
    (RATE_LIMIT_MAX_REQUESTS requests per RATE_LIMIT_WINDOW_S, server-side
    enforced per-USER not per-opponent — confirmed via 429 response).
    Reads our local DB only; the `cmd_run` outer loop must `sync` first
    so other-teammate submissions are visible (they push to scrim-db; we
    pull). Local DB lacks rows submitted by teammates without a recent
    push — those will hit the server-side 429 and `cmd_run` retries on
    backoff.
    """
    while True:
        cutoff = datetime.now(UTC).timestamp() - RATE_LIMIT_WINDOW_S
        rows = conn.execute(
            """
            SELECT requested_at FROM matches
            WHERE triggered_by = 'unrated' AND requested_at IS NOT NULL
            ORDER BY requested_at DESC
            LIMIT ?
            """,
            (RATE_LIMIT_MAX_REQUESTS,),
        ).fetchall()
        recent = [
            r["requested_at"]
            for r in rows
            if datetime.fromisoformat(r["requested_at"]).timestamp() > cutoff
        ]
        if len(recent) < RATE_LIMIT_MAX_REQUESTS:
            return
        oldest = datetime.fromisoformat(recent[-1])
        wait_s = (
            int(RATE_LIMIT_WINDOW_S - (datetime.now(UTC) - oldest).total_seconds()) + 2
        )
        print(
            f"  rate limit: {len(recent)}/{RATE_LIMIT_MAX_REQUESTS} requests "
            f"in last {RATE_LIMIT_WINDOW_S}s; sleeping {wait_s}s",
        )
        time.sleep(min(wait_s, 30))


def _request_unrated(team_id: str, maps: list[str]) -> str:
    body: dict[str, Any] = {"opponentTeamId": team_id}
    if maps:
        body["mapNames"] = maps[:5]
    data = api_post("/api/matches/unrated", body)
    match_id = data.get("matchId")
    if not match_id:
        msg = f"no matchId in response: {data}"
        raise RuntimeError(msg)
    return match_id


def _upsert_match_row(
    conn: sqlite3.Connection, m: dict[str, Any], our_team_id: str
) -> None:
    """Insert/update a row in `matches` from an API match payload (the same
    shape returned by both `/api/matches` and `/api/matches/<id>['match']`)."""
    if m.get("teamAId") == our_team_id:
        our_side = "A"
        opp_id = m.get("teamBId")
        opp_name = m.get("teamBName")
        our_version = m.get("teamAVersion")
        their_version = m.get("teamBVersion")
        our_rating_before = m.get("ratingABefore")
        elo_delta = m.get("eloDeltaA")
    elif m.get("teamBId") == our_team_id:
        our_side = "B"
        opp_id = m.get("teamAId")
        opp_name = m.get("teamAName")
        our_version = m.get("teamBVersion")
        their_version = m.get("teamAVersion")
        our_rating_before = m.get("ratingBBefore")
        elo_delta = m.get("eloDeltaB")
    else:
        # Match doesn't involve us — skip.
        return
    conn.execute(
        """
        INSERT INTO matches (
            match_id, team_id, status, requested_at, completed_at,
            score_a, score_b, our_side, our_version, their_version,
            triggered_by, team_a_id, team_b_id, team_b_name,
            our_rating_before, elo_delta, raw
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(match_id) DO UPDATE SET
            status = excluded.status,
            completed_at = excluded.completed_at,
            score_a = excluded.score_a,
            score_b = excluded.score_b,
            our_side = excluded.our_side,
            our_version = excluded.our_version,
            their_version = excluded.their_version,
            triggered_by = excluded.triggered_by,
            team_a_id = excluded.team_a_id,
            team_b_id = excluded.team_b_id,
            team_b_name = excluded.team_b_name,
            our_rating_before = excluded.our_rating_before,
            elo_delta = excluded.elo_delta,
            raw = excluded.raw
        """,
        (
            m["id"],
            opp_id,
            m.get("status"),
            m.get("createdAt"),
            m.get("completedAt"),
            m.get("scoreA"),
            m.get("scoreB"),
            our_side,
            our_version,
            their_version,
            m.get("triggeredBy"),
            m.get("teamAId"),
            m.get("teamBId"),
            opp_name,
            our_rating_before,
            elo_delta,
            json.dumps(m),
        ),
    )


def _record_match_request(
    conn: sqlite3.Connection,
    match_id: str,
    team_id: str,
    maps: list[str],
) -> None:
    """Stub row for a freshly-requested match. `sync` will fill in the rest
    once the platform processes it."""
    conn.execute(
        """
        INSERT OR IGNORE INTO matches
        (match_id, team_id, map_names, requested_at, status, triggered_by)
        VALUES (?, ?, ?, ?, 'requested', 'unrated')
        """,
        (match_id, team_id, json.dumps(maps), _now_iso()),
    )
    conn.commit()


def _fetch_and_store_match(conn: sqlite3.Connection, match_id: str) -> dict:
    """Fetch /api/matches/<id> and update both the match row + games."""
    data = api_get(f"/api/matches/{match_id}")
    m = data.get("match", {}) or {}
    games = data.get("games", []) or []
    our_team_id = _our_team_id()
    if m.get("id"):
        _upsert_match_row(conn, m, our_team_id)
    for g in games:
        conn.execute(
            """
            INSERT OR REPLACE INTO games
            (match_id, game_number, map_name, winner, win_condition, turns)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                match_id,
                g.get("gameNumber"),
                g.get("mapName"),
                g.get("winner"),
                g.get("winCondition"),
                g.get("turns"),
            ),
        )
    conn.commit()
    return data


def _wait_for_match(conn: sqlite3.Connection, match_id: str) -> dict:
    """Block until match completes (or POLL_TIMEOUT_S)."""
    start = time.time()
    while True:
        data = _fetch_and_store_match(conn, match_id)
        m = data.get("match", {})
        status = m.get("status", "?")
        stage = m.get("stage", "")
        if status in {"complete", "error"}:
            return data
        if time.time() - start > POLL_TIMEOUT_S:
            print(
                f"timeout waiting for {match_id} (last status={status} stage={stage})"
            )
            return data
        print(f"  {match_id}: {status} {stage}", end="\r", flush=True)
        time.sleep(POLL_INTERVAL_S)


# ---------- sync (submissions + recent matches) ----------


def _sync_submissions(conn: sqlite3.Connection) -> int:
    data = api_get("/api/submissions")
    subs = data.get("submissions", data) if isinstance(data, dict) else data
    n = 0
    for s in subs:
        conn.execute(
            """
            INSERT INTO submissions (version, submission_id, name, uploaded_at, is_active)
            VALUES (?,?,?,?,?)
            ON CONFLICT(version) DO UPDATE SET
                submission_id = excluded.submission_id,
                name = excluded.name,
                uploaded_at = excluded.uploaded_at,
                is_active = excluded.is_active
            """,
            (
                s.get("version"),
                s.get("id"),
                s.get("name"),
                s.get("uploadedAt"),
                1 if s.get("isActive") else 0,
            ),
        )
        n += 1
    conn.commit()
    return n


def _sync_matches(
    conn: sqlite3.Connection,
    page_size: int = 100,
    max_pages: int = 500,
    full: bool = False,
) -> tuple[int, int]:
    """Walk /api/matches in reverse-chron order until we hit a match_id we
    already have in DB (incremental sync). Returns (new, updated)."""
    our_team_id = _our_team_id()
    cursor: str | None = None
    new = updated = 0
    # Track consecutive all-existing pages to decide when to stop. A single
    # all-existing page isn't enough — the first sync may have been
    # truncated by `max_pages`, leaving a gap of older unseen rows after a
    # block of fresh ones. After N consecutive all-existing pages we
    # assume the tail is fully covered.
    EXISTING_PAGE_STREAK_TO_EXIT = 5
    consecutive_all_existing = 0
    for _ in range(max_pages):
        params: dict[str, Any] = {"teamIds": our_team_id, "limit": str(page_size)}
        if cursor:
            params["cursor"] = cursor
        data = api_get("/api/matches", params)
        matches = data.get("matches", []) or []
        if not matches:
            break
        page_new = 0
        for m in matches:
            mid = m.get("id")
            if not mid:
                continue
            existed = conn.execute(
                "SELECT 1 FROM matches WHERE match_id = ?",
                (mid,),
            ).fetchone()
            _upsert_match_row(conn, m, our_team_id)
            if existed:
                updated += 1
            else:
                new += 1
                page_new += 1
        conn.commit()
        cursor = data.get("nextCursor") or data.get("cursor")
        if not cursor:
            break
        if full:
            continue
        if page_new == 0:
            consecutive_all_existing += 1
            if consecutive_all_existing >= EXISTING_PAGE_STREAK_TO_EXIT:
                break
        else:
            consecutive_all_existing = 0
    return new, updated


def cmd_sync(args: argparse.Namespace) -> None:
    with _connect() as conn:
        n_subs = _sync_submissions(conn)
        new, updated = _sync_matches(conn, full=args.full)
        print(f"submissions: {n_subs} synced")
        print(
            f"matches: {new} new, {updated} updated{' (full walk)' if args.full else ''}"
        )


# ---------- subcommands ----------


def cmd_add(args: argparse.Namespace) -> None:
    name = args.name or args.team_id
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO opponents (team_id, team_name, added_at) VALUES (?, ?, ?)",
            (args.team_id, name, _now_iso()),
        )
    print(f"added: {args.team_id} ({name})")


def cmd_ladder(args: argparse.Namespace) -> None:
    """Print ladder rankings with team_ids ready to copy into `add`. Read-only
    — pick opponents manually rather than adding by rating heuristic alone."""
    our_team_id = _our_team_id()
    me_data = api_get(f"/api/teams/{our_team_id}")
    our_rating = me_data.get("rating", {}).get("rating") or 0
    data = api_get("/api/ladder")
    rankings = data if isinstance(data, list) else data.get("rankings", []) or []
    rows = []
    for i, r in enumerate(rankings, 1):
        if args.region and r.get("region") != args.region:
            continue
        if args.category and r.get("category") != args.category:
            continue
        if not args.include_banned and r.get("ladderBanned"):
            continue
        rows.append((i, r))
    if args.around is not None:
        # Find our position in filtered list, take ±around.
        our_idx = next(
            (idx for idx, (_, r) in enumerate(rows) if r["teamId"] == our_team_id), None
        )
        if our_idx is not None:
            lo = max(0, our_idx - args.around)
            hi = min(len(rows), our_idx + args.around + 1)
            rows = rows[lo:hi]
    rows = rows[: args.limit]
    print(
        f"our rating: {our_rating:.0f}    region={args.region or 'all'}  category={args.category or 'all'}"
    )
    print(f"  {'#':>3}  {'team':<35} {'rating':>6}  {'Δ':>6}  region   team_id")
    for rank, r in rows:
        rating = r.get("rating") or 0
        flag = " *" if r["teamId"] == our_team_id else "  "
        print(
            f"  {rank:>3}  {r.get('teamName', '?'):<35} {rating:>6.0f}  "
            f"{rating - our_rating:+6.0f}  {r.get('region', '?'):<8} {r['teamId']}{flag}",
        )


def cmd_remove(args: argparse.Namespace) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM opponents WHERE team_id = ?", (args.team_id,))
    print(f"removed: {args.team_id}")


def cmd_list(_args: argparse.Namespace) -> None:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT team_id, team_name, added_at FROM opponents ORDER BY added_at",
        ).fetchall()
    if not rows:
        print("no tracked opponents — use `add <team_id>` or `add-top`")
        return
    for r in rows:
        print(f"  {r['team_id']}  {r['team_name']}")


def _cambc_bin() -> str:
    """Locate the `cambc` CLI executable. Prefer one on PATH; fall back to
    the well-known cambc venv since this script is typically invoked
    through that interpreter and `subprocess` won't see venv-local
    binaries unless they're on PATH."""

    found = which("cambc")
    if found:
        return found
    candidate = Path.home() / "Code" / "venvs" / "cambc" / "bin" / "cambc"
    if candidate.exists():
        return str(candidate)
    msg = "`cambc` CLI not found on PATH or in ~/Code/venvs/cambc/bin/"
    raise SystemExit(msg)


def cmd_search(args: argparse.Namespace) -> None:
    subprocess.run([_cambc_bin(), "team", "search", args.query], check=False)


def cmd_submit(args: argparse.Namespace) -> None:
    """Wrap `cambc submission upload` so the submission's `name` field is
    set to a reproducible identifier — defaults to `<bot_path> (<git_sha>)`,
    e.g. `intgrah/v54.7.9 (bb45e58)`. The git short sha lets you trace any
    submission back to the exact source it was built from. Pass `--name`
    to override.

    `bot` accepts either an absolute path, a path relative to cwd, or a
    short `owner/name` form resolved under `bots/`."""
    bot_arg = args.bot
    bot_path = Path(bot_arg)
    if not bot_path.exists():
        candidate = ROOT / "bots" / bot_arg
        if candidate.exists():
            bot_path = candidate
        else:
            msg = f"bot path not found: {bot_arg} (also tried {candidate})"
            raise SystemExit(msg)
    if args.name:
        name = args.name
    else:
        sha = _git("rev-parse", "--short", "HEAD", check=False) or "?"
        dirty = _git("status", "--porcelain", check=False)
        name = f"{bot_arg} ({sha}{'+dirty' if dirty else ''})"
    cmd = [_cambc_bin(), "submission", "upload", str(bot_path), "-n", name]
    print(f"$ {' '.join(cmd)}")
    rc = subprocess.run(cmd, check=False).returncode
    if rc != 0:
        raise SystemExit(rc)
    with _connect() as conn:
        n = _sync_submissions(conn)
        print(f"submissions synced ({n} entries)")


def cmd_run(args: argparse.Namespace) -> None:
    rounds_left = args.rounds if not args.forever else None
    while rounds_left is None or rounds_left > 0:
        with _connect() as conn:
            # Refresh statuses so completed matches stop blocking the
            # rate-limit gate and so map-picker sees real history.
            try:
                _sync_matches(conn)
            except Exception as e:
                print(f"  sync failed (continuing with stale data): {e}")
            if args.team:
                opponents = [args.team]
            else:
                # Order by least-recently-queued first (NULLs — never
                # played — sort earliest). This way `--forever` cycles
                # through opponents, prioritizing ones we haven't touched.
                opponents = [
                    r["team_id"]
                    for r in conn.execute(
                        """
                        SELECT o.team_id,
                               (SELECT MAX(m.requested_at) FROM matches m
                                WHERE m.team_id = o.team_id
                                  AND m.triggered_by = 'unrated') AS last_q
                        FROM opponents o
                        ORDER BY last_q IS NULL DESC, last_q ASC
                        """,
                    ).fetchall()
                ]
            if not opponents:
                print("no opponents; use `add <team_id>`, `add-top`, or pass --team")
                return
            for team_id in opponents:
                maps = (
                    args.maps.split(",")
                    if args.maps
                    else _pick_maps_for_opponent(conn, team_id)
                )
                tag = (
                    "forever"
                    if args.forever
                    else f"round {args.rounds - rounds_left + 1}/{args.rounds}"
                )
                print(f"[{tag}] {team_id}  maps={maps}")
                _wait_for_rate_slot(conn)
                try:
                    match_id = _request_unrated(team_id, maps)
                except (Exception, SystemExit) as e:
                    # api_post raises SystemExit(1) on HTTP 429; treat any
                    # request failure as transient and back off briefly so
                    # we don't tight-loop on a server-side rate-limit.
                    print(f"  request failed: {e}")
                    time.sleep(15)
                    continue
                _record_match_request(conn, match_id, team_id, maps)
                print(f"  match_id={match_id}")
                if not args.async_:
                    data = _wait_for_match(conn, match_id)
                    m = data.get("match", {})
                    print(
                        f"  -> {m.get('status', '?')}  "
                        f"{m.get('scoreA', 0)}-{m.get('scoreB', 0)}",
                    )
        if rounds_left is not None:
            rounds_left -= 1


def cmd_poll(_args: argparse.Namespace) -> None:
    with _connect() as conn:
        pending = conn.execute(
            "SELECT match_id FROM matches WHERE status NOT IN ('complete', 'error') OR status IS NULL",
        ).fetchall()
        if not pending:
            print("no pending matches")
            return
        for r in pending:
            mid = r["match_id"]
            data = _fetch_and_store_match(conn, mid)
            m = data.get("match", {})
            print(
                f"  {mid}: {m.get('status', '?')}  "
                f"{m.get('scoreA', 0)}-{m.get('scoreB', 0)}",
            )


def _resolve_version_filter(
    conn: sqlite3.Connection,
    bot: str | None,
    version: int | None,
) -> tuple[int | None, str]:
    """Return (version_int, label) given either --bot NAME or --version V."""
    if version is not None:
        row = conn.execute(
            "SELECT name FROM submissions WHERE version = ?",
            (version,),
        ).fetchone()
        return version, f"v{version} ({row['name'] if row and row['name'] else '—'})"
    if bot is not None:
        row = conn.execute(
            "SELECT version, name FROM submissions WHERE name = ? "
            "ORDER BY version DESC LIMIT 1",
            (bot,),
        ).fetchone()
        if not row:
            msg = f"no submission named {bot!r} (run `scrim sync` first)"
            raise SystemExit(msg)
        return int(row["version"]), f"v{row['version']} ({bot})"
    return None, "all versions"


def _summarise_team(
    conn: sqlite3.Connection,
    team_id: str,
    version_filter: int | None,
    by_map: bool = False,
) -> None:
    name_row = conn.execute(
        "SELECT team_name FROM opponents WHERE team_id = ?",
        (team_id,),
    ).fetchone()
    name = name_row["team_name"] if name_row else team_id
    where = "m.team_id = ? AND m.status = 'complete'"
    params: list[Any] = [team_id]
    if version_filter is not None:
        where += " AND m.our_version = ?"
        params.append(version_filter)

    if by_map:
        # Per-game per-map view requires the `games` table populated. We
        # don't bulk-pull games (would be 1 API call per match); fetch
        # missing ones on demand for the matches in scope.
        missing = conn.execute(
            f"SELECT m.match_id FROM matches m WHERE {where} "
            f"AND NOT EXISTS (SELECT 1 FROM games g WHERE g.match_id = m.match_id)",
            params,
        ).fetchall()
        if missing:
            print(f"  fetching games for {len(missing)} matches...")
            for r in missing:
                _fetch_and_store_match(conn, r["match_id"])
        rows = conn.execute(
            f"""
            SELECT g.map_name, g.winner, m.our_side, COUNT(*) AS n
            FROM games g JOIN matches m ON g.match_id = m.match_id
            WHERE {where}
            GROUP BY g.map_name, g.winner, m.our_side
            """,
            params,
        ).fetchall()
        if not rows:
            print(f"\n{name}  ({team_id}): no completed games")
            return
        by: dict[str, dict[str, int]] = {}
        for r in rows:
            bucket = by.setdefault(r["map_name"] or "?", {"w": 0, "l": 0, "d": 0})
            winner = r["winner"]
            side = r["our_side"]
            if winner == "draw" or winner is None:
                bucket["d"] += r["n"]
            elif (winner == "a" and side == "A") or (winner == "b" and side == "B"):
                bucket["w"] += r["n"]
            else:
                bucket["l"] += r["n"]
        total_w = total_l = total_d = 0
        print(f"\n{name}  ({team_id})")
        print(f"  {'map':<30} {'W':>3} {'L':>3} {'D':>3}")
        for m in sorted(by):
            b = by[m]
            total_w += b["w"]
            total_l += b["l"]
            total_d += b["d"]
            print(f"  {m:<30} {b['w']:>3} {b['l']:>3} {b['d']:>3}")
        total = total_w + total_l + total_d
        pct = (100.0 * total_w / total) if total else 0.0
        print(
            f"  {'TOTAL':<30} {total_w:>3} {total_l:>3} {total_d:>3}   ({pct:.0f}% W)"
        )
        return

    # Match-level summary — derive W/L from score_a/b directly. No games
    # fetch required; works for any match that has completed.
    rows = conn.execute(
        f"""
        SELECT m.score_a, m.score_b, m.our_side, m.triggered_by, COUNT(*) AS n
        FROM matches m
        WHERE {where}
          AND m.score_a IS NOT NULL AND m.score_b IS NOT NULL
        GROUP BY m.our_side, m.triggered_by,
                 CASE
                     WHEN m.score_a > m.score_b THEN 'a'
                     WHEN m.score_b > m.score_a THEN 'b'
                     ELSE 'd'
                 END,
                 m.score_a, m.score_b
        """,
        params,
    ).fetchall()
    if not rows:
        print(f"\n{name}  ({team_id}): no completed matches")
        return
    by_trigger: dict[str, dict[str, int]] = {}
    for r in rows:
        side = r["our_side"]
        a, b = r["score_a"], r["score_b"]
        bucket = by_trigger.setdefault(
            r["triggered_by"] or "?", {"w": 0, "l": 0, "d": 0}
        )
        n = r["n"]
        if a == b:
            bucket["d"] += n
        elif (a > b and side == "A") or (b > a and side == "B"):
            bucket["w"] += n
        else:
            bucket["l"] += n
    print(f"\n{name}  ({team_id})")
    print(f"  {'kind':<10} {'W':>3} {'L':>3} {'D':>3}")
    total_w = total_l = total_d = 0
    for kind in sorted(by_trigger):
        b = by_trigger[kind]
        total_w += b["w"]
        total_l += b["l"]
        total_d += b["d"]
        print(f"  {kind:<10} {b['w']:>3} {b['l']:>3} {b['d']:>3}")
    total = total_w + total_l + total_d
    pct = (100.0 * total_w / total) if total else 0.0
    print(f"  {'TOTAL':<10} {total_w:>3} {total_l:>3} {total_d:>3}   ({pct:.0f}% W)")


def cmd_status(args: argparse.Namespace) -> None:
    with _connect() as conn:
        version_filter, label = _resolve_version_filter(conn, args.bot, args.version)
        print(f"filter: {label}")
        if args.team:
            _summarise_team(conn, args.team, version_filter, by_map=args.by_map)
            return
        rows = conn.execute("SELECT team_id FROM opponents").fetchall()
        if not rows:
            print("no tracked opponents")
            return
        for r in rows:
            _summarise_team(conn, r["team_id"], version_filter, by_map=args.by_map)


def _git(*args: str, capture: bool = True, check: bool = True) -> str:
    res = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=capture,
        text=True,
        check=False,
    )
    if check and res.returncode != 0:
        msg = f"git {' '.join(args)} failed (rc={res.returncode}): {res.stderr.strip()}"
        raise RuntimeError(
            msg,
        )
    return res.stdout.strip()


def _remote_db_blob_sha() -> str | None:
    """Return the blob sha of `scrim.db` on `origin/scrim-db`, or None if
    the branch doesn't exist remotely."""
    _git("fetch", "origin", SCRIM_DB_BRANCH, check=False)
    out = _git(
        "rev-parse",
        "--verify",
        f"origin/{SCRIM_DB_BRANCH}:{SCRIM_DB_FILENAME_IN_BRANCH}",
        check=False,
    )
    return out or None


def _write_blob_to(sha: str, dest: Path) -> None:
    """Stream `git cat-file blob <sha>` into `dest` atomically."""
    res = subprocess.run(
        ["git", "cat-file", "blob", sha],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(res.stdout)
    tmp.replace(dest)


def cmd_pull_state(_args: argparse.Namespace) -> None:
    """Overwrite local scrim.db with origin/scrim-db's snapshot, then re-sync
    from /api so any locally-known-only state is rebuilt from API truth."""
    sha = _remote_db_blob_sha()
    if not sha:
        print(
            f"origin/{SCRIM_DB_BRANCH} has no {SCRIM_DB_FILENAME_IN_BRANCH} — nothing to pull"
        )
        return
    _write_blob_to(sha, DB_PATH)
    print(f"pulled scrim.db (blob {sha[:10]})")
    with _connect() as conn:
        n_subs = _sync_submissions(conn)
        new, updated = _sync_matches(conn)
        print(f"  resync: submissions={n_subs}  matches: {new} new, {updated} updated")


def cmd_push_state(_args: argparse.Namespace) -> None:
    """Push the local scrim.db to origin/scrim-db. If origin moved since our
    last snapshot, pull-merge first (which overwrites local — but everything
    derivable from /api will be re-synced; only locally-known queued
    match_ids could be lost, which is why we sync first to refresh)."""
    if not DB_PATH.exists():
        msg = f"{DB_PATH} missing — nothing to push"
        raise SystemExit(msg)
    # Sync from API first — capture any queued match_ids the API now knows
    # about (in case a previous run was interrupted before push).
    with _connect() as conn:
        _sync_submissions(conn)
        _sync_matches(conn)
    # Hash the local DB into a blob.
    blob_sha = _git("hash-object", "-w", str(DB_PATH))
    # Build a one-entry tree.
    tree_in = f"100644 blob {blob_sha}\t{SCRIM_DB_FILENAME_IN_BRANCH}\n"
    res = subprocess.run(
        ["git", "mktree"],
        cwd=ROOT,
        input=tree_in,
        capture_output=True,
        text=True,
        check=True,
    )
    tree_sha = res.stdout.strip()
    # Find parent (current origin/scrim-db tip, if any).
    _git("fetch", "origin", SCRIM_DB_BRANCH, check=False)
    parent = _git("rev-parse", "--verify", f"origin/{SCRIM_DB_BRANCH}", check=False)
    parent_args = ["-p", parent] if parent else []
    msg = f"scrim db @ {_now_iso()}"
    res = subprocess.run(
        ["git", "commit-tree", tree_sha, *parent_args, "-m", msg],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    commit_sha = res.stdout.strip()
    _git("update-ref", f"refs/heads/{SCRIM_DB_BRANCH}", commit_sha)
    _git("push", "origin", SCRIM_DB_BRANCH)
    print(f"pushed scrim.db (commit {commit_sha[:10]}, blob {blob_sha[:10]})")


def cmd_queued(_args: argparse.Namespace) -> None:
    """Show in-flight matches (status not yet 'complete' or 'error')."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT m.match_id, m.team_id, m.status, m.requested_at, m.map_names,
                   m.our_version, o.team_name
            FROM matches m
            LEFT JOIN opponents o ON o.team_id = m.team_id
            WHERE m.status IS NULL OR m.status NOT IN ('complete', 'error')
            ORDER BY m.requested_at DESC
            """,
        ).fetchall()
    if not rows:
        print("no queued matches")
        return
    print(
        f"  {'match_id':<14} {'opponent':<25} {'v':>4} {'status':<10} {'maps':<40} requested_at"
    )
    for r in rows:
        opp = (r["team_name"] or r["team_id"])[:25]
        try:
            maps = ",".join(json.loads(r["map_names"])) if r["map_names"] else ""
        except (json.JSONDecodeError, TypeError):
            maps = "?"
        print(
            f"  {r['match_id'][:13]:<14} {opp:<25} {r['our_version'] or '?':>4} "
            f"{(r['status'] or 'pending')[:10]:<10} {maps[:40]:<40} {r['requested_at']}",
        )


def cmd_replays(args: argparse.Namespace) -> None:
    """Download replays for a match. Uses S3 presigned URLs from the API."""
    out_dir = Path(args.out) if args.out else ROOT / "replays_remote"
    out_dir.mkdir(parents=True, exist_ok=True)
    token = get_token()
    if not token:
        print("not logged in")
        return
    data = api_get(f"/api/matches/{args.match_id}")
    games = data.get("games", []) or []
    if not games:
        print("no games yet")
        return
    a = data.get("match", {}).get("teamAName", "A").replace(" ", "_")
    b = data.get("match", {}).get("teamBName", "B").replace(" ", "_")
    for g in games:
        gn = g.get("gameNumber")
        url = f"{get_api_url()}/api/matches/replay?matchId={args.match_id}&game={gn}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            replay_url = json.loads(resp.read())["url"]
        replay_bytes = urllib.request.urlopen(replay_url, timeout=60).read()
        out_path = out_dir / f"{a}_vs_{b}_{args.match_id}_g{gn}.replay26"
        out_path.write_bytes(replay_bytes)
        print(f"  game {gn} ({g.get('mapName', '?')}) -> {out_path}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("add", help="add tracked opponent")
    sp.add_argument("team_id")
    sp.add_argument("--name", help="display label")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("ladder", help="print ladder with team_ids ready to copy")
    sp.add_argument("--region", help="filter by region (uk|international)")
    sp.add_argument("--category", help="filter by category (main|novice)")
    sp.add_argument("--limit", type=int, default=20, help="max rows to show")
    sp.add_argument(
        "--around", type=int, help="show N teams above/below us instead of top"
    )
    sp.add_argument("--include-banned", action="store_true")
    sp.set_defaults(func=cmd_ladder)

    sp = sub.add_parser("remove", help="drop tracked opponent")
    sp.add_argument("team_id")
    sp.set_defaults(func=cmd_remove)

    sp = sub.add_parser("list", help="list tracked opponents")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("search", help="search teams via cambc team search")
    sp.add_argument("query")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("submit", help="upload bot via cambc; record submission")
    sp.add_argument("bot", help="bot path or owner/name (e.g. intgrah/v54.7.9)")
    sp.add_argument("-n", "--name", help="submission name (default: bot path)")
    sp.set_defaults(func=cmd_submit)

    sp = sub.add_parser("sync", help="pull /api/submissions + recent matches")
    sp.add_argument(
        "--full",
        action="store_true",
        help="walk all match pages (default: exit early after 5 all-existing pages)",
    )
    sp.set_defaults(func=cmd_sync)

    sp = sub.add_parser("run", help="submit unrated matches")
    sp.add_argument("--team", help="single team_id (default: all tracked)")
    sp.add_argument("--rounds", type=int, default=1)
    sp.add_argument("--maps", help="comma-separated map names (default: cycle)")
    sp.add_argument(
        "--async",
        dest="async_",
        action="store_true",
        help="submit and exit; use `poll` later to update status",
    )
    sp.add_argument(
        "--forever",
        action="store_true",
        help="loop indefinitely (rate-limit gates pacing)",
    )
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("poll", help="update DB for pending matches")
    sp.set_defaults(func=cmd_poll)

    sp = sub.add_parser("status", help="W/L summary")
    sp.add_argument("--team", help="filter to one opponent")
    sp.add_argument("--bot", help="filter by submission name (e.g. intgrah/v54.7.9)")
    sp.add_argument("--version", type=int, help="filter by submission version number")
    sp.add_argument(
        "--by-map",
        action="store_true",
        help="per-map breakdown (lazy-fetches /api/matches/<id> for missing games)",
    )
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("queued", help="show in-flight matches")
    sp.set_defaults(func=cmd_queued)

    sp = sub.add_parser("pull-state", help="pull shared scrim.db from origin/scrim-db")
    sp.set_defaults(func=cmd_pull_state)

    sp = sub.add_parser("push-state", help="push local scrim.db to origin/scrim-db")
    sp.set_defaults(func=cmd_push_state)

    sp = sub.add_parser("replays", help="download replays for a match")
    sp.add_argument("match_id")
    sp.add_argument("--out", help="output directory")
    sp.set_defaults(func=cmd_replays)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
