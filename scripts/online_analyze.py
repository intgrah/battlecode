import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

from cambc.api import api_get
from cambc.auth import get_token, load_credentials

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from analysis.parse import extract_map_meta, parse
from analysis.scan import scan_replay


def fetch_my_matches(
    limit: int = 20,
    match_type: str | None = None,
    cursor: str | None = None,
) -> tuple[list[dict], str, str | None]:
    creds = load_credentials()
    my_team_id = creds["team"]["id"]
    my_team_name = creds["team"]["name"]

    params: dict[str, str] = {"limit": str(min(limit, 100)), "team": my_team_name}
    if match_type:
        params["type"] = match_type
    if cursor:
        params["cursor"] = cursor

    data = api_get("/api/matches", params)
    matches = [
        m
        for m in data.get("matches", [])
        if m.get("teamAId") == my_team_id or m.get("teamBId") == my_team_id
    ]
    return matches, my_team_id, data.get("nextCursor")


def download_replay(match_id: str, game_num: int) -> bytes:
    token = get_token()
    url = f"https://game.battlecode.cam/api/matches/replay?matchId={match_id}&game={game_num}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp_data = json.loads(resp.read())
    return urllib.request.urlopen(resp_data["url"], timeout=60).read()


def analyze_matches(
    matches: list[dict],
    my_team_id: str,
    *,
    verbose: bool = False,
) -> None:
    wins, losses, _draws = 0, 0, 0
    per_opponent = defaultdict(
        lambda: {"wins": 0, "losses": 0, "games_won": 0, "games_lost": 0},
    )
    per_map = defaultdict(lambda: {"wins": 0, "losses": 0})
    game_analyses = []

    for m in matches:
        match_id = m["id"]
        status = m.get("status")
        if status != "complete":
            continue

        we_are_a = m["teamAId"] == my_team_id
        opp_name = m["teamBName"] if we_are_a else m["teamAName"]
        our_score = m.get("scoreA", 0) if we_are_a else m.get("scoreB", 0)
        opp_score = m.get("scoreB", 0) if we_are_a else m.get("scoreA", 0)
        we_won = m.get("winnerId") == my_team_id
        mtype = "UR" if m.get("triggeredBy") == "unrated" else "L"

        if we_won:
            wins += 1
            per_opponent[opp_name]["wins"] += 1
        else:
            losses += 1
            per_opponent[opp_name]["losses"] += 1

        result = "W" if we_won else "L"
        date = (m.get("completedAt") or "")[:16].replace("T", " ")
        print(
            f"  {result} {our_score}-{opp_score} vs {opp_name:<30s} [{mtype}] {date}  {match_id[:8]}",
        )

        detail = api_get(f"/api/matches/{match_id}")
        games = detail.get("games", [])

        for g in games:
            game_num = g["gameNumber"]
            map_name = g.get("mapName", "?")
            g_won = g.get("winnerId") == my_team_id
            turns = g.get("turnsPlayed", "?")
            condition = g.get("winCondition", "?")

            if g_won:
                per_opponent[opp_name]["games_won"] += 1
                per_map[map_name]["wins"] += 1
            else:
                per_opponent[opp_name]["games_lost"] += 1
                per_map[map_name]["losses"] += 1

            if verbose:
                gr = "W" if g_won else "L"
                print(f"    g{game_num} {gr} {map_name:<20s} t={turns:<5s} {condition}")

            try:
                replay_data = download_replay(match_id, game_num)
                tmp = ROOT / "replays_remote" / "_tmp_online.replay26"
                tmp.parent.mkdir(parents=True, exist_ok=True)
                tmp.write_bytes(replay_data)
                r = parse(str(tmp))
                meta = extract_map_meta(r)
                s = scan_replay(r, meta)
                our_team = 0 if we_are_a else 1
                game_analyses.append(
                    {
                        "opponent": opp_name,
                        "map": map_name,
                        "won": g_won,
                        "turns": g.get("turnsPlayed", 0),
                        "condition": condition,
                        "scan": s,
                        "our_team": our_team,
                    },
                )
                tmp.unlink(missing_ok=True)
            except Exception as e:  # noqa: BLE001
                print(f"    (replay unavailable: {e})")

    print()
    total = wins + losses
    if total == 0:
        print("No completed matches found.")
        return

    print(f"=== {wins}W-{losses}L ({100 * wins / total:.0f}%) ===")
    print()

    print("Per opponent:")
    for opp in sorted(
        per_opponent,
        key=lambda o: -(per_opponent[o]["wins"] + per_opponent[o]["losses"]),
    ):
        d = per_opponent[opp]
        gw, gl = d["games_won"], d["games_lost"]
        print(f"  {opp:<30s} {d['wins']}W-{d['losses']}L  (games {gw}-{gl})")
    print()

    print("Per map:")
    for m in sorted(per_map):
        d = per_map[m]
        gt = d["wins"] + d["losses"]
        print(f"  {m:<24s} {d['wins']}W-{d['losses']}L ({100 * d['wins'] / gt:.0f}%)")
    print()

    if not game_analyses:
        return

    def avg(lst: list[float]) -> float:
        return sum(lst) / len(lst) if lst else 0

    def med(lst: list[float]) -> float:
        if not lst:
            return 0
        s = sorted(lst)
        return s[len(s) // 2]

    our_ti = []
    our_harvesters = []
    our_first_income = []
    our_peak_income = []
    our_damage = []
    our_builders = []
    opp_ti = []
    opp_peak_income = []

    for ga in game_analyses:
        s = ga["scan"]
        t = ga["our_team"]
        e = 1 - t
        rh = s.resource_history.get(t, [])
        if rh:
            our_ti.append(rh[-1].titanium_collected)
        our_harvesters.append(s.harvester_count.get(t, 0))
        our_first_income.append(s.first_resource_turn.get(t) or 9999)
        ir = s.income_rate.get(t, [])
        if ir:
            our_peak_income.append(max(r for _, r in ir))
        our_damage.append(s.total_damage.get(t, 0))
        our_builders.append(s.entities_placed.get(t, {}).get("builder_bot", 0))

        rh_e = s.resource_history.get(e, [])
        if rh_e:
            opp_ti.append(rh_e[-1].titanium_collected)
        ir_e = s.income_rate.get(e, [])
        if ir_e:
            opp_peak_income.append(max(r for _, r in ir_e))

    print("Aggregated (avg / median):")
    print(f"  Ti collected:    {avg(our_ti):>7.0f} / {med(our_ti):>7.0f}")
    print(
        f"  Harvesters:      {avg(our_harvesters):>7.1f} / {med(our_harvesters):>7.0f}",
    )
    print(
        f"  First income:    t{avg(our_first_income):>6.0f} / t{med(our_first_income):>6.0f}",
    )
    print(
        f"  Peak income:     {avg(our_peak_income):>7.1f} / {med(our_peak_income):>7.1f}/t",
    )
    print(f"  Builders:        {avg(our_builders):>7.1f} / {med(our_builders):>7.0f}")
    print(f"  Damage dealt:    {avg(our_damage):>7.0f} / {med(our_damage):>7.0f}")
    print()
    print("Opponent avg:")
    print(f"  Ti collected:    {avg(opp_ti):>7.0f}")
    print(f"  Peak income:     {avg(opp_peak_income):>7.1f}/t")

    win_analyses = [ga for ga in game_analyses if ga["won"]]
    loss_analyses = [ga for ga in game_analyses if not ga["won"]]

    if win_analyses and loss_analyses:
        print()
        print("Win vs Loss comparison (our avg):")
        for label, subset in [("  Wins: ", win_analyses), ("  Losses:", loss_analyses)]:
            ti = [
                ga["scan"]
                .resource_history.get(ga["our_team"], [])[-1]
                .titanium_collected
                for ga in subset
                if ga["scan"].resource_history.get(ga["our_team"])
            ]
            pi = []
            for ga in subset:
                ir = ga["scan"].income_rate.get(ga["our_team"], [])
                if ir:
                    pi.append(max(r for _, r in ir))
            dmg = [ga["scan"].total_damage.get(ga["our_team"], 0) for ga in subset]
            fi = [
                ga["scan"].first_resource_turn.get(ga["our_team"]) or 9999
                for ga in subset
            ]
            print(
                f"{label} Ti={avg(ti):.0f}  peak_inc={avg(pi):.1f}/t  first_inc=t{avg(fi):.0f}  dmg={avg(dmg):.0f}  n={len(subset)}",
            )


def main() -> None:
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser(description="Analyze recent online matches")
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=10,
        help="Number of matches to fetch",
    )
    parser.add_argument(
        "-t",
        "--type",
        choices=["ladder", "unrated"],
        default=None,
        help="Filter match type",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show per-game details",
    )
    args = parser.parse_args()

    print("Fetching recent matches...")
    matches, my_team_id, _ = fetch_my_matches(limit=args.limit, match_type=args.type)
    print(f"Found {len(matches)} matches\n")

    analyze_matches(matches, my_team_id, verbose=args.verbose)


if __name__ == "__main__":
    main()
