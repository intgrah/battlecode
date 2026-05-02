"""Translation of `bots/intgrah/v54.7.9/builder/update/`."""
from __future__ import annotations

from . import econ
from . import patrol
from . import prune
from . import reflect
from . import role
from . import threat
from . import turrets
from . import vision
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller
if TYPE_CHECKING:
    from builder import Builder
from config import DEBUG_INVARIANTS
from util.debug import Scope

def update(builder, ct):
    with Scope.new_timed("update") as _g:
        with Scope.new_timed("prune") as _g:
            prune.prune_stale(builder, ct)
        with Scope.new_timed("vision") as _g:
            vision.update_vision(builder, ct)
        with Scope.new_timed("reflect") as _g:
            reflect.update_reflect(builder)
        with Scope.new_timed("reachability") as _g:
            builder.update_reachability()
        with Scope.new_timed("ore_deny") as _g:
            turrets.update_ore_denial(builder)
        with Scope.new_timed("turrets") as _g:
            turrets.update_enemy_turrets(builder)
        with Scope.new_timed("threat") as _g:
            threat.apply_threat_overlay(builder)
        with Scope.new_timed("role") as _g:
            role.update_role(builder)
        with Scope.new_timed("econ") as _g:
            econ.update_map_econ(builder, ct)
        with Scope.new_timed("econ_reach") as _g:
            econ.update_economy_reachability(builder)
        with Scope.new_timed("junctions") as _g:
            econ.update_junctions(builder)
        with Scope.new_timed("dangling") as _g:
            with Scope.new_timed("dangling") as _g:
                econ.update_unreachable_dangling(builder)
            with Scope.new_timed("dangling") as _g:
                econ.update_dangling(builder)
        with Scope.new_timed("ore_target") as _g:
            with Scope.new_timed("update_ti_ore_target") as _g:
                econ.update_ti_ore_target(builder)
            with Scope.new_timed("update_ax_ore_target") as _g:
                econ.update_ax_ore_target(builder)
            with Scope.new_timed("update_offensive_ore_target") as _g:
                econ.update_offensive_ore_target(builder)
        with Scope.new_timed("foundry_target") as _g:
            econ.update_foundry_target(builder)
        with Scope.new_timed("ti_sink") as _g:
            econ.update_ti_sink(builder)
        with Scope.new_timed("patrol") as _g:
            patrol.update_patrol(builder)
        if DEBUG_INVARIANTS:
            with Scope.new_timed("invariants") as _g:
                econ.check_invariants(builder)
