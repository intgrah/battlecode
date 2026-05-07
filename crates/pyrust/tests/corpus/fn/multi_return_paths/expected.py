from __future__ import annotations


def classify(n):
    if n < 0:
        return -1
    if n == 0:
        return 0
    return 1


print(classify(-5))
print(classify(0))
print(classify(7))
