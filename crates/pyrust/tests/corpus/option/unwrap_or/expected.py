from __future__ import annotations

def lookup(found):
    return 99 if found else None

print(lookup(True) if lookup(True) is not None else 0)
print(lookup(False) if lookup(False) is not None else -1)
