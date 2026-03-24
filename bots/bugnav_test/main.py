import importlib
import sys
import tempfile
from pathlib import Path

from cambc import Controller, EntityType, Position

sys.path.insert(0, str(Path(__file__).parent / ".." / "v27"))

bugnav_mod = importlib.import_module("bugnav")
util_mod = importlib.import_module("util")
BugNav = bugnav_mod.BugNav
DIRS = util_mod.DIRS
step_road = util_mod.step_road


class Player:
    def __init__(self) -> None:
        self.nav = BugNav()
        self.target = None
        self.spawned = False
        self.f = None

    def run(self, ct: Controller) -> None:
        if self.f is None:
            team = ct.get_team().name.lower()
            trace_path = Path(tempfile.gettempdir()) / f"bugnav_trace_{team}.txt"
            self.f = trace_path.open("w")

        if ct.get_entity_type() == EntityType.CORE:
            if not self.spawned:
                ti, _ = ct.get_global_resources()
                if ti >= ct.get_builder_bot_cost()[0]:
                    pos = ct.get_position()
                    for d in DIRS:
                        sp = pos.add(d)
                        if ct.can_spawn(sp):
                            ct.spawn_builder(sp)
                            self.spawned = True
                            return
            return

        if ct.get_entity_type() != EntityType.BUILDER_BOT:
            return

        pos = ct.get_position()
        w, h = ct.get_map_width(), ct.get_map_height()
        if self.target is None:
            self.target = Position(w - 3, h - 3)

        if pos.distance_squared(self.target) <= 8:
            self.target = (
                Position(2, 2) if self.target.x > w // 2 else Position(w - 3, h - 3)
            )
            self.nav.reset()

        if self.nav.unreachable:
            self.nav.unreachable = False
            self.target = (
                Position(2, 2) if self.target.x > w // 2 else Position(w - 3, h - 3)
            )
            self.nav.reset()

        before = (pos.x, pos.y)
        self.nav.go(ct, self.target, lambda d: step_road(ct, d))
        after = ct.get_position()
        assert self.f is not None
        self.f.write(
            f"t{ct.get_current_round()}: ({before[0]},{before[1]})->({after.x},{after.y})\n",
        )
        self.f.flush()
