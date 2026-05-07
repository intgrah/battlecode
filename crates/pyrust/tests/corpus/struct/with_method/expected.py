from __future__ import annotations


class Counter:
    n: int

    def __init__(self, n: int) -> None:
        self.n = n

    def increment(self) -> None:
        self.n = self.n + 1

    def value(self):
        return self.n


c = Counter(n=10)
c.increment()
c.increment()
c.increment()
print(c.value())
