import os
from pathlib import Path

import click
from rich.console import Console

from cambcpypy.config import find_config
from cambcpypy.engine import run_game

console = Console()


def _print_summary(console: Console, result: object, name_a: str, name_b: str) -> None:
    winner = getattr(result, "winner", None)
    turns = getattr(result, "turns_played", 0)
    condition = getattr(result, "win_condition", "")
    resign_message = getattr(result, "resign_message", None)

    condition_labels = {
        "core_destroyed": "Core destroyed",
        "resigned": "Resigned",
        "resources": "Resources (tiebreak)",
        "axionite_collected": "Axionite collected (tiebreak)",
        "titanium_collected": "Titanium collected (tiebreak)",
        "harvesters": "Harvesters (tiebreak)",
        "axionite_stored": "Axionite stored (tiebreak)",
        "titanium_stored": "Titanium stored (tiebreak)",
        "coinflip": "Coinflip (tiebreak)",
        "timeout": "Draw",
    }
    reason = condition_labels.get(condition, condition)

    winner_str = {0: "A", 1: "B"}.get(winner, "") if isinstance(winner, int) else winner
    if winner_str == "A":
        winner_name = name_a
        winner_style = "[bold green]"
    elif winner_str == "B":
        winner_name = name_b
        winner_style = "[bold green]"
    else:
        winner_name = "Draw"
        winner_style = "[bold yellow]"

    console.print()
    console.print(
        f"  {winner_style}Winner: {winner_name}[/]  [dim]({reason}, turn {turns})[/dim]"
    )
    if resign_message:
        console.print(f"  [dim italic]Resign message: {resign_message}[/dim italic]")
    console.print()

    from rich.table import Table

    t = Table(show_header=True, box=None, padding=(0, 2))
    t.add_column("", style="dim")
    a_style = "bold" if winner_str == "A" else ""
    b_style = "bold" if winner_str == "B" else ""
    t.add_column(name_a, justify="right", style=a_style)
    t.add_column(name_b, justify="right", style=b_style)
    a_ti = getattr(result, "player_a_titanium", 0)
    a_ax = getattr(result, "player_a_axionite", 0)
    a_tic = getattr(result, "player_a_titanium_collected", 0)
    a_axc = getattr(result, "player_a_axionite_collected", 0)
    b_ti = getattr(result, "player_b_titanium", 0)
    b_ax = getattr(result, "player_b_axionite", 0)
    b_tic = getattr(result, "player_b_titanium_collected", 0)
    b_axc = getattr(result, "player_b_axionite_collected", 0)
    t.add_row("Titanium", f"{a_ti} ({a_tic} mined)", f"{b_ti} ({b_tic} mined)")
    t.add_row("Axionite", f"{a_ax} ({a_axc} mined)", f"{b_ax} ({b_axc} mined)")
    t.add_row(
        "Units", str(getattr(result, "units_a", 0)), str(getattr(result, "units_b", 0))
    )
    t.add_row(
        "Buildings",
        str(getattr(result, "buildings_a", 0)),
        str(getattr(result, "buildings_b", 0)),
    )
    console.print(t)
    console.print()


def resolve_map_path(path_str: str, maps_dir: Path) -> Path:
    """Resolve a map path. Tries: raw path, maps_dir/path, path+.map26, maps_dir/path+.map26."""
    p = Path(path_str)
    if p.exists():
        return p

    if not p.is_absolute():
        # Try maps_dir/path
        candidate = maps_dir / path_str
        if candidate.exists():
            return candidate
        # Try adding .map26 extension
        if not path_str.endswith(".map26"):
            with_ext = Path(path_str + ".map26")
            if with_ext.exists():
                return with_ext
            candidate_ext = maps_dir / (path_str + ".map26")
            if candidate_ext.exists():
                return candidate_ext

    return p  # Return as-is; caller will get a file-not-found naturally


def resolve_bot_path(path_str: str, bots_dir: Path) -> str:
    """Resolve a bot path. Checks raw path first, then bots_dir/path."""
    p = Path(path_str)

    # If it's already a valid path, use it directly
    if not p.exists() and not p.is_absolute():
        # Try resolving relative to bots_dir
        candidate = bots_dir / path_str
        if candidate.exists():
            p = candidate

    if p.is_dir():
        main_py = p / "main.py"
        if main_py.is_file():
            return str(main_py.resolve())
        msg = f"Directory '{path_str}' does not contain main.py"
        raise click.BadParameter(msg)
    if p.is_file():
        return str(p.resolve())
    msg = f"Bot not found: '{path_str}'"
    raise click.BadParameter(msg)


@click.command()
@click.argument("bot_a")
@click.argument("bot_b")
@click.argument("map_path", required=False, default=None)
@click.option("--replay", default=None, help="Output replay path")
@click.option("--seed", default=None, type=int)
@click.option("--watch", "auto_watch", is_flag=True, help="Open visualizer after match")
@click.option(
    "--tle",
    default=0,
    type=int,
    help="Turn time limit in ms (0 to disable, server uses 2)",
)
@click.option(
    "--map-random", is_flag=True, help="Pick a random map from maps directory"
)
def run(
    bot_a: str,
    bot_b: str,
    map_path: str | None,
    replay: str | None,
    seed: int | None,
    auto_watch: bool,
    tle: int,
    map_random: bool,
) -> None:
    """Run a local match between two bots.

    MAP_PATH is optional — if omitted, uses the first .map26 file in the maps directory.
    """

    config, project_root = find_config()

    # Apply config defaults where CLI didn't override
    replay = replay or config.replay
    seed = seed if seed is not None else config.seed
    bots_dir = (project_root / config.bots_dir).resolve()
    maps_dir = (project_root / config.maps_dir).resolve()

    # Game types are re-exported in cambc/__init__.py via _types.py,
    # so `from cambc import *` already works. engine_root is passed to the
    # Rust engine for sys.path setup (redundant here, needed by server binary).
    engine_root = str(Path(__file__).resolve().parent.parent)

    player_a = resolve_bot_path(bot_a, bots_dir)
    player_b = resolve_bot_path(bot_b, bots_dir)

    # Resolve map — pick first (or random) if not specified
    if map_path is None:
        maps = sorted(maps_dir.glob("*.map26"))
        if not maps:
            console.print(
                "[red]No .map26 files found in maps/ directory. Provide a map path.[/red]"
            )
            raise SystemExit(1)
        if map_random:
            import random

            mp = random.choice(maps)
        else:
            mp = maps[0]
    else:
        mp = resolve_map_path(map_path, maps_dir)
    resolved_map = str(mp.resolve())

    name_a = (
        Path(player_a).parent.name
        if Path(player_a).name == "main.py"
        else Path(player_a).stem
    )
    name_b = (
        Path(player_b).parent.name
        if Path(player_b).name == "main.py"
        else Path(player_b).stem
    )

    console.print(f"[bold]Running match:[/bold] {name_a} vs {name_b}")
    tle_label = "off" if tle == 0 else f"{tle}ms"
    console.print(f"  Map: {mp.name}  Seed: {seed}  Replay: {replay}  TLE: {tle_label}")

    try:
        result = run_game(
            player_a, player_b, engine_root, resolved_map, replay, seed, tle
        )
    except Exception as e:
        console.print(f"[red bold]Error:[/red bold] {e}")
        raise SystemExit(1)

    if os.path.exists(replay):
        console.print(f"[green]Replay written to {replay}[/green]")

    _print_summary(console, result, name_a, name_b)

    if auto_watch:
        from cambcpypy.commands import watch as watch_mod

        ctx = click.get_current_context()
        ctx.invoke(watch_mod.watch, replay_file=replay)

    # do not put code after this
