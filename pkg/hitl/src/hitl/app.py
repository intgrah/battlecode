"""FastAPI web app for annotating critical bot events on the go.

Routes:
    GET  /              — annotation UI for one event
    POST /annotate      — submit an annotation, returns next event
    POST /reveal/{id}   — submit bot_was_right signal after reveal
    GET  /png/{event}   — rendered event PNG
    GET  /healthz       — liveness probe
"""

from __future__ import annotations

import functools
import json
import time
from pathlib import Path
from typing import Annotated, Final

from fastapi import Cookie, FastAPI, Form, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from hitl.config import db_path, pngs_dir
from hitl.db import Store
from hitl.schema import (
    ActionKind,
    Annotation,
    BuildType,
    Direction,
    OutcomeSubjective,
    Reason,
)

_PKG_DIR: Final = Path(__file__).resolve().parent
_TEMPLATES = Environment(
    loader=FileSystemLoader(str(_PKG_DIR / "templates")),
    autoescape=select_autoescape(["html"]),
)

app = FastAPI(title="HITL Annotation")
app.mount("/static", StaticFiles(directory=str(_PKG_DIR / "static")), name="static")


@functools.cache
def _store() -> Store:
    return Store(db_path())


def _session_id(cookie: str | None) -> str:
    if cookie:
        return cookie
    return f"s-{int(time.time() * 1000)}"


def _render_event_page(row: dict | None, session_id: str) -> str:
    counts = _store().event_counts()
    t = _TEMPLATES.get_template("event.html")
    return t.render(
        event=row,
        session_id=session_id,
        reasons=[r.value for r in Reason],
        actions=[a.value for a in ActionKind],
        build_types=[b.value for b in BuildType],
        directions=[d.value for d in Direction],
        subjective=[s.value for s in OutcomeSubjective],
        total=counts[0],
        annotated=counts[1],
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(session: Annotated[str | None, Cookie()] = None) -> Response:
    sid = _session_id(session)
    row = _store().pick_next_event(sid)
    html = _render_event_page(dict(row) if row else None, sid)
    resp = HTMLResponse(html)
    resp.set_cookie("session", sid, max_age=60 * 60 * 24 * 365, httponly=True)
    return resp


@app.get("/png/{event_id}")
def event_png(event_id: str) -> Response:
    png_path = _store().get_event_png(event_id)
    if not png_path:
        return Response(status_code=404)
    p = Path(png_path)
    if not p.exists():
        p = pngs_dir() / f"{event_id}.png"
    if not p.exists():
        return Response(status_code=404)
    return FileResponse(p, media_type="image/png")


@app.post("/annotate")
def annotate(
    event_id: Annotated[str, Form()],
    direction: Annotated[str, Form()],
    action: Annotated[str, Form()],
    build_type: Annotated[str, Form()] = "",
    reasons: Annotated[str, Form()] = "",
    free_text: Annotated[str, Form()] = "",
    outcome_context: Annotated[str, Form()] = "",
    session: Annotated[str | None, Cookie()] = None,
) -> JSONResponse:
    sid = _session_id(session)
    ann = Annotation(
        event_id=event_id,
        direction=Direction(direction),
        action=ActionKind(action),
        build_type=BuildType(build_type) if build_type else None,
        reasons=[Reason(r) for r in json.loads(reasons or "[]")],
        free_text=free_text,
        outcome_context=[
            OutcomeSubjective(o) for o in json.loads(outcome_context or "[]")
        ],
        session_id=sid,
        timestamp_ms=int(time.time() * 1000),
    )
    ann_id = _store().insert_annotation(ann)
    row = _store().get_event(event_id)
    return JSONResponse(
        {
            "annotation_id": ann_id,
            "bot_action": row["bot_action"] if row else None,
        }
    )


@app.post("/reveal/{annotation_id}")
def reveal(annotation_id: int, right: Annotated[str, Form()]) -> JSONResponse:
    _store().set_bot_was_right(
        annotation_id, right=right.lower() in ("1", "true", "yes")
    )
    return JSONResponse({"ok": True})


@app.get("/stats")
def stats() -> JSONResponse:
    total, annotated = _store().event_counts()
    return JSONResponse({"events": total, "annotations": annotated})


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)
