from cambc import Controller, Direction, EntityType, Position
from marker import TaskKind

from .base import BuilderBase
from .build import Build, BuildKind

# Max foundries to build. Each costs +100% scale so limit to control costs.
_MAX_FOUNDRIES = 3


class FoundryMixin(BuilderBase):
    def _place_foundry(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Build | None] | None:
        n_foundries = len(self.belief.my_foundries)
        if n_foundries >= _MAX_FOUNDRIES:
            return None
        # Need at least some ax flow before building first foundry.
        # For subsequent foundries, require unrefined ax excess to justify the cost.
        f = self.belief.my_flow
        if n_foundries == 0:
            has_both = any(
                f.ti[i] > 0 and f.ax[i] > 0 for i in self.belief.my_transport
            )
            if not has_both:
                return None
        else:
            # Only build more foundries if there's unrefined ax excess somewhere.
            has_ax_excess = any(f.ax_excess[i] > 0.05 for i in self.belief.my_foundries)
            if not has_ax_excess:
                return None
            # And we can afford it.
            cost, _ = ct.get_foundry_cost()
            ti, _ = ct.get_global_resources()
            if ti < cost * 2:
                return None

        w = self.belief.w
        best_tile: int | None = None
        best_score = 0.0
        best_dist = 999999

        for i in self.belief.my_transport:
            ent = self.belief.entity[i]
            if ent is None:
                continue
            if ent[0] not in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
                continue
            ti_f = f.ti[i]
            ax_f = f.ax[i]
            if ti_f <= 0 or ax_f <= 0:
                continue
            score = min(ti_f, ax_f)
            cx, cy = i % w, i // w
            dist = (pos.x - cx) ** 2 + (pos.y - cy) ** 2
            if self._is_claimed(i, TaskKind.FIX_EXCESS):
                continue
            if score > best_score or (score == best_score and dist < best_dist):
                best_score = score
                best_dist = dist
                best_tile = i

        if best_tile is None:
            return None

        tx, ty = best_tile % w, best_tile // w
        target = Position(tx, ty)

        if pos.distance_squared(target) <= 2 and pos != target:
            self._debug_target = (target, 255, 128, 0)
            return Direction.CENTRE, Build(BuildKind.FOUNDRY, target)

        adj = self._cardinal_adjacent(pos, target)
        if adj is None:
            return None
        move, build = self._move_toward_with_road(ct, pos, adj)
        if move != Direction.CENTRE and build is None:
            new_pos = pos.add(move)
            if new_pos.distance_squared(target) <= 2 and new_pos != target:
                build = Build(BuildKind.FOUNDRY, target)
        self._debug_target = (target, 255, 128, 0)
        return move, build
