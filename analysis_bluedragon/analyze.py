"""Deep analysis of Blue Dragon's economy and strategy across replays."""

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "proto"))

import cambc_pb2

BD_TEAM_ID = "023ce802-d72e-44f5-b99e-71a6f97db4b7"

ETYPE_ONEOFS = [
    "core", "builder_bot", "road", "conveyor", "splitter",
    "armoured_conveyor", "bridge", "harvester", "foundry",
    "barrier", "marker", "gunner", "sentinel", "breach", "launcher",
]

ETYPE_DISPLAY = {
    "core": "core", "builder_bot": "builder", "road": "road",
    "conveyor": "conveyor", "splitter": "splitter",
    "armoured_conveyor": "arm_conv", "bridge": "bridge",
    "harvester": "harvester", "foundry": "foundry",
    "barrier": "barrier", "marker": "marker", "gunner": "gunner",
    "sentinel": "sentinel", "breach": "breach", "launcher": "launcher",
}


def detect_etype(entity) -> str:
    for name in ETYPE_ONEOFS:
        if entity.HasField(name):
            return name
    return "unknown"


@dataclass
class EntityInfo:
    etype: str
    team: int
    x: int
    y: int
    born: int


@dataclass
class TurnSnapshot:
    turn: int
    ti_a: int = 0
    ax_a: int = 0
    ti_collected_a: int = 0
    ax_collected_a: int = 0
    ti_b: int = 0
    ax_b: int = 0
    ti_collected_b: int = 0
    ax_collected_b: int = 0
    counts_a: dict[str, int] = field(default_factory=dict)
    counts_b: dict[str, int] = field(default_factory=dict)


@dataclass
class BuildEvent:
    turn: int
    team: int
    etype: str
    x: int
    y: int


def parse_replay(path: Path) -> tuple[cambc_pb2.Replay, list[TurnSnapshot], list[BuildEvent], int | None]:
    replay = cambc_pb2.Replay()
    replay.ParseFromString(path.read_bytes())
    m = replay.map

    entities: dict[int, EntityInfo] = {}
    snapshots: list[TurnSnapshot] = []
    builds: list[BuildEvent] = []

    for c in m.cores:
        entities[c.id] = EntityInfo("core", c.team, c.position.x, c.position.y, 0)

    ti_a, ax_a, ti_col_a, ax_col_a = 1000, 0, 0, 0
    ti_b, ax_b, ti_col_b, ax_col_b = 1000, 0, 0, 0

    for turn_idx, turn in enumerate(replay.turns):
        turn_num = turn_idx + 1
        for update in turn.updates:
            kind = update.WhichOneof("kind")
            if kind == "place_entity":
                e = update.place_entity.entity
                etype = detect_etype(e)
                entities[e.id] = EntityInfo(etype, e.team, e.position.x, e.position.y, turn_num)
                builds.append(BuildEvent(turn_num, e.team, etype, e.position.x, e.position.y))
            elif kind == "remove_entity":
                entities.pop(update.remove_entity.id, None)
            elif kind == "move_builder_bot":
                mb = update.move_builder_bot
                if mb.id in entities:
                    entities[mb.id].x = mb.to.x
                    entities[mb.id].y = mb.to.y
            elif kind == "update_players":
                p = update.update_players.players
                ti_a, ax_a = p.a.titanium, p.a.axionite
                ti_col_a, ax_col_a = p.a.titanium_collected, p.a.axionite_collected
                ti_b, ax_b = p.b.titanium, p.b.axionite
                ti_col_b, ax_col_b = p.b.titanium_collected, p.b.axionite_collected

        counts_a: dict[str, int] = defaultdict(int)
        counts_b: dict[str, int] = defaultdict(int)
        for ent in entities.values():
            if ent.team == 0:
                counts_a[ent.etype] += 1
            else:
                counts_b[ent.etype] += 1

        snapshots.append(TurnSnapshot(
            turn=turn_num,
            ti_a=ti_a, ax_a=ax_a, ti_collected_a=ti_col_a, ax_collected_a=ax_col_a,
            ti_b=ti_b, ax_b=ax_b, ti_collected_b=ti_col_b, ax_collected_b=ax_col_b,
            counts_a=dict(counts_a), counts_b=dict(counts_b),
        ))

    winner = replay.winner if replay.HasField("winner") else None
    return replay, snapshots, builds, winner


def determine_bd_team(match_meta: dict) -> int | None:
    if match_meta["teamAId"] == BD_TEAM_ID:
        return 0
    if match_meta["teamBId"] == BD_TEAM_ID:
        return 1
    return None


def bd_counts(snap: TurnSnapshot, bd_team: int) -> dict[str, int]:
    return snap.counts_a if bd_team == 0 else snap.counts_b


def bd_ti(snap: TurnSnapshot, bd_team: int) -> int:
    return snap.ti_a if bd_team == 0 else snap.ti_b


def bd_ax(snap: TurnSnapshot, bd_team: int) -> int:
    return snap.ax_a if bd_team == 0 else snap.ax_b


def bd_ti_collected(snap: TurnSnapshot, bd_team: int) -> int:
    return snap.ti_collected_a if bd_team == 0 else snap.ti_collected_b


def bd_ax_collected(snap: TurnSnapshot, bd_team: int) -> int:
    return snap.ax_collected_a if bd_team == 0 else snap.ax_collected_b


def analyze_one(rf: Path, meta: dict, bd_team: int) -> dict:
    opponent = meta["teamBName"] if bd_team == 0 else meta["teamAName"]

    print(f"\n{'='*80}")
    print(f"  {rf.name}  |  BD={'A' if bd_team==0 else 'B'} vs {opponent}")
    print(f"{'='*80}")

    replay, snapshots, builds, winner = parse_replay(rf)
    bd_won = (winner == bd_team) if winner is not None else False
    print(f"  Result: {'BD WIN' if bd_won else 'BD LOSS'}  |  Turns: {len(snapshots)}  |  Map: {replay.map.width}x{replay.map.height}")

    bd_builds = [b for b in builds if b.team == bd_team]
    en_builds = [b for b in builds if b.team != bd_team]

    # Build order (first 25, skip markers)
    print(f"\n  Build order (first 25):")
    shown = 0
    for b in bd_builds:
        if b.etype == "marker":
            continue
        print(f"    T{b.turn:4d}  {ETYPE_DISPLAY.get(b.etype, b.etype):12s} ({b.x},{b.y})")
        shown += 1
        if shown >= 25:
            break

    # Build counts
    bd_c: dict[str, int] = defaultdict(int)
    en_c: dict[str, int] = defaultdict(int)
    for b in bd_builds:
        bd_c[b.etype] += 1
    for b in en_builds:
        en_c[b.etype] += 1
    print(f"\n  Total builds:  {'type':15s} {'BD':>5s} {'Opp':>5s}")
    for t in sorted(set(bd_c) | set(en_c)):
        if t == "marker":
            continue
        print(f"                 {ETYPE_DISPLAY.get(t,t):15s} {bd_c.get(t,0):5d} {en_c.get(t,0):5d}")

    # Economy every 100 turns
    print(f"\n  Economy (BD):  {'Turn':>5s} {'Ti':>6s} {'Ax':>5s} {'TiCol':>6s} {'Harv':>5s} {'Conv':>5s} {'Brdg':>5s} {'Barr':>5s} {'Sent':>5s} {'Bldr':>5s} {'Fndy':>5s} {'Lncr':>5s}")
    for snap in snapshots:
        if snap.turn % 100 != 0 and snap.turn != 1 and snap.turn != len(snapshots):
            continue
        c = bd_counts(snap, bd_team)
        print(f"                 {snap.turn:5d} {bd_ti(snap,bd_team):6d} {bd_ax(snap,bd_team):5d} {bd_ti_collected(snap,bd_team):6d}"
              f" {c.get('harvester',0):5d} {c.get('conveyor',0):5d} {c.get('bridge',0):5d}"
              f" {c.get('barrier',0):5d} {c.get('sentinel',0):5d} {c.get('builder_bot',0):5d}"
              f" {c.get('foundry',0):5d} {c.get('launcher',0):5d}")

    # Spending per 100-turn window
    print(f"\n  Spending per window:")
    by_window: dict[int, list[BuildEvent]] = defaultdict(list)
    for b in bd_builds:
        if b.etype != "marker":
            by_window[(b.turn - 1) // 100].append(b)
    for w in sorted(by_window):
        types: dict[str, int] = defaultdict(int)
        for b in by_window[w]:
            types[ETYPE_DISPLAY.get(b.etype, b.etype)] += 1
        s = ", ".join(f"{v}x{k}" for k, v in sorted(types.items(), key=lambda x: -x[1]))
        print(f"    T{w*100+1:4d}-{(w+1)*100:4d}: {len(by_window[w]):3d} builds  [{s}]")

    # First harvester context
    bd_harvesters = [b for b in bd_builds if b.etype == "harvester"]
    first_h_turn = bd_harvesters[0].turn if bd_harvesters else None
    first_h_ti = None
    if first_h_turn:
        for snap in snapshots:
            if snap.turn >= first_h_turn:
                first_h_ti = bd_ti(snap, bd_team)
                break
        print(f"\n  First harvester: T{first_h_turn}, Ti={first_h_ti}")
        # What was built before the first harvester?
        before = [b for b in bd_builds if b.turn < first_h_turn and b.etype != "marker"]
        if before:
            types_before: dict[str, int] = defaultdict(int)
            for b in before:
                types_before[ETYPE_DISPLAY.get(b.etype, b.etype)] += 1
            print(f"  Built before: {dict(types_before)}")

    # Harvester spacing
    if len(bd_harvesters) >= 2:
        print(f"  Harvester intervals: ", end="")
        for i in range(1, min(len(bd_harvesters), 8)):
            gap = bd_harvesters[i].turn - bd_harvesters[i-1].turn
            print(f"+{gap}", end=" ")
        print()

    # Aggression indicators: barriers/sentinels placed near enemy core
    en_team = 1 - bd_team
    en_core_x, en_core_y = None, None
    for c in replay.map.cores:
        if c.team == en_team:
            en_core_x, en_core_y = c.position.x, c.position.y
    bd_aggro_builds = []
    if en_core_x is not None:
        for b in bd_builds:
            if b.etype in ("barrier", "sentinel", "gunner", "breach"):
                dist = max(abs(b.x - en_core_x), abs(b.y - en_core_y))
                if dist <= 10:
                    bd_aggro_builds.append((b, dist))
    if bd_aggro_builds:
        print(f"\n  Aggro builds near enemy core (dist<=10):")
        for b, d in bd_aggro_builds[:10]:
            print(f"    T{b.turn:4d}  {ETYPE_DISPLAY.get(b.etype,b.etype):12s} dist={d}")

    return {
        "file": rf.name,
        "opponent": opponent,
        "bd_won": bd_won,
        "turns": len(snapshots),
        "map_w": replay.map.width,
        "map_h": replay.map.height,
        "first_h_turn": first_h_turn,
        "first_h_ti": first_h_ti,
        "total_harvesters": len(bd_harvesters),
        "total_barriers": bd_c.get("barrier", 0),
        "total_sentinels": bd_c.get("sentinel", 0),
        "total_builders_spawned": bd_c.get("builder_bot", 0),
        "total_roads": bd_c.get("road", 0),
        "total_conveyors": bd_c.get("conveyor", 0),
        "total_bridges": bd_c.get("bridge", 0),
        "total_foundries": bd_c.get("foundry", 0),
        "total_launchers": bd_c.get("launcher", 0),
        "final_ti_collected": bd_ti_collected(snapshots[-1], bd_team) if snapshots else 0,
        "final_ax_collected": bd_ax_collected(snapshots[-1], bd_team) if snapshots else 0,
        "aggro_builds_near_core": len(bd_aggro_builds),
    }


def main() -> None:
    replay_dir = Path(__file__).parent
    with open(replay_dir / "matches.json") as f:
        all_matches = json.load(f)
    match_lookup = {m["id"]: m for m in all_matches}

    replay_files = sorted(replay_dir.glob("*.replay26"))
    print(f"Found {len(replay_files)} replays\n")

    results: list[dict] = []
    for rf in replay_files:
        match_id = rf.stem.rsplit("_", 1)[0]
        meta = match_lookup.get(match_id)
        if meta is None:
            continue
        bd_team = determine_bd_team(meta)
        if bd_team is None:
            continue
        results.append(analyze_one(rf, meta, bd_team))

    # === AGGREGATE ===
    print(f"\n\n{'#'*80}")
    print(f"  AGGREGATE: {len(results)} games")
    print(f"{'#'*80}")

    wins = sum(1 for r in results if r["bd_won"])
    print(f"\n  Win rate: {wins}/{len(results)} ({100*wins/max(len(results),1):.0f}%)")

    # First harvester
    h_turns = [r["first_h_turn"] for r in results if r["first_h_turn"]]
    h_tis = [r["first_h_ti"] for r in results if r["first_h_ti"] is not None]
    if h_turns:
        print(f"\n  First harvester turn:  min={min(h_turns)} avg={sum(h_turns)/len(h_turns):.0f} max={max(h_turns)} median={sorted(h_turns)[len(h_turns)//2]}")
        print(f"  First harvester Ti:    min={min(h_tis)} avg={sum(h_tis)/len(h_tis):.0f} max={max(h_tis)} median={sorted(h_tis)[len(h_tis)//2]}")

    # Average building counts
    def avg_field(field: str) -> str:
        vals = [r[field] for r in results]
        return f"min={min(vals)} avg={sum(vals)/len(vals):.1f} max={max(vals)}"

    print(f"\n  Total harvesters:   {avg_field('total_harvesters')}")
    print(f"  Total barriers:     {avg_field('total_barriers')}")
    print(f"  Total sentinels:    {avg_field('total_sentinels')}")
    print(f"  Total builders:     {avg_field('total_builders_spawned')}")
    print(f"  Total roads:        {avg_field('total_roads')}")
    print(f"  Total conveyors:    {avg_field('total_conveyors')}")
    print(f"  Total bridges:      {avg_field('total_bridges')}")
    print(f"  Total foundries:    {avg_field('total_foundries')}")
    print(f"  Total launchers:    {avg_field('total_launchers')}")
    print(f"  Final Ti collected: {avg_field('final_ti_collected')}")
    print(f"  Final Ax collected: {avg_field('final_ax_collected')}")
    print(f"  Aggro near core:    {avg_field('aggro_builds_near_core')}")

    # Build order patterns: what is the first non-builder, non-road build?
    print(f"\n  === Common opening patterns ===")
    openers: dict[str, int] = defaultdict(int)
    for r in results:
        # Already encoded in per-game output, but let's aggregate
        pass

    # Per-opponent stats
    print(f"\n  === Per-opponent ===")
    by_opp: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_opp[r["opponent"]].append(r)
    for opp, games in sorted(by_opp.items()):
        w = sum(1 for g in games if g["bd_won"])
        avg_h = sum(g["total_harvesters"] for g in games) / len(games)
        avg_b = sum(g["total_barriers"] for g in games) / len(games)
        print(f"    {opp:20s}  {w}/{len(games)} wins  avg_harv={avg_h:.1f}  avg_barr={avg_b:.1f}")


if __name__ == "__main__":
    main()
