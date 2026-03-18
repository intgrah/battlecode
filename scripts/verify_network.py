"""Compare bot's network belief against ground truth from replay.

Ground truth: for each conveyor, trace its output chain. If the chain
reaches a core-adjacent tile, the conveyor is connected. Otherwise not.

Bot belief: extracted from _dbg JSON lines in bot_output events.

Usage:
    python scripts/verify_network.py replay.replay26 [turn] [team]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from proto.cambc_pb2 import Replay

DIR_DELTA = {
    0: (0, 0),
    1: (0, -1),
    2: (1, -1),
    3: (1, 0),
    4: (1, 1),
    5: (0, 1),
    6: (-1, 1),
    7: (-1, 0),
    8: (-1, -1),
}

TRANSPORT = {"conveyor", "armoured_conveyor", "splitter", "bridge"}


def build_ground_truth(r, at_turn, team):
    """Build the actual conveyor graph at a given turn."""
    alive = {}  # id -> (team, kind, pos, direction)

    core_pos = None
    for c in r.map.cores:
        if c.team == team:
            core_pos = (c.position.x, c.position.y)

    if core_pos is None:
        return None

    core_tiles = set()
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            core_tiles.add((core_pos[0] + dx, core_pos[1] + dy))

    for _i, turn in enumerate(r.turns[:at_turn]):
        for u in turn.updates:
            k = u.WhichOneof("kind")
            if k == "place_entity":
                e = u.place_entity.entity
                ek = e.WhichOneof("kind") or "?"
                pos = (e.position.x, e.position.y)
                direction = None
                if ek == "conveyor":
                    direction = e.conveyor.direction
                elif ek == "armoured_conveyor":
                    direction = e.armoured_conveyor.direction
                elif ek == "splitter":
                    direction = e.splitter.direction
                elif ek == "bridge":
                    direction = None  # bridges have target, not direction
                alive[e.id] = (e.team, ek, pos, direction)
            elif k == "remove_entity":
                alive.pop(u.remove_entity.id, None)

    # Build graph: pos -> (kind, out_pos) for team's transport
    graph = {}
    harvesters = []
    for eid, (t, ek, pos, d) in alive.items():
        if t != team:
            continue
        if ek in TRANSPORT and d is not None:
            dx, dy = DIR_DELTA.get(d, (0, 0))
            out = (pos[0] + dx, pos[1] + dy)
            graph[pos] = {"kind": ek, "out": out, "id": eid}
        elif ek == "harvester":
            harvesters.append(pos)

    # Trace connectivity: for each conveyor, follow output chain to core
    def is_connected(start) -> bool:
        cur = start
        seen = set()
        while cur not in seen:
            if cur in core_tiles:
                return True
            seen.add(cur)
            if cur not in graph:
                return False
            cur = graph[cur]["out"]
        return False

    connected = {}
    for pos in graph:
        connected[pos] = is_connected(pos)

    # Find breaks: conveyor whose output tile has no transport building
    breaks = []
    for pos, info in graph.items():
        out = info["out"]
        if out in core_tiles:
            continue
        if out not in graph:
            breaks.append((pos, out))

    return {
        "core": core_pos,
        "graph": graph,
        "connected": connected,
        "harvesters": harvesters,
        "breaks": breaks,
    }


def extract_bot_beliefs(r, at_turn, team):
    """Extract bot beliefs from _dbg JSON in bot_output events."""
    import json

    entities = {}
    bot_positions = {}

    beliefs = {}  # bot_id -> last belief dict

    for _i, turn in enumerate(r.turns[:at_turn]):
        for u in turn.updates:
            k = u.WhichOneof("kind")
            if k == "place_entity":
                e = u.place_entity.entity
                ek = e.WhichOneof("kind") or "?"
                entities[e.id] = (e.team, ek)
                bot_positions[e.id] = (e.position.x, e.position.y)
            elif k == "move_builder_bot":
                m = u.move_builder_bot
                bot_positions[m.id] = (m.to.x, m.to.y)
            elif k == "bot_output":
                bo = u.bot_output
                if bo.id in entities and entities[bo.id][0] == team:
                    for line in bo.output.split("\n"):
                        line = line.strip()
                        if line.startswith("{") and '"_dbg"' in line:
                            try:
                                d = json.loads(line)
                                if d.get("_dbg"):
                                    beliefs[bo.id] = d
                            except json.JSONDecodeError:
                                pass

    return beliefs, bot_positions


def render_map(r, gt, at_turn, team, center=None, radius=8):
    """Render ASCII map showing ground truth connectivity."""
    w, h = r.map.width, r.map.height

    if center:
        x0 = max(0, center[0] - radius)
        x1 = min(w, center[0] + radius + 1)
        y0 = max(0, center[1] - radius)
        y1 = min(h, center[1] + radius + 1)
    else:
        x0, y0, x1, y1 = 0, 0, w, h

    lines = []
    lines.append(f"    {''.join(f'{x % 10}' for x in range(x0, x1))}")
    for y in range(y0, y1):
        row = f"{y:3d} "
        for x in range(x0, x1):
            pos = (x, y)
            if pos == gt["core"]:
                row += "C"
            elif pos in gt["graph"]:
                gt["graph"][pos]
                if gt["connected"][pos]:
                    row += "+"  # connected conveyor
                else:
                    row += "-"  # disconnected conveyor
            elif pos in list(gt["harvesters"]):
                row += "H"
            else:
                env = (
                    r.map.rows[y].tiles[x]
                    if y < len(r.map.rows) and x < len(r.map.rows[y].tiles)
                    else 0
                )
                if env == 1:
                    row += "#"
                elif env in (2, 3):
                    row += "o"
                else:
                    row += "."
            # Mark breaks
        lines.append(row)

    # Mark breaks with X
    for _conv_pos, break_pos in gt["breaks"]:
        bx, by = break_pos
        if x0 <= bx < x1 and y0 <= by < y1:
            line_idx = by - y0 + 1  # +1 for header
            col_idx = bx - x0 + 4  # +4 for row label
            if line_idx < len(lines) and col_idx < len(lines[line_idx]):
                line = list(lines[line_idx])
                line[col_idx] = "X"
                lines[line_idx] = "".join(line)

    return "\n".join(lines)


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    at_turn = int(sys.argv[2]) if len(sys.argv) > 2 else None
    team = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    r = Replay()
    r.ParseFromString(Path(path).open("rb").read())

    if at_turn is None:
        at_turn = len(r.turns)

    gt = build_ground_truth(r, at_turn, team)
    if gt is None:
        print(f"No core found for team {team}")
        return

    print(f"=== Network Ground Truth at turn {at_turn} ===")
    print(f"Core: {gt['core']}")
    print(f"Conveyors: {len(gt['graph'])}")
    print(f"Connected: {sum(1 for v in gt['connected'].values() if v)}")
    print(f"Disconnected: {sum(1 for v in gt['connected'].values() if not v)}")
    print(f"Harvesters: {len(gt['harvesters'])}")
    print(f"Breaks: {len(gt['breaks'])}")
    print()

    if gt["breaks"]:
        print("=== Breaks ===")
        for conv_pos, break_pos in gt["breaks"]:
            conn = gt["connected"].get(conv_pos, False)
            print(
                f"  Conv({conv_pos[0]},{conv_pos[1]}) -> gap({break_pos[0]},{break_pos[1]})  upstream_connected={conn}",
            )
        print()

    print(
        "=== Map (+ = connected, - = disconnected, X = break, H = harvester, C = core) ===",
    )
    print(render_map(r, gt, at_turn, team))
    print()

    # Show disconnected chains
    disconnected = [(p, gt["graph"][p]) for p in gt["graph"] if not gt["connected"][p]]
    if disconnected:
        print(f"=== Disconnected chain tiles ({len(disconnected)}) ===")
        for pos, info in disconnected[:20]:
            print(
                f"  ({pos[0]},{pos[1]}) -> ({info['out'][0]},{info['out'][1]})  kind={info['kind']}",
            )


if __name__ == "__main__":
    main()
