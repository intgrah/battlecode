from __future__ import annotations


def quadrant(p) -> str:
    match p:
        case (0, 0):
            return "origin"
        case (0, _):
            return "y-axis"
        case (_, 0):
            return "x-axis"
        case _:
            return "elsewhere"


print(quadrant((0, 0)))
print(quadrant((0, 5)))
print(quadrant((3, 0)))
print(quadrant((1, 1)))
