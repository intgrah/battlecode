from __future__ import annotations


def maybe(n):
    return n if n >= 0 else None


a = maybe(5)
b = maybe(-1)
print(a)
if b is None:
    print("none")
