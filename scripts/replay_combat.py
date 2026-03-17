import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proto"))
from cambc_pb2 import Entity, Replay

TEAM = {0: "A", 1: "B"}
TURRET_KINDS = {"gunner", "sentinel", "breach", "launcher"}


def entity_kind(e: Entity) -> str:
    return e.WhichOneof("kind") or "unknown"


def parse(path: str) -> Replay:
    with Path(path).open("rb") as f:
        r = Replay()
        r.ParseFromString(f.read())
        return r


def analyze_combat(r: Replay) -> None:
    total_turns = len(r.turns)
    w, h = r.map.width, r.map.height

    entities = {}
    entity_pos = {}
    entity_team = {}
    pos_to_entity = {}

    turrets_built = {0: defaultdict(int), 1: defaultdict(int)}
    turrets_alive = {0: defaultdict(int), 1: defaultdict(int)}
    turret_fire_count = {0: defaultdict(int), 1: defaultdict(int)}

    self_destructs = {0: [], 1: []}
    damage_events = {0: [], 1: []}
    damaged_this_turn = set()

    buildings_destroyed = {0: defaultdict(int), 1: defaultdict(int)}
    builder_losses = {0: 0, 1: 0}
    builder_kills = {0: 0, 1: 0}

    raid_arrivals = {0: [], 1: []}

    core_pos = {0: None, 1: None}
    for c in r.map.cores:
        core_pos[c.team] = (c.position.x, c.position.y)

    for turn_idx, turn in enumerate(r.turns):
        damaged_this_turn.clear()
        for u in turn.updates:
            kind = u.WhichOneof("kind")
            if kind == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                team = e.team
                entities[e.id] = (team, ek, e.max_hp)
                entity_pos[e.id] = (e.position.x, e.position.y)
                entity_team[e.id] = team
                pos_to_entity[(e.position.x, e.position.y)] = e.id
                if ek in TURRET_KINDS:
                    turrets_built[team][ek] += 1
                    turrets_alive[team][ek] += 1
            elif kind == "move_builder_bot":
                mb = u.move_builder_bot
                old = entity_pos.get(mb.id)
                if old:
                    pos_to_entity.pop(old, None)
                new = (mb.to.x, mb.to.y)
                entity_pos[mb.id] = new
                pos_to_entity[new] = mb.id

                if mb.id in entity_team:
                    team = entity_team[mb.id]
                    enemy_core = core_pos[1 - team]
                    if enemy_core:
                        dx = abs(new[0] - enemy_core[0])
                        dy = abs(new[1] - enemy_core[1])
                        if dx <= 5 and dy <= 5:
                            raid_arrivals[team].append(turn_idx)
            elif kind == "remove_entity":
                eid = u.remove_entity.id
                if eid in entities:
                    team, ek, _ = entities[eid]
                    if ek in TURRET_KINDS:
                        turrets_alive[team][ek] -= 1
                    if ek == "builder_bot":
                        builder_losses[team] += 1
                        epos = entity_pos.get(eid)
                        if eid in damaged_this_turn:
                            builder_kills[1 - team] += 1
                        elif epos:
                            self_destructs[team].append((turn_idx, epos))
                    elif ek != "marker" and eid in damaged_this_turn:
                        buildings_destroyed[1 - team][ek] += 1
                    old = entity_pos.pop(eid, None)
                    if old:
                        pos_to_entity.pop(old, None)
            elif kind == "update_hp":
                eid = u.update_hp.id
                if u.update_hp.delta < 0 and eid in entities:
                    damaged_this_turn.add(eid)
                    victim_team = entities[eid][0]
                    attacker_team = 1 - victim_team
                    dmg = abs(u.update_hp.delta)
                    victim_type = entities[eid][1]
                    damage_events[attacker_team].append((turn_idx, dmg, victim_type))
            elif kind == "fire_turret":
                f = u.fire_turret
                f_from = getattr(f, "from")
                fpos = (f_from.x, f_from.y)
                firer_id = pos_to_entity.get(fpos)
                if firer_id and firer_id in entities:
                    team, ek, _ = entities[firer_id]
                    turret_fire_count[team][ek] += 1

    print(f"Combat Report  |  {total_turns} turns  |  {w}x{h}")
    print()

    for t in (0, 1):
        label = TEAM[t]
        print(f"--- Team {label} ---")

        total_dmg = sum(d for _, d, _ in damage_events[t])
        print(f"  Total damage dealt: {total_dmg}")

        if damage_events[t]:
            dmg_by_victim = defaultdict(int)
            for _, d, vtype in damage_events[t]:
                dmg_by_victim[vtype] += d
            print(f"  Damage by target: {dict(dmg_by_victim)}")

            first_dmg = damage_events[t][0][0]
            last_dmg = damage_events[t][-1][0]
            print(f"  Damage window: t{first_dmg} - t{last_dmg}")

            window = 100
            peak_dps = 0
            dmg_timeline = [0] * total_turns
            for turn, d, _ in damage_events[t]:
                dmg_timeline[turn] += d
            for i in range(window, total_turns):
                dps = sum(dmg_timeline[i - window : i]) / window
                peak_dps = max(peak_dps, dps)
            print(f"  Peak DPS (100t window): {peak_dps:.1f}/t")

        sd_list = self_destructs[t]
        print(f"  Self-destructs: {len(sd_list)}")
        if sd_list:
            sd_turns = [s[0] for s in sd_list]
            print(f"  SD window: t{min(sd_turns)} - t{max(sd_turns)}")

        print(f"  Builder losses: {builder_losses[t]} (killed: {builder_kills[t]})")

        if turrets_built[t]:
            print(f"  Turrets built: {dict(turrets_built[t])}")
            print(f"  Turret shots: {dict(turret_fire_count[t])}")
            total_built = sum(turrets_built[t].values())
            total_shots = sum(turret_fire_count[t].values())
            if total_built > 0:
                print(f"  Shots per turret: {total_shots / total_built:.1f}")

        destroyed = buildings_destroyed[t]
        if destroyed:
            print(f"  Enemy buildings destroyed: {dict(destroyed)}")

        raids = raid_arrivals[t]
        if raids:
            print(f"  Raids near enemy core: {len(raids)} (first t{raids[0]})")

        print()


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    analyze_combat(parse(path))


if __name__ == "__main__":
    main()
