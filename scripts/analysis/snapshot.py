from __future__ import annotations

from .constants import DIR_DELTA, MOBILE_KINDS, TURRET_KINDS, Pos
from .types import EntityState, GameState, ResourceSnapshot


def entity_kind(e: object) -> str:
    return e.WhichOneof("kind") or "unknown"  # type: ignore[attr-defined]


def core_tiles(core_pos: dict[int, Pos], team: int) -> set[Pos]:
    cp = core_pos.get(team)
    if not cp:
        return set()
    return {(cp[0] + dx, cp[1] + dy) for dx in range(-1, 2) for dy in range(-1, 2)}


def conveyor_output(es: EntityState) -> Pos | None:
    if es.kind == "bridge" and es.bridge_target:
        return es.bridge_target
    if es.kind in ("conveyor", "armoured_conveyor", "splitter") and es.direction != 0:
        dx, dy = DIR_DELTA[es.direction]
        return (es.pos[0] + dx, es.pos[1] + dy)
    return None


def building_entity_at(state: GameState, pos: Pos) -> EntityState | None:
    eid = state.building_at.get(pos)
    if eid is not None and eid in state.entities:
        return state.entities[eid]
    return None


def team_entities(
    state: GameState,
    team: int,
    kind: str | None = None,
) -> list[EntityState]:
    return [
        e
        for e in state.entities.values()
        if e.team == team and (kind is None or e.kind == kind)
    ]


def sample_turns(total: int) -> list[int]:
    key = [0, 50, 100, 200, 300, 500, 750, 1000, 1250, 1500, 1750, total - 1]
    return sorted({t for t in key if 0 <= t < total})


def replay_snapshots(replay: object, turns: list[int] | None = None) -> list[GameState]:
    m = replay.map  # type: ignore[attr-defined]
    w, h = m.width, m.height
    tiles: list[list[int]] = [[0] * w for _ in range(h)]
    for y, row in enumerate(m.rows):
        for x, t in enumerate(row.tiles):
            tiles[y][x] = t

    core_pos: dict[int, Pos] = {}
    for c in m.cores:
        core_pos[c.team] = (c.position.x, c.position.y)

    entities: dict[int, EntityState] = {}
    building_at: dict[Pos, int] = {}
    resources: dict[int, ResourceSnapshot] = {
        0: ResourceSnapshot(0, 1000, 0, 0, 0),
        1: ResourceSnapshot(0, 1000, 0, 0, 0),
    }

    all_turns = replay.turns  # type: ignore[attr-defined]
    total = len(all_turns)
    if turns is None:
        turns = sample_turns(total)
    turn_set = set(turns)

    snapshots: list[GameState] = []
    flow_events: list[tuple[Pos, Pos]] = []

    for turn_idx, turn in enumerate(all_turns):
        flow_events.clear()

        for u in turn.updates:
            kind = u.WhichOneof("kind")
            if kind == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                pos: Pos = (e.position.x, e.position.y)
                direction = 0
                bridge_target: Pos | None = None
                if ek in ("conveyor", "armoured_conveyor", "splitter"):
                    direction = getattr(e, ek).direction
                elif ek == "bridge":
                    bridge_target = (e.bridge.target.x, e.bridge.target.y)
                elif ek in TURRET_KINDS and ek != "launcher":
                    direction = getattr(e, ek).direction
                es = EntityState(
                    id=e.id,
                    team=e.team,
                    kind=ek,
                    pos=pos,
                    hp=e.hp,
                    max_hp=e.max_hp,
                    direction=direction,
                    bridge_target=bridge_target,
                )
                entities[e.id] = es
                if ek not in MOBILE_KINDS:
                    building_at[pos] = e.id
            elif kind == "move_builder_bot":
                mb = u.move_builder_bot
                if mb.id in entities:
                    entities[mb.id].pos = (mb.to.x, mb.to.y)
            elif kind == "remove_entity":
                eid = u.remove_entity.id
                if eid in entities:
                    epos = entities[eid].pos
                    if building_at.get(epos) == eid:
                        del building_at[epos]
                    del entities[eid]
            elif kind == "update_hp":
                eid = u.update_hp.id
                if eid in entities:
                    entities[eid].hp += u.update_hp.delta
            elif kind == "update_players":
                p = u.update_players.players
                resources[0] = ResourceSnapshot(
                    turn_idx,
                    p.a.titanium,
                    p.a.axionite,
                    p.a.titanium_collected,
                    p.a.axionite_collected,
                )
                resources[1] = ResourceSnapshot(
                    turn_idx,
                    p.b.titanium,
                    p.b.axionite,
                    p.b.titanium_collected,
                    p.b.axionite_collected,
                )
            elif kind == "distribute_resources":
                for mv in u.distribute_resources.moves:
                    frm: Pos = (getattr(mv, "from").x, getattr(mv, "from").y)
                    to: Pos = (mv.to.x, mv.to.y)
                    flow_events.append((frm, to))

        if turn_idx in turn_set:
            snap = GameState(
                turn=turn_idx,
                width=w,
                height=h,
                tiles=[row[:] for row in tiles],
                core_pos=dict(core_pos),
                entities={
                    eid: EntityState(
                        id=e.id,
                        team=e.team,
                        kind=e.kind,
                        pos=e.pos,
                        hp=e.hp,
                        max_hp=e.max_hp,
                        direction=e.direction,
                        bridge_target=e.bridge_target,
                    )
                    for eid, e in entities.items()
                },
                building_at=dict(building_at),
                resources={
                    t: ResourceSnapshot(
                        r.turn,
                        r.titanium,
                        r.axionite,
                        r.titanium_collected,
                        r.axionite_collected,
                    )
                    for t, r in resources.items()
                },
                flow_events=list(flow_events),
            )
            snapshots.append(snap)

    return snapshots
