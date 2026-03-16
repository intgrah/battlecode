import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proto"))
from cambc_pb2 import Entity, Replay

TEAM = {0: "A", 1: "B"}
TURRET_KINDS = {"gunner", "sentinel", "breach"}


def entity_kind(e: Entity) -> str:
    return e.WhichOneof("kind") or "unknown"


def parse(path: str) -> Replay:
    with open(path, "rb") as f:
        r = Replay()
        r.ParseFromString(f.read())
        return r


def collect(r: Replay) -> dict:
    total_turns = len(r.turns)
    placed = {0: Counter(), 1: Counter()}
    removed = {0: Counter(), 1: Counter()}
    entities = {}
    entity_pos = {}
    final_hp = {}
    moves = 0
    total_damage = {0: 0, 1: 0}
    damage_by_kind = {0: Counter(), 1: Counter()}
    kills = {0: 0, 1: 0}
    tle_count = {0: 0, 1: 0}
    resource_history = {0: [], 1: []}
    conveyor_moves_per_turn = []
    first_built = {0: {}, 1: {}}
    fire_count = {0: Counter(), 1: Counter()}
    exec_time_total = {0: 0, 1: 0}
    exec_time_samples = {0: 0, 1: 0}
    max_exec_time = {0: 0, 1: 0}
    pos_to_entity = {}

    for turn_idx, turn in enumerate(r.turns):
        conveyor_moves_this_turn = 0
        for u in turn.updates:
            kind = u.WhichOneof("kind")
            if kind == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                entities[e.id] = (e.team, ek, e.max_hp)
                entity_pos[e.id] = (e.position.x, e.position.y)
                pos_to_entity[(e.position.x, e.position.y)] = e.id
                final_hp[e.id] = e.hp
                placed[e.team][ek] += 1
                if ek not in first_built[e.team]:
                    first_built[e.team][ek] = turn_idx
            elif kind == "move_builder_bot":
                mb = u.move_builder_bot
                old_pos = entity_pos.get(mb.id)
                if old_pos:
                    pos_to_entity.pop(old_pos, None)
                new_pos = (mb.to.x, mb.to.y)
                entity_pos[mb.id] = new_pos
                pos_to_entity[new_pos] = mb.id
                moves += 1
            elif kind == "remove_entity":
                eid = u.remove_entity.id
                if eid in entities:
                    team, ek, _ = entities[eid]
                    removed[team][ek] += 1
                    if final_hp.get(eid, 0) <= 0:
                        kills[1 - team] += 1
                    old_pos = entity_pos.pop(eid, None)
                    if old_pos:
                        pos_to_entity.pop(old_pos, None)
                    final_hp.pop(eid, None)
            elif kind == "update_hp":
                eid = u.update_hp.id
                if eid in final_hp:
                    final_hp[eid] += u.update_hp.delta
                if u.update_hp.delta < 0 and eid in entities:
                    victim_team = entities[eid][0]
                    attacker_team = 1 - victim_team
                    total_damage[attacker_team] += abs(u.update_hp.delta)
            elif kind == "fire_turret":
                f = u.fire_turret
                fpos = (f.from_.x, f.from_.y)
                firer_id = pos_to_entity.get(fpos)
                if firer_id and firer_id in entities:
                    team, ek, _ = entities[firer_id]
                    fire_count[team][ek] += 1
                    dmg = abs(u.update_hp.delta) if hasattr(u, "update_hp") else 0
                    damage_by_kind[team][ek] += dmg
            elif kind == "bot_output":
                bo = u.bot_output
                if bo.id in entities:
                    team = entities[bo.id][0]
                    if bo.tled:
                        tle_count[team] += 1
                    if bo.exec_time_us > 0:
                        exec_time_total[team] += bo.exec_time_us
                        exec_time_samples[team] += 1
                        max_exec_time[team] = max(max_exec_time[team], bo.exec_time_us)
            elif kind == "update_players":
                p = u.update_players.players
                resource_history[0].append((turn_idx, p.a.titanium, p.a.axionite, p.a.titanium_collected, p.a.axionite_collected))
                resource_history[1].append((turn_idx, p.b.titanium, p.b.axionite, p.b.titanium_collected, p.b.axionite_collected))
            elif kind == "distribute_resources":
                conveyor_moves_this_turn += len(u.distribute_resources.moves)
        conveyor_moves_per_turn.append(conveyor_moves_this_turn)

    alive = {0: Counter(), 1: Counter()}
    for eid, hp in final_hp.items():
        if eid in entities and hp > 0:
            team, ek, _ = entities[eid]
            alive[team][ek] += 1

    return {
        "winner": TEAM.get(r.winner, "?") if r.HasField("winner") else "draw",
        "total_turns": total_turns,
        "placed": placed, "removed": removed, "alive": alive,
        "moves": moves, "total_damage": total_damage, "damage_by_kind": damage_by_kind,
        "kills": kills, "tle_count": tle_count, "fire_count": fire_count,
        "resource_history": resource_history, "conveyor_moves_per_turn": conveyor_moves_per_turn,
        "first_built": first_built,
        "exec_time_total": exec_time_total, "exec_time_samples": exec_time_samples,
        "max_exec_time": max_exec_time,
    }


def print_stats(s: dict) -> None:
    print(f"Winner: Team {s['winner']}  |  Turns: {s['total_turns']}")
    print()

    for t in (0, 1):
        label = TEAM[t]
        rh = s["resource_history"][t]
        final_ti = rh[-1][1] if rh else 0
        final_ax = rh[-1][2] if rh else 0
        final_ti_col = rh[-1][3] if rh else 0
        final_ax_col = rh[-1][4] if rh else 0

        print(f"--- Team {label} ---")
        print(f"  Resources:  Ti={final_ti}  Ax={final_ax}")
        print(f"  Collected:  Ti={final_ti_col}  Ax={final_ax_col}")
        print(f"  Damage dealt: {s['total_damage'][t]}  |  Kills: {s['kills'][t]}")
        if s["damage_by_kind"][t]:
            print(f"  Damage by type: {dict(s['damage_by_kind'][t])}")
        if s["fire_count"][t]:
            print(f"  Shots fired: {dict(s['fire_count'][t])}")
        print(f"  TLEs: {s['tle_count'][t]}")
        avg_us = s["exec_time_total"][t] / s["exec_time_samples"][t] if s["exec_time_samples"][t] else 0
        print(f"  CPU: avg={avg_us:.0f}us  max={s['max_exec_time'][t]}us")
        print(f"  Built: {dict(s['placed'][t])}")
        print(f"  Lost:  {dict(s['removed'][t])}")
        print(f"  Alive: {dict(s['alive'][t])}")

        milestones = [
            f"{k}@{s['first_built'][t][k]}"
            for k in ["harvester", "conveyor", "foundry", "gunner", "sentinel", "breach", "launcher"]
            if k in s["first_built"][t]
        ]
        if milestones:
            print(f"  Firsts: {', '.join(milestones)}")

        if rh and len(rh) >= 5:
            samples = [rh[i] for i in range(0, len(rh), max(1, len(rh) // 4))]
            if rh[-1] not in samples:
                samples.append(rh[-1])
            print("  Ti curve: " + " -> ".join(f"t{s[0]}:{s[1]}" for s in samples))

        print()

    total_conv = sum(s["conveyor_moves_per_turn"])
    n = s["total_turns"]
    avg_conv = total_conv / n if n else 0
    peak_conv = max(s["conveyor_moves_per_turn"]) if s["conveyor_moves_per_turn"] else 0
    print(f"Builder moves: {s['moves']}")
    print(f"Conveyor transfers: {total_conv} total  avg={avg_conv:.1f}/turn  peak={peak_conv}/turn")


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    print_stats(collect(parse(path)))


if __name__ == "__main__":
    main()
