from __future__ import annotations

import random
from typing import TYPE_CHECKING

from cambc import Direction, EntityType, Position, Team
from god_mode import GodMode
from rust import EntityBuilderBot, EntitySentinel, Game, RawMem

INF = 1_000_000_000

if TYPE_CHECKING:
    from collections.abc import Generator

    from cambc import Controller


class Player:
    def __init__(self) -> None:
        self.core: int | None = None
        self.builder_id: int | None = None
        self.turret_id: int | None = None
        self.team: Team | None = None
        self.enemy_team: Team | None = None
        self.workers_built: int = 0
        self.built = False
        self.turn_work: Generator | None = None
        self.last_rnd = -1
        self.log: str = ""
        self.progress = 0

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

    def print(self, message: object) -> None:
        self.log += str(message) + "\n"

    def run(self, ct: Controller) -> None:

        if ct.get_entity_type() != EntityType.CORE:
            ct.resign("non core got a turn")
            return

        self.ct = ct
        self.g = Game.open(RawMem(), ct)

        rnd = ct.get_current_round()
        if self.last_rnd != rnd:
            self.log = ""
            self.last_rnd = rnd
            self.turns_this_round = 0
            self.turn_work = self.run_turn_section()

        if self.turn_work is None:
            print(self.log)
            return

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

        self.g.player(self.ct.get_team()).titanium = INF
        self.g.entities[self.core].base.hp = INF

        if self.builder_id is None:
            assert self.ct.can_spawn(self.ct.get_position())
            self.builder_id = self.ct.spawn_builder(self.ct.get_position())
            self.g.entities[self.builder_id].base.hp = INF
            GodMode.hide_last(self.g, self.core)
            for i in range(len(self.g.unit_order)):
                uid = self.g.unit_order[i]
                if uid == self.builder_id:
                    self.g.unit_order[i] = self.core
                    break

        if self.turret_id is None:
            self.turret_id = GodMode.build(
                self, EntityType.SENTINEL, Position(0, 0), Direction.SOUTH
            )
            assert self.turret_id is not None
            self.g.entities[self.turret_id].base.hp = INF
            GodMode.hide_last(self.g, self.core)
            for i in range(len(self.g.unit_order)):
                uid = self.g.unit_order[i]
                if uid == self.turret_id:
                    self.g.unit_order[i] = self.core
                    break

        for i in range(self.workers_built, 40):
            cont = GodMode.build(self, EntityType.LAUNCHER, Position(0, 0), silent=True)
            assert cont is not None, "cont is none"

            for j in range(len(self.g.unit_order)):
                uid = self.g.unit_order[j]
                if uid == cont:
                    self.print((j, cont))
                    self.g.unit_order[j] = self.core
                    break
            GodMode.destroy(self, cont)
            self.workers_built = i
            yield

        if not self.built:
            road_id = GodMode.build(
                self, EntityType.ROAD, Position(10, 10), silent=True
            )
            if road_id is not None:
                GodMode.move_last_in_replay(self, Position(-1, -1))
            GodMode.move(self, self.core, Position(1, 1))
            self.built = True

        GodMode.draw_line(
            self,
            Position(-1, -1),
            Position(self.ct.get_map_width(), self.ct.get_map_height()),
        )
        GodMode.draw_line(
            self,
            Position(self.ct.get_map_width() - 1, 0),
            Position(0, self.ct.get_map_height() - 1),
        )

        rnd = self.ct.get_current_round()

        zero_like = -10 if rnd % 4 == 3 else 0

        team_state = self.g.player(self.team)
        team_state.titanium = zero_like
        team_state.axionite = 0
        team_state.titanium_collected = 0
        team_state.axionite_collected = -1

        enemy_ax = random.randint(-INF, INF) if rnd < 1999 else random.randint(-INF, -2)

        enemy_state = self.g.player(self.enemy_team)
        enemy_state.titanium = INF + zero_like
        enemy_state.titanium_collected = 0
        enemy_state.axionite = enemy_ax
        enemy_state.axionite_collected = enemy_ax

        # busy work
        for i in range(100000):
            self.progress = i
            yield
