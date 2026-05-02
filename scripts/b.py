"""Run cambc-libre matches on `root@b`. No streaming, no daemon.

Subcommands:
  sync                    rsync engine source, bots, maps to remote
  build                   build cambc-libre + a Rust bot on remote
  run A B [opts]          run match(es); replays come back to replays/b/
  ssh ...                 forwarded `ssh root@b ...`

Env:
  REMOTE   override host (default `root@b`)
  RUSTFLAGS  inherited by remote cargo (e.g. `-Awarnings`)
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REMOTE = os.environ.get("REMOTE", "root@b")
REMOTE_DIR = "/root/battlecode"
LOCAL_REPLAYS = ROOT / "replays" / "b"


def ssh(*args: str, check: bool = True) -> int:
    cmd = [
        "ssh",
        "-o",
        "ControlMaster=auto",
        "-o",
        "ControlPath=~/.ssh/cm-%C",
        "-o",
        "ControlPersist=60s",
        REMOTE,
        *args,
    ]
    return subprocess.run(cmd, check=check).returncode


def rsync(src: str, dst: str, *extra: str) -> None:
    subprocess.run(["rsync", "-az", "--mkpath", *extra, src, dst], check=True)  # noqa: S607


def cmd_sync(_: argparse.Namespace) -> None:
    ssh(f"mkdir -p {REMOTE_DIR}")
    # Engine + workspace, excluding heavy build artefacts.
    rsync(
        f"{ROOT}/",
        f"{REMOTE}:{REMOTE_DIR}/",
        "--delete",
        "--exclude=target/",
        "--exclude=replays/",
        "--exclude=.git/",
        "--exclude=__pycache__/",
        "--exclude=.venv/",
        "--exclude=node_modules/",
        "--exclude=*.replay26",
    )
    print(f"synced {ROOT} → {REMOTE}:{REMOTE_DIR}")


def cmd_build(args: argparse.Namespace) -> None:
    flags = os.environ.get("RUSTFLAGS", "")
    env = f"RUSTFLAGS={shlex.quote(flags)}" if flags else ""
    bot = args.bot
    extra_env = f"DEBUG_DUMP={args.debug_dump}" if args.debug_dump else ""
    script = f"""set -e
. "$HOME/.cargo/env"
cd {REMOTE_DIR}
{env} {extra_env} cargo install --path crates/libre --bin cambc-libre --offline --quiet 2>&1 | tail -3 || true
{env} {extra_env} cargo build --release -p {shlex.quote(bot)}
"""
    ssh(script)


def cmd_run(args: argparse.Namespace) -> None:
    LOCAL_REPLAYS.mkdir(parents=True, exist_ok=True)
    remote_dir = f"/tmp/b_replays_{int(time.time())}"  # noqa: S108
    debug = "DEBUG_DUMP=1 " if args.debug_dump else ""
    rounds_arg = f"--rounds {args.rounds}" if args.rounds else ""
    map_arg = args.map
    n = args.n
    a, b = args.bot_a, args.bot_b
    a_safe = a.replace("/", "_")
    b_safe = b.replace("/", "_")
    cmd = f"""set -e
. "$HOME/.cargo/env"
mkdir -p {remote_dir}
cd {REMOTE_DIR}
for i in $(seq 1 {n}); do
    out={remote_dir}/{a_safe}_vs_{b_safe}_{map_arg}_$i.replay26
    {debug}cambc-libre run {rounds_arg} --replay $out {shlex.quote(a)} {shlex.quote(b)} {shlex.quote(map_arg)} 2>&1 | tail -8
done
"""
    print(f"running {n} game(s) on {REMOTE}: {a} vs {b} on {map_arg}")
    ssh(cmd)
    rsync(f"{REMOTE}:{remote_dir}/", f"{LOCAL_REPLAYS}/")
    ssh(f"rm -rf {remote_dir}")
    print(f"replays → {LOCAL_REPLAYS}")


def cmd_ssh(args: argparse.Namespace) -> None:
    ssh(*args.cmd, check=False)


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sync").set_defaults(fn=cmd_sync)

    bld = sub.add_parser("build")
    bld.add_argument("bot", default="v55", nargs="?")
    bld.add_argument(
        "--debug-dump", default="1", help="DEBUG_DUMP value (default 1, empty to unset)"
    )
    bld.set_defaults(fn=cmd_build)

    run = sub.add_parser("run")
    run.add_argument("bot_a")
    run.add_argument("bot_b")
    run.add_argument("-m", "--map", default="craters")
    run.add_argument("-n", type=int, default=1)
    run.add_argument("-r", "--rounds", type=int, default=200)
    run.add_argument(
        "--no-debug-dump", dest="debug_dump", action="store_false", default=True
    )
    run.set_defaults(fn=cmd_run)

    s = sub.add_parser("ssh")
    s.add_argument("cmd", nargs=argparse.REMAINDER)
    s.set_defaults(fn=cmd_ssh)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
