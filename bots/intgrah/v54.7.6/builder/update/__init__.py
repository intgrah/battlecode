from __future__ import annotations

from typing import TYPE_CHECKING

from config import DEBUG_INVARIANTS
from util.debug import Scope

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


def update(self: Builder, ct: Controller) -> None:
    with Scope("update", time=True):
        with Scope("prune", time=True):
            self.prune_stale(ct)
        with Scope("vision", time=True):
            self.update_vision(ct)
        with Scope("reflect", time=True):
            self.update_reflect()
        with Scope("reachability", time=True):
            self.update_reachability()
        with Scope("ore_deny", time=True):
            self.update_ore_denial()
        with Scope("turrets", time=True):
            self.update_enemy_turrets()
        with Scope("role", time=True):
            self.update_role(ct)
        with Scope("econ", time=True):
            self.update_map_econ(ct)
        with Scope("econ_reach", time=True):
            self.update_economy_reachability()
        with Scope("junctions", time=True):
            self.update_junctions()
        with Scope("dangling", time=True):
            self.update_unreachable_dangling()
            self.update_dangling()
        with Scope("ore", time=True):
            self.update_ore_target()
            self.update_ax_ore_target()
            self.update_offensive_ore_target()
        with Scope("foundry_target", time=True):
            self.update_foundry_target()
        with Scope("ti_sink", time=True):
            self.update_ti_sink()
        # Oracle: verifies the incrementally-maintained sets against
        # a from-scratch recomputation. Timed in its own scope so the
        # cost can be excluded by subtraction from the surrounding
        # `update` total. Gated on DEBUG_INVARIANTS — a no-op (apart
        # from the empty Scope) in production.
        if DEBUG_INVARIANTS:
            with Scope("invariants", time=True):
                self.check_invariants()
