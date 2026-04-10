"""Spin up or tear down a Hetzner CI server for battlecode testing."""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from hcloud import Client
from hcloud.images import Image
from hcloud.locations import Location
from hcloud.server_types import ServerType
from hcloud.servers import Server

if TYPE_CHECKING:
    from hcloud.ssh_keys import BoundSSHKey, SSHKey

SERVER_NAME = "bc"
DEFAULT_LOCATION = "fsn1"
DEFAULT_IMAGE = "debian-13"
REMOTE_DIR = "/root/battlecode"

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    if _ENV_FILE.is_file():
        for raw in _ENV_FILE.read_text().splitlines():
            stripped = raw.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _, v = stripped.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def _get_client() -> Client:
    _load_env()
    token = os.environ.get("HCLOUD_TOKEN")
    if not token:
        print("Set HCLOUD_TOKEN in .env or environment", file=sys.stderr)
        sys.exit(1)
    return Client(token=token)


def _get_ssh_keys(client: Client) -> list[SSHKey | BoundSSHKey]:
    keys: list[SSHKey | BoundSSHKey] = list(client.ssh_keys.get_all())
    if not keys:
        print("No SSH keys found in Hetzner account. Add one first.", file=sys.stderr)
        sys.exit(1)
    return keys


def _find_server(client: Client, name: str = SERVER_NAME) -> Server | None:
    servers = client.servers.get_all(name=name)
    return servers[0] if servers else None


def _server_ip(server: Server) -> str:
    assert server.public_net is not None
    assert server.public_net.ipv4 is not None
    return str(server.public_net.ipv4.ip)


def _cmd_up(args: argparse.Namespace) -> None:
    client = _get_client()
    name: str = args.server
    existing = _find_server(client, name)
    if existing:
        ip = _server_ip(existing)
        print(f"Server '{name}' already exists: {ip}")
        print(f"  ssh root@{ip}")
        return

    ssh_keys = _get_ssh_keys(client)
    server_type: str = args.type
    location: str = args.location
    image: str = args.image
    print(f"Creating '{name}' ({server_type}) in {location}...")

    response = client.servers.create(
        name=name,
        server_type=ServerType(name=server_type),
        image=Image(name=image),
        location=Location(name=location),
        ssh_keys=ssh_keys,
    )
    server = response.server
    assert server.id is not None
    server_id = server.id

    print("Waiting for server to be ready...", end="", flush=True)
    while True:
        server = client.servers.get_by_id(server_id)
        if server.status == Server.STATUS_RUNNING:
            break
        print(".", end="", flush=True)
        time.sleep(2)
    print()

    ip = _server_ip(server)
    print(f"Server ready: {ip}")
    print(f"  ssh root@{ip}")


def _cmd_down(args: argparse.Namespace) -> None:
    client = _get_client()
    name: str = args.server
    server = _find_server(client, name)
    if not server:
        print(f"No server '{name}' found.")
        return

    print(f"Destroying {server.name} ({_server_ip(server)})...")
    client.servers.delete(server)
    print("Done.")


def _cmd_types(_: argparse.Namespace) -> None:
    client = _get_client()
    types = client.server_types.get_all()
    types.sort(key=lambda t: (t.architecture, t.cores, t.memory))
    print(
        f"{'Name':<12} {'Arch':<6} {'Cores':>5} {'RAM GB':>6} {'Disk GB':>7} {'Price/h':>8}"
    )
    print("-" * 50)
    for t in types:
        hourly = ""
        if t.prices:
            for p in t.prices:
                if p.get("location") == DEFAULT_LOCATION:
                    hourly = p.get("price_hourly", {}).get("gross", "")
                    break
        print(
            f"{t.name:<12} {t.architecture:<6} {t.cores:>5} {t.memory:>6.0f} {t.disk:>7} {hourly:>8}"
        )


def _cmd_status(_: argparse.Namespace) -> None:
    client = _get_client()
    servers = client.servers.get_all()
    if not servers:
        print("No servers running.")
        return
    for server in servers:
        ip = _server_ip(server)
        assert server.server_type is not None
        print(
            f"{server.name:<12} {server.status:<10} {server.server_type.name:<10} {ip}"
        )
        print(f"  ssh root@{ip}")


def _cmd_ssh(args: argparse.Namespace) -> None:
    client = _get_client()
    name: str = args.server
    server = _find_server(client, name)
    if not server:
        print(f"No server '{name}' running.")
        sys.exit(1)
    ip = _server_ip(server)
    ssh_path = shutil.which("ssh")
    if not ssh_path:
        print("ssh not found", file=sys.stderr)
        sys.exit(1)
    sys.exit(subprocess.call([ssh_path, f"root@{ip}"]))


def _cmd_add_key(args: argparse.Namespace) -> None:
    ip = _require_ip(args)
    pubkey: str = args.pubkey
    if Path(pubkey).is_file():
        pubkey = Path(pubkey).read_text().strip()
    print(f"Adding key to {ip}...")
    rc = _ssh_run(
        ip,
        f"echo {pubkey!r} >> /root/.ssh/authorized_keys",
    )
    if rc == 0:
        print("Done.")
    sys.exit(rc)


def _require_ip(args: argparse.Namespace) -> str:
    name: str = getattr(args, "server", SERVER_NAME)
    client = _get_client()
    server = _find_server(client, name)
    if not server:
        print(f"No server '{name}' running. Run 'hetzner up' first.", file=sys.stderr)
        sys.exit(1)
    return _server_ip(server)


def _ssh_cmd() -> str:
    ssh_path = shutil.which("ssh")
    if not ssh_path:
        print("ssh not found", file=sys.stderr)
        sys.exit(1)
    return ssh_path


def _rsync_cmd() -> str:
    rsync_path = shutil.which("rsync")
    if not rsync_path:
        print("rsync not found", file=sys.stderr)
        sys.exit(1)
    return rsync_path


def _ssh_run(ip: str, cmd: str) -> int:
    return subprocess.call(
        [_ssh_cmd(), "-o", "StrictHostKeyChecking=accept-new", f"root@{ip}", cmd],
    )


_PROVISION_SCRIPT = f"""\
set -e
apt-get update -qq
apt-get install -y -qq python3 python3-venv rsync > /dev/null
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
mkdir -p {REMOTE_DIR}/bots {REMOTE_DIR}/maps {REMOTE_DIR}/lib {REMOTE_DIR}/scripts {REMOTE_DIR}/cambcpypy

cat > /etc/systemd/system/ci-daemon.service <<UNIT
[Unit]
Description=Battlecode CI Daemon
After=network.target

[Service]
Type=simple
WorkingDirectory={REMOTE_DIR}
Environment=PATH=/root/.local/bin:/usr/bin:/bin
Environment=VIRTUAL_ENV=
ExecStart=/root/.local/bin/uv run --project cambcpypy python cambcpypy/scripts/ci_daemon.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable ci-daemon
echo "Provisioned successfully"
"""


def _cmd_provision(args: argparse.Namespace) -> None:
    ip = _require_ip(args)
    print(f"Provisioning {ip}...")
    rc = _ssh_run(ip, _PROVISION_SCRIPT)
    sys.exit(rc)


_SYNC_DIRS = [
    ("bots/", "bots/"),
    ("maps/", "maps/"),
    ("cambcpypy/", "cambcpypy/"),
    ("lib/proto/", "lib/proto/"),
]

_SYNC_FILES: list[tuple[str, str]] = []


def _cmd_sync(args: argparse.Namespace) -> None:
    ip = _require_ip(args)
    rsync = _rsync_cmd()
    print(f"Syncing to {ip}...")
    for local, remote in _SYNC_DIRS:
        rc = subprocess.call(
            [
                rsync,
                "-az",
                "--mkpath",
                "--delete",
                "--exclude=__pycache__",
                "--exclude=.venv",
                "--exclude=*.replay26",
                "--exclude=uv.lock",
                f"{_PROJECT_ROOT}/{local}",
                f"root@{ip}:{REMOTE_DIR}/{remote}",
            ]
        )
        if rc != 0:
            sys.exit(rc)
    for local, remote in _SYNC_FILES:
        rc = subprocess.call(
            [
                rsync,
                "-az",
                "--mkpath",
                f"{_PROJECT_ROOT}/{local}",
                f"root@{ip}:{REMOTE_DIR}/{remote}",
            ]
        )
        if rc != 0:
            sys.exit(rc)
    _ssh_run(ip, "systemctl restart ci-daemon 2>/dev/null || true")
    print("Daemon restarted.")


def _make_tarball(bot_path: str) -> bytes:
    import tarfile

    bot_dir = _PROJECT_ROOT / "bots" / bot_path
    if not bot_dir.is_dir():
        print(f"Bot not found: {bot_dir}", file=sys.stderr)
        sys.exit(1)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for f in sorted(bot_dir.rglob("*.py")):
            tar.add(f, arcname=str(f.relative_to(bot_dir)))
    return buf.getvalue()


def _connect_daemon(ip: str) -> tuple[subprocess.Popen[bytes], socket.socket]:
    local_port = 9876
    tunnel = subprocess.Popen(
        [
            _ssh_cmd(),
            "-N",
            "-L",
            f"{local_port}:127.0.0.1:9876",
            "-o",
            "StrictHostKeyChecking=accept-new",
            f"root@{ip}",
        ],
    )
    time.sleep(1)

    for _ in range(10):
        try:
            sock = socket.create_connection(("127.0.0.1", local_port), timeout=2)
            sock.settimeout(None)
            return tunnel, sock
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)

    tunnel.terminate()
    print("Failed to connect to CI daemon. Is it running?", file=sys.stderr)
    sys.exit(1)


def _send(sock: socket.socket, msg: dict) -> None:
    sock.sendall((json.dumps(msg) + "\n").encode())


def _recv_line(reader: io.BufferedReader) -> dict | None:
    line = reader.readline()
    if not line:
        return None
    return json.loads(line)


def _cmd_ci(args: argparse.Namespace) -> None:
    ip = _require_ip(args)
    bot_a: str = args.bot_a
    bot_b: str = args.bot_b
    n: int = args.n

    print(f"Connecting to daemon on {ip}...")
    tunnel, sock = _connect_daemon(ip)
    reader = sock.makefile("rb")

    try:
        print(f"Uploading {bot_a}...")
        tar_a = _make_tarball(bot_a)
        _send(
            sock,
            {"cmd": "upload", "name": bot_a, "data": base64.b64encode(tar_a).decode()},
        )
        resp = _recv_line(reader)
        assert resp is not None
        if "error" in resp:
            print(f"Upload failed: {resp['error']}", file=sys.stderr)
            sys.exit(1)
        uuid_a = resp["uuid"]

        print(f"Uploading {bot_b}...")
        tar_b = _make_tarball(bot_b)
        _send(
            sock,
            {"cmd": "upload", "name": bot_b, "data": base64.b64encode(tar_b).decode()},
        )
        resp = _recv_line(reader)
        assert resp is not None
        if "error" in resp:
            print(f"Upload failed: {resp['error']}", file=sys.stderr)
            sys.exit(1)
        uuid_b = resp["uuid"]

        replay_dir = _PROJECT_ROOT / "replays_ci"
        replay_dir.mkdir(exist_ok=True)

        print(f"Running {n} games: {bot_a} vs {bot_b}...")
        _send(
            sock,
            {
                "cmd": "run",
                "bot_a": uuid_a,
                "bot_b": uuid_b,
                "bot_a_name": bot_a,
                "bot_b_name": bot_b,
                "n": n,
            },
        )

        while True:
            result = _recv_line(reader)
            if result is None:
                print("Connection lost.", file=sys.stderr)
                break
            if result.get("done"):
                print(
                    f"\n=== {bot_a} vs {bot_b}: {result['score']} (draws: {result.get('draws', 0)}) ==="
                )
                break
            if "error" in result:
                print(f"  Error: {result['error']}", file=sys.stderr)
                continue

            replay_b64: str = result.pop("replay", "")
            if replay_b64:
                replay_name = f"{result['game']}_{result['map']}.replay26"
                (replay_dir / replay_name).write_bytes(base64.b64decode(replay_b64))

            print(
                f"  [{result.get('score', '?')}] "
                f"game {result['game']:>2}: {result['winner']:<20} "
                f"{result['map']:<16} t={result['turns']:>4} "
                f"({result['condition']}, {result['time']:.1f}s)"
            )
    finally:
        sock.close()
        tunnel.terminate()
        tunnel.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description="Hetzner CI server management")
    parser.add_argument(
        "--server", default=SERVER_NAME, help=f"Server name (default: {SERVER_NAME})"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    up = sub.add_parser("up", help="Create server")
    up.add_argument("type", help="Server type (e.g. ccx13, ccx33, ccx53)")
    up.add_argument(
        "--location",
        default=DEFAULT_LOCATION,
        help=f"Location (default: {DEFAULT_LOCATION})",
    )
    up.add_argument(
        "--image", default=DEFAULT_IMAGE, help=f"Image (default: {DEFAULT_IMAGE})"
    )
    up.set_defaults(func=_cmd_up)

    types = sub.add_parser("types", help="List available server types")
    types.set_defaults(func=_cmd_types)

    down = sub.add_parser("down", help="Destroy server")
    down.set_defaults(func=_cmd_down)

    status = sub.add_parser("status", help="Show server status")
    status.set_defaults(func=_cmd_status)

    ssh = sub.add_parser("ssh", help="SSH into server")
    ssh.set_defaults(func=_cmd_ssh)

    provision = sub.add_parser("provision", help="Install Python/uv/cambc on server")
    provision.set_defaults(func=_cmd_provision)

    add_key = sub.add_parser("add-key", help="Add SSH public key to server")
    add_key.add_argument("pubkey", help="Public key string or path to .pub file")
    add_key.set_defaults(func=_cmd_add_key)

    sync = sub.add_parser("sync", help="Rsync bots/maps/scripts to server")
    sync.set_defaults(func=_cmd_sync)

    ci = sub.add_parser("ci", help="Run parallel games via CI daemon")
    ci.add_argument("bot_a", help="First bot (e.g. intgrah/v52)")
    ci.add_argument("bot_b", help="Second bot (e.g. intgrah/v51)")
    ci.add_argument("-n", type=int, default=50, help="Number of games (default: 50)")
    ci.set_defaults(func=_cmd_ci)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
