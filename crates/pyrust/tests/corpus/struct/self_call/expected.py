from __future__ import annotations


class Point:
    x: int
    y: int

    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y

    @staticmethod
    def at(n):
        return Point(x=n, y=n)

    def doubled(self):
        return Point.at(self.x * 2)


p = Point.at(7)
q = p.doubled()
print(q.x)
print(q.y)
