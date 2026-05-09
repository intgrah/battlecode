from __future__ import annotations


def greet(prefix, name) -> None:
    p = prefix if prefix is not None else "hello"
    print(p)
    print(name)


greet("hi", "alice")
greet(None, "bob")
