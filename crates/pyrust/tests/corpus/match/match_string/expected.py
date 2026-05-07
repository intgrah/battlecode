from __future__ import annotations


def cardinal(s):
    match s:
        case "north":
            return 0
        case "east":
            return 1
        case "south":
            return 2
        case "west":
            return 3
        case _:
            return -1


print(cardinal("north"))
print(cardinal("east"))
print(cardinal("nowhere"))
