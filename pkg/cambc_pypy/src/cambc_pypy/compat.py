"""Backwards-compatibility helpers for CLI restructuring."""

import click
from rich.console import Console

console = Console()

_SHOWN_WARNINGS: set[str] = set()


def deprecation_warning(old: str, new: str) -> None:
    """Print a one-time deprecation warning suggesting the new command."""
    key = f"{old}->{new}"
    if key not in _SHOWN_WARNINGS:
        _SHOWN_WARNINGS.add(key)
        console.print(
            f"[yellow]Warning: `cambc {old}` is deprecated. Use: cambc {new}[/yellow]\n"
        )


class SmartGroup(click.Group):
    """A Click group that routes unknown subcommands to a default command.

    If the first argument isn't a known subcommand, it's treated as an
    argument to the default command (e.g. `cambc match <uuid>` routes to
    `cambc match info <uuid>`).
    """

    def __init__(self, *args, default_cmd: str = "info", **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.default_cmd = default_cmd

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if args and args[0] not in self.commands and not args[0].startswith("-"):
            args = [self.default_cmd, *args]
        return super().parse_args(ctx, args)
