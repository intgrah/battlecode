"""CLI entry point: hitl serve | hitl seed | hitl stats.

Event extraction is a separate tool (pkg/hitl/scripts/extract.py) because it
depends on `proto` to parse replays, which is dev-machine-only. The runtime
package stays proto-free so the server deploys thin.
"""

import secrets
from pathlib import Path

import typer
import uvicorn
from PIL import Image, ImageDraw

from hitl.config import blobs_dir, db_path, pngs_dir
from hitl.db import Store
from hitl.schema import BeliefState, Event, EventTrigger, Game, GameState, OutcomeAuto

app = typer.Typer(help="HITL annotation platform", no_args_is_help=True)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8080, *, reload: bool = False) -> None:
    """Start the annotation web server.

    Binds to loopback by default. The systemd unit passes --host 0.0.0.0
    explicitly to listen on all interfaces behind tailscale.
    """
    uvicorn.run("hitl.app:app", host=host, port=port, reload=reload)


@app.command()
def stats() -> None:
    """Print DB summary."""
    s = Store(db_path())
    n_events, n_ann = s.event_counts()
    typer.echo(f"events:      {n_events}")
    typer.echo(f"annotations: {n_ann}")
    typer.echo(f"db:          {db_path()}")
    typer.echo(f"blobs:       {blobs_dir()}")
    typer.echo(f"pngs:        {pngs_dir()}")


@app.command()
def seed(n: int = 3) -> None:
    """Insert N fake events + rendered PNGs so the UI has something to show."""
    s = Store(db_path())
    s.upsert_game(
        Game(
            replay_id="fixture",
            our_side="A",
            opponent="drewfett/v54",
            map_name="socket",
            winner="them",
            end_turn=2000,
            outcome_auto=[OutcomeAuto.LOST_TI, OutcomeAuto.NO_REFINED_AX],
        )
    )
    for i in range(n):
        event_id = f"fixture-{i}-{secrets.token_hex(3)}"
        belief = BeliefState(
            role="ECON",
            ore_target=(5 + i, 3),
            dangling_output=None,
            scout_target=None,
            symmetry="ROT",
            ti=320,
            ax=0,
            scale=1.4,
        )
        game = GameState(
            my_pos=(10 + i, 10),
            hp=40,
            max_hp=40,
            action_cooldown=0,
            move_cooldown=0,
            nearby_enemies=[],
            nearby_allies=[(11 + i, 10)],
        )
        evt = Event(
            event_id=event_id,
            replay_id="fixture",
            turn=300 + 50 * i,
            unit_id=1000 + i,
            unit_type="BuilderBot",
            team="A",
            trigger=EventTrigger.IDLE_WITH_TI,
            belief=belief,
            game=game,
            bot_action=f"move {'N' if i % 2 else 'SE'}",
        )
        blob = blobs_dir() / f"{event_id}.json"
        blob.write_text(evt.model_dump_json(indent=2))
        png = _render_fixture_png(evt)
        s.insert_event(evt, blob_path=blob, png_path=png)
    typer.echo(f"seeded {n} fixture events")


def _render_fixture_png(evt: Event) -> Path:
    """Render a placeholder 480x480 PNG for an event."""
    w = h = 480
    tile = 20
    img = Image.new("RGB", (w, h), "#111")
    d = ImageDraw.Draw(img)
    for x in range(0, w, tile):
        d.line((x, 0, x, h), fill="#222")
    for y in range(0, h, tile):
        d.line((0, y, w, y), fill="#222")
    px = evt.game.my_pos[0] * tile
    py = evt.game.my_pos[1] * tile
    d.rectangle((px, py, px + tile, py + tile), fill="#4f90ff")
    if evt.belief.ore_target:
        ox, oy = evt.belief.ore_target
        d.rectangle(
            (ox * tile, oy * tile, ox * tile + tile, oy * tile + tile),
            outline="#e6c347",
        )
    d.text((10, 10), f"event {evt.event_id[:16]}", fill="#eee")
    d.text((10, 24), f"turn {evt.turn} | {evt.trigger.value}", fill="#9aa3ad")
    path = pngs_dir() / f"{evt.event_id}.png"
    img.save(path, "PNG")
    return path


@app.command("clear-annotations")
def clear_annotations(*, yes: bool = typer.Option(default=False)) -> None:
    """Wipe all annotations. Keeps events."""
    if not yes:
        typer.echo("pass --yes to confirm")
        raise typer.Exit(1)
    s = Store(db_path())
    with s.tx() as c:
        c.execute("DELETE FROM annotations")
    typer.echo("annotations cleared")


if __name__ == "__main__":
    app()
