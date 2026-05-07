from __future__ import annotations


class Cell:
    row: int
    col: int
    weight: int

    def __init__(self, row: int, col: int, weight: int):
        self.row = row
        self.col = col
        self.weight = weight


r = 2
c = 5
cell = Cell(row=r, col=c, weight=100)
print(cell.row)
print(cell.col)
print(cell.weight)
