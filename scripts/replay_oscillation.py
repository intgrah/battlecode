"""Detect position oscillation cycles in builder movement."""

import sys
from collections import defaultdict
from pathlib import Path

from proto.cambc_pb2 import Entity, Replay


def entity_kind(e: Entity) -> str:
    return e.WhichOneof("kind") or "unknown"


def analyze_oscillation(path: str) -> None:
    with Path(path).open("rb") as f:
        r = Replay()
        r.ParseFromString(f.read())

    entities = {}
    builder_pos = {}
    builder_pos_history = defaultdict(list)
    dead = set()

    for _turn_idx, turn in enumerate(r.turns):
        for u in turn.updates:
            k = u.WhichOneof("kind")
            if k == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                entities[e.id] = (e.team, ek)
                if ek == "builder_bot":
                    builder_pos[e.id] = (e.position.x, e.position.y)
            elif k == "move_builder_bot":
                m = u.move_builder_bot
                builder_pos[m.id] = (m.to.x, m.to.y)
            elif k == "remove_entity":
                dead.add(u.remove_entity.id)
        for bid, (_team, kind) in entities.items():
            if kind == "builder_bot" and bid in builder_pos and bid not in dead:
                builder_pos_history[bid].append(builder_pos[bid])

    total_turns = len(r.turns)
    w, h = r.map.width, r.map.height
    print(f"Oscillation Report  |  {total_turns} turns  |  {w}x{h}")

    for team_id in (0, 1):
        team_bots = sorted(
            bid
            for bid, (team, kind) in entities.items()
            if team == team_id and kind == "builder_bot"
        )
        if not team_bots:
            continue
        team_name = "A" if team_id == 0 else "B"
        print(f"\n--- Team {team_name} ({len(team_bots)} builders) ---")

        total_oscillating_turns = 0
        total_bot_turns = 0

        for bid in team_bots:
            positions = builder_pos_history.get(bid, [])
            if len(positions) < 10:
                continue
            total_bot_turns += len(positions)

            worst_period = 0
            worst_repeat = 0
            worst_start = 0
            worst_seq = []

            for period in range(2, 25):
                max_repeat = 0
                best_start = 0
                best_seq = []
                for i in range(len(positions) - period * 2):
                    seq = tuple(positions[i : i + period])
                    distinct = len(set(seq))
                    if distinct < 2:
                        continue
                    j = i + period
                    repeats = 0
                    while (
                        j + period <= len(positions)
                        and tuple(positions[j : j + period]) == seq
                    ):
                        repeats += 1
                        j += period
                    if repeats > max_repeat:
                        max_repeat = repeats
                        best_start = i
                        best_seq = list(seq)
                if max_repeat > worst_repeat:
                    worst_repeat = max_repeat
                    worst_period = period
                    worst_start = best_start
                    worst_seq = best_seq

            if worst_repeat >= 3:
                osc_turns = worst_repeat * worst_period
                total_oscillating_turns += osc_turns
                pct = 100 * osc_turns / len(positions)
                print(
                    f"  Bot {bid}: period={worst_period} x{worst_repeat + 1} "
                    f"from t~{worst_start} ({osc_turns} turns, {pct:.0f}%) "
                    f"seq={worst_seq[:6]}",
                )
            else:
                print(f"  Bot {bid}: no significant oscillation")

        if total_bot_turns > 0:
            pct = 100 * total_oscillating_turns / total_bot_turns
            print(
                f"  Total oscillating: {total_oscillating_turns}/{total_bot_turns} turns ({pct:.0f}%)",
            )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: replay_oscillation.py <replay_path>")
        sys.exit(1)
    analyze_oscillation(sys.argv[1])
