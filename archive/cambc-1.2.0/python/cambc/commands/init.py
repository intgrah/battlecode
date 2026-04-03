from pathlib import Path

import click
from rich.console import Console

from cambc.config import CONFIG_FILENAME

console = Console()

DEFAULT_CONFIG = """\
# cambc.toml — Cambridge Battlecode project config

bots_dir = "bots"
maps_dir = "maps"
replay = "replay.replay26"
seed = 1
"""


@click.command()
def init():
    """Initialize a cambc.toml config file in the current directory."""
    config_path = Path.cwd() / CONFIG_FILENAME
    if config_path.exists():
        console.print(f"[yellow]{CONFIG_FILENAME} already exists.[/yellow]")
        return

    config_path.write_text(DEFAULT_CONFIG)
    console.print(f"[green]Created {CONFIG_FILENAME}[/green]")
