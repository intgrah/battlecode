from __future__ import annotations

import sys
from pathlib import Path

from scripts.analysis.constants import CONVEYOR_KINDS, TURRET_KINDS, Pos
from scripts.analysis.parse import extract_map_meta, parse
from scripts.analysis.snapshot import entity_kind


def chebyshev(a: Pos, b: Pos) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def trace(path: str) -> None:
    replay = parse(path)
    meta = extract_map_meta(replay)

    our_team = 0
    enemy_team = 1

    our_core = meta.core_pos.get(our_team)
    if our_core is None:
        print("no core for team 0")
        return

    entities: dict[int, tuple[int, str]] = {}
    entity_pos: dict[int, Pos] = {}
    building_at: dict[Pos, int] = {}
    our_infra: set[Pos] = set()

    raid_dist = 12

    events: list[str] = []

    for turn_idx, turn in enumerate(replay.turns):
        for u in turn.updates:
            kind = u.WhichOneof("kind")

            if kind == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                pos: Pos = (e.position.x, e.position.y)
                entities[e.id] = (e.team, ek)
                entity_pos[e.id] = pos
                if ek not in ("builder_bot", "marker"):
                    building_at[pos] = e.id
                if e.team == our_team and ek not in (
                    "builder_bot",
                    "marker",
                    "road",
                    "barrier",
                ):
                    our_infra.add(pos)
                if e.team == enemy_team and ek in TURRET_KINDS:
                    dist = chebyshev(pos, our_core)
                    near_infra = min(
                        (chebyshev(pos, p) for p in our_infra),
                        default=999,
                    )
                    events.append(
                        f"t{turn_idx:4d}  ENEMY TURRET PLANTED  @ {pos}  dist_core={dist}  dist_infra={near_infra}  type={ek}",
                    )

            elif kind == "move_builder_bot":
                mb = u.move_builder_bot
                new_pos: Pos = (mb.to.x, mb.to.y)
                if mb.id in entities:
                    team, ek = entities[mb.id]
                    entity_pos[mb.id] = new_pos
                    if team == enemy_team:
                        dist = chebyshev(new_pos, our_core)
                        if dist <= raid_dist:
                            near_infra = min(
                                (chebyshev(new_pos, p) for p in our_infra),
                                default=999,
                            )
                            if near_infra <= 2:
                                events.append(
                                    f"t{turn_idx:4d}  ENEMY BUILDER NEAR INFRA  @ {new_pos}  dist_core={dist}  dist_infra={near_infra}",
                                )

            elif kind == "remove_entity":
                eid = u.remove_entity.id
                if eid in entities:
                    team, ek = entities[eid]
                    pos = entity_pos.get(eid, (-1, -1))
                    if team == our_team and ek in CONVEYOR_KINDS:
                        events.append(
                            f"t{turn_idx:4d}  OUR CONVEYOR KILLED  @ {pos}  type={ek}",
                        )
                        our_infra.discard(pos)
                    elif team == our_team and ek == "harvester":
                        events.append(f"t{turn_idx:4d}  OUR HARVESTER KILLED @ {pos}")
                        our_infra.discard(pos)
                    elif team == enemy_team and ek in TURRET_KINDS:
                        events.append(
                            f"t{turn_idx:4d}  ENEMY TURRET REMOVED @ {pos}  type={ek}",
                        )
                    epos = entity_pos.pop(eid, None)
                    if epos and building_at.get(epos) == eid:
                        del building_at[epos]

    print(f"\n=== {Path(path).name} ===")
    if not events:
        print("  no notable events")
        return
    for e in events[:80]:
        print(" ", e)
    if len(events) > 80:
        print(f"  ... and {len(events) - 80} more")


def main() -> None:
    paths = sys.argv[1:] if len(sys.argv) > 1 else []
    if not paths:
        print("usage: python raid_trace.py <replay.replay26> ...")
        sys.exit(1)
    for p in paths:
        trace(p)


if __name__ == "__main__":
    main()
