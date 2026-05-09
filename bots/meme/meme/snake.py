from __future__ import annotations

from typing import TYPE_CHECKING, Generator

from cambc import EntityType, Position, Team, Direction, ResourceType
from rust import Game, RawMem, EntityBuilderBot, EntitySentinel, EntityBridge, GameDiffPlaceEntity
from god_mode import GodMode

from apsp import extract_path

INF = 1_000_000_000

if TYPE_CHECKING:
    from main import Player
    from cambc import Controller

class Snake:

    def __init__(self, n: int) -> None:
        self.n = n
        self.initialised = False
        self.position: Position | None = None
        self.tail: list[int] = []
        self.visited: set[tuple[int, int]] = set()

    def _init(self, p: Player, pos: Position) -> Generator:
        
        if self.initialised:
            return
        
        self.position = pos

        assert p.core is not None

        for i in range(len(self.tail), self.n):
            bid = GodMode.build(p, EntityType.BARRIER, pos)
            assert bid is not None
            p.g.entities[bid].base.hp = INF
            self.tail.append(bid)
            yield

        self.initialised = True

    def update(self, p: Player) -> Generator:

        turret = p.turret_id

        assert p.apsp is not None and p.pnb is not None and p.core is not None and turret is not None

        core_pos = [Position(core.x, core.y) for core in p.map.cores]
        friendly_core, enemy_core = (core_pos[0], core_pos[1]) if p.map.cores[0].team == p.team else (core_pos[1], core_pos[0])

        w = p.map.width
        h = p.map.height

        if self.position is None or not self.initialised:
            self.position = None
            furthest = 0
            for pos in [Position(0, 0), Position(w - 1, 0), Position(0, h - 1), Position(w - 1, h - 1)]:
                dist = enemy_core.distance_squared(pos)
                if dist > furthest and pos.distance_squared(friendly_core) > 2:
                    furthest = dist
                    self.position = pos
            assert self.position is not None, "position is none"

            yield from self._init(p, self.position)

        if self.position.distance_squared(enemy_core) <= 20:
            _SURROUND_DELTAS = (
                (-2, -2), (-1, -2), (0, -2), (1, -2), (2, -2),
                (-2, -1),                               (2, -1),
                (-2,  0),                               (2,  0),
                (-2,  1),                               (2,  1),
                (-2,  2), (-1,  2), (0,  2), (1,  2), (2,  2),
            )
            attack_positions = [
                Position(enemy_core.x + dx, enemy_core.y + dy)
                for dx, dy in _SURROUND_DELTAS
                if 0 <= enemy_core.x + dx < w and 0 <= enemy_core.y + dy < h
            ]
            pos_key = (self.position.x, self.position.y)
            if any(pos_key == (ap.x, ap.y) for ap in attack_positions):
                self.visited.add(pos_key)
            unvisited = [ap for ap in attack_positions if (ap.x, ap.y) not in self.visited]
            if not unvisited:
                return
            pos = self.position
            next_pos = min(unvisited, key=lambda ap: (ap.distance_squared(pos), -ap.distance_squared(enemy_core)))
        else:
            path = extract_path(p.apsp, p.pnb, p.map.width, (self.position.x, self.position.y), (enemy_core.x, enemy_core.y))

            if len(path) < 2:
                next_pos = self.position
                dir = next_pos.direction_to(enemy_core)
                next_pos = next_pos.add(dir)
            else:
                next_pos = path[1]

        yield

        self.position = next_pos

        if any(next_pos.distance_squared(p) <= 2 for p in core_pos):
            next_pos = self.position.add(self.position.direction_to(enemy_core))
            if any(next_pos.distance_squared(p) <= 2 for p in core_pos):
                return

        if all(next_pos.distance_squared(p) > 2 for p in core_pos):
            GodMode.move(p, self.tail[0], next_pos)
            self.tail = self.tail[1:] + [self.tail[0]]
            yield