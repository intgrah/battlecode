import click
from rich.console import Console

from cambc import __version__

console = Console()

@click.group()
@click.version_option(version=__version__)
def main():
    """Cambridge Battlecode CLI"""
    from cambc.version_check import check_for_update
    latest = check_for_update()
    if latest:
        console.print(
            f"[yellow]Update available: {__version__} -> {latest}. "
            f"Run: pip install --upgrade cambc[/yellow]"
        )

from cambc.commands import starter, run, watch, login, logout, test, matches, match_detail, teams, test_run, test_matches, submit, status, map_editor
main.add_command(starter.starter)
main.add_command(run.run)
main.add_command(watch.watch)
main.add_command(login.login)
main.add_command(logout.logout)
main.add_command(submit.submit)
main.add_command(status.status)
main.add_command(test.unrated)
main.add_command(matches.matches)
main.add_command(match_detail.match_detail)
main.add_command(teams.teams)
main.add_command(test_run.test_run)
main.add_command(test_matches.test_matches)
main.add_command(map_editor.map_editor)
