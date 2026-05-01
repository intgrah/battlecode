from __future__ import annotations

def add_one(v):
    v.append(1)

xs = [10, 20]
add_one(xs)
add_one(xs)
print(xs)
