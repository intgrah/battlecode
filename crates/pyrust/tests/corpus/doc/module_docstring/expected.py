from __future__ import annotations

"""
A two-line module.

Greets the world.
"""


def greet(name) -> None:
    """
    Greets the named recipient.

    The greeting is fixed; only the name varies.
    """
    print(name)


greet("world")
