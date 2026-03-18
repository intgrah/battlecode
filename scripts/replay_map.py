import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from proto.cambc_pb2 import Entity, Replay

TEAM = {0: "A", 1: "B"}

ENV_CHARS = {0: ".", 1: "#", 2: "T", 3: "X"}

ENTITY_CHARS = {
    "core": "@",
    "builder_bot": "b",
    "splitter": "Y",
    "bridge": "=",
    "harvester": "H",
    "foundry": "F",
    "road": "-",
    "barrier": "B",
    "marker": ",",
    "gunner": "g",
    "sentinel": "s",
    "breach": "x",
    "launcher": "L",
}

DIR_ARROWS = {
    0: "o",
    1: "^",
    2: "/",
    3: ">",
    4: "\\",
    5: "v",
    6: "\\",
    7: "<",
    8: "/",
}


def entity_kind(e: Entity) -> str:
    return e.WhichOneof("kind") or "unknown"


def parse(path: str) -> Replay:
    with Path(path).open("rb") as f:
        r = Replay()
        r.ParseFromString(f.read())
        return r


def analyze(r: Replay, target_turn: int | None = None) -> dict:
    w, h = r.map.width, r.map.height

    env_grid = [list(row.tiles) for row in r.map.rows]

    entities = {}
    entity_pos = {}
    entity_team = {}
    builder_visits = {0: defaultdict(int), 1: defaultdict(int)}
    building_grid = {}

    total_turns = len(r.turns)
    if target_turn is None:
        target_turn = total_turns

    for turn_idx, turn in enumerate(r.turns):
        if turn_idx > target_turn:
            break
        for u in turn.updates:
            kind = u.WhichOneof("kind")
            if kind == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                entities[e.id] = ek
                entity_pos[e.id] = (e.position.x, e.position.y)
                entity_team[e.id] = e.team
                conv_dir = None
                if ek == "conveyor" and e.HasField("conveyor"):
                    conv_dir = e.conveyor.direction
                elif ek == "armoured_conveyor" and e.HasField("armoured_conveyor"):
                    conv_dir = e.armoured_conveyor.direction
                if ek != "builder_bot":
                    building_grid[(e.position.x, e.position.y)] = (
                        e.team,
                        ek,
                        e.id,
                        conv_dir,
                    )
                if ek == "builder_bot":
                    builder_visits[e.team][(e.position.x, e.position.y)] += 1
            elif kind == "move_builder_bot":
                mb = u.move_builder_bot
                old = entity_pos.get(mb.id)
                new = (mb.to.x, mb.to.y)
                entity_pos[mb.id] = new
                if mb.id in entity_team:
                    builder_visits[entity_team[mb.id]][new] += 1
            elif kind == "remove_entity":
                eid = u.remove_entity.id
                old = entity_pos.pop(eid, None)
                if old and old in building_grid and building_grid[old][2] == eid:
                    del building_grid[old]
                entities.pop(eid, None)
                entity_team.pop(eid, None)

    return {
        "w": w,
        "h": h,
        "env_grid": env_grid,
        "entities": entities,
        "entity_pos": entity_pos,
        "entity_team": entity_team,
        "builder_visits": builder_visits,
        "building_grid": building_grid,
        "target_turn": target_turn,
    }


def render_state(d: dict) -> str:
    w, h = d["w"], d["h"]
    grid = [["." for _ in range(w)] for _ in range(h)]

    for y in range(h):
        for x in range(w):
            grid[y][x] = ENV_CHARS.get(d["env_grid"][y][x], "?")

    for (x, y), entry in d["building_grid"].items():
        team, ek, _, conv_dir = (
            entry[0],
            entry[1],
            entry[2],
            entry[3] if len(entry) > 3 else None,
        )
        if ek in ("conveyor", "armoured_conveyor") and conv_dir is not None:
            ch = DIR_ARROWS.get(conv_dir, ">")
        else:
            ch = ENTITY_CHARS.get(ek, "?")
        if team == 1:
            ch = ch.upper()
        grid[y][x] = ch

    bot_positions = set()
    for eid, ek in d["entities"].items():
        if ek == "builder_bot" and eid in d["entity_pos"]:
            x, y = d["entity_pos"][eid]
            team = d["entity_team"].get(eid, 0)
            grid[y][x] = "1" if team == 0 else "2"
            bot_positions.add((x, y))

    lines = [f"  {''.join(str(x % 10) for x in range(w))}"]
    lines.extend(f"{y:2d} {''.join(grid[y])}" for y in range(h))
    return "\n".join(lines)


def render_heatmap(d: dict, team: int) -> str:
    w, h = d["w"], d["h"]
    visits = d["builder_visits"][team]
    if not visits:
        return f"Team {TEAM[team]}: no builder movement"

    max_v = max(visits.values())
    grid = [["." for _ in range(w)] for _ in range(h)]

    for y in range(h):
        for x in range(w):
            if d["env_grid"][y][x] == 1:
                grid[y][x] = "#"

    for (x, y), count in visits.items():
        intensity = 1 if max_v <= 1 else min(9, 1 + int(8 * count / max_v))
        grid[y][x] = str(intensity)

    lines = [f"  {''.join(str(x % 10) for x in range(w))}"]
    lines.extend(f"{y:2d} {''.join(grid[y])}" for y in range(h))

    total_tiles = sum(1 for v in visits.values() if v > 0)
    map_tiles = sum(1 for y in range(h) for x in range(w) if d["env_grid"][y][x] != 1)
    coverage = 100 * total_tiles / max(map_tiles, 1)
    lines.append(f"Coverage: {total_tiles}/{map_tiles} tiles ({coverage:.0f}%)")
    lines.append(f"Max visits: {max_v}")
    return "\n".join(lines)


def main() -> None:
    args = sys.argv[1:]
    path = "replay.replay26"
    turn = None
    mode = "all"

    for a in args:
        if a.startswith("t="):
            turn = int(a[2:])
        elif a in ("map", "heat", "heatA", "heatB", "all"):
            mode = a
        elif not a.startswith("-"):
            path = a

    r = parse(path)
    d = analyze(r, turn)

    if mode in ("all", "map"):
        print(f"Map state at turn {d['target_turn']}")
        print(render_state(d))
        print()

    if mode in ("all", "heat", "heatA"):
        print(f"Team A builder heatmap (turns 0-{d['target_turn']})")
        print(render_heatmap(d, 0))
        print()

    if mode in ("all", "heat", "heatB"):
        print(f"Team B builder heatmap (turns 0-{d['target_turn']})")
        print(render_heatmap(d, 1))


if __name__ == "__main__":
    main()
