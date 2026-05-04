import sys


def w(msg: str) -> None:
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


class Player:
    def __init__(self) -> None:
        self._tried = False

    def run(self, ct) -> None:
        if self._tried:
            return
        self._tried = True
        try:
            with open("/proc/self/cmdline", "rb") as fh:
                w(f"CMDLINE: {fh.read()!r}")
        except Exception as e:
            w(f"OPEN_ERR: {type(e).__name__}: {e}")
        try:
            w(f"ARGV: {sys.argv!r}")
        except Exception as e:
            w(f"ARGV_ERR: {type(e).__name__}: {e}")
        ct.resign("done")
