from __future__ import annotations

from typing import TYPE_CHECKING, override

from unit import Unit

if TYPE_CHECKING:
    from cambc import Controller, Position

__all__ = ["Breach"]


class Breach(Unit):
    targets: tuple[Position, ...]

    @override
    def post_init(self, ct: Controller) -> None:
        super().post_init(ct)
        fwd = ct.get_direction()
        left = fwd.rotate_left().rotate_left()
        right = fwd.rotate_right().rotate_right()
        c = ct.get_position().add(fwd).add(fwd).add(fwd)
        l1 = c.add(left)
        l2 = l1.add(left)
        r1 = c.add(right)
        r2 = r1.add(right)
        self.targets = tuple(t for t in (l2, l1, c, r1, r2) if self.in_bounds(t))

    @override
    def run(self, ct: Controller) -> None:
        super().run(ct)
        if self.round % 4 != 0:
            return
        if ct.get_action_cooldown() > 0:
            return
        candidates = [t for t in self.targets if ct.can_fire(t)]
        if candidates:
            ct.fire(self.rng.choice(candidates))
