"""Core unit logic — spawn builder bots."""

from __future__ import annotations

from cambc import Controller, Environment, Position
from unit import Unit

_ORE_ENVS = (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE)


class Core(Unit):
    def __init__(self, ct: Controller) -> None:
        self.pos = ct.get_position()
        self.w = ct.get_map_width()
        self.h = ct.get_map_height()
        self._got_ax: bool = False
        self.spawned = 0

    def _preferred_direction(self, ct: Controller) -> tuple[int, int]:
        """Return a (dx, dy) unit-ish direction to bias spawning toward.

        If any ore is visible, point toward the nearest ore tile.
        Otherwise, point toward the center of the map.
        """
        pos = self.pos
        best_dist = 1 << 30
        best_dx, best_dy = 0, 0
        for tile in ct.get_nearby_tiles():
            if ct.get_tile_env(tile) in _ORE_ENVS:
                d = abs(tile.x - pos.x) + abs(tile.y - pos.y)
                if d < best_dist:
                    best_dist = d
                    best_dx = tile.x - pos.x
                    best_dy = tile.y - pos.y

        if best_dist < (1 << 30):
            return (_sign(best_dx), _sign(best_dy))

        cx, cy = self.w // 2, self.h // 2
        return (_sign(cx - pos.x), _sign(cy - pos.y))

    def run(self, ct: Controller) -> None:

        if ct.get_current_round() > 400:
            ct.resign()

        ti, ax = ct.get_global_resources()
        self._got_ax |= ax > 0

        hurt = ct.get_hp() < ct.get_max_hp()
        if hurt:
            bti, _ = ct.get_builder_bot_cost()
            need_ti = max(bti - ti, 0)
            need_ax = (need_ti + 3) // 4
            ct.convert(min(need_ax, ax + 1 - need_ax))

        should_spawn = (
            self.spawned < 3 or self._got_ax and ct.get_unit_count() < 10 or hurt
        )

        if should_spawn:
            pos = self.pos
            pdx, pdy = self._preferred_direction(ct)
            # Sort the 3x3 spawn tiles so the one closest to the
            # preferred direction is tried first.
            candidates = [(dx, dy) for dx in range(-1, 2) for dy in range(-1, 2)]
            candidates.sort(key=lambda t: max(abs(t[0] - pdx), abs(t[1] - pdy)))
            for dx, dy in candidates:
                p = Position(pos.x + dx, pos.y + dy)
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    self.spawned += 1
                    return


def _sign(x: int) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0
