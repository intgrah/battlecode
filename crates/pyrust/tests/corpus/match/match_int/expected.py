from __future__ import annotations


def name(n):
    match n:
        case 0:
            return "zero"
        case 1:
            return "one"
        case _:
            return "many"


print(name(0))
print(name(1))
print(name(7))
