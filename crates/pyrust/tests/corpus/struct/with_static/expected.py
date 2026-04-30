class Point:
    x: int
    y: int

    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y

    @staticmethod
    def origin():
        return Point(x=0, y=0)

o = Point.origin()
print(o.x)
print(o.y)
