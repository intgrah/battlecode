from __future__ import annotations

import sys
import traceback
from typing import TYPE_CHECKING

from builder import Builder
from cambc import Controller, EntityType, GameError
from core import Core
from gunner import Gunner
from launcher import Launcher
from sentinel import Sentinel

if TYPE_CHECKING:
    from unit import Unit


class Player:
    def __init__(self) -> None:
        self.unit: Unit | None = None

    def run(self, ct: Controller) -> None:
        if self.unit is None:
            try:
                match ct.get_entity_type():
                    case EntityType.BUILDER_BOT:
                        self.unit = Builder(ct)
                    case EntityType.CORE:
                        self.unit = Core(ct)
                    case EntityType.SENTINEL:
                        self.unit = Sentinel(ct)
                    case EntityType.GUNNER:
                        self.unit = Gunner(ct)
                    case EntityType.LAUNCHER:
                        self.unit = Launcher(ct)
                    case _:
                        return
            except RuntimeError as e:
                # Builder.__init__ can raise "Core not visible at spawn"
                # on certain maps where the spawn position lands on a
                # core tile but get_nearby_buildings doesn't return the
                # core entity within the same round (engine quirk).
                # Skip this turn — re-init next round.
                print(f"INIT_RETRY: {e}", file=sys.stderr)
                return
        try:
            self.unit.run(ct)
        except GameError as e:
            print(traceback.format_exc())
            print(f"GAME_ERROR: {e}")
            print(traceback.format_exc(), file=sys.stderr)
            print(f"GAME_ERROR: {e}", file=sys.stderr)
            ct.resign(str(e))
        except Exception as e:  # noqa: BLE001
            print(traceback.format_exc())
            print(f"EXCEPTION: {e}")
            print(traceback.format_exc(), file=sys.stderr)
            print(f"EXCEPTION: {e}", file=sys.stderr)
            ct.resign(str(e))
