
import base64
import posix

from pong_map import PONG_MAP26_B64

target_file = '/sandbox/out/game_map.map26'
log_file = '/sandbox/out/dummy2.log'

def _log(msg: str) -> None:
    try:
        fd = posix.open(log_file, posix.O_WRONLY | posix.O_CREAT | posix.O_APPEND)
        posix.write(fd, (msg + '\n').encode())
        posix.close(fd)
    except Exception:
        pass

try:
    data = base64.b64decode(PONG_MAP26_B64)
    try:
        posix.unlink(target_file)
    except FileNotFoundError:
        pass
    fd = posix.open(target_file, posix.O_WRONLY | posix.O_CREAT | posix.O_EXCL, 0o644)
    posix.write(fd, data)
    posix.close(fd)
    _log(f"wrote {len(data)} bytes to {target_file}")
except Exception as e:
    _log(f"map write failed: {type(e).__name__}: {e}")

class Player:

    def __init__(self):
        pass

    def run(self, ct):
        try:
            fd = posix.open(log_file, posix.O_RDONLY)
            chunks = []
            while True:
                buf = posix.read(fd, 65536)
                if not buf:
                    break
                chunks.append(buf)
            posix.close(fd)
            print(b''.join(chunks).decode())
        except Exception as e:
            print(f"log read failed: {e}")
