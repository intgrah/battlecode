from __future__ import annotations

def parity(n):
    match n:
        case 0 | 2 | 4 | 6 | 8:
            return "even-low"
        case 1 | 3 | 5 | 7 | 9:
            return "odd-low"
        case _:
            return "big"

print(parity(2))
print(parity(7))
print(parity(42))
