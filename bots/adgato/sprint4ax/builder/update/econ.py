from __future__ import annotations

from typing import TYPE_CHECKING

from building import BuildingArmouredConveyor, BuildingConveyor, BuildingHarvester, BuildingFoundry
from cambc import Controller, Environment
from config import DEBUG_TIMING
from util import DIR8, DIR4

from ..flow import FlowValue
from ..role import Role
from ..task_harvest import ore_available, pick_ore_target
from ..task_repair import find_dangling, is_dangling

if TYPE_CHECKING:
    from builder import Builder

_OPENING_ROLES = [
    (Role.ECON, True, 0),
    (Role.ECON, False, 1),
    (Role.ECON, False, 2),
]

_INITIAL_WEIGHTS = {
    True: {Role.DEFENSE: 3, Role.OFFENSE: 0, Role.ECON: 3},
    False: {Role.DEFENSE: 3, Role.OFFENSE: 0, Role.ECON: 3},
}

_TRANSITION: dict[Role, dict[Role, int]] = {
    Role.ECON: {Role.OFFENSE: 0, Role.DEFENSE: 50, Role.ECON: 50},
    Role.DEFENSE: {Role.OFFENSE: 0, Role.DEFENSE: 80, Role.ECON: 20},
    Role.OFFENSE: {Role.OFFENSE: 0, Role.DEFENSE: 50, Role.ECON: 50},
}

_REASSIGN_PERIOD = 150
_REASSIGN_AFTER = 200

def _pick_initial_role(self: Builder, ct: Controller) -> Role:
    if self.rnd > 10:
        early = self.rnd < 200
        w = _INITIAL_WEIGHTS[early]
        roles, weights = zip(*w.items(), strict=False)
        return self.rng.choices(roles, weights=weights)[0]
    idx = ct.get_unit_count() - 3
    if 0 <= idx < len(_OPENING_ROLES):
        role, perm, scout_dir = _OPENING_ROLES[idx]
        self.permanent_role = perm
        if scout_dir is not None:
            self.scout_active = True
            self.scout_direction = scout_dir
        return role
    return Role.ECON


def update_role(self: Builder, ct: Controller) -> None:
    if self.role is None:
        self.role = _pick_initial_role(self, ct)
    if self.rnd > 25:
        self.scout_active = False

    if (
        self.role_age > _REASSIGN_PERIOD
        and self.rnd > _REASSIGN_AFTER
        and not self.permanent_role
    ):
        self.role_age = 0
        row = _TRANSITION[self.role]
        roles, weights = zip(*row.items(), strict=False)
        self.role = self.rng.choices(roles, weights=weights)[0]
        if self.role == Role.OFFENSE:
            self.role_age = -300

    self.role_age += 1


def _update_dangling(self: Builder, ct: Controller) -> None:
    my_pos = self.my_pos
    if is_dangling(self, ct, my_pos):
        self.dangling_output = my_pos
    else:
        match self.get_building(my_pos):
            case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                target = my_pos.add(d)
                if is_dangling(self, ct, target):
                    self.dangling_output = target
            case _:
                for d in DIR8:
                    n = my_pos.add(d)
                    if is_dangling(self, ct, n):
                        self.dangling_output = n
                        break
    if self.pending_bridge:
        self.dangling_output = self.pending_bridge
    elif self.dangling_output is None or not is_dangling(
        self, ct, self.dangling_output
    ):
        self.dangling_output = find_dangling(self, ct)
    
    # update dangling flow
    if self.dangling_output:
        ti = 0
        ax = 0
        rax = 0
        for pos in self.conveyors_to_here[self._idx(self.dangling_output)]:
            flow = self.get_flow(pos)
            ti += flow.ti
            ax += flow.ax
            rax += flow.rax

        pos = self.dangling_output
        for d in DIR4:
            adj = pos.add(d)
            match self.get_building(adj):
                case BuildingFoundry():
                    flow = self.get_flow(adj)
                    rax += flow.rax
                case BuildingHarvester():
                    ti_ore = self.get_env(adj) == Environment.ORE_TITANIUM
                    ti += 1 if ti_ore else 0
                    ax += 0 if ti_ore else 1

        self.dangling_flow = FlowValue(ti, ax, rax)

def _update_ore_target(self: Builder, ct: Controller) -> None:
    my_pos = self.my_pos
    candidate_ore = pick_ore_target(self, ct)
    if (
        not self.ore_target
        or not ore_available(self, ct, self.ore_target)
        or (
            candidate_ore
            and candidate_ore.distance_squared(my_pos) <= 2
            and self.ore_target.distance_squared(my_pos) > 2
        )
    ):
        self.ore_target = candidate_ore


def update_economy(self: Builder, ct: Controller) -> None:
    if DEBUG_TIMING:
        t0 = ct.get_cpu_time_elapsed()
        _update_dangling(self, ct)
        t1 = ct.get_cpu_time_elapsed()
        print(f"  loose={t1 - t0}us")
        _update_ore_target(self, ct)
        t2 = ct.get_cpu_time_elapsed()
        print(f"  ore={t2 - t1}us")
    else:
        _update_dangling(self, ct)
        _update_ore_target(self, ct)
