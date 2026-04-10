"""Spin up or tear down a Hetzner CI server for battlecode testing."""

from __future__ import annotations

import argparse
import os
import shutil
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

SERVER_NAME = "bc-ci"
DEFAULT_TYPE = "ccx53"
DEFAULT_LOCATION = "fsn1"
DEFAULT_IMAGE = "debian-13"
REMOTE_DIR = "/root/battlecode2"

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


def _find_server(client: Client) -> Server | None:
    servers = client.servers.get_all(name=SERVER_NAME)
    return servers[0] if servers else None


def _server_ip(server: Server) -> str:
    assert server.public_net is not None
    assert server.public_net.ipv4 is not None
    return str(server.public_net.ipv4.ip)


def _cmd_up(args: argparse.Namespace) -> None:
    client = _get_client()
    existing = _find_server(client)
    if existing:
        ip = _server_ip(existing)
        print(f"Server already exists: {ip}")
        print(f"  ssh root@{ip}")
        return

    ssh_keys = _get_ssh_keys(client)
    server_type: str = args.type
    location: str = args.location
    image: str = args.image
    print(f"Creating {server_type} in {location}...")

    response = client.servers.create(
        name=SERVER_NAME,
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


def _cmd_down(_: argparse.Namespace) -> None:
    client = _get_client()
    server = _find_server(client)
    if not server:
        print("No server found.")
        return

    print(f"Destroying {server.name} ({_server_ip(server)})...")
    client.servers.delete(server)
    print("Done.")


def _cmd_status(_: argparse.Namespace) -> None:
    client = _get_client()
    server = _find_server(client)
    if not server:
        print("No server running.")
        return
    ip = _server_ip(server)
    assert server.server_type is not None
    print(f"Name:   {server.name}")
    print(f"Status: {server.status}")
    print(f"Type:   {server.server_type.name}")
    print(f"IP:     {ip}")
    print(f"  ssh root@{ip}")


def _cmd_ssh(_: argparse.Namespace) -> None:
    client = _get_client()
    server = _find_server(client)
    if not server:
        print("No server running.")
        sys.exit(1)
    ip = _server_ip(server)
    ssh_path = shutil.which("ssh")
    if not ssh_path:
        print("ssh not found", file=sys.stderr)
        sys.exit(1)
    sys.exit(subprocess.call([ssh_path, f"root@{ip}"]))


def _require_ip() -> str:
    client = _get_client()
    server = _find_server(client)
    if not server:
        print("No server running. Run 'hetzner up' first.", file=sys.stderr)
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
mkdir -p {REMOTE_DIR}
cd {REMOTE_DIR}
uv venv -q --python 3.12
uv pip install -q cambc
echo "Provisioned successfully"
"""


def _cmd_provision(_: argparse.Namespace) -> None:
    ip = _require_ip()
    print(f"Provisioning {ip}...")
    rc = _ssh_run(ip, _PROVISION_SCRIPT)
    sys.exit(rc)


def _cmd_sync(_: argparse.Namespace) -> None:
    ip = _require_ip()
    rsync = _rsync_cmd()
    print(f"Syncing to {ip}...")
    rc = subprocess.call(
        [
            rsync,
            "-az",
            "--delete",
            "--exclude=__pycache__",
            "--exclude=.venv",
            "--exclude=*.replay26",
            f"{_PROJECT_ROOT}/bots/",
            f"root@{ip}:{REMOTE_DIR}/bots/",
        ]
    )
    if rc != 0:
        sys.exit(rc)
    rc = subprocess.call(
        [
            rsync,
            "-az",
            f"{_PROJECT_ROOT}/maps/",
            f"root@{ip}:{REMOTE_DIR}/maps/",
        ]
    )
    if rc != 0:
        sys.exit(rc)
    rc = subprocess.call(
        [
            rsync,
            "-az",
            f"{_PROJECT_ROOT}/scripts/ci.sh",
            f"root@{ip}:{REMOTE_DIR}/scripts/ci.sh",
        ]
    )
    sys.exit(rc)


def _cmd_ci(args: argparse.Namespace) -> None:
    ip = _require_ip()
    n: int = args.n
    _cmd_sync(args)
    print(f"Running CI with {n} maps...")
    rc = _ssh_run(
        ip,
        f'export PATH="$HOME/.local/bin:$PATH" && cd {REMOTE_DIR} && bash scripts/ci.sh {n}',
    )
    sys.exit(rc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Hetzner CI server management")
    sub = parser.add_subparsers(dest="command", required=True)

    up = sub.add_parser("up", help="Create server")
    up.add_argument(
        "--type", default=DEFAULT_TYPE, help=f"Server type (default: {DEFAULT_TYPE})"
    )
    up.add_argument(
        "--location",
        default=DEFAULT_LOCATION,
        help=f"Location (default: {DEFAULT_LOCATION})",
    )
    up.add_argument(
        "--image", default=DEFAULT_IMAGE, help=f"Image (default: {DEFAULT_IMAGE})"
    )
    up.set_defaults(func=_cmd_up)

    down = sub.add_parser("down", help="Destroy server")
    down.set_defaults(func=_cmd_down)

    status = sub.add_parser("status", help="Show server status")
    status.set_defaults(func=_cmd_status)

    ssh = sub.add_parser("ssh", help="SSH into server")
    ssh.set_defaults(func=_cmd_ssh)

    provision = sub.add_parser("provision", help="Install Python/uv/cambc on server")
    provision.set_defaults(func=_cmd_provision)

    sync = sub.add_parser("sync", help="Rsync bots/maps/scripts to server")
    sync.set_defaults(func=_cmd_sync)

    ci = sub.add_parser("ci", help="Sync and run CI on server")
    ci.add_argument("-n", type=int, default=12, help="Number of maps (default: 12)")
    ci.set_defaults(func=_cmd_ci)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
