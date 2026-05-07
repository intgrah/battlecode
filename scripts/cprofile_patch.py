"""Inject per-Player cProfile into a translated bot's main.py.

cambc-libre runs all bot units in one Python interpreter (no
subinterpreter isolation), so a module-level cProfile.enable() clashes.
This patch attaches the Profile to the Player instance instead, so each
Player has its own profiler, enabled around its own run() call.

Usage: python3 /tmp/cprofile_patch.py path/to/main.py
"""

from __future__ import annotations

import sys

SNIPPET = """
# === per-Player cProfile (cambc-libre safe — no module-level enable) ===
import cProfile as _cP
import io as _io
import pstats as _pstats
import sys as _sys

_CP_REPORT_EVERY = 200

_cp_orig_init = Player.__init__
def _cp_wrap_init(self, *a, **kw):
    _cp_orig_init(self, *a, **kw)
    self._cp_prof = _cP.Profile()
    self._cp_turns = 0
Player.__init__ = _cp_wrap_init

_cp_orig_run = Player.run
def _cp_wrap_run(self, ct):
    # runcall handles enable/disable internally — sandbox forbids
    # `finally` and `BaseException` so we can't write the wrap by hand.
    self._cp_prof.runcall(_cp_orig_run, self, ct)
    self._cp_turns += 1
    if self._cp_turns % _CP_REPORT_EVERY == 0:
        try:
            uid = ct.get_id()
        except Exception:
            uid = -1
        s = _io.StringIO()
        ps = _pstats.Stats(self._cp_prof, stream=s).sort_stats('cumulative')
        ps.print_stats(30)
        print('CPROF_BEGIN uid=' + str(uid) + ' turn=' + str(self._cp_turns), file=_sys.stderr, flush=True)
        for line in s.getvalue().splitlines():
            if line.strip():
                print('CPROF ' + line, file=_sys.stderr, flush=True)
        print('CPROF_END uid=' + str(uid), file=_sys.stderr, flush=True)
Player.run = _cp_wrap_run
"""

for path in sys.argv[1:]:
    s = open(path).read()
    if "_CP_PROF" in s or "_cp_wrap_init" in s:
        s = s.split("# === per-Player cProfile")[0]
        s = s.split("# === cProfile per-subinterpreter")[0]
    s += SNIPPET
    open(path, "w").write(s)
    print(f"patched {path}")
