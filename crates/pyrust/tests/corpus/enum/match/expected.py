from __future__ import annotations

from enum import Enum, auto

class Light(Enum):
    Red = auto()
    Yellow = auto()
    Green = auto()

def action(l):
    match l:
        case Light.Red:
            return "stop"
        case Light.Yellow:
            return "slow"
        case Light.Green:
            return "go"

print(action(Light.Red))
print(action(Light.Yellow))
print(action(Light.Green))
