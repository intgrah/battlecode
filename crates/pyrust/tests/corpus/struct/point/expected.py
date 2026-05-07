from __future__ import annotations


class Point:
    x: int
    y: int

    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y


p = Point(x=3, y=4)
print(p.x)
print(p.y)
