"""Place a foundry adjacent to a mixed-flow conveyor.

Method 2 of RAx refining (splitter tech). Detects a conveyor carrying both
Ti and Ax flow, then places a foundry on a vacant tile adjacent to it. The
foundry will be fed by a splitter (placed by the place_splitter_foundry
task) which replaces the conveyor.

Unlike place_foundry_ti_conv, this preserves the original conveyor until
the splitter replaces it, keeping the Ti chain intact.
"""

from cambc import Controller, Direction, EntityType, Position

from .base import BuilderBase
from .build import Action, PlaceFoundry


class PlaceFoundryMixedConvMixin(BuilderBase):
    def _place_foundry_mixed_conv(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Action | None] | None:
        w = self.belief.w
        f = self.belief.my_flow
        best_conv: int | None = None
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
            if score > best_score or (score == best_score and dist < best_dist):
                best_score = score
                best_dist = dist
                best_conv = i

        if best_conv is None:
            return None

        cx, cy = best_conv % w, best_conv // w
        foundry_pos: Position | None = None
        foundry_dist = 999999
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = cx + dx, cy + dy
            if not self.belief.in_bounds(nx, ny):
                continue
            ni = self.belief.idx(nx, ny)
            env = self.belief.env[ni]
            if env is None or env != env.EMPTY:
                continue
            ent = self.belief.entity[ni]
            if ent is not None:
                continue
            d = (pos.x - nx) ** 2 + (pos.y - ny) ** 2
            if d < foundry_dist:
                foundry_dist = d
                foundry_pos = Position(nx, ny)

        if foundry_pos is None:
            return None

        if pos.distance_squared(foundry_pos) <= 2 and pos != foundry_pos:
            self._debug_target = (foundry_pos, 255, 128, 0)
            return Direction.CENTRE, PlaceFoundry(foundry_pos)

        adj = self._cardinal_adjacent(pos, foundry_pos)
        if adj is None:
            return None
        move, build = self._move_toward_with_road(ct, pos, adj)
        if move != Direction.CENTRE and build is None:
            new_pos = pos.add(move)
            if new_pos.distance_squared(foundry_pos) <= 2 and new_pos != foundry_pos:
                build = PlaceFoundry(foundry_pos)
        self._debug_target = (foundry_pos, 255, 128, 0)
        return move, build
