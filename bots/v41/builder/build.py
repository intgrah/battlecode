from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from cambc import Controller, Direction, Position


class BuildKind(Enum):
    HARVESTER = auto()
    CONVEYOR = auto()
    BRIDGE = auto()
    ROAD = auto()
    SELF_DESTRUCT = auto()
    HEAL = auto()


@dataclass(frozen=True, slots=True)
class Build:
    kind: BuildKind
    pos: Position
    aux: Direction | Position | None = None

    def execute(self, ct: Controller) -> None:
        ti, _ = ct.get_global_resources()
        match self.kind:
            case BuildKind.HARVESTER:
                cost, _ = ct.get_harvester_cost()
                if ti >= cost and ct.can_build_harvester(self.pos):
                    ct.build_harvester(self.pos)
            case BuildKind.CONVEYOR:
                assert isinstance(self.aux, Direction)
                self._destroy_friendly(ct, self.pos)
                cost, _ = ct.get_conveyor_cost()
                if ti >= cost and ct.can_build_conveyor(self.pos, self.aux):
                    ct.build_conveyor(self.pos, self.aux)
            case BuildKind.BRIDGE:
                assert isinstance(self.aux, Position)
                self._destroy_friendly(ct, self.pos)
                cost, _ = ct.get_bridge_cost()
                if ti >= cost and ct.can_build_bridge(self.pos, self.aux):
                    ct.build_bridge(self.pos, self.aux)
            case BuildKind.ROAD:
                cost, _ = ct.get_road_cost()
                if ti >= cost and ct.can_build_road(self.pos):
                    ct.build_road(self.pos)
            case BuildKind.SELF_DESTRUCT:
                ct.self_destruct()
            case BuildKind.HEAL:
                if ct.can_heal(self.pos):
                    ct.heal(self.pos)

    @staticmethod
    def _destroy_friendly(ct: Controller, pos: Position) -> None:
        bid = ct.get_tile_building_id(pos)
        if bid is not None and ct.get_team(bid) == ct.get_team():
            ct.destroy(pos)
