import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "proto"))
from cambc_pb2 import Entity, Replay

DIR_DELTA = {
    0: (0, 0), 1: (0, -1), 2: (1, -1), 3: (1, 0), 4: (1, 1),
    5: (0, 1), 6: (-1, 1), 7: (-1, 0), 8: (-1, -1),
}

MOBILE_KINDS = {"builder_bot"}
CONVEYOR_KINDS = {"conveyor", "armoured_conveyor", "splitter", "bridge"}
TURRET_KINDS = {"gunner", "sentinel", "breach", "launcher"}
VISION_SQ = {
    "builder_bot": 20, "core": 36,
    "gunner": 13, "sentinel": 32, "breach": 10, "launcher": 26,
}
ATTACK_SQ = {"gunner": 13, "sentinel": 32, "breach": 5, "launcher": 26}


def entity_kind(e: Entity) -> str:
    return e.WhichOneof("kind") or "unknown"


def parse(path: str) -> Replay:
    with Path(path).open("rb") as f:
        r = Replay()
        r.ParseFromString(f.read())
        return r


@dataclass
class EntityState:
    id: int
    team: int
    kind: str
    pos: tuple[int, int]
    hp: int
    max_hp: int
    direction: int = 0
    bridge_target: tuple[int, int] | None = None


@dataclass
class GameState:
    turn: int
    width: int
    height: int
    tiles: list[list[int]]
    core_pos: dict[int, tuple[int, int]]
    entities: dict[int, EntityState]
    building_at: dict[tuple[int, int], int]
    resources: dict[int, dict]
    flow_events: list[tuple[tuple[int, int], tuple[int, int]]]

    def team_entities(self, team: int, kind: str | None = None) -> list[EntityState]:
        return [
            e for e in self.entities.values()
            if e.team == team and (kind is None or e.kind == kind)
        ]

    def passable(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height and self.tiles[y][x] != 1

    def ore_tiles(self) -> list[tuple[int, int, str]]:
        ores = []
        for y in range(self.height):
            for x in range(self.width):
                t = self.tiles[y][x]
                if t == 2:
                    ores.append((x, y, "titanium"))
                elif t == 3:
                    ores.append((x, y, "axionite"))
        return ores

    def core_tiles(self, team: int) -> set[tuple[int, int]]:
        cp = self.core_pos.get(team)
        if not cp:
            return set()
        return {(cp[0] + dx, cp[1] + dy) for dx in range(-1, 2) for dy in range(-1, 2)}

    def conveyor_output(self, e: EntityState) -> tuple[int, int] | None:
        if e.kind == "bridge" and e.bridge_target:
            return e.bridge_target
        if e.kind in ("conveyor", "armoured_conveyor", "splitter") and e.direction != 0:
            dx, dy = DIR_DELTA[e.direction]
            return (e.pos[0] + dx, e.pos[1] + dy)
        return None

    def building_entity_at(self, pos: tuple[int, int]) -> EntityState | None:
        eid = self.building_at.get(pos)
        if eid and eid in self.entities:
            return self.entities[eid]
        return None


def replay_snapshots(replay: Replay, sample_turns: list[int] | None = None) -> list[GameState]:
    m = replay.map
    w, h = m.width, m.height
    tiles = [[0] * w for _ in range(h)]
    for y, row in enumerate(m.rows):
        for x, t in enumerate(row.tiles):
            tiles[y][x] = t

    core_pos = {}
    for c in m.cores:
        core_pos[c.team] = (c.position.x, c.position.y)

    entities: dict[int, EntityState] = {}
    building_at: dict[tuple[int, int], int] = {}
    resources = {0: {"ti": 1000, "ax": 0, "ti_col": 0, "ax_col": 0},
                 1: {"ti": 1000, "ax": 0, "ti_col": 0, "ax_col": 0}}

    if sample_turns is None:
        total = len(replay.turns)
        sample_turns = sorted(set(
            [0, total - 1]
            + list(range(0, total, max(1, total // 10)))
        ))

    sample_set = set(sample_turns)
    snapshots = []
    flow_events: list[tuple[tuple[int, int], tuple[int, int]]] = []

    for turn_idx, turn in enumerate(replay.turns):
        flow_events.clear()

        for u in turn.updates:
            kind = u.WhichOneof("kind")
            if kind == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                pos = (e.position.x, e.position.y)
                direction = 0
                bridge_target = None
                if ek in ("conveyor", "armoured_conveyor", "splitter"):
                    sub = getattr(e, ek)
                    direction = sub.direction
                elif ek == "bridge":
                    bridge_target = (e.bridge.target.x, e.bridge.target.y)
                elif ek in TURRET_KINDS and ek != "launcher":
                    sub = getattr(e, ek)
                    direction = sub.direction
                es = EntityState(
                    id=e.id, team=e.team, kind=ek, pos=pos,
                    hp=e.hp, max_hp=e.max_hp, direction=direction,
                    bridge_target=bridge_target,
                )
                entities[e.id] = es
                if ek not in MOBILE_KINDS:
                    building_at[pos] = e.id
            elif kind == "move_builder_bot":
                mb = u.move_builder_bot
                if mb.id in entities:
                    new = (mb.to.x, mb.to.y)
                    entities[mb.id].pos = new
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
                resources[0] = {"ti": p.a.titanium, "ax": p.a.axionite,
                                "ti_col": p.a.titanium_collected, "ax_col": p.a.axionite_collected}
                resources[1] = {"ti": p.b.titanium, "ax": p.b.axionite,
                                "ti_col": p.b.titanium_collected, "ax_col": p.b.axionite_collected}
            elif kind == "distribute_resources":
                for mv in u.distribute_resources.moves:
                    frm = (getattr(mv, "from").x, getattr(mv, "from").y)
                    to = (mv.to.x, mv.to.y)
                    flow_events.append((frm, to))

        if turn_idx in sample_set:
            snap = GameState(
                turn=turn_idx, width=w, height=h,
                tiles=[row[:] for row in tiles],
                core_pos=dict(core_pos),
                entities={eid: EntityState(
                    id=e.id, team=e.team, kind=e.kind, pos=e.pos,
                    hp=e.hp, max_hp=e.max_hp, direction=e.direction,
                    bridge_target=e.bridge_target,
                ) for eid, e in entities.items()},
                building_at=dict(building_at),
                resources={t: dict(r) for t, r in resources.items()},
                flow_events=list(flow_events),
            )
            snapshots.append(snap)

    return snapshots


def full_replay(replay: Replay) -> list[GameState]:
    return replay_snapshots(replay, list(range(len(replay.turns))))
