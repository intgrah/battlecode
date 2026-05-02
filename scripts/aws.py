"""Spin up or tear down an AWS EC2 CI server for battlecode testing.

Mirror of hetzner.py — same provisioning, sync, and CI daemon interface,
just backed by AWS EC2 instead of Hetzner Cloud.

Requires: pip install boto3
Credentials: AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY in .env or environment.
"""

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
import tarfile
import time
from pathlib import Path

import boto3

SERVER_NAME = "bc"
DEFAULT_REGION = "us-east-1"
DEFAULT_INSTANCE_TYPE = "m7g.8xlarge"  # Graviton ARM64 (matches ladder); 4GB/vCPU for sweep workers
DEFAULT_AMI = "ami-0e9865ca8e02dc0ab"  # Debian 12 arm64 us-east-1
REMOTE_DIR = "/home/admin/battlecode"

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    if _ENV_FILE.is_file():
        for raw in _ENV_FILE.read_text().splitlines():
            stripped = raw.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _, v = stripped.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def _get_ec2(region: str = DEFAULT_REGION):
    _load_env()
    return boto3.resource("ec2", region_name=region)


def _get_client(region: str = DEFAULT_REGION):
    _load_env()
    return boto3.client("ec2", region_name=region)


def _find_instance(ec2, name: str = SERVER_NAME):
    instances = list(
        ec2.instances.filter(
            Filters=[
                {"Name": "tag:Name", "Values": [name]},
                {"Name": "instance-state-name", "Values": ["running", "pending"]},
            ]
        )
    )
    return instances[0] if instances else None


def _instance_ip(instance) -> str:
    return instance.public_ip_address


def _get_or_create_sg(ec2_client, region: str) -> str:
    """Get or create a security group that allows SSH."""
    sg_name = "bc-ci-sg"
    try:
        resp = ec2_client.describe_security_groups(GroupNames=[sg_name])
        return resp["SecurityGroups"][0]["GroupId"]
    except ec2_client.exceptions.ClientError:
        pass
    resp = ec2_client.create_security_group(
        GroupName=sg_name,
        Description="Battlecode CI - SSH access",
    )
    sg_id = resp["GroupId"]
    ec2_client.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[
            {
                "IpProtocol": "tcp",
                "FromPort": 22,
                "ToPort": 22,
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
            }
        ],
    )
    return sg_id


def _get_or_create_keypair(ec2_client) -> str:
    """Ensure an EC2 key pair exists that matches our local SSH key."""
    key_name = "bc-ci-key"
    try:
        ec2_client.describe_key_pairs(KeyNames=[key_name])
        return key_name
    except ec2_client.exceptions.ClientError:
        pass
    _load_env()
    pubkey_env = os.environ.get("AWS_SSH_KEY", "")
    if pubkey_env:
        pubkey_path = Path(os.path.expanduser(pubkey_env))
    else:
        pubkey_path = Path.home() / ".ssh" / "id_ed25519.pub"
        if not pubkey_path.exists():
            pubkey_path = Path.home() / ".ssh" / "id_rsa.pub"
    if not pubkey_path.exists():
        print(f"SSH public key not found: {pubkey_path}", file=sys.stderr)
        sys.exit(1)
    ec2_client.import_key_pair(
        KeyName=key_name,
        PublicKeyMaterial=pubkey_path.read_bytes(),
    )
    return key_name


def _cmd_up(args: argparse.Namespace) -> None:
    region = args.region
    ec2 = _get_ec2(region)
    ec2_client = _get_client(region)
    name = args.server

    existing = _find_instance(ec2, name)
    if existing:
        ip = _instance_ip(existing)
        print(f"Server '{name}' already running: {ip}")
        print(f"  ssh root@{ip}")
        return

    instance_type = args.type
    ami = args.ami
    sg_id = _get_or_create_sg(ec2_client, region)
    key_name = _get_or_create_keypair(ec2_client)

    print(f"Launching '{name}' ({instance_type}) in {region}...")
    instances = ec2.create_instances(
        ImageId=ami,
        InstanceType=instance_type,
        KeyName=key_name,
        SecurityGroupIds=[sg_id],
        MinCount=1,
        MaxCount=1,
        BlockDeviceMappings=[
            {
                "DeviceName": "/dev/xvda",
                "Ebs": {
                    "VolumeSize": 100,
                    "VolumeType": "gp3",
                    "DeleteOnTermination": True,
                },
            },
        ],
        InstanceMarketOptions={
            "MarketType": "spot",
            "SpotOptions": {
                "SpotInstanceType": "one-time",
                "InstanceInterruptionBehavior": "terminate",
            },
        },
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [{"Key": "Name", "Value": name}],
            }
        ],
    )
    instance = instances[0]
    print("Waiting for instance to be running...", end="", flush=True)
    instance.wait_until_running()
    instance.reload()
    print()

    ip = _instance_ip(instance)
    print(f"Instance ready: {ip}")
    print(f"  ssh root@{ip}")
    print("  (wait ~30s for SSH to be available, then run: aws.py provision)")


def _cmd_down(args: argparse.Namespace) -> None:
    ec2 = _get_ec2(args.region)
    name = args.server
    instance = _find_instance(ec2, name)
    if not instance:
        print(f"No instance '{name}' found.")
        return
    print(f"Terminating {name} ({_instance_ip(instance)})...")
    instance.terminate()
    print("Done.")


def _cmd_status(args: argparse.Namespace) -> None:
    ec2 = _get_ec2(args.region)
    instances = list(
        ec2.instances.filter(
            Filters=[{"Name": "instance-state-name", "Values": ["running", "pending"]}]
        )
    )
    if not instances:
        print("No instances running.")
        return
    for inst in instances:
        name_tag = ""
        if inst.tags:
            for t in inst.tags:
                if t["Key"] == "Name":
                    name_tag = t["Value"]
        ip = inst.public_ip_address or "pending"
        print(f"{name_tag:<12} {inst.state['Name']:<10} {inst.instance_type:<14} {ip}")
        if inst.public_ip_address:
            print(f"  ssh root@{ip}")


def _cmd_ssh(args: argparse.Namespace) -> None:
    ec2 = _get_ec2(args.region)
    name = args.server
    instance = _find_instance(ec2, name)
    if not instance:
        print(f"No instance '{name}' running.", file=sys.stderr)
        sys.exit(1)
    ip = _instance_ip(instance)
    # Debian AMI uses 'admin' user, not root
    user = "admin"
    sys.exit(subprocess.call([_ssh_cmd(), f"{user}@{ip}"]))


# ── Shared infrastructure (identical to hetzner.py) ──────────────


def _require_ip(args: argparse.Namespace) -> str:
    ec2 = _get_ec2(args.region)
    name = args.server
    instance = _find_instance(ec2, name)
    if not instance:
        print(f"No instance '{name}' running.", file=sys.stderr)
        sys.exit(1)
    return _instance_ip(instance)


def _ssh_cmd() -> str:
    p = shutil.which("ssh")
    if not p:
        print("ssh not found", file=sys.stderr)
        sys.exit(1)
    return p


def _rsync_cmd() -> str:
    p = shutil.which("rsync")
    if not p:
        print("rsync not found", file=sys.stderr)
        sys.exit(1)
    return p


def _ssh_identity() -> str:
    _load_env()
    key = os.environ.get("AWS_SSH_KEY", "")
    if key:
        pem = os.path.expanduser(key.replace(".pub", ".pem"))
        if Path(pem).exists():
            return pem
    return ""


def _ssh_run(ip: str, cmd: str, user: str = "admin") -> int:
    args = [_ssh_cmd(), "-o", "StrictHostKeyChecking=accept-new"]
    identity = _ssh_identity()
    if identity:
        args.extend(["-i", identity])
    args.append(f"{user}@{ip}")
    args.append(cmd)
    return subprocess.call(args)


_PROVISION_SCRIPT = f"""\
set -e
# Kill any background apt processes that hold the lock
sudo killall -q apt-get apt unattended-upgrades 2>/dev/null || true
sleep 1
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-venv rsync pypy3 > /dev/null
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# Install CPython 3.12 — bot sources use `from typing import override`
# which requires 3.12+. PyPy is avoided because its multiprocessing
# SemLock._rebuild fails across spawn/forkserver, crashing the
# ProcessPoolExecutor workers.
uv python install 3.12

sudo mkdir -p {REMOTE_DIR}/bots {REMOTE_DIR}/maps {REMOTE_DIR}/cambc_pypy {REMOTE_DIR}/proto
sudo chown -R $(whoami) {REMOTE_DIR}

cat > /tmp/ci-daemon.service <<UNIT
[Unit]
Description=Battlecode CI Daemon
After=network.target

[Service]
Type=simple
WorkingDirectory={REMOTE_DIR}
Environment=PATH=/home/admin/.local/bin:/usr/bin:/bin
Environment=VIRTUAL_ENV=
ExecStart=/home/admin/.local/bin/uv run --python pypy3 --project cambc_pypy python cambc_pypy/scripts/ci_daemon.py
Restart=always
RestartSec=2
User=admin

[Install]
WantedBy=multi-user.target
UNIT

sudo mv /tmp/ci-daemon.service /etc/systemd/system/ci-daemon.service
sudo systemctl daemon-reload
sudo systemctl enable ci-daemon
echo "Provisioned successfully"
"""


def _cmd_provision(args: argparse.Namespace) -> None:
    ip = _require_ip(args)
    user = "admin"
    print(f"Provisioning {ip}...")
    rc = _ssh_run(ip, _PROVISION_SCRIPT, user=user)
    sys.exit(rc)


_SYNC_DIRS = [
    ("bots/", "bots/"),
    ("maps/", "maps/"),
    ("pkg/cambc_pypy/", "cambc_pypy/"),
    ("pkg/proto/", "proto/"),
]



def _cmd_sync(args: argparse.Namespace) -> None:
    ip = _require_ip(args)
    rsync = _rsync_cmd()
    user = "admin"
    identity = _ssh_identity()
    rsh = f"ssh -o StrictHostKeyChecking=accept-new"
    if identity:
        rsh += f" -i {identity}"
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
                "-e", rsh,
                f"{_PROJECT_ROOT}/{local}",
                f"{user}@{ip}:{REMOTE_DIR}/{remote}",
            ]
        )
        if rc != 0:
            sys.exit(rc)

    # Remove any stale workspace root (upstream now uses path-sourced proto,
    # so a workspace root with proto declared causes uv to fail).
    _ssh_run(ip, f"rm -f {REMOTE_DIR}/pyproject.toml", user=user)
    # Bust cached venv so a stale install isn't reused.
    _ssh_run(ip, f"rm -rf {REMOTE_DIR}/.venv", user=user)

    # Rewrite the systemd unit. Visualiser dependency dropped (upstream no
    # longer ships it as a Python package).
    service = (
        "[Unit]\nDescription=Battlecode CI Daemon\nAfter=network.target\n\n"
        "[Service]\nType=simple\n"
        f"WorkingDirectory={REMOTE_DIR}\n"
        "Environment=PATH=/home/admin/.local/bin:/usr/bin:/bin\n"
        "Environment=VIRTUAL_ENV=\n"
        # PrivateTmp=no: the default can isolate /tmp such that named
        # POSIX semaphores created by the parent ProcessPoolExecutor
        # aren't visible to spawned worker children (SemLock._rebuild
        # fails with FileNotFoundError). Hetzner runs as root with no
        # sandboxing and doesn't hit this; AWS runs as admin under
        # the default unit sandbox and does.
        "PrivateTmp=no\n"
        "ExecStart=/home/admin/.local/bin/uv run --python pypy3 "
        "--project cambc_pypy "
        "python cambc_pypy/scripts/ci_daemon.py\n"
        "Restart=always\nRestartSec=2\nUser=admin\n\n"
        "[Install]\nWantedBy=multi-user.target\n"
    )
    service_cmd = (
        f"sudo tee /etc/systemd/system/ci-daemon.service > /dev/null <<'__EOF_SVC__'\n"
        f"{service}"
        f"__EOF_SVC__\n"
        f"sudo systemctl daemon-reload"
    )
    _ssh_run(ip, service_cmd, user=user)

    _ssh_run(ip, "sudo systemctl restart ci-daemon 2>/dev/null || true", user=user)
    # Wait for daemon to come back up and start listening. systemctl restart
    # returns immediately; the daemon needs time to import pypy + engine.
    for attempt in range(30):
        rc = _ssh_run(
            ip,
            "python3 -c 'import socket,sys; s=socket.socket(); s.settimeout(2); "
            "sys.exit(0 if s.connect_ex((\"127.0.0.1\",9876))==0 else 1)'",
            user=user,
        )
        if rc == 0:
            print(f"Daemon ready (attempt {attempt + 1}).")
            return
        time.sleep(1)
    print("WARNING: daemon did not come up within 30s after restart.", file=sys.stderr)


def _make_tarball(bot_path: str) -> bytes:
    bot_dir = _PROJECT_ROOT / "bots" / bot_path
    if not bot_dir.is_dir():
        print(f"Bot not found: {bot_dir}", file=sys.stderr)
        sys.exit(1)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", dereference=True) as tar:
        for f in sorted(bot_dir.rglob("*.py")):
            tar.add(f.resolve(), arcname=str(f.relative_to(bot_dir)))
    return buf.getvalue()


def _connect_daemon(ip: str, user: str = "admin") -> tuple[subprocess.Popen[bytes], socket.socket]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    local_port = s.getsockname()[1]
    s.close()
    identity = _ssh_identity()
    ssh_args = [
        _ssh_cmd(),
        "-N",
        "-L",
        f"{local_port}:127.0.0.1:9876",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=4",
        "-o",
        "ExitOnForwardFailure=yes",
    ]
    if identity:
        ssh_args.extend(["-i", identity])
    ssh_args.append(f"{user}@{ip}")
    tunnel = subprocess.Popen(ssh_args)
    time.sleep(1)
    for _ in range(10):
        try:
            sock = socket.create_connection(("127.0.0.1", local_port), timeout=2)
            sock.settimeout(None)
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
        else:
            return tunnel, sock
    tunnel.terminate()
    print("Failed to open SSH tunnel to CI daemon.", file=sys.stderr)
    sys.exit(1)


def _ping_daemon(sock: socket.socket, reader: io.BufferedReader, timeout: float = 45.0) -> bool:
    """Verify daemon is actually serving by round-tripping a ping. Tolerates slow startup."""
    deadline = time.time() + timeout
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            _send(sock, {"cmd": "ping"})
            sock.settimeout(3.0)
            resp = _recv_line(reader)
            sock.settimeout(None)
            if resp and resp.get("pong"):
                if attempt > 1:
                    print(f"Daemon ready after {attempt} attempts.")
                return True
        except (TimeoutError, OSError, json.JSONDecodeError):
            pass
        try:
            sock.settimeout(None)
        except OSError:
            pass
        time.sleep(1.0)
    return False


def _send(sock: socket.socket, msg: dict) -> None:
    sock.sendall((json.dumps(msg) + "\n").encode())


def _recv_line(reader: io.BufferedReader) -> dict | None:
    line = reader.readline()
    if not line:
        return None
    return json.loads(line)


_CHECKPOINT_DIR = _PROJECT_ROOT / "replays" / "ci"


def _checkpoint_path(job_id: str) -> Path:
    return _CHECKPOINT_DIR / f".sweep_{job_id}.json"


def _save_checkpoint(job_id: str, payload: dict) -> None:
    _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    _checkpoint_path(job_id).write_text(json.dumps(payload))


def _load_checkpoint(job_id: str) -> dict | None:
    p = _checkpoint_path(job_id)
    if not p.is_file():
        return None
    return json.loads(p.read_text())


def _format_result_line(result: dict, replay_dir: Path) -> str:
    resign_msg = result.get("resign_message")
    suffix = f" [{resign_msg}]" if resign_msg else ""
    replay_name = f"{result['game']}_{result['map']}.replay26"
    return (
        f"  [{result.get('score', '?')}] "
        f"game {result['game']:>2}: {result['winner']:<20} "
        f"{result['map']:<16} t={result['turns']:>4} "
        f"Ti {result.get('a_ti', 0):>5}/{result.get('b_ti', 0):<5} "
        f"Ax {result.get('a_ax', 0):>5}/{result.get('b_ax', 0):<5} "
        f"({result['condition']}, {result['time']:.1f}s){suffix} "
        f"-> {(replay_dir / replay_name).relative_to(_PROJECT_ROOT)}"
    )


def _open_tunnel_with_retry(ip: str, max_attempts: int = 6) -> tuple[subprocess.Popen[bytes], socket.socket, io.BufferedReader]:
    """Open SSH tunnel + ping daemon; retry both on failure with backoff."""
    last_err = "unknown"
    for attempt in range(1, max_attempts + 1):
        try:
            tunnel, sock = _connect_daemon(ip)
        except SystemExit:
            last_err = "ssh tunnel"
            wait = min(30, 2 ** attempt)
            print(f"  reconnect attempt {attempt}/{max_attempts}: ssh tunnel failed; sleeping {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        reader = sock.makefile("rb")
        if _ping_daemon(sock, reader, timeout=90.0):
            return tunnel, sock, reader
        last_err = "daemon ping"
        try:
            sock.close()
        except OSError:
            pass
        tunnel.terminate()
        try:
            tunnel.wait(timeout=5)
        except subprocess.TimeoutExpired:
            tunnel.kill()
        wait = min(30, 2 ** attempt)
        print(f"  reconnect attempt {attempt}/{max_attempts}: {last_err} failed; sleeping {wait}s", file=sys.stderr)
        time.sleep(wait)
    print(f"Could not (re)connect after {max_attempts} attempts (last: {last_err}).", file=sys.stderr)
    sys.exit(1)


def _close_conn(tunnel: subprocess.Popen[bytes], sock: socket.socket) -> None:
    try:
        sock.close()
    except OSError:
        pass
    tunnel.terminate()
    try:
        tunnel.wait(timeout=5)
    except subprocess.TimeoutExpired:
        tunnel.kill()


def _cmd_ci(args: argparse.Namespace) -> None:
    ip = _require_ip(args)
    bot_a: str = args.bot_a
    bot_b: str = args.bot_b
    n: int = args.n
    keep: bool = args.keep
    resume_id: str | None = args.resume

    replay_dir = _CHECKPOINT_DIR
    replay_dir.mkdir(parents=True, exist_ok=True)

    job_id: str | None = resume_id
    received = 0  # count of result lines already printed
    errors = 0
    draws = 0
    completed = False

    print(f"Connecting to daemon on {ip}...")
    tunnel, sock, reader = _open_tunnel_with_retry(ip)
    try:
        if resume_id is None:
            print(f"Uploading {bot_a}...")
            tar_a = _make_tarball(bot_a)
            _send(sock, {"cmd": "upload", "name": bot_a, "data": base64.b64encode(tar_a).decode()})
            resp = _recv_line(reader)
            if resp is None or "error" in resp:
                print(f"Upload failed: {resp.get('error') if resp else 'connection closed'}", file=sys.stderr)
                sys.exit(1)
            uuid_a = resp["uuid"]

            print(f"Uploading {bot_b}...")
            tar_b = _make_tarball(bot_b)
            _send(sock, {"cmd": "upload", "name": bot_b, "data": base64.b64encode(tar_b).decode()})
            resp = _recv_line(reader)
            if resp is None or "error" in resp:
                print(f"Upload failed: {resp.get('error') if resp else 'connection closed'}", file=sys.stderr)
                sys.exit(1)
            uuid_b = resp["uuid"]

            print(f"Running {n} games: {bot_a} vs {bot_b}...")
            _send(sock, {
                "cmd": "run",
                "bot_a": uuid_a,
                "bot_b": uuid_b,
                "bot_a_name": bot_a,
                "bot_b_name": bot_b,
                "n": n,
            })
        else:
            print(f"Resume not supported by current daemon; starting fresh.")

        # Simple streaming protocol: daemon sends one JSON line per game
        # completion (with `winner_side`, `error`, etc.), then a final
        # `{"done": True, "score": "A-B", "draws": ..., "errors": ...}`.
        # No job_id, no subscribe, no heartbeats — matches the daemon's
        # current `_handle_run` implementation.
        while True:
            result = _recv_line(reader)
            if result is None:
                print("Run failed: connection closed", file=sys.stderr)
                sys.exit(1)
            if "error" in result and result.get("fatal"):
                print(f"Daemon fatal: {result['error']}", file=sys.stderr)
                sys.exit(1)
            if result.get("done"):
                draws = result.get("draws", 0)
                errors = result.get("errors", 0)
                completed = True
                score = result["score"]
                summary = f"\n=== {bot_a} vs {bot_b}: {score} (draws: {draws}"
                if errors:
                    summary += f", errors: {errors}"
                summary += ") ==="
                print(summary)
                if errors > 0:
                    pct = 100.0 * errors / max(1, n)
                    level = "WARNING" if pct < 25 else "CRITICAL"
                    print(f"{level}: {errors}/{n} games crashed ({pct:.0f}%).", file=sys.stderr)
                break

            received += 1
            if "error" in result:
                print(f"  [error] game {result.get('game', '?')}: {result['error']}", file=sys.stderr)
            else:
                # Daemon doesn't currently embed replay bytes in the
                # streamed result; replays live on the server's disk
                # under UPLOAD_DIR and would need a separate fetch step
                # (out of scope for this minimal protocol).
                score = result.get("score", "?")
                print(
                    f"  [{score}] game {result.get('game', '?'):>2}: "
                    f"winner={result.get('winner_side', '?'):<5} "
                    f"map={result.get('map', '?'):<20} "
                    f"t={result.get('turns', 0):>4} "
                    f"time={result.get('time', 0):.1f}s"
                )
    finally:
        _close_conn(tunnel, sock)

        # Always terminate unless --keep. Leaving instances up costs money and
        # a stale daemon may have a poisoned process pool on next run.
        if keep:
            if completed:
                print(f"--keep set; leaving {args.server} ({ip}) running.")
            else:
                print(f"--keep set; leaving {args.server} ({ip}) running despite incomplete run.", file=sys.stderr)
        else:
            try:
                ec2 = _get_ec2(args.region)
                instance = _find_instance(ec2, args.server)
                if instance:
                    print(f"Terminating {args.server} ({_instance_ip(instance)})...")
                    instance.terminate()
                    print("Done.")
            except Exception as e:
                print(f"Failed to terminate instance: {e}", file=sys.stderr)

        if not completed:
            sys.exit(2)
        if errors and errors >= n // 2:
            print(f"Majority of games ({errors}/{n}) errored. Treating as failure.", file=sys.stderr)
            sys.exit(3)


def main() -> None:
    parser = argparse.ArgumentParser(description="AWS EC2 CI server management")
    parser.add_argument("--server", default=SERVER_NAME, help=f"Server name tag (default: {SERVER_NAME})")
    parser.add_argument("--region", default=DEFAULT_REGION, help=f"AWS region (default: {DEFAULT_REGION})")
    sub = parser.add_subparsers(dest="command", required=True)

    up = sub.add_parser("up", help="Launch instance")
    up.add_argument("type", nargs="?", default=DEFAULT_INSTANCE_TYPE, help=f"Instance type (default: {DEFAULT_INSTANCE_TYPE})")
    up.add_argument("--ami", default=DEFAULT_AMI, help=f"AMI ID (default: {DEFAULT_AMI})")
    up.set_defaults(func=_cmd_up)

    down = sub.add_parser("down", help="Terminate instance")
    down.set_defaults(func=_cmd_down)

    status = sub.add_parser("status", help="Show running instances")
    status.set_defaults(func=_cmd_status)

    ssh = sub.add_parser("ssh", help="SSH into instance")
    ssh.set_defaults(func=_cmd_ssh)

    provision = sub.add_parser("provision", help="Install Python/uv on instance")
    provision.set_defaults(func=_cmd_provision)

    sync = sub.add_parser("sync", help="Rsync bots/maps to instance")
    sync.set_defaults(func=_cmd_sync)

    ci = sub.add_parser("ci", help="Run parallel games via CI daemon")
    ci.add_argument("bot_a", help="First bot (e.g. drewfett/v55)")
    ci.add_argument("bot_b", help="Second bot (e.g. intgrah/v54.3.0)")
    ci.add_argument("-n", type=int, default=30, help="Number of games (default: 30 — keep small; iterate fast on changes that should be ≥10pp")
    ci.add_argument("--keep", action="store_true", help="Do not terminate instance after sweep")
    ci.add_argument("--resume", help="Resume an existing job_id (skip uploads, re-subscribe)")
    ci.set_defaults(func=_cmd_ci)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
