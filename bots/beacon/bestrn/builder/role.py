"""Translation of `bots/intgrah/v54.7.9/builder/role.py`."""
from __future__ import annotations

from enum import IntEnum

class Role(IntEnum):
    Econ = 0
    Defense = 1
    Push = 2
    PermEcon = 3
    PermDefense = 4
    Parasitic = 5
    EconReactive = 6

    def is_offensive(self):
        return (self == Role.Push or self == Role.Parasitic)
