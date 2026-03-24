from cambc import Controller, Direction, EntityType, Environment, Position
from map_belief import MapBelief

from .base import BuilderBase
from .build import Build, BuildKind

_CARDINALS = [(-1, 0), (1, 0), (0, -1), (0, 1)]

_PERP: dict[Direction, list[tuple[int, int]]] = {
    Direction.NORTH: [(-1, 0), (1, 0)],
    Direction.SOUTH: [(-1, 0), (1, 0)],
    Direction.EAST: [(0, -1), (0, 1)],
    Direction.WEST: [(0, -1), (0, 1)],
}


def _is_foundry_site(belief: MapBelief, nx: int, ny: int) -> bool:
    if not belief.in_bounds(nx, ny):
        return False
    ni = belief.idx(nx, ny)
    env = belief.env[ni]
    if env is None or env in (
        Environment.WALL,
        Environment.ORE_TITANIUM,
        Environment.ORE_AXIONITE,
    ):
        return False
    ent = belief.entity[ni]
    return ent is None or ent[0] in (EntityType.MARKER, EntityType.ROAD)


class FoundryMixin(BuilderBase):
    def _place_foundry(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Build | None] | None:
        if self.belief.my_foundries:
            return None

        w = self.belief.w
        best_site: tuple[int, int] | None = None
        best_score = 0.0
        best_dist = 999999

        for i in self.belief.my_transport:
            ent = self.belief.entity[i]
            if ent is None:
                continue
            etype = ent[0]
            if etype not in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
                continue
            ti_f = self.belief.my_flow.ti[i]
            ax_f = self.belief.my_flow.ax[i]
            if ti_f <= 0 or ax_f <= 0:
                continue
            cx, cy = i % w, i // w

            conv_dir = self.belief.direction[i]
            if conv_dir is None or conv_dir not in _PERP:
                continue

            score = min(ti_f, ax_f)
            cx, cy = i % w, i // w
            for ddx, ddy in _PERP[conv_dir]:
                nx, ny = cx + ddx, cy + ddy
                if not _is_foundry_site(self.belief, nx, ny):
                    continue
                dist = (pos.x - nx) ** 2 + (pos.y - ny) ** 2
                if score > best_score or (score == best_score and dist < best_dist):
                    best_score = score
                    best_dist = dist
                    best_site = (nx, ny)

        if best_site is None:
            return None

        site_pos = Position(best_site[0], best_site[1])
        if pos.distance_squared(site_pos) <= 2 and pos != site_pos:
            self._debug_target = (site_pos, 255, 128, 0)
            return Direction.CENTRE, Build(BuildKind.FOUNDRY, site_pos)

        adj = self._cardinal_adjacent(pos, site_pos)
        if adj is None:
            return None
        move, build = self._move_toward_with_road(ct, pos, adj)
        if move != Direction.CENTRE and build is None:
            new_pos = pos.add(move)
            if new_pos.distance_squared(site_pos) <= 2 and new_pos != site_pos:
                build = Build(BuildKind.FOUNDRY, site_pos)
        self._debug_target = (site_pos, 255, 128, 0)
        return move, build

    def _split_foundry(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Build | None] | None:
        w = self.belief.w

        for fi in self.belief.my_foundries:
            fx, fy = fi % w, fi // w
            for ddx, ddy in _CARDINALS:
                nx, ny = fx + ddx, fy + ddy
                if not self.belief.in_bounds(nx, ny):
                    continue
                ni = self.belief.idx(nx, ny)
                ent = self.belief.entity[ni]
                if ent is None:
                    continue
                etype, team = ent
                if team != self.belief.my_team:
                    continue
                if etype not in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
                    continue
                if self.belief.my_flow.ti[ni] <= 0 or self.belief.my_flow.ax[ni] <= 0:
                    continue

                conv_dir = self.belief.direction[ni]
                if conv_dir is None:
                    continue

                splitter_pos = Position(nx, ny)
                if pos.distance_squared(splitter_pos) <= 2 and pos != splitter_pos:
                    self._debug_target = (splitter_pos, 255, 200, 0)
                    return Direction.CENTRE, Build(
                        BuildKind.SPLITTER, splitter_pos, aux=conv_dir,
                    )

                adj = self._cardinal_adjacent(pos, splitter_pos)
                if adj is None:
                    continue
                move, build = self._move_toward_with_road(ct, pos, adj)
                if move != Direction.CENTRE and build is None:
                    new_pos = pos.add(move)
                    if (
                        new_pos.distance_squared(splitter_pos) <= 2
                        and new_pos != splitter_pos
                    ):
                        build = Build(BuildKind.SPLITTER, splitter_pos, aux=conv_dir)
                self._debug_target = (splitter_pos, 255, 200, 0)
                return move, build

        return None
