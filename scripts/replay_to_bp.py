"""Extract a P1-team .bp blueprint from the final state of a replay.

Walks all turns, applies place/move/remove diffs, then dumps every team-A
non-builder, non-marker, non-road, non-barrier entity as a .bp line.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pkg/proto/src"))
from proto import cambc_pb2

DIR_NAMES = {
    1: "NORTH",
    2: "NORTHEAST",
    3: "EAST",
    4: "SOUTHEAST",
    5: "SOUTH",
    6: "SOUTHWEST",
    7: "WEST",
    8: "NORTHWEST",
}

KIND_NAMES = {
    "conveyor": "CONVEYOR",
    "splitter": "SPLITTER",
    "armoured_conveyor": "ARMOURED_CONVEYOR",
    "bridge": "BRIDGE",
    "harvester": "HARVESTER",
    "foundry": "FOUNDRY",
}

KEEP_KINDS = set(KIND_NAMES.keys())


def extract(replay_path: Path) -> str:
    r = cambc_pb2.Replay()
    r.ParseFromString(replay_path.read_bytes())

    placements: dict[int, dict] = {}

    for turn in r.turns:
        for u in turn.updates:
            kind = u.WhichOneof("kind")
            if kind == "place_entity":
                e = u.place_entity.entity
                ek = e.WhichOneof("kind") or "unknown"
                rec = {
                    "team": e.team,
                    "kind": ek,
                    "x": e.position.x,
                    "y": e.position.y,
                    "direction": None,
                    "bridge_target": None,
                }
                if ek == "conveyor" and e.HasField("conveyor"):
                    rec["direction"] = e.conveyor.direction
                elif ek == "armoured_conveyor" and e.HasField("armoured_conveyor"):
                    rec["direction"] = e.armoured_conveyor.direction
                elif ek == "splitter" and e.HasField("splitter"):
                    rec["direction"] = e.splitter.direction
                elif ek == "bridge" and e.HasField("bridge"):
                    rec["bridge_target"] = (e.bridge.target.x, e.bridge.target.y)
                elif ek == "gunner" and e.HasField("gunner"):
                    rec["direction"] = e.gunner.direction
                elif ek == "sentinel" and e.HasField("sentinel"):
                    rec["direction"] = e.sentinel.direction
                elif ek == "breach" and e.HasField("breach"):
                    rec["direction"] = e.breach.direction
                placements[e.id] = rec
            elif kind == "remove_entity":
                placements.pop(u.remove_entity.id, None)
            elif kind == "move_builder_bot":
                pass

    lines = []
    for rec in placements.values():
        if rec["team"] != 0:
            continue
        if rec["kind"] not in KEEP_KINDS:
            continue
        kind_str = KIND_NAMES[rec["kind"]]
        parts = [f"{rec['x']} {rec['y']} {kind_str}"]
        if rec["direction"] is not None and rec["direction"] in DIR_NAMES:
            parts.append(f"dir={DIR_NAMES[rec['direction']]}")
        if rec["bridge_target"] is not None:
            tx, ty = rec["bridge_target"]
            parts.append(f"bridge={tx},{ty}")
        lines.append(" ".join(parts))

    lines.sort()
    return "\n".join(lines) + "\n"


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: replay_to_bp.py REPLAY.replay26 OUT.bp")
        sys.exit(2)
    out = extract(Path(sys.argv[1]))
    Path(sys.argv[2]).write_text(out)
    print(f"wrote {len(out.splitlines())} placements to {sys.argv[2]}")


if __name__ == "__main__":
    main()
