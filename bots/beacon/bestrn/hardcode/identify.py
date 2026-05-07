"""
Stub for `bots/intgrah/v54.7.9/hardcode/identify.py`.

Phase E will replace this with the real identifier. For now, callers
gate on `HARDCODE` and never reach these — they panic if invoked.
"""

from __future__ import annotations


def find_core(_ct, _hint):
    """
    Placeholder for `find_core(ct, pos)`. Real impl returns the centre of a
    known core in vision; the stub is unreachable when `HARDCODE` is false.
    """
    return (_ for _ in ()).throw(NotImplementedError())


def identify_map(_w, _h, _my_core) -> None:
    """
    Placeholder for `identify_map(w, h, my_core)`. Real impl returns a
    `KnownMap` describing the precomputed level. Returns `None` because
    the v55 default is `HARDCODE=false`.
    """
    return


class KnownMap:
    """
    Opaque placeholder for the hardcoded-map type. Phase E will define the
    real shape (level id, symmetry, tile encoding).
    """
