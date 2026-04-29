"""Extract Pantheon's per-turn spawn-decision dataset from match replays
and fit a model to predict spawn vs no-spawn.

Usage:
    uv run python scripts/pantheon_spawn.py replays_remote/Blue_Dragon_vs_Pantheon_g*.replay26
"""

from __future__ import annotations

import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from scripts.replay import load_replay

PANTHEON_TEAM = 1
BUILDER_BASE_COST = 30
INITIAL_SCALE_MILLI = 1000

SCALE_CONTRIB = {
    "conveyor": 10,
    "splitter": 10,
    "armoured_conveyor": 10,
    "bridge": 100,
    "road": 5,
    "barrier": 10,
    "harvester": 50,
    "gunner": 100,
    "breach": 100,
    "launcher": 100,
    "sentinel": 200,
    "foundry": 500,
    "builder_bot": 200,
    "core": 0,
    "marker": 0,
}

ENTITY_KIND_FIELDS = (
    "builder_bot",
    "conveyor",
    "splitter",
    "armoured_conveyor",
    "bridge",
    "harvester",
    "foundry",
    "road",
    "barrier",
    "marker",
    "core",
    "gunner",
    "sentinel",
    "breach",
    "launcher",
)


def entity_kind(entity) -> str:
    for f in ENTITY_KIND_FIELDS:
        if entity.HasField(f):
            return f
    return "unknown"


@dataclass
class SpawnRow:
    replay: str
    turn: int
    ti: int
    scale_milli: int
    builder_cost: int
    cd: int
    rounds_since_spawn: int
    spawned_count: int
    live_units: int
    live_harvesters: int
    income_recent: float
    delivery_rate_16: float
    delivery_rate_100: float
    ti_collected: int
    spawned: bool


def extract(replay_path: str) -> list[SpawnRow]:
    replay = load_replay(replay_path)
    rows: list[SpawnRow] = []

    ti = 500
    ti_collected = 0
    scale_milli = INITIAL_SCALE_MILLI
    cd = 0
    spawned_count = 0
    last_spawn_turn = -(10**6)
    live_kinds: dict[str, int] = {}

    core_id: int | None = None
    entity_kind_by_id: dict[int, tuple[int, str]] = {}

    ti_history: deque[tuple[int, int]] = deque(maxlen=200)
    collected_history: deque[tuple[int, int]] = deque(maxlen=200)

    for turn_idx, turn in enumerate(replay.turns):
        spawned_this_turn = False

        ti_pre = ti
        scale_pre = scale_milli
        cd_pre = cd
        last_spawn_pre = last_spawn_turn
        spawned_count_pre = spawned_count

        for u in turn.updates:
            kind = u.WhichOneof("kind")
            if kind == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                entity_kind_by_id[e.id] = (e.team, ek)
                if e.team == PANTHEON_TEAM:
                    if ek == "core":
                        core_id = e.id
                    else:
                        live_kinds[ek] = live_kinds.get(ek, 0) + 1
                        scale_milli += SCALE_CONTRIB.get(ek, 0)
                    if ek == "builder_bot":
                        spawned_this_turn = True
                        spawned_count += 1
                        last_spawn_turn = turn_idx
            elif kind == "remove_entity":
                eid = u.remove_entity.id
                if eid in entity_kind_by_id:
                    team, ek = entity_kind_by_id.pop(eid)
                    if team == PANTHEON_TEAM and ek != "core":
                        live_kinds[ek] = live_kinds.get(ek, 0) - 1
                        scale_milli -= SCALE_CONTRIB.get(ek, 0)
            elif kind == "set_action_cooldown":
                if core_id is not None and u.set_action_cooldown.id == core_id:
                    cd = u.set_action_cooldown.value
            elif kind == "update_players":
                p = u.update_players.players
                player = p.b if PANTHEON_TEAM == 1 else p.a
                ti = player.titanium
                ti_collected = player.titanium_collected

        # Use pre-turn state as the features the core observed when deciding.
        rounds_since = turn_idx - last_spawn_pre if last_spawn_pre >= 0 else turn_idx
        builder_cost = BUILDER_BASE_COST * scale_pre // 1000
        live_units = sum(
            live_kinds.get(k, 0)
            for k in (
                "builder_bot",
                "harvester",
                "gunner",
                "sentinel",
                "breach",
                "launcher",
            )
        ) + (1 if core_id is not None else 0)
        live_harvesters = live_kinds.get("harvester", 0)

        ti_history.append((turn_idx, ti_pre))
        collected_history.append((turn_idx, ti_collected))
        if len(ti_history) >= 100:
            old_t, old_ti = ti_history[-100]
            income_recent = (ti_pre - old_ti) / max(1, turn_idx - old_t)
        else:
            income_recent = 0.0
        if len(collected_history) >= 16:
            old_t, old_c = collected_history[-16]
            delivery_rate_16 = (ti_collected - old_c) / max(1, turn_idx - old_t)
        else:
            delivery_rate_16 = 0.0
        if len(collected_history) >= 100:
            old_t, old_c = collected_history[-100]
            delivery_rate_100 = (ti_collected - old_c) / max(1, turn_idx - old_t)
        else:
            delivery_rate_100 = 0.0

        rows.append(
            SpawnRow(
                replay=Path(replay_path).stem,
                turn=turn_idx,
                ti=ti_pre,
                scale_milli=scale_pre,
                builder_cost=builder_cost,
                cd=cd_pre,
                rounds_since_spawn=rounds_since,
                spawned_count=spawned_count_pre,
                live_units=live_units,
                live_harvesters=live_harvesters,
                income_recent=income_recent,
                delivery_rate_16=delivery_rate_16,
                delivery_rate_100=delivery_rate_100,
                ti_collected=ti_collected,
                spawned=spawned_this_turn,
            )
        )

        # Decay cooldown at end of round (the engine does this between turns).
        if cd > 0:
            cd -= 1

    return rows


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: pantheon_spawn.py <replay1> [replay2 ...]")
        sys.exit(1)

    all_rows: list[SpawnRow] = []
    for path in sys.argv[1:]:
        rows = extract(path)
        all_rows.extend(rows)
        spawns = sum(1 for r in rows if r.spawned)
        print(f"{Path(path).name}: {len(rows)} turns, {spawns} spawns")

    out = Path("pantheon_spawn.csv")
    cols = list(SpawnRow.__dataclass_fields__.keys())
    with out.open("w") as f:
        f.write(",".join(cols) + "\n")
        for r in all_rows:
            f.write(",".join(str(getattr(r, c)) for c in cols) + "\n")
    print(f"\nWrote {len(all_rows)} rows to {out}")


if __name__ == "__main__":
    main()
