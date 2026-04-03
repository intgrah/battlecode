import os
from pathlib import Path

import click
from rich.console import Console

from cambc.config import find_config

console = Console()


def _print_summary(console: Console, result: dict, name_a: str, name_b: str):
    winner = result["winner"]
    turns = result["turns"]
    condition = result["win_condition"]

    if condition == "core_destroyed":
        reason = "Core destroyed"
    elif condition == "resources":
        reason = "Resources (tiebreak)"
    else:
        reason = "Draw"

    if winner == "A":
        winner_name = name_a
        winner_style = "[bold green]"
    elif winner == "B":
        winner_name = name_b
        winner_style = "[bold green]"
    else:
        winner_name = "Draw"
        winner_style = "[bold yellow]"

    console.print()
    console.print(f"  {winner_style}Winner: {winner_name}[/]  [dim]({reason}, turn {turns})[/dim]")
    console.print()

    # Resource table
    from rich.table import Table
    t = Table(show_header=True, box=None, padding=(0, 2))
    t.add_column("", style="dim")
    a_style = "bold" if winner == "A" else ""
    b_style = "bold" if winner == "B" else ""
    t.add_column(name_a, justify="right", style=a_style)
    t.add_column(name_b, justify="right", style=b_style)
    t.add_row(
        "Titanium",
        f"{result['a_titanium']} ({result['a_titanium_collected']} mined)",
        f"{result['b_titanium']} ({result['b_titanium_collected']} mined)",
    )
    t.add_row(
        "Axionite",
        f"{result['a_axionite']} ({result['a_axionite_collected']} mined)",
        f"{result['b_axionite']} ({result['b_axionite_collected']} mined)",
    )
    t.add_row("Units", str(result["a_units"]), str(result["b_units"]))
    t.add_row("Buildings", str(result["a_buildings"]), str(result["b_buildings"]))
    console.print(t)
    console.print()


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
        raise click.BadParameter(
            f"Directory '{path_str}' does not contain main.py"
        )
    if p.is_file():
        return str(p.resolve())
    raise click.BadParameter(f"Bot not found: '{path_str}'")


@click.command()
@click.argument("bot_a")
@click.argument("bot_b")
@click.argument("map_path", required=False, default=None)
@click.option("--replay", default=None, help="Output replay path")
@click.option("--seed", default=None, type=int)
@click.option("--watch", "auto_watch", is_flag=True, help="Open visualizer after match")
def run(bot_a: str, bot_b: str, map_path: str | None, replay: str | None, seed: int | None, auto_watch: bool):
    """Run a local match between two bots.

    MAP_PATH is optional — if omitted, uses the first .map26 file in the maps directory.
    """
    from cambc.cambc_engine import run_game

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

    # Resolve map — pick first available if not specified
    if map_path is None:
        maps = sorted(maps_dir.glob("*.map26"))
        if not maps:
            console.print("[red]No .map26 files found in maps/ directory. Provide a map path.[/red]")
            raise SystemExit(1)
        mp = maps[0]
    else:
        mp = Path(map_path)
        if not mp.exists() and not mp.is_absolute():
            candidate = maps_dir / map_path
            if candidate.exists():
                mp = candidate
    resolved_map = str(mp.resolve())

    name_a = Path(player_a).parent.name if Path(player_a).name == "main.py" else Path(player_a).stem
    name_b = Path(player_b).parent.name if Path(player_b).name == "main.py" else Path(player_b).stem

    console.print(f"[bold]Running match:[/bold] {name_a} vs {name_b}")
    console.print(f"  Map: {mp.name}  Seed: {seed}  Replay: {replay}")

    try:
        result = run_game(player_a, player_b, engine_root, resolved_map, replay, seed)
    except Exception as e:
        console.print(f"[red bold]Error:[/red bold] {e}")
        raise SystemExit(1)

    if os.path.exists(replay):
        console.print(f"[green]Replay written to {replay}[/green]")

    _print_summary(console, result, name_a, name_b)

    if auto_watch:
        from cambc.commands import watch as watch_mod
        ctx = click.get_current_context()
        ctx.invoke(watch_mod.watch, replay_file=replay)

    # Skip normal Py_Finalize to avoid CPython 3.12 bug where
    # Py_EndInterpreter doesn't fully unregister sub-interpreters,
    # causing a fatal "remaining subinterpreters" abort on exit.
    os._exit(0)

    # do not put code after this
