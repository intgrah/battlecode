"""Compare bot network belief against ground truth from replay.

For each belief snapshot (dumped every 50 turns), extract ground truth at the
same turn and compare connectivity and flow for tiles the bot claims to know about.

Usage:
    python scripts/compare_belief.py replay.replay26 /tmp/v32_belief.jsonl [team]
"""

import json
import sys
import tempfile
from pathlib import Path

from proto.cambc_pb2 import Replay
from scripts.replay import load_replay

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
CARDINAL_DELTAS = [(0, -1), (1, 0), (0, 1), (-1, 0)]


def build_state_at_turn(
    r: Replay,
    at_turn: int,
    team: int,
) -> dict | None:
    alive = {}
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

    for turn in r.turns[:at_turn]:
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
                alive[e.id] = (e.team, ek, pos, direction)
            elif k == "remove_entity":
                alive.pop(u.remove_entity.id, None)

    graph = {}
    harvesters = []
    for t, ek, pos, d in alive.values():
        if t != team:
            continue
        if ek in TRANSPORT and d is not None:
            dx, dy = DIR_DELTA.get(d, (0, 0))
            out = (pos[0] + dx, pos[1] + dy)
            graph[pos] = {"kind": ek, "out": out}
        elif ek == "harvester":
            harvesters.append(pos)

    def is_connected(start: tuple[int, int]) -> bool:
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

    harvester_set = {tuple(h) for h in harvesters}
    all_buildings = set(graph.keys()) | harvester_set | core_tiles

    def harvester_output_count(hpos: tuple[int, int]) -> int:
        count = 0
        for dx, dy in CARDINAL_DELTAS:
            adj = (hpos[0] + dx, hpos[1] + dy)
            if adj in all_buildings:
                count += 1
        return max(count, 1)

    def count_upstream(
        pos: tuple[int, int],
        seen: set[tuple[int, int]] | None = None,
    ) -> float:
        if seen is None:
            seen = set()
        if pos in seen:
            return 0.0
        seen.add(pos)
        total = 0.0
        for dx, dy in CARDINAL_DELTAS:
            adj = (pos[0] + dx, pos[1] + dy)
            if adj in harvester_set:
                total += 0.25 / harvester_output_count(adj)
            if adj in graph:
                info = graph[adj]
                if info["out"] == pos:
                    upstream = count_upstream(adj, seen)
                    if info["kind"] == "splitter":
                        upstream /= 3.0
                    total += upstream
        return total

    connected = {pos: is_connected(pos) for pos in graph}
    flow = {pos: round(count_upstream(pos), 3) for pos in graph}

    return {
        "core": core_pos,
        "graph": graph,
        "connected": connected,
        "flow": flow,
        "harvesters": harvesters,
    }


def main() -> None:
    replay_path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    default_belief = Path(tempfile.gettempdir()) / "v32_belief.jsonl"
    belief_path = sys.argv[2] if len(sys.argv) > 2 else str(default_belief)
    team = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    r = load_replay(replay_path)

    beliefs = []
    with Path(belief_path).open() as f:
        beliefs.extend(json.loads(line) for line in f)

    turns_seen = sorted({b["turn"] for b in beliefs})

    total_conn_correct = 0
    total_conn_wrong = 0
    total_conn_missing = 0
    total_flow_close = 0
    total_flow_off = 0
    total_flow_compared = 0

    for turn in turns_seen:
        gt = build_state_at_turn(r, turn, team)
        if gt is None:
            continue

        turn_beliefs = [b for b in beliefs if b["turn"] == turn]

        all_belief_tiles = {k: v for b in turn_beliefs for k, v in b["tiles"].items()}

        conn_correct = 0
        conn_wrong = 0
        conn_missing = 0
        flow_close = 0
        flow_off = 0
        flow_compared = 0

        for tile_key, belief_info in all_belief_tiles.items():
            x, y = map(int, tile_key.split(","))
            pos = (x, y)

            gt_connected = gt["connected"].get(pos)
            gt_flow = gt["flow"].get(pos, 0.0)
            b_connected = belief_info["connected"]
            b_flow = belief_info["flow"]

            if gt_connected is None:
                conn_missing += 1
                continue

            if b_connected == gt_connected:
                conn_correct += 1
            else:
                conn_wrong += 1
                if turn in turns_seen[:5] or conn_wrong <= 3:
                    print(
                        f"  t{turn} ({x},{y}): belief={b_connected} gt={gt_connected}",
                    )

            if b_connected is not None and gt_connected is not None:
                flow_compared += 1
                if abs(b_flow - gt_flow) < 0.1:
                    flow_close += 1
                else:
                    flow_off += 1
                    if turn in turns_seen[:5] or flow_off <= 3:
                        print(
                            f"  t{turn} ({x},{y}): belief_flow={b_flow} gt_flow={gt_flow}",
                        )

        total_conn_correct += conn_correct
        total_conn_wrong += conn_wrong
        total_conn_missing += conn_missing
        total_flow_close += flow_close
        total_flow_off += flow_off
        total_flow_compared += flow_compared

    print()
    print("=== Connectivity Accuracy ===")
    total_conn = total_conn_correct + total_conn_wrong
    if total_conn > 0:
        print(
            f"  Correct: {total_conn_correct}/{total_conn} ({100 * total_conn_correct / total_conn:.1f}%)",
        )
        print(
            f"  Wrong:   {total_conn_wrong}/{total_conn} ({100 * total_conn_wrong / total_conn:.1f}%)",
        )
    print(f"  Missing from GT (stale belief): {total_conn_missing}")

    print()
    print("=== Flow Accuracy ===")
    if total_flow_compared > 0:
        print(
            f"  Close (<0.1 diff): {total_flow_close}/{total_flow_compared} ({100 * total_flow_close / total_flow_compared:.1f}%)",
        )
        print(
            f"  Off (>=0.1 diff):  {total_flow_off}/{total_flow_compared} ({100 * total_flow_off / total_flow_compared:.1f}%)",
        )

    gt_final = build_state_at_turn(r, turns_seen[-1], team)
    if gt_final:
        gt_breaks = []
        for pos, info in gt_final["graph"].items():
            out = info["out"]
            core_tiles = set()
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    core_tiles.add((gt_final["core"][0] + dx, gt_final["core"][1] + dy))
            if out not in core_tiles and out not in gt_final["graph"]:
                gt_breaks.append((pos, out))
        print()
        print(f"=== Breaks at t{turns_seen[-1]} ===")
        print(f"  Ground truth breaks: {len(gt_breaks)}")
        for conv, gap in gt_breaks[:10]:
            print(f"    Conv({conv[0]},{conv[1]}) -> gap({gap[0]},{gap[1]})")


if __name__ == "__main__":
    main()
