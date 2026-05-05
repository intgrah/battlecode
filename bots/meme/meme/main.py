from __future__ import annotations

import astar
from cambc import Controller, Environment, Position, Team
from map26 import Map26
from rust import Entity, Game, RawMem


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
        except Exception as e:
            print(f"[map] {e}")

    def run(self, ct: Controller) -> None:
        for i in range(len(self._ti_path) - 1):
            ax, ay = self._ti_path[i]
            bx, by = self._ti_path[i + 1]
            ct.draw_indicator_line(Position(ax, ay), Position(bx, by), 255, 200, 0)

        try:
            g = Game.open(RawMem(), ct)
        except Exception as e:
            print(f"[failed] {type(e).__name__}: {e}")
            return

        step = ct.get_current_round()
        steps = [
            lambda: print(f"game_map: {g.game_map.width}x{g.game_map.height}"),
            lambda: print(f"turn={g.turn}"),
            lambda: print(f"next_id={g.next_id}"),
            lambda: print(f"resign_message={g.resign_message!r}"),
            lambda: print(f"unit_order={list(g.unit_order)}"),
            lambda: print(f"harvesters={list(g.harvesters)}"),
            lambda: print(
                f"player_a: ti={g.player(Team.A).titanium} ax={g.player(Team.A).axionite} scale_milli={g.player(Team.A).scale_milli}"
            ),
            lambda: print(
                f"player_b: ti={g.player(Team.B).titanium} ax={g.player(Team.B).axionite} scale_milli={g.player(Team.B).scale_milli}"
            ),
            lambda: print(f"entities.items={g.entities.items}"),
            lambda: print(f"entities.bucket_mask={g.entities.bucket_mask}"),
            lambda: print(f"entities.ctrl=0x{g.entities.ctrl:x}"),
            lambda: print(f"slots={[hex(s) for s in g.entities.occupied_slots()]}"),
            lambda: print(
                f"slot0_bytes={g._raw.read_bytes(next(iter(g.entities.occupied_slots())), 64).hex()}"
            ),
            lambda: print(
                f"entities={[(hex(g._raw.read_u64(s+8)), hex(g._raw.read_u8(s+60))) for s in g.entities.occupied_slots()]}"
            ),
        ]
        if step < len(steps):
            try:
                steps[step]()
            except Exception as e:
                print(f"[step{step}] {type(e).__name__}: {e}")
