"""Parse a .replay26 file and print match results with periodic stats.

Uses manual protobuf wire-format decoding based on the schema extracted from
the visualiser JS bundle. No external dependencies required.

Schema (relevant fields):
  Replay {
    Map map = 1;
    repeated Turn turns = 3;
    optional Team winner = 4;  // 0=TEAM_A, 1=TEAM_B
  }
  Turn { repeated Update updates = 1; }
  Update {
    oneof kind {
      placeEntity = 1;   // PlaceEntity { Entity entity = 1 }
      moveBuilderBot = 2;
      removeEntity = 3;  // RemoveEntity { int32 id = 1 }
      distributeResources = 4;
      updateHp = 5;
      updatePlayers = 6; // UpdatePlayers { Players players = 1 }
      setActionCooldown = 7;
      setMoveCooldown = 8;
      botOutput = 9;     // BotOutput { int32 id=1, string stdout=2, uint32 execTimeUs=3, bool tled=4 }
      indicatorLine = 10;
      indicatorDot = 11;
      fireTurret = 12;
    }
  }
  Players { Player a = 1; Player b = 2; }
  Player {
    int32 titanium = 1; int32 axionite = 2; int32 resourcesCollected = 3;
    int32 titaniumCollected = 4; int32 axioniteCollected = 5;
  }
  Entity {
    int32 id = 1; Team team = 2; Pos position = 3; int32 hp = 4; int32 maxHp = 5;
    oneof kind { builderBot=10, conveyor=11, splitter=12, armouredConveyor=13,
      bridge=14, harvester=15, foundry=16, road=17, barrier=18, marker=19,
      core=20, gunner=21, sentinel=22, breach=23, launcher=24 }
  }
"""

import sys
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

# ── Protobuf wire format helpers ──────────────────────────────────────


def decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        b = data[pos]
        result |= (b & 0x7F) << shift
        pos += 1
        if (b & 0x80) == 0:
            break
        shift += 7
    return result, pos


def to_signed(val: int) -> int:
    return val if val <= 0x7FFFFFFF else val - 0x100000000


def iter_fields(
    data: bytes, start: int = 0, end: int | None = None
) -> Iterator[tuple[int, int, int, int]]:
    """Yield (field_number, wire_type, value, next_pos) for each field."""
    if end is None:
        end = len(data)
    pos = start
    while pos < end:
        tag, pos = decode_varint(data, pos)
        field_num = tag >> 3
        wire_type = tag & 0x07
        if wire_type == 0:  # varint
            value, pos = decode_varint(data, pos)
            yield field_num, wire_type, value, pos
        elif wire_type == 2:  # length-delimited
            length, pos = decode_varint(data, pos)
            value = data[pos : pos + length]
            pos += length
            yield field_num, wire_type, value, pos
        elif wire_type == 5:  # 32-bit
            value = data[pos : pos + 4]
            pos += 4
            yield field_num, wire_type, value, pos
        elif wire_type == 1:  # 64-bit
            value = data[pos : pos + 8]
            pos += 8
            yield field_num, wire_type, value, pos
        else:
            break


# ── Entity kind mapping ───────────────────────────────────────────────

ENTITY_KINDS = {
    10: "builder_bot",
    11: "conveyor",
    12: "splitter",
    13: "armoured_conveyor",
    14: "bridge",
    15: "harvester",
    16: "foundry",
    17: "road",
    18: "barrier",
    19: "marker",
    20: "core",
    21: "gunner",
    22: "sentinel",
    23: "breach",
    24: "launcher",
}


# ── Parsing helpers ───────────────────────────────────────────────────


def parse_player(data: bytes) -> dict:
    p = {
        "titanium": 0,
        "axionite": 0,
        "resources_collected": 0,
        "titanium_collected": 0,
        "axionite_collected": 0,
    }
    for fnum, wtype, raw_val, _ in iter_fields(data):
        if wtype == 0:
            val = to_signed(raw_val)
            if fnum == 1:
                p["titanium"] = val
            elif fnum == 2:
                p["axionite"] = val
            elif fnum == 3:
                p["resources_collected"] = val
            elif fnum == 4:
                p["titanium_collected"] = val
            elif fnum == 5:
                p["axionite_collected"] = val
    return p


def parse_players(data: bytes) -> tuple[dict, dict]:
    a, b = {}, {}
    for fnum, wtype, val, _ in iter_fields(data):
        if fnum == 1 and wtype == 2:
            a = parse_player(val)
        elif fnum == 2 and wtype == 2:
            b = parse_player(val)
    return a, b


def parse_position(data: bytes) -> tuple[int, int]:
    """Extract (x, y) from a Pos message."""
    x, y = 0, 0
    for fnum, wtype, val, _ in iter_fields(data):
        if fnum == 1 and wtype == 0:
            x = to_signed(val)
        elif fnum == 2 and wtype == 0:
            y = to_signed(val)
    return (x, y)


def parse_entity(data: bytes) -> dict:
    """Extract id, team, position, and kind from an Entity message."""
    ent = {"id": 0, "team": "A", "kind": "unknown", "pos": (0, 0)}
    for fnum, wtype, val, _ in iter_fields(data):
        if fnum == 1 and wtype == 0:
            ent["id"] = val
        elif fnum == 2 and wtype == 0:
            ent["team"] = "A" if val == 0 else "B"
        elif fnum == 3 and wtype == 2:
            ent["pos"] = parse_position(val)
        elif fnum in ENTITY_KINDS:
            ent["kind"] = ENTITY_KINDS[fnum]
    return ent


def parse_bot_output(data: bytes) -> dict:
    out = {"id": 0, "stdout": "", "exec_time_us": 0, "tled": False}
    for fnum, wtype, val, _ in iter_fields(data):
        if fnum == 1 and wtype == 0:
            out["id"] = val
        elif fnum == 2 and wtype == 2:
            out["stdout"] = val.decode("utf-8", errors="replace")
        elif fnum == 3 and wtype == 0:
            out["exec_time_us"] = val
        elif fnum == 4 and wtype == 0:
            out["tled"] = bool(val)
    return out


# ── Main replay parser ────────────────────────────────────────────────


def parse_replay(path: str, snapshot_interval: int = 100) -> dict:
    with Path(path).open("rb") as f:
        data = f.read()

    result = {
        "turns": 0,
        "winner": None,
        "map_width": 0,
        "map_height": 0,
        "snapshots": [],  # periodic stats snapshots
        "final_a": None,
        "final_b": None,
        "entities_built": {"A": defaultdict(int), "B": defaultdict(int)},
        "entities_lost": {"A": defaultdict(int), "B": defaultdict(int)},
        "bot_stdout": [],  # (turn, entity_id, text)
        "tles": [],  # (turn, entity_id)
        "turret_fires": 0,
        "core_positions": {},  # team -> (x, y)
    }

    # Track live entities: id -> {"team", "kind"}
    live_entities: dict[int, dict] = {}
    current_a: dict = {}
    current_b: dict = {}
    turn = 0

    for fnum, wtype, val, _ in iter_fields(data):
        if fnum == 1 and wtype == 2:  # Map
            for mf, mw, mv, _ in iter_fields(val):
                if mf == 1 and mw == 0:
                    result["map_width"] = mv
                elif mf == 2 and mw == 0:
                    result["map_height"] = mv
                elif mf == 4 and mw == 2:  # Initial core placement
                    team_num, pos = 0, (0, 0)
                    for sf, sw, sv, _ in iter_fields(mv):
                        if sf == 1 and sw == 0:
                            team_num = sv
                        elif sf == 3 and sw == 2:
                            pos = parse_position(sv)
                    team = "A" if team_num == 1 else "B"
                    result["core_positions"][team] = pos

        elif fnum == 3 and wtype == 2:  # Turn
            turn += 1
            for uf, uw, uv, _ in iter_fields(val):
                if uf != 1 or uw != 2:
                    continue
                # Each Update message
                for kf, kw, kv, _ in iter_fields(uv):
                    if kf == 1 and kw == 2:  # placeEntity
                        for pf, pw, pv, _ in iter_fields(kv):
                            if pf == 1 and pw == 2:
                                ent = parse_entity(pv)
                                live_entities[ent["id"]] = {
                                    "team": ent["team"],
                                    "kind": ent["kind"],
                                }
                                result["entities_built"][ent["team"]][ent["kind"]] += 1
                                if ent["kind"] == "core":
                                    result["core_positions"][ent["team"]] = ent["pos"]

                    elif kf == 3 and kw == 2:  # removeEntity
                        eid = 0
                        for rf, rw, rv, _ in iter_fields(kv):
                            if rf == 1 and rw == 0:
                                eid = rv
                        if eid in live_entities:
                            info = live_entities.pop(eid)
                            result["entities_lost"][info["team"]][info["kind"]] += 1

                    elif kf == 6 and kw == 2:  # updatePlayers
                        for pf, pw, pv, _ in iter_fields(kv):
                            if pf == 1 and pw == 2:
                                current_a, current_b = parse_players(pv)

                    elif kf == 9 and kw == 2:  # botOutput
                        out = parse_bot_output(kv)
                        if out["stdout"].strip():
                            result["bot_stdout"].append(
                                (turn, out["id"], out["stdout"].strip()),
                            )
                        if out["tled"]:
                            result["tles"].append((turn, out["id"]))

                    elif kf == 12 and kw == 2:  # fireTurret
                        result["turret_fires"] += 1

            # Snapshot at intervals
            if turn % snapshot_interval == 0:
                # Count live entities by team and kind
                counts = {"A": defaultdict(int), "B": defaultdict(int)}
                for info in live_entities.values():
                    counts[info["team"]][info["kind"]] += 1
                result["snapshots"].append(
                    {
                        "turn": turn,
                        "player_a": dict(current_a) if current_a else {},
                        "player_b": dict(current_b) if current_b else {},
                        "entity_counts": {
                            "A": dict(counts["A"]),
                            "B": dict(counts["B"]),
                        },
                    },
                )

        elif fnum == 4 and wtype == 0:  # winner
            result["winner"] = "A" if val == 0 else "B"

    result["turns"] = turn
    result["final_a"] = current_a
    result["final_b"] = current_b
    # Convert defaultdicts
    result["entities_built"] = {k: dict(v) for k, v in result["entities_built"].items()}
    result["entities_lost"] = {k: dict(v) for k, v in result["entities_lost"].items()}
    return result


# ── Display ───────────────────────────────────────────────────────────


def fmt_player_line(p: dict) -> str:
    if not p:
        return "no data"
    ti = p.get("titanium", 0)
    ax = p.get("axionite", 0)
    ti_c = p.get("titanium_collected", 0)
    ax_c = p.get("axionite_collected", 0)
    return f"Ti:{ti:>5}  Ax:{ax:>4}  Ti deliv:{ti_c:>5}  Ax deliv:{ax_c:>4}"


def fmt_entity_counts(counts: dict) -> str:
    if not counts:
        return "-"
    # Show interesting entities, skip markers and roads for brevity
    important = [
        "core",
        "builder_bot",
        "harvester",
        "conveyor",
        "splitter",
        "bridge",
        "armoured_conveyor",
        "foundry",
        "gunner",
        "sentinel",
        "breach",
        "launcher",
        "barrier",
    ]
    parts = []
    for k in important:
        v = counts.get(k, 0)
        if v > 0:
            short = {
                "builder_bot": "bot",
                "harvester": "harv",
                "conveyor": "conv",
                "armoured_conveyor": "a.conv",
                "sentinel": "sent",
                "launcher": "lncr",
                "barrier": "barr",
                "foundry": "fndy",
            }.get(k, k)
            parts.append(f"{short}:{v}")
    # Add road/marker counts compactly
    roads = counts.get("road", 0)
    markers = counts.get("marker", 0)
    if roads:
        parts.append(f"road:{roads}")
    if markers:
        parts.append(f"mrkr:{markers}")
    return "  ".join(parts) if parts else "-"


def print_results(r: dict) -> None:
    w = 70
    print(f"\n{'=' * w}")
    print(
        f"  MATCH RESULT — {r['map_width']}x{r['map_height']} map, {r['turns']} turns",
    )
    winner = r["winner"]
    if winner:
        print(f"  Winner: Team {winner}")
    else:
        print("  Winner: DRAW / unknown")
    print(f"  Turret shots fired: {r['turret_fires']}")
    cores = r.get("core_positions", {})
    if cores:
        parts = [f"Team {t}: ({x},{y})" for t, (x, y) in sorted(cores.items())]
        print(f"  Core positions: {', '.join(parts)}")
    print(f"{'=' * w}")

    # ── Periodic snapshots ──
    if r["snapshots"]:
        print(f"\n  {'TURN':>6}  {'Team A':^34}  {'Team B':^34}")
        print(f"  {'-' * 6}  {'-' * 34}  {'-' * 34}")
        for snap in r["snapshots"]:
            t = snap["turn"]
            a_line = fmt_player_line(snap["player_a"])
            b_line = fmt_player_line(snap["player_b"])
            print(f"  {t:>6}  {a_line}  {b_line}")
        print()

        # Entity count timeline
        print("  ENTITY COUNTS (alive)")
        print(f"  {'TURN':>6}  {'Team A':^30}  |  {'Team B':^30}")
        print(f"  {'-' * 6}  {'-' * 30}  |  {'-' * 30}")
        for snap in r["snapshots"]:
            t = snap["turn"]
            a_ents = fmt_entity_counts(snap["entity_counts"]["A"])
            b_ents = fmt_entity_counts(snap["entity_counts"]["B"])
            print(f"  {t:>6}  {a_ents:<30}  |  {b_ents:<30}")
        print()

    # ── Totals ──
    print("  BUILDINGS CONSTRUCTED")
    for label, team in [("A", "A"), ("B", "B")]:
        built = r["entities_built"].get(team, {})
        lost = r["entities_lost"].get(team, {})
        if built:
            print(f"    Team {label}:")
            for kind in sorted(set(list(built.keys()) + list(lost.keys()))):
                b = built.get(kind, 0)
                lost_count = lost.get(kind, 0)
                lost_str = f"  (lost {lost_count})" if lost_count else ""
                print(f"      {kind:<20} built: {b:>4}{lost_str}")
    print()

    # ── Final state ──
    print("  FINAL STATE")
    for label, p in [("A", r["final_a"]), ("B", r["final_b"])]:
        if p:
            print(f"    Team {label}: {fmt_player_line(p)}")
    print()

    # ── Bot stdout ──
    if r["bot_stdout"]:
        show_all = "--all-output" in sys.argv
        if show_all:
            print(f"  BOT OUTPUT (all {len(r['bot_stdout'])} lines)")
            for turn, eid, text in r["bot_stdout"]:
                print(f"    [T{turn:>4} E{eid:>4}] {text[:100]}")
        else:
            print(f"  BOT OUTPUT (last 20 lines of {len(r['bot_stdout'])} total)")
            for turn, eid, text in r["bot_stdout"][-20:]:
                print(f"    [T{turn:>4} E{eid:>4}] {text[:100]}")
        print()

    # ── TLEs ──
    if r["tles"]:
        print(f"  TIME LIMIT EXCEEDED: {len(r['tles'])} occurrences")
        for turn, eid in r["tles"][:10]:
            print(f"    Turn {turn}, entity {eid}")
        if len(r["tles"]) > 10:
            print(f"    ... and {len(r['tles']) - 10} more")
        print()

    print(f"{'=' * w}\n")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    r = parse_replay(path)
    print_results(r)
