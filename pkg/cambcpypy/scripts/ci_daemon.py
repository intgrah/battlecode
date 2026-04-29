"""CI daemon: accepts game jobs over TCP, runs them in parallel, streams results."""

from __future__ import annotations

import asyncio
import base64
import binascii
import io
import json
import random
import shutil
import socket
import sys
import tarfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Final
from uuid import uuid4

from cambcpypy.engine import run_game

HOST: Final[str] = "127.0.0.1"
PORT: Final[int] = 9876
UPLOAD_DIR: Final[Path] = Path("uploads")
MAPS_DIR: Final[Path] = Path("maps")
PRUNE_HOURS: Final[int] = 24

executor: ProcessPoolExecutor


def _prune_uploads() -> None:
    if not UPLOAD_DIR.exists():
        return
    cutoff = time.time() - PRUNE_HOURS * 3600
    for d in UPLOAD_DIR.iterdir():
        if d.is_dir() and d.stat().st_mtime < cutoff:
            shutil.rmtree(d)
            print(f"Pruned {d.name}")


def _run_one_game(
    bot_a_path: str,
    bot_b_path: str,
    map_path: str,
    seed: int,
    game_idx: int,
    bot_a_name: str,
    bot_b_name: str,
    replay_dir: str,
) -> dict[str, Any]:

    map_name = Path(map_path).stem
    replay_path = f"{replay_dir}/{game_idx}_{map_name}.replay26"
    t0 = time.perf_counter()
    result = run_game(
        bot_a_path,
        bot_b_path,
        "cambcpypy/src/cambcpypy",
        map_path,
        replay_path,
        seed=seed,
        suppress_indicators=True,
        quiet=True,
    )
    elapsed = time.perf_counter() - t0

    if result.winner == 0:
        winner_name = bot_a_name
        winner_side = "a"
    elif result.winner == 1:
        winner_name = bot_b_name
        winner_side = "b"
    else:
        winner_name = "draw"
        winner_side = "draw"

    replay_b64 = ""
    replay_file = Path(replay_path)
    if replay_file.is_file():
        replay_b64 = base64.b64encode(replay_file.read_bytes()).decode()

    return {
        "game": game_idx,
        "map": map_name,
        "seed": seed,
        "winner": winner_name,
        "winner_side": winner_side,
        "condition": result.win_condition,
        "turns": result.turns_played,
        "time": round(elapsed, 2),
        "a_ti": result.player_a_titanium_collected,
        "b_ti": result.player_b_titanium_collected,
        "a_ax": result.player_a_axionite_collected,
        "b_ax": result.player_b_axionite_collected,
        "resign_message": result.resign_message,
        "replay": replay_b64,
    }


def _resolve_bot_main(uuid: str) -> str | None:
    bot_dir = UPLOAD_DIR / uuid
    main = bot_dir / "main.py"
    if main.is_file():
        return str(main)
    return None


async def _handle_upload(msg: dict[str, Any]) -> dict[str, Any]:
    data_b64: str = msg.get("data", "")
    name: str = msg.get("name", "unknown")
    try:
        raw = base64.b64decode(data_b64)
    except binascii.Error:
        return {"error": "invalid base64 data"}

    if len(raw) > 10 * 1024 * 1024:
        return {"error": "upload too large (max 10MB)"}

    uuid = uuid4().hex[:12]
    dest = UPLOAD_DIR / uuid
    dest.mkdir(parents=True, exist_ok=True)

    buf = io.BytesIO(raw)
    try:
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            tar.extractall(path=dest)
    except tarfile.TarError:
        shutil.rmtree(dest)
        return {"error": "invalid tarball"}

    print(f"Uploaded {name} -> {uuid}")
    return {"uuid": uuid}


async def _handle_run(
    msg: dict[str, Any],
    writer: asyncio.StreamWriter,
) -> None:
    bot_a_uuid: str = msg.get("bot_a", "")
    bot_b_uuid: str = msg.get("bot_b", "")
    n: int = msg.get("n", 1)
    bot_a_name: str = msg.get("bot_a_name", bot_a_uuid)
    bot_b_name: str = msg.get("bot_b_name", bot_b_uuid)

    bot_a_path = _resolve_bot_main(bot_a_uuid)
    if bot_a_path is None:
        _write_line(writer, {"error": f"bot not found: {bot_a_uuid}"})
        return

    bot_b_path = _resolve_bot_main(bot_b_uuid)
    if bot_b_path is None:
        _write_line(writer, {"error": f"bot not found: {bot_b_uuid}"})
        return

    maps = sorted(MAPS_DIR.glob("*.map26"))
    if not maps:
        _write_line(writer, {"error": "no maps on server"})
        return

    job_id = uuid4().hex[:12]
    replay_dir = UPLOAD_DIR / job_id / "replays"
    replay_dir.mkdir(parents=True, exist_ok=True)

    base_seed = random.randint(1, 100000)
    loop = asyncio.get_event_loop()

    tasks: list[asyncio.Future[dict[str, Any]]] = []
    for i in range(n):
        map_path = str(maps[i % len(maps)])
        seed = base_seed + i
        fut = loop.run_in_executor(
            executor,
            _run_one_game,
            bot_a_path,
            bot_b_path,
            map_path,
            seed,
            i,
            bot_a_name,
            bot_b_name,
            str(replay_dir),
        )
        tasks.append(fut)

    wins_a = 0
    wins_b = 0
    draws = 0
    pending = set(tasks)

    while pending:
        done_set, pending = await asyncio.wait(
            pending, return_when=asyncio.FIRST_COMPLETED
        )
        for task in done_set:
            try:
                result = task.result()
            except Exception as e:
                result = {"error": str(e)}

            side = result.get("winner_side")
            if side == "a":
                wins_a += 1
            elif side == "b":
                wins_b += 1
            else:
                draws += 1

            result["score"] = f"{wins_a}-{wins_b}"

            if writer.is_closing():
                for t in pending:
                    t.cancel()
                return

            _write_line(writer, result)
            await writer.drain()

    _write_line(writer, {"done": True, "score": f"{wins_a}-{wins_b}", "draws": draws})
    await writer.drain()


def _write_line(writer: asyncio.StreamWriter, obj: dict[str, Any]) -> None:
    writer.write((json.dumps(obj) + "\n").encode())


async def _handle_client(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    addr = writer.get_extra_info("peername")
    print(f"Connection from {addr}")

    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                _write_line(writer, {"error": "invalid JSON"})
                await writer.drain()
                continue

            cmd = msg.get("cmd", "")
            match cmd:
                case "upload":
                    resp = await _handle_upload(msg)
                    _write_line(writer, resp)
                    await writer.drain()
                case "run":
                    await _handle_run(msg, writer)
                case "ping":
                    _write_line(writer, {"pong": True})
                    await writer.drain()
                case _:
                    _write_line(writer, {"error": f"unknown command: {cmd}"})
                    await writer.drain()
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        print(f"Disconnected {addr}")
        writer.close()


async def _main() -> None:
    global executor

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    _prune_uploads()

    executor = ProcessPoolExecutor(max_tasks_per_child=1)
    print(f"Starting CI daemon on {HOST}:{PORT}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, PORT))
    sock.setblocking(False)
    server = await asyncio.start_server(
        _handle_client, sock=sock, limit=64 * 1024 * 1024
    )
    async with server:
        await server.serve_forever()


def main() -> None:
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        print("\nShutting down.")
        sys.exit(0)


if __name__ == "__main__":
    main()
