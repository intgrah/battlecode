from __future__ import annotations


def greet(prefix, name):
    p = prefix if prefix is not None else "hello"
    print(p)
    print(name)


greet("hi", "alice")
greet(None, "bob")
