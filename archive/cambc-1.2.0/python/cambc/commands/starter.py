import importlib.resources
from pathlib import Path

import click
from rich.console import Console
from rich.prompt import Confirm

from cambc.config import CONFIG_FILENAME

console = Console()

DEFAULT_CONFIG = """\
# cambc.toml - Cambridge Battlecode project config

bots_dir = "bots"
maps_dir = "maps"
replay = "replay.replay26"
seed = 1
"""

GITIGNORE = """\
# Replays (regenerated with cambc run)
*.replay26

# Python
__pycache__/
*.pyc

# Virtual environments
.venv/
venv/
"""

STARTER_BOT = importlib.resources.files("cambc.data") / "starter_bot.py"


def _get_maps_source():
    """Resolve maps: repo root `maps/` in development, bundled package data when pip-installed."""
    # In the monorepo: commands/ → cambc/ → python/ → cli/ → repo root
    repo_maps = Path(__file__).resolve().parent.parent.parent.parent.parent / "maps"
    if repo_maps.is_dir() and any(repo_maps.glob("*.map26")):
        return repo_maps
    return importlib.resources.files("cambc.data.maps")


@click.command()
def starter():
    """Scaffold a new Cambridge Battlecode project."""
    project_root = Path.cwd()
    config_path = project_root / CONFIG_FILENAME

    console.print("[bold]Cambridge Battlecode — project setup[/bold]\n")

    # 1. Config file (always created)
    if config_path.exists():
        console.print(f"  [dim]{CONFIG_FILENAME} already exists, skipping.[/dim]")
    else:
        config_path.write_text(DEFAULT_CONFIG, encoding="utf-8")
        console.print(f"  [green]+[/green] Created {CONFIG_FILENAME}")

    # 2. .gitignore
    gitignore_path = project_root / ".gitignore"
    if gitignore_path.exists():
        console.print("  [dim].gitignore already exists, skipping.[/dim]")
    else:
        gitignore_path.write_text(GITIGNORE, encoding="utf-8")
        console.print("  [green]+[/green] Created .gitignore")

    # 3. Always create bots/ and maps/ directories (config references them)
    bots_dir = project_root / "bots"
    maps_dir = project_root / "maps"
    bots_dir.mkdir(exist_ok=True)
    maps_dir.mkdir(exist_ok=True)

    # 4. Maps
    include_maps = Confirm.ask("\n  Include default maps?", default=True)
    if include_maps:
        count = 0
        available = 0
        maps_source = _get_maps_source()
        for item in maps_source.iterdir():
            if item.name.endswith(".map26"):
                available += 1
                dest = maps_dir / item.name
                if dest.exists():
                    continue
                dest.write_bytes(item.read_bytes())
                count += 1
        if count > 0:
            console.print(f"  [green]+[/green] Copied {count} maps to maps/")
        elif available > 0:
            console.print("  [dim]All maps already present, skipping.[/dim]")
        else:
            console.print("  [yellow]No default maps found. Download maps from the platform.[/yellow]")

    # 5. Starter bot
    include_bot = Confirm.ask("\n  Create a starter bot?", default=True)
    if include_bot:
        bot_dir = bots_dir / "starter"
        bot_dir.mkdir(parents=True, exist_ok=True)
        main_py = bot_dir / "main.py"
        if main_py.exists():
            console.print("  [dim]bots/starter/main.py already exists, skipping.[/dim]")
        else:
            main_py.write_text(STARTER_BOT.read_text())
            console.print("  [green]+[/green] Created bots/starter/main.py")

    # Done — show the full dev loop
    console.print("\n[bold green]Ready![/bold green] Get started:\n")
    if include_bot and include_maps:
        run_cmd = "cambc run starter starter default_small1.map26"
    elif include_bot:
        run_cmd = "cambc run starter starter <map_path>"
    else:
        run_cmd = "cambc run <bot_a> <bot_b> <map_path>"
    console.print(f"  1. Run a match:    {run_cmd}")
    console.print("  2. Watch replay:   cambc watch replay.replay26")
    console.print("  3. Edit your bot:  bots/starter/main.py" if include_bot else "  3. Write your bot: bots/<name>/main.py")
    console.print("  4. Submit:         cambc submit bots/starter" if include_bot else "  4. Submit:         cambc submit bots/<name>")
