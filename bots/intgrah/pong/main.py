from __future__ import annotations

import os
import sys
from collections import deque

from cambc import (
    Controller,
    Direction,
    EntityType,
    GameError,
    Position,
)

LOG = bool(os.environ.get("DEBUG_LOG"))


def log(msg: str) -> None:
    if LOG:
        print(msg, file=sys.stderr, flush=True)


SCHEDULE: list[tuple[int, str, int, int, object]] = [
    (0, "FOUNDRY", 8, 6, None),
    (1, "FOUNDRY", 6, 8, None),
    (1, "BRIDGE", 4, 9, (7, 9)),
    (2, "BRIDGE", 6, 11, (6, 8)),
    (2, "BRIDGE", 5, 6, (6, 8)),
    (3, "HARVESTER", 5, 7, None),
    (3, "HARVESTER", 4, 6, None),
    (4, "CONVEYOR", 10, 8, "WEST"),
    (4, "CONVEYOR", 7, 10, "NORTH"),
    (5, "CONVEYOR", 10, 9, "WEST"),
    (5, "CONVEYOR", 11, 8, "WEST"),
    (6, "CONVEYOR", 8, 5, "SOUTH"),
    (24, "HARVESTER", 7, 5, None),
    (28, "CONVEYOR", 5, 8, "EAST"),
    (32, "CONVEYOR", 9, 6, "WEST"),
    (36, "CONVEYOR", 10, 6, "WEST"),
    (40, "CONVEYOR", 8, 4, "SOUTH"),
    (40, "CONVEYOR", 11, 9, "NORTH"),
    (44, "CONVEYOR", 10, 10, "NORTH"),
    (48, "CONVEYOR", 4, 8, "EAST"),
    (72, "HARVESTER", 4, 7, None),
    (76, "CONVEYOR", 6, 10, "EAST"),
    (80, "CONVEYOR", 5, 10, "EAST"),
    (84, "CONVEYOR", 3, 8, "EAST"),
    (88, "CONVEYOR", 7, 4, "EAST"),
    (88, "CONVEYOR", 11, 6, "WEST"),
    (92, "CONVEYOR", 10, 11, "NORTH"),
    (116, "BRIDGE", 10, 14, (10, 11)),
    (120, "CONVEYOR", 11, 10, "NORTH"),
    (124, "CONVEYOR", 6, 4, "EAST"),
    (152, "HARVESTER", 6, 5, None),
    (176, "HARVESTER", 5, 4, None),
    (180, "CONVEYOR", 12, 6, "WEST"),
    (184, "CONVEYOR", 3, 7, "SOUTH"),
    (208, "HARVESTER", 3, 6, None),
    (212, "CONVEYOR", 11, 11, "NORTH"),
    (240, "BRIDGE", 11, 14, (11, 11)),
    (244, "CONVEYOR", 3, 9, "EAST"),
    (300, "FOUNDRY", 2, 9, None),
    (304, "CONVEYOR", 4, 10, "EAST"),
    (308, "CONVEYOR", 6, 12, "NORTH"),
    (340, "BRIDGE", 7, 13, (6, 12)),
    (372, "HARVESTER", 7, 12, None),
    (408, "HARVESTER", 8, 13, None),
    (440, "HARVESTER", 5, 12, None),
    (476, "HARVESTER", 6, 13, None),
    (477, "CONVEYOR", 3, 10, "EAST"),
    (479, "BRIDGE", 0, 10, (3, 10)),
    (481, "BRIDGE", 0, 13, (0, 10)),
    (481, "CONVEYOR", 6, 3, "SOUTH"),
    (482, "CONVEYOR", 13, 6, "WEST"),
    (482, "CONVEYOR", 13, 7, "NORTH"),
    (483, "CONVEYOR", 13, 8, "NORTH"),
    (483, "CONVEYOR", 13, 9, "NORTH"),
    (484, "CONVEYOR", 13, 10, "NORTH"),
    (484, "CONVEYOR", 5, 3, "EAST"),
    (485, "HARVESTER", 4, 3, None),
    (485, "CONVEYOR", 1, 9, "EAST"),
    (486, "CONVEYOR", 13, 11, "NORTH"),
    (488, "HARVESTER", 13, 12, None),
    (488, "CONVEYOR", 2, 10, "NORTH"),
    (489, "CONVEYOR", 2, 11, "NORTH"),
    (489, "CONVEYOR", 0, 9, "EAST"),
    (490, "CONVEYOR", 0, 8, "SOUTH"),
    (490, "CONVEYOR", 0, 7, "SOUTH"),
    (491, "CONVEYOR", 10, 15, "NORTH"),
    (494, "FOUNDRY", 10, 16, None),
    (497, "BRIDGE", 10, 19, (10, 16)),
    (497, "CONVEYOR", 9, 16, "EAST"),
    (500, "HARVESTER", 8, 16, None),
    (502, "HARVESTER", 9, 17, None),
    (503, "CONVEYOR", 14, 11, "WEST"),
    (503, "CONVEYOR", 15, 11, "WEST"),
    (505, "HARVESTER", 15, 12, None),
    (506, "CONVEYOR", 12, 14, "WEST"),
    (506, "CONVEYOR", 0, 6, "SOUTH"),
    (509, "BRIDGE", 2, 4, (0, 6)),
    (512, "HARVESTER", 2, 5, None),
    (512, "CONVEYOR", 3, 4, "WEST"),
    (515, "HARVESTER", 3, 5, None),
    (517, "HARVESTER", 4, 4, None),
    (520, "HARVESTER", 3, 3, None),
    (520, "CONVEYOR", 2, 12, "NORTH"),
    (523, "BRIDGE", 3, 13, (2, 12)),
    (526, "HARVESTER", 3, 12, None),
    (529, "HARVESTER", 4, 13, None),
    (531, "HARVESTER", 1, 12, None),
    (532, "HARVESTER", 2, 13, None),
    (532, "CONVEYOR", 11, 16, "WEST"),
    (534, "HARVESTER", 12, 16, None),
    (535, "HARVESTER", 11, 17, None),
    (536, "CONVEYOR", 13, 14, "WEST"),
    (536, "CONVEYOR", 16, 11, "WEST"),
    (537, "CONVEYOR", 17, 11, "WEST"),
    (537, "HARVESTER", 17, 12, None),
    (538, "CONVEYOR", 14, 14, "WEST"),
    (538, "CONVEYOR", 15, 14, "WEST"),
    (539, "CONVEYOR", 18, 11, "WEST"),
    (539, "CONVEYOR", 0, 14, "NORTH"),
    (540, "CONVEYOR", 19, 11, "WEST"),
    (540, "HARVESTER", 19, 12, None),
    (541, "CONVEYOR", 10, 20, "NORTH"),
    (541, "HARVESTER", 9, 20, None),
    (543, "HARVESTER", 11, 20, None),
    (543, "CONVEYOR", 16, 14, "WEST"),
    (544, "CONVEYOR", 17, 14, "WEST"),
    (544, "CONVEYOR", 10, 21, "NORTH"),
    (545, "CONVEYOR", 9, 21, "EAST"),
    (545, "HARVESTER", 8, 21, None),
    (546, "CONVEYOR", 0, 15, "NORTH"),
    (546, "BRIDGE", 3, 15, (0, 15)),
    (548, "FOUNDRY", 3, 16, None),
    (549, "BRIDGE", 3, 19, (3, 16)),
    (550, "HARVESTER", 3, 20, None),
    (550, "CONVEYOR", 4, 16, "WEST"),
    (551, "HARVESTER", 5, 16, None),
    (552, "HARVESTER", 4, 17, None),
    (552, "CONVEYOR", 2, 16, "EAST"),
    (553, "HARVESTER", 1, 16, None),
    (554, "HARVESTER", 2, 17, None),
    (554, "CONVEYOR", 4, 19, "WEST"),
    (555, "CONVEYOR", 5, 19, "WEST"),
    (555, "HARVESTER", 5, 20, None),
    (556, "CONVEYOR", 6, 19, "WEST"),
    (556, "CONVEYOR", 7, 19, "WEST"),
    (557, "HARVESTER", 7, 20, None),
    (557, "CONVEYOR", 17, 15, "NORTH"),
    (559, "FOUNDRY", 17, 16, None),
    (560, "BRIDGE", 17, 19, (17, 16)),
    (561, "HARVESTER", 17, 20, None),
    (561, "CONVEYOR", 16, 16, "EAST"),
    (562, "HARVESTER", 15, 16, None),
    (563, "HARVESTER", 16, 17, None),
    (563, "CONVEYOR", 11, 21, "WEST"),
    (564, "HARVESTER", 12, 21, None),
    (564, "CONVEYOR", 2, 19, "EAST"),
    (565, "CONVEYOR", 1, 19, "EAST"),
    (565, "HARVESTER", 1, 20, None),
    (566, "CONVEYOR", 18, 16, "WEST"),
    (566, "HARVESTER", 18, 17, None),
    (567, "HARVESTER", 19, 16, None),
    (567, "CONVEYOR", 16, 19, "EAST"),
    (568, "CONVEYOR", 15, 19, "EAST"),
    (568, "HARVESTER", 15, 20, None),
    (569, "CONVEYOR", 14, 19, "EAST"),
    (569, "CONVEYOR", 13, 19, "EAST"),
    (570, "HARVESTER", 13, 20, None),
    (570, "CONVEYOR", 18, 19, "WEST"),
    (571, "CONVEYOR", 19, 19, "WEST"),
    (571, "HARVESTER", 19, 20, None),
]

DIR_BY_NAME: dict[str, Direction] = {
    "NORTH": Direction.NORTH,
    "NORTHEAST": Direction.NORTHEAST,
    "EAST": Direction.EAST,
    "SOUTHEAST": Direction.SOUTHEAST,
    "SOUTH": Direction.SOUTH,
    "SOUTHWEST": Direction.SOUTHWEST,
    "WEST": Direction.WEST,
    "NORTHWEST": Direction.NORTHWEST,
}

ENTITY_BY_KIND: dict[str, EntityType] = {
    "CONVEYOR": EntityType.CONVEYOR,
    "SPLITTER": EntityType.SPLITTER,
    "ARMOURED_CONVEYOR": EntityType.ARMOURED_CONVEYOR,
    "BRIDGE": EntityType.BRIDGE,
    "HARVESTER": EntityType.HARVESTER,
    "FOUNDRY": EntityType.FOUNDRY,
    "ROAD": EntityType.ROAD,
    "BARRIER": EntityType.BARRIER,
}

KING_DIRS: tuple[Direction, ...] = (
    Direction.NORTH,
    Direction.NORTHEAST,
    Direction.EAST,
    Direction.SOUTHEAST,
    Direction.SOUTH,
    Direction.SOUTHWEST,
    Direction.WEST,
    Direction.NORTHWEST,
)


def task_extra(extra: object) -> Direction | Position | None:
    if isinstance(extra, str):
        return DIR_BY_NAME[extra]
    if isinstance(extra, tuple):
        return Position(extra[0], extra[1])
    return None


class Player:
    def __init__(self) -> None:
        self.idx: int | None = None
        self.spawned: int = 0
        self.done: set[int] = set()

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self._run_core(ct)
        elif etype == EntityType.BUILDER_BOT:
            self._run_builder(ct)

    def _run_core(self, ct: Controller) -> None:
        if self.spawned >= 2 or ct.get_action_cooldown() != 0:
            return
        target = self._next_unbuilt_pos(ct)
        core_pos = ct.get_position()
        candidates: list[Position] = [core_pos, *(core_pos.add(d) for d in KING_DIRS)]
        spawnable = [p for p in candidates if ct.can_spawn(p)]
        if not spawnable:
            log(f"r={ct.get_current_round()} CORE no spawnable")
            return
        if target is not None:
            spawnable.sort(key=lambda p: p.distance_squared(target))
        sp = spawnable[0]
        ct.spawn_builder(sp)
        self.spawned += 1
        log(
            f"r={ct.get_current_round()} CORE spawn {self.spawned} at ({sp.x},{sp.y}) target={target}"
        )

    def _next_unbuilt_pos(self, ct: Controller) -> Position | None:
        for task in SCHEDULE:
            _, kind, x, y, _ = task
            pos = Position(x, y)
            if not _is_built(ct, pos, kind):
                return pos
        return None

    def _run_builder(self, ct: Controller) -> None:
        if self.idx is None:
            self.idx = _determine_idx(ct)
            log(
                f"r={ct.get_current_round()} B{self.idx} INIT pos={_p(ct.get_position())}"
            )

        r = ct.get_current_round()
        my_task = self._my_next_task(ct)
        if my_task is None:
            log(f"r={r} B{self.idx} idle (no tasks)")
            return
        _, kind, x, y, extra = my_task
        target = Position(x, y)
        log(
            f"r={r} B{self.idx} pos={_p(ct.get_position())} "
            f"task={kind}@({x},{y}) acd={ct.get_action_cooldown()} mcd={ct.get_move_cooldown()}"
        )

        built = self._try_build(ct, kind, target, extra)
        if built:
            log(f"r={r} B{self.idx} BUILT {kind}@({x},{y})")
            self.done.add(SCHEDULE.index(my_task))
        move_target = self._later_target(ct, my_task) if built else target
        if move_target is not None:
            self._advance_toward(ct, move_target)
        if not built:
            built = self._try_build(ct, kind, target, extra)
            if built:
                log(f"r={r} B{self.idx} BUILT-after-move {kind}@({x},{y})")
                self.done.add(SCHEDULE.index(my_task))

    def _advance_toward(self, ct: Controller, target: Position) -> None:
        my = ct.get_position()
        if my.distance_squared(target) <= 2:
            return
        r = ct.get_current_round()
        next_step = _bfs_first_step(ct, my, target)
        if next_step is None:
            log(
                f"r={r} B{self.idx} STUCK no path from {_p(my)} to "
                f"action-radius of ({target.x},{target.y})"
            )
            return
        try:
            passable = ct.is_tile_passable(next_step)
        except GameError:
            log(f"r={r} B{self.idx} step={_p(next_step)} OUT_OF_VISION")
            return
        d = _delta_to_dir(next_step.x - my.x, next_step.y - my.y)
        if d is None:
            return
        if not passable and ct.get_action_cooldown() == 0:
            try:
                empty = ct.is_tile_empty(next_step)
            except GameError:
                empty = False
            if empty:
                try:
                    ct.build(EntityType.ROAD, next_step)
                    log(f"r={r} B{self.idx} ROAD@{_p(next_step)}")
                except GameError as e:
                    log(f"r={r} B{self.idx} ROAD@{_p(next_step)} FAIL {e}")
        if ct.get_move_cooldown() == 0 and ct.can_move(d):
            ct.move(d)
            log(f"r={r} B{self.idx} MOVE {d.value} -> {_p(next_step)}")
        else:
            log(
                f"r={r} B{self.idx} CAN'T move {d.value} to {_p(next_step)} "
                f"(mcd={ct.get_move_cooldown()} can_move={ct.can_move(d)})"
            )

    def _my_next_task(self, ct: Controller) -> tuple[int, str, int, int, object] | None:
        idx = self.idx or 0
        for i, task in enumerate(SCHEDULE):
            if i % 2 != idx or i in self.done:
                continue
            _, kind, x, y, _ = task
            if _is_built(ct, Position(x, y), kind):
                self.done.add(i)
                continue
            return task
        return None

    def _later_target(
        self, ct: Controller, current_task: tuple[int, str, int, int, object]
    ) -> Position | None:
        try:
            cur_idx = SCHEDULE.index(current_task)
        except ValueError:
            return None
        idx = self.idx or 0
        for j in range(cur_idx + 2, len(SCHEDULE), 2):
            if j % 2 != idx or j in self.done:
                continue
            _, kind, x, y, _ = SCHEDULE[j]
            if _is_built(ct, Position(x, y), kind):
                self.done.add(j)
                continue
            return Position(x, y)
        return None

    def _try_build(
        self,
        ct: Controller,
        kind: str,
        pos: Position,
        extra: object,
    ) -> bool:
        if ct.get_action_cooldown() != 0:
            return False
        my = ct.get_position()
        if my.distance_squared(pos) > 2:
            return False
        etype = ENTITY_BY_KIND[kind]
        try:
            bid = ct.get_tile_building_id(pos)
        except GameError:
            return False
        if bid is not None:
            try:
                existing = ct.get_entity_type(bid)
            except GameError:
                return False
            if existing == etype:
                return False
            if not ct.can_destroy(pos):
                return False
            try:
                ct.destroy(pos)
            except GameError as e:
                log(
                    f"r={ct.get_current_round()} B{self.idx} DESTROY@({pos.x},{pos.y}) FAIL {e}"
                )
                return False
            log(
                f"r={ct.get_current_round()} B{self.idx} DESTROY@({pos.x},{pos.y}) {existing.name}"
            )
        ev = task_extra(extra)
        try:
            if ev is None:
                ct.build(etype, pos)
            else:
                ct.build(etype, pos, ev)
        except GameError as e:
            log(
                f"r={ct.get_current_round()} B{self.idx} BUILD {kind}@({pos.x},{pos.y}) FAIL {e}"
            )
            return False
        return True


def _p(pos: Position) -> str:
    return f"({pos.x},{pos.y})"


SCHEDULE_TARGETS: frozenset[tuple[int, int]] = frozenset(
    (x, y) for _, _, x, y, _ in SCHEDULE
)

WALLS: frozenset[tuple[int, int]] = frozenset(
    {
        (1, 2),
        (1, 3),
        (1, 4),
        (1, 5),
        (1, 6),
        (1, 28),
        (1, 29),
        (1, 30),
        (1, 31),
        (1, 32),
        (2, 28),
        (2, 30),
        (3, 28),
        (3, 30),
        (4, 28),
        (4, 29),
        (4, 30),
        (6, 28),
        (6, 29),
        (6, 30),
        (6, 31),
        (6, 32),
        (7, 28),
        (7, 32),
        (8, 28),
        (8, 32),
        (9, 28),
        (9, 29),
        (9, 30),
        (9, 31),
        (9, 32),
        (11, 28),
        (11, 29),
        (11, 30),
        (11, 31),
        (11, 32),
        (12, 28),
        (12, 29),
        (13, 29),
        (13, 30),
        (13, 31),
        (14, 28),
        (14, 29),
        (14, 30),
        (14, 31),
        (14, 32),
        (16, 28),
        (16, 29),
        (16, 30),
        (16, 31),
        (16, 32),
        (17, 28),
        (17, 32),
        (18, 28),
        (18, 30),
        (18, 32),
        (19, 1),
        (19, 2),
        (19, 3),
        (19, 5),
        (19, 28),
        (19, 30),
        (19, 31),
        (19, 32),
        (20, 1),
        (20, 3),
        (20, 5),
        (21, 1),
        (21, 3),
        (21, 4),
        (21, 5),
        (24, 0),
        (24, 1),
        (24, 2),
        (24, 3),
        (24, 4),
        (24, 5),
        (24, 6),
        (24, 7),
        (24, 8),
        (24, 9),
        (24, 10),
        (24, 11),
        (24, 12),
        (24, 13),
        (24, 14),
        (24, 15),
        (24, 16),
        (24, 17),
        (24, 18),
        (24, 19),
        (24, 20),
        (24, 21),
        (24, 22),
        (24, 23),
        (24, 24),
        (24, 25),
        (24, 26),
        (24, 27),
        (24, 28),
        (24, 29),
        (24, 30),
        (24, 31),
        (24, 32),
        (24, 33),
        (24, 34),
        (25, 0),
        (25, 1),
        (25, 2),
        (25, 3),
        (25, 4),
        (25, 5),
        (25, 6),
        (25, 7),
        (25, 8),
        (25, 9),
        (25, 10),
        (25, 11),
        (25, 12),
        (25, 13),
        (25, 14),
        (25, 15),
        (25, 16),
        (25, 17),
        (25, 18),
        (25, 19),
        (25, 20),
        (25, 21),
        (25, 22),
        (25, 23),
        (25, 24),
        (25, 25),
        (25, 26),
        (25, 27),
        (25, 28),
        (25, 29),
        (25, 30),
        (25, 31),
        (25, 32),
        (25, 33),
        (25, 34),
        (28, 1),
        (28, 3),
        (28, 4),
        (28, 5),
        (29, 1),
        (29, 3),
        (29, 5),
        (30, 1),
        (30, 2),
        (30, 3),
        (30, 5),
        (30, 28),
        (30, 30),
        (30, 31),
        (30, 32),
        (31, 28),
        (31, 30),
        (31, 32),
        (32, 28),
        (32, 32),
        (33, 28),
        (33, 29),
        (33, 30),
        (33, 31),
        (33, 32),
        (35, 28),
        (35, 29),
        (35, 30),
        (35, 31),
        (35, 32),
        (36, 29),
        (36, 30),
        (36, 31),
        (37, 28),
        (37, 29),
        (38, 28),
        (38, 29),
        (38, 30),
        (38, 31),
        (38, 32),
        (40, 28),
        (40, 29),
        (40, 30),
        (40, 31),
        (40, 32),
        (41, 28),
        (41, 32),
        (42, 28),
        (42, 32),
        (43, 28),
        (43, 29),
        (43, 30),
        (43, 31),
        (43, 32),
        (45, 28),
        (45, 29),
        (45, 30),
        (46, 28),
        (46, 30),
        (47, 28),
        (47, 30),
        (48, 2),
        (48, 3),
        (48, 4),
        (48, 5),
        (48, 6),
        (48, 28),
        (48, 29),
        (48, 30),
        (48, 31),
        (48, 32),
    }
)


def _determine_idx(ct: Controller) -> int:
    my_id = ct.get_id()
    builder_ids: list[int] = []
    for u in ct.get_nearby_units():
        try:
            if ct.get_entity_type(u) == EntityType.BUILDER_BOT:
                builder_ids.append(u)
        except GameError:
            continue
    builder_ids.sort()
    try:
        return builder_ids.index(my_id)
    except ValueError:
        return 0


def _is_built(ct: Controller, pos: Position, kind: str) -> bool:
    try:
        bid = ct.get_tile_building_id(pos)
    except GameError:
        return False
    if bid is None:
        return False
    try:
        etype = ct.get_entity_type(bid)
    except GameError:
        return False
    return etype == ENTITY_BY_KIND.get(kind)


def _delta_to_dir(dx: int, dy: int) -> Direction | None:
    for d in KING_DIRS:
        if d.delta() == (dx, dy):
            return d
    return None


def _bfs_first_step(ct: Controller, start: Position, goal: Position) -> Position | None:
    """BFS through passable + empty (non-wall, non-building) tiles toward
    a tile within action radius of `goal`. Returns the first king-step
    (or None). Empty steps imply a road must be laid before walking."""
    w = ct.get_map_width()
    h = ct.get_map_height()
    if not (0 <= goal.x < w and 0 <= goal.y < h):
        return None

    parent: dict[tuple[int, int], tuple[int, int]] = {}
    seen: set[tuple[int, int]] = {(start.x, start.y)}
    q: deque[tuple[int, int]] = deque([(start.x, start.y)])
    end: tuple[int, int] | None = None
    while q:
        x, y = q.popleft()
        cur = Position(x, y)
        if (
            (x, y) != (start.x, start.y)
            and (x, y) != (goal.x, goal.y)
            and cur.distance_squared(goal) <= 2
        ):
            end = (x, y)
            break
        for d in KING_DIRS:
            dx, dy = d.delta()
            nx, ny = x + dx, y + dy
            if (nx, ny) in seen:
                continue
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            if (nx, ny) == (goal.x, goal.y):
                continue
            if (nx, ny) in WALLS:
                continue
            np = Position(nx, ny)
            try:
                ok = ct.is_tile_passable(np) or ct.is_tile_empty(np)
            except GameError:
                ok = True
            if not ok:
                continue
            seen.add((nx, ny))
            parent[(nx, ny)] = (x, y)
            q.append((nx, ny))
    if end is None:
        return None
    cur_node = end
    while parent.get(cur_node) != (start.x, start.y):
        if cur_node not in parent:
            return None
        cur_node = parent[cur_node]
    return Position(cur_node[0], cur_node[1])
