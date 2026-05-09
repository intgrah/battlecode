from __future__ import annotations

import random
from collections import deque
from typing import TYPE_CHECKING, override

from apsp import apsp, pnb
from cambc import Direction, EntityType, Position, Team
from ct_hash import ct_changed
from god_mode import GodMode
from map26 import Map26
from rust import EntityBuilderBot, EntitySentinel, Game, RawMem
from snake import Snake

from trolls._base import Troll
from trolls.draw_pentagram import draw_pentagram
from trolls.emergency import win_without_ct
from trolls.gg import write_gg
from trolls.long_bridge import long_bridge
from trolls.snipe import snipe
from trolls.surround_map import surround_map

INF = 1_000_000_000

if TYPE_CHECKING:
    from collections.abc import Generator

    from cambc import Controller


class Meme(Troll):
    def __init__(self) -> None:
        self.core: int | None = None
        self.builder_id: int | None = None
        self.turret_id: int | None = None
        self.team: Team | None = None
        self.enemy_team: Team | None = None
        self.snake: Snake = Snake(16)
        self.workers_built: int = 0
        self.turn_work: Generator | None = None
        self.last_rnd = -1
        self.log: str = ""
        self.progress = 0
        self.raw_mem: RawMem | None = None
        self.written_gg: bool = False
        self.won_without_ct: bool = False
        self.map = m = Map26.read()
        self.bridge_queue: deque[tuple[int, int]] = deque()
        self.bridge_pos_idx: int = 0
        if m.width <= 50 and m.height <= 50:
            self.pnb = pnb(m)
            self.apsp = apsp(m, self.pnb)
        else:
            self.pnb = None
            self.apsp = None

    def builder(self) -> EntityBuilderBot:
        assert self.builder_id is not None
        me = self.g.entities[self.builder_id].as_variant
        assert isinstance(me, EntityBuilderBot)
        return me

    def turret(self) -> EntitySentinel:
        assert self.turret_id is not None
        me = self.g.entities[self.turret_id].as_variant
        assert isinstance(me, EntitySentinel)
        return me

    def give_order(self, bid: int) -> None:
        assert self.core is not None
        for i in range(len(self.g.unit_order)):
            uid = self.g.unit_order[i]
            if uid == bid:
                self.g.unit_order[i] = self.core
                break

    def print(self, message: object) -> None:
        self.log += str(message) + "\n"

    @override
    def run(self, ct: Controller) -> None:
        if self.won_without_ct:
            return

        if ct_changed(ct) or self.pnb is None:
            print("don't call ct methods!")
            g = Game.open(RawMem(), ct)
            win_without_ct(g)
            write_gg(g, self.map)
            self.won_without_ct = True
            return

        if ct.get_entity_type() != EntityType.CORE:
            ct.resign("non core got a turn")
            return

        if self.raw_mem is None:
            self.raw_mem = RawMem()

        self.ct = ct
        self.g = Game.open(self.raw_mem, ct)

        if not self.written_gg:
            write_gg(self.g, self.map)
            self.written_gg = True

        rnd = ct.get_current_round()
        if self.last_rnd != rnd:
            self.log = ""
            self.last_rnd = rnd
            self.turn_work = self.run_turn_section()

        if self.turn_work is None:
            print(self.log)
            return

        Exception = BaseException
        try:
            while ct.get_cpu_time_elapsed() < 1500:
                next(self.turn_work)

            self.print(f"workers_built {self.workers_built}")
            self.print(f"progress {self.progress}")

        except StopIteration:
            self.print("stopped iterating!")
            self.turn_work = None

        except Exception as e:
            self.print(f"error {e}")
            self.turn_work = None

        del self.g
        del self.ct

        print(self.log)

    def run_turn_section(self) -> Generator:
        if self.team is None or self.enemy_team is None:
            self.team = self.ct.get_team()
            self.enemy_team = Team.A if self.team == Team.B else Team.B

        if self.core is None:
            self.core = self.ct.get_id()

        player = self.g.player(self.ct.get_team())
        player.titanium = INF
        player.scale_milli = 0
        self.g.entities[self.core].base.hp = INF

        rnd = self.ct.get_current_round()

        zero_like = -10 if rnd % 4 == 3 else 0

        team_state = self.g.player(self.team)
        team_state.titanium_collected = 0
        team_state.axionite_collected = -1
        enemy_ax = random.randint(-INF, INF) if rnd < 1999 else random.randint(-INF, -2)
        enemy_state = self.g.player(self.enemy_team)
        enemy_state.axionite = enemy_ax
        enemy_state.axionite_collected = enemy_ax
        enemy_state.titanium = INF + zero_like
        enemy_state.titanium_collected = 0

        core_pos = self.ct.get_position()

        if self.builder_id is None:
            assert self.ct.can_spawn(core_pos)
            self.builder_id = self.ct.spawn_builder(core_pos)
            self.g.entities[self.builder_id].base.hp = INF
            self.give_order(self.builder_id)

        if self.turret_id is None:
            self.turret_id = GodMode.build(
                self, EntityType.SENTINEL, Position(0, 0), Direction.SOUTH
            )
            assert self.turret_id is not None
            self.g.entities[self.turret_id].base.hp = INF
            GodMode.hide_last(self.g, self.core)
            self.give_order(self.turret_id)

        for i in range(self.workers_built, 10):
            cont = GodMode.build(self, EntityType.LAUNCHER, Position(0, 0), silent=True)
            assert cont is not None, "cont is none"
            self.give_order(cont)
            GodMode.destroy(self, cont)
            self.workers_built = i + 1
            yield

        core_pos = [Position(core.x, core.y) for core in self.map.cores]
        friendly_core = (
            core_pos[0] if self.map.cores[0].team == self.team else core_pos[1]
        )

        adj = friendly_core.add(
            random.choice(
                [Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST]
            )
        )
        if core_pos != adj:
            self.print("move in replay")
            GodMode.move_in_replay(self, self.core, adj)

        self.print("surround map")
        yield from surround_map(self)

        if rnd % 3 == 0:
            yield from snipe(self)

        if rnd > 100:
            self.print("draw pentagram")
            yield from draw_pentagram(self, adj, 5, rnd * 5)

            self.print("long bridge")
            yield from long_bridge(self)

        self.print("snake update")
        yield from self.snake.update(self)

        team_state = self.g.player(self.team)
        team_state.titanium = zero_like
        team_state.axionite = 0
