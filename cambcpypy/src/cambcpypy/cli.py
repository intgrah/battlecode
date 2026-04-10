import click
from rich.console import Console

from cambcpypy import __version__
from cambcpypy.compat import deprecation_warning

console = Console()


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """Cambridge Battlecode CLI"""
    from cambcpypy.version_check import check_for_update

    latest = check_for_update()
    if latest:
        console.print(
            f"[yellow]Update available: {__version__} -> {latest}. "
            f"Run: pip install --upgrade cambc[/yellow]"
        )


# -- Unchanged top-level commands --
from cambcpypy.commands import login, logout, map_editor, run, starter, status, watch

main.add_command(run.run)
main.add_command(watch.watch)
main.add_command(login.login)
main.add_command(logout.logout)
main.add_command(starter.starter)
main.add_command(status.status)
main.add_command(map_editor.map_editor)

# -- New entity groups --
from cambcpypy.commands.ladder import ladder
from cambcpypy.commands.match_group import match as match_group
from cambcpypy.commands.submission import submission
from cambcpypy.commands.team_group import team

main.add_command(submission)
main.add_command(match_group)
main.add_command(team)
main.add_command(ladder)

# -- submit as alias for submission upload --


@click.command("submit")
@click.argument("path", type=click.Path(exists=True))
@click.option("--name", "-n", default=None, help="Optional name for this submission")
def submit(path: str, name: str | None) -> None:
    """Upload a bot to the platform (alias for `submission upload`)."""
    from cambcpypy.commands.submission import upload

    ctx = click.get_current_context()
    ctx.invoke(upload, path=path, name=name)


main.add_command(submit)

# -- Deprecated aliases (hidden, show warning) --


@click.command("matches", hidden=True)
@click.option(
    "--type", "match_type", default=None, type=click.Choice(["ladder", "unrated"])
)
@click.option("--team", default=None)
@click.option("--mine", is_flag=True)
@click.option("--limit", default=20, type=int)
@click.option("--cursor", default=None)
def _dep_matches(match_type, team, mine, limit, cursor) -> None:
    """Deprecated. Use: cambc match list"""
    deprecation_warning("matches", "match list")
    from cambcpypy.commands.matches import _show_matches

    _show_matches(match_type, team, limit, cursor, mine=mine)


main.add_command(_dep_matches)


@click.command("unrated", hidden=True)
@click.argument("opponent_id")
@click.option("--match", "source_match", default=None)
@click.option(
    "--map",
    "maps",
    multiple=True,
    help="Map name (repeatable, up to 5). Omit for random.",
)
def _dep_unrated(opponent_id, source_match, maps) -> None:
    """Deprecated. Use: cambc match unrated"""
    deprecation_warning("unrated", "match unrated")
    from cambcpypy.commands.test import _show_unrated

    _show_unrated(opponent_id, source_match, maps or None)


main.add_command(_dep_unrated)


@click.command("test-run", hidden=True)
@click.argument("bot_a")
@click.argument("bot_b")
@click.option(
    "--map",
    "maps",
    multiple=True,
    help="Map name (repeatable, up to 5). Omit for random.",
)
def _dep_test_run(bot_a, bot_b, maps) -> None:
    """Deprecated. Use: cambc match test"""
    deprecation_warning("test-run", "match test")
    from cambcpypy.commands.test_run import _show_test_run

    _show_test_run(bot_a, bot_b, maps)


main.add_command(_dep_test_run)


@click.command("test-matches", hidden=True)
@click.option("--limit", default=20, type=int)
def _dep_test_matches(limit) -> None:
    """Deprecated. Use: cambc match tests"""
    deprecation_warning("test-matches", "match tests")
    from cambcpypy.commands.test_matches import _show_test_matches

    _show_test_matches(limit)


main.add_command(_dep_test_matches)


# For `teams`, re-register the old group with a deprecation warning
from cambcpypy.commands.teams import teams as _teams_group


class _DeprecatedTeamsGroup(click.Group):
    def invoke(self, ctx):
        deprecation_warning("teams", "team")
        return super().invoke(ctx)


_dep_teams = _DeprecatedTeamsGroup(
    "teams",
    commands=_teams_group.commands,
    help="Deprecated. Use: cambc team",
    hidden=True,
)
main.add_command(_dep_teams)


@click.command("init", hidden=True)
def _dep_init() -> None:
    """Deprecated. Use: cambc starter"""
    deprecation_warning("init", "starter")
    from cambcpypy.commands.init import init as _init_impl

    click.get_current_context().invoke(_init_impl)


main.add_command(_dep_init)
