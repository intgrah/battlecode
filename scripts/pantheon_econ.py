"""Per Pantheon-game stats: first ax-harvester, first foundry, first ax delivery."""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from scripts.analysis.parse import parse
from scripts.analysis.snapshot import entity_kind

SCALE_PCT: dict[str, float] = {
    "builder_bot": 20.0,
    "conveyor": 1.0,
    "splitter": 1.0,
    "bridge": 10.0,
    "armoured_conveyor": 1.0,
    "harvester": 5.0,
    "foundry": 50.0,
    "road": 0.5,
    "barrier": 1.0,
    "gunner": 10.0,
    "sentinel": 20.0,
    "breach": 10.0,
    "launcher": 10.0,
    "core": 0.0,
    "marker": 0.0,
}


def analyse(path: Path, pantheon_team: int) -> dict | None:
    replay = parse(str(path))
    m = replay.map
    ax_tiles: set[tuple[int, int]] = set()
    for y, row in enumerate(m.rows):
        for x, t in enumerate(row.tiles):
            if t == 3:
                ax_tiles.add((x, y))

    scale_pct: float = 0.0
    entity_kind_by_id: dict[int, str] = {}
    entity_team_by_id: dict[int, int] = {}
    titanium = [500, 500]
    ax_collected = [0, 0]

    first_ax_harv: tuple[int, int, float] | None = None
    first_foundry: tuple[int, int, float] | None = None
    first_ax_delivery: tuple[int, int, float] | None = None

    for turn_idx, turn in enumerate(replay.turns):
        for u in turn.updates:
            kind = u.WhichOneof("kind")
            if kind == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                team = e.team
                pos = (e.position.x, e.position.y)
                entity_kind_by_id[e.id] = ek
                entity_team_by_id[e.id] = team
                if team == pantheon_team and ek in SCALE_PCT:
                    scale_pct += SCALE_PCT[ek]
                if team == pantheon_team:
                    if (
                        ek == "harvester"
                        and e.harvester.resource_type == 2
                        and first_ax_harv is None
                    ):
                        first_ax_harv = (
                            turn_idx,
                            titanium[team],
                            1.0 + scale_pct / 100.0,
                        )
                    if (
                        ek == "harvester"
                        and pos in ax_tiles
                        and not hasattr(analyse, "_seen")
                    ):
                        pass
                    if ek == "foundry" and first_foundry is None:
                        first_foundry = (
                            turn_idx,
                            titanium[team],
                            1.0 + scale_pct / 100.0,
                        )
            elif kind == "remove_entity":
                eid = u.remove_entity.id
                ek = entity_kind_by_id.pop(eid, None)
                team = entity_team_by_id.pop(eid, None)
                if team == pantheon_team and ek in SCALE_PCT:
                    scale_pct -= SCALE_PCT[ek]
            elif kind == "update_players":
                p = u.update_players.players
                titanium[0] = p.a.titanium
                titanium[1] = p.b.titanium
                for t, pl in ((0, p.a), (1, p.b)):
                    if (
                        t == pantheon_team
                        and pl.axionite_collected > ax_collected[t]
                        and first_ax_delivery is None
                    ):
                        first_ax_delivery = (
                            turn_idx,
                            titanium[t],
                            1.0 + scale_pct / 100.0,
                        )
                    ax_collected[t] = pl.axionite_collected

    return {
        "path": path.name,
        "first_ax_harv": first_ax_harv,
        "first_foundry": first_foundry,
        "first_ax_delivery": first_ax_delivery,
    }


def stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "min": min(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
    }


def main() -> None:
    mapping_json = sys.argv[1]
    replay_dir = Path(sys.argv[2])
    mapping: dict[str, int] = json.loads(Path(mapping_json).read_text())

    rows = []
    for f in sorted(replay_dir.glob("*.replay26")):
        match_id = f.name.split("_game_")[0]
        if match_id not in mapping:
            continue
        team = mapping[match_id]
        rows.append(analyse(f, team))

    delivery_before_harv = [
        r
        for r in rows
        if r["first_ax_delivery"] is not None
        and (
            r["first_ax_harv"] is None
            or r["first_ax_delivery"][0] < r["first_ax_harv"][0]
        )
    ]
    print(
        f"Games where ax delivered before own ax harvester: {len(delivery_before_harv)}"
    )
    for r in delivery_before_harv[:10]:
        h = r["first_ax_harv"][0] if r["first_ax_harv"] else None
        print(f"  {r['path']}: del={r['first_ax_delivery'][0]} harv={h}")
    foundry_no_harv = [
        r for r in rows if r["first_foundry"] is not None and r["first_ax_harv"] is None
    ]
    print(f"Games with foundry but no ax harvester: {len(foundry_no_harv)}")
    foundry_before_harv = [
        r
        for r in rows
        if r["first_foundry"] is not None
        and r["first_ax_harv"] is not None
        and r["first_foundry"][0] < r["first_ax_harv"][0]
    ]
    print(
        f"Games where foundry built before first ax harvester: {len(foundry_before_harv)}"
    )
    for r in foundry_no_harv:
        print(f"  no-harv: {r['path']}: foundry round={r['first_foundry'][0]}")
    for label in ("first_ax_harv", "first_foundry", "first_ax_delivery"):
        rounds = [r[label][0] for r in rows if r[label] is not None]
        ti = [r[label][1] for r in rows if r[label] is not None]
        scale = [r[label][2] for r in rows if r[label] is not None]
        print(f"=== {label} ({len(rounds)}/{len(rows)} games) ===")
        print(f"  round:    {stats(rounds)}")
        print(f"  titanium: {stats(ti)}")
        print(f"  scale:    {stats(scale)}")


if __name__ == "__main__":
    main()
