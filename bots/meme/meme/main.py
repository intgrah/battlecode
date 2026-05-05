from __future__ import annotations

import astar
from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
    Position,
    Team,
)
from map26 import Map26
from rust import Game, RawMem


class Player:
    def __init__(self) -> None:
        self._ti_ore: tuple[int, int] | None = None
        self._ax_ore: tuple[int, int] | None = None
        self._ti_path: list[tuple[int, int]] = []
        try:
            m = Map26.read()
            if m.cores:
                ref_x, ref_y = m.cores[0].x, m.cores[0].y
                best_ti = best_ax = -1
                for y in range(m.height):
                    for x in range(m.width):
                        env = m.tile(x, y)
                        match env:
                            case Environment.ORE_TITANIUM:
                                d = (x - ref_x) ** 2 + (y - ref_y) ** 2
                                if best_ti < 0 or d < best_ti:
                                    best_ti = d
                                    self._ti_ore = (x, y)
                            case Environment.ORE_AXIONITE:
                                d = (x - ref_x) ** 2 + (y - ref_y) ** 2
                                if best_ax < 0 or d < best_ax:
                                    best_ax = d
                                    self._ax_ore = (x, y)
                if self._ti_ore is not None:
                    self._ti_path = astar.run(
                        m, start=self._ti_ore, goal=(ref_x, ref_y)
                    )
        except Exception as e:  # noqa: BLE001
            print(f"[map] {e}")

    def run(self, ct: Controller) -> None:
        match ct.get_entity_type():
            case EntityType.CORE:
                self.run_core(ct)
            case EntityType.BUILDER_BOT:
                self.run_builder(ct)

    def run_builder(self, ct: Controller) -> None:
        pos = ct.get_position()
        match ct.get_current_round():
            case 2:
                ct.build_harvester(pos.add(Direction.SOUTH))
            case 3:
                ct.build_conveyor(pos.add(Direction.SOUTHWEST), Direction.WEST)
                ct.move(Direction.WEST)
            case 4:
                ct.place_marker(pos.add(Direction.WEST), 0xDEADBEEF)
            case 5:
                ct.build_road(pos.add(Direction.NORTHWEST))
            case 6:
                ct.build_foundry(pos.add(Direction.SOUTHWEST))
                ct.move(Direction.EAST)
            case 7:
                ct.build_splitter(pos.add(Direction.SOUTHEAST), Direction.EAST)
                ct.move(Direction.EAST)
            case 8:
                ct.build_bridge(pos.add(Direction.SOUTHEAST), pos.add(Direction.EAST))
            case 9:
                ct.build_gunner(pos.add(Direction.EAST), Direction.EAST)

    def run_core(self, ct: Controller) -> None:
        if ct.get_current_round() == 1:
            ct.spawn_builder(ct.get_position().add(Direction.SOUTH))
        for i in range(len(self._ti_path) - 1):
            ax, ay = self._ti_path[i]
            bx, by = self._ti_path[i + 1]
            ct.draw_indicator_line(Position(ax, ay), Position(bx, by), 255, 200, 0)

        try:
            g = Game.open(RawMem(), ct)
        except Exception as e:  # noqa: BLE001
            print(f"[failed] {type(e).__name__}: {e}")
            return
        try:
            match ct.get_current_round() - 50:
                case 1:
                    print(f"game_map: {g.game_map.width}x{g.game_map.height}")
                case 2:
                    print(f"turn={g.turn}")
                case 3:
                    print(f"next_id={g.next_id}")
                case 4:
                    print(f"resign_message={g.resign_message!r}")
                case 5:
                    print(f"unit_order={list(g.unit_order)}")
                case 6:
                    print(f"harvesters={list(g.harvesters)}")
                case 7:
                    print(
                        f"player_a: ti={g.player(Team.A).titanium} ax={g.player(Team.A).axionite} scale_milli={g.player(Team.A).scale_milli}"
                    )
                case 8:
                    print(
                        f"player_b: ti={g.player(Team.B).titanium} ax={g.player(Team.B).axionite} scale_milli={g.player(Team.B).scale_milli}"
                    )

                case 9:
                    print(f"len(entities)={len(g.entities)}")
                case 10:
                    print(f"keys={list(g.entities)}")
                case 11:
                    print(f"entities[1]={g.entities[1]!r}")
                case 12:
                    print(f"3 in entities = {3 in g.entities}")
                case 13:
                    print(f"items={[(k, repr(v)) for k, v in g.entities.items()]}")
                case 14:
                    print(
                        f"slots_raw={[g._raw.read_bytes(e._addr, 72).hex() for e in g.entities.values()]}"
                    )
        except Exception as e:  # noqa: BLE001
            print(f"[error] {type(e).__name__}: {e}")
