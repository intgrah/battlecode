from __future__ import annotations

import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

import pygame
from cambc import GameConstants

from blueprint import (
    DELTA_DIR,
    DIR_DELTA,
    DIRECTIONAL,
    BlueprintEntry,
    Direction,
    Entity,
)
from blueprint.cost import blueprint_cost_range, final_scale, initial_scale
from blueprint.editor._state import State
from blueprint.editor.assets import (
    BG_COLOUR,
    EMPTY_COLOUR,
    Assets,
    load_assets,
)
from blueprint.editor.export import load_blueprint, write_blueprint
from blueprint.editor.map_io import MapData, Tile, load_map
from blueprint.editor.sequencing import Scored, sequence
from blueprint.editor.symmetry import (
    Symmetry,
    detect_symmetry,
    mirror_delta,
    mirror_pos,
)

__all__ = ["main", "run"]


BASE_TILE_PX = 24
SIDEBAR_PX = 230
MARGIN_PX = 10
MIN_ZOOM = 0.4
MAX_ZOOM = 3.0
ZOOM_STEP = 1.15

COLOUR_GRID = (40, 40, 48)
COLOUR_CORE_A = (120, 200, 120)
COLOUR_CORE_B = (210, 120, 120)
COLOUR_UNROUTED = (220, 60, 60)
COLOUR_TEXT = (230, 230, 230)
COLOUR_HELP = (170, 170, 180)
COLOUR_BRIDGE_LINE = (210, 170, 90)

KEY_TO_ENTITY: dict[int, Entity] = {
    pygame.K_c: Entity.CONVEYOR,
    pygame.K_a: Entity.ARMOURED_CONVEYOR,
    pygame.K_s: Entity.SPLITTER,
    pygame.K_b: Entity.BRIDGE,
    pygame.K_h: Entity.HARVESTER,
    pygame.K_f: Entity.FOUNDRY,
    pygame.K_g: Entity.GUNNER,
    pygame.K_n: Entity.SENTINEL,
    pygame.K_k: Entity.BREACH,
    pygame.K_l: Entity.LAUNCHER,
    pygame.K_w: Entity.BARRIER,
    pygame.K_r: Entity.ROAD,
}


@dataclass
class Editor:
    mdata: MapData
    sym: Symmetry
    state: State = field(default_factory=State.empty)
    tool: Entity = Entity.CONVEYOR
    bridge_source: tuple[int, int] | None = None
    status: str = ""
    zoom: float = 1.0
    pan: tuple[int, int] = (MARGIN_PX, MARGIN_PX)
    fullscreen: bool = False
    last_direction: dict[Entity, Direction] = field(
        default_factory=lambda: {
            Entity.CONVEYOR: Direction.EAST,
            Entity.ARMOURED_CONVEYOR: Direction.EAST,
            Entity.SPLITTER: Direction.EAST,
            Entity.GUNNER: Direction.EAST,
            Entity.SENTINEL: Direction.EAST,
            Entity.BREACH: Direction.EAST,
        },
    )
    n_builders: int = 6
    """Initial squad size assumed for cost estimation."""
    """Per-entity last-used facing; new placements default to this."""

    @property
    def tile_px(self) -> int:
        return max(8, int(BASE_TILE_PX * self.zoom))

    def place(self, pos: tuple[int, int], entity: Entity) -> None:
        # Bridge-target click: only r² matters (walls/core/ore are fine
        # as a destination). Handle before any other validation.
        if entity == Entity.BRIDGE and self.bridge_source is not None:
            src = self.bridge_source
            dx, dy = pos[0] - src[0], pos[1] - src[1]
            d2 = dx * dx + dy * dy
            limit = GameConstants.BRIDGE_TARGET_RADIUS_SQ
            if d2 == 0 or d2 > limit:
                self.status = f"bridge needs 0 < r² <= {limit}, got {d2}"
                self.bridge_source = None
                return
            self.state.place(
                BlueprintEntry(pos=src, kind=Entity.BRIDGE, bridge_target=pos),
            )
            self.bridge_source = None
            self.status = f"bridge {src}->{pos}"
            return

        tile = self.mdata.tile(*pos)
        if tile == Tile.WALL:
            self.status = f"can't place on wall @ {pos}"
            return
        for core in (self.mdata.core_a, self.mdata.core_b):
            if abs(pos[0] - core[0]) <= 1 and abs(pos[1] - core[1]) <= 1:
                self.status = f"can't place on core @ {pos}"
                return
        if entity == Entity.HARVESTER and tile not in (
            Tile.ORE_TITANIUM,
            Tile.ORE_AXIONITE,
        ):
            self.status = "harvester needs ore"
            return

        if entity == Entity.BRIDGE:
            # First click — record source, wait for target click.
            self.bridge_source = pos
            self.status = f"bridge src {pos}, click target"
            return

        direction: Direction | None = None
        if entity in DIRECTIONAL:
            direction = self.last_direction.get(entity, Direction.EAST)
        entry = BlueprintEntry(pos=pos, kind=entity, direction=direction)
        self.state.place(entry)
        self.status = f"placed {entity.name} @ {pos}"

    def erase(self, pos: tuple[int, int]) -> None:
        if pos in self.state.entries:
            self.state.erase(pos)
            self.status = f"erased {pos}"

    def rotate_at(self, pos: tuple[int, int], step: int) -> None:
        self.state.rotate(pos, step)
        entry = self.state.entries.get(pos)
        if entry is not None and entry.direction is not None:
            self.last_direction[entry.kind] = entry.direction

    def save(self) -> None:
        scored = sequence(self.state.entries, self.mdata.core_a)
        bad = [s for s in scored if s.unrouted]
        if bad:
            self.status = f"save blocked: {len(bad)} unrouted"
            return
        path = write_blueprint(self.mdata.name, scored)
        self.state.dirty = False
        self.status = f"saved {path}"

    def tile_to_screen(self, pos: tuple[int, int]) -> tuple[int, int]:
        return (
            self.pan[0] + pos[0] * self.tile_px,
            self.pan[1] + pos[1] * self.tile_px,
        )

    def screen_to_tile(self, mx: int, my: int) -> tuple[int, int] | None:
        x = (mx - self.pan[0]) // self.tile_px
        y = (my - self.pan[1]) // self.tile_px
        if not (0 <= x < self.mdata.w and 0 <= y < self.mdata.h):
            return None
        return (int(x), int(y))


def _draw_tile(
    surf: pygame.Surface,
    rect: pygame.Rect,
    tile: Tile,
    assets: Assets,
) -> None:
    if tile == Tile.EMPTY:
        pygame.draw.rect(surf, EMPTY_COLOUR, rect)
    elif tile == Tile.WALL:
        sprite = assets.wall()
        if sprite is not None:
            surf.blit(sprite, rect.topleft)
        else:
            pygame.draw.rect(surf, (48, 12, 8), rect)
    elif tile in (Tile.ORE_TITANIUM, Tile.ORE_AXIONITE):
        pygame.draw.rect(surf, EMPTY_COLOUR, rect)
        sprite = assets.ore(axionite=tile == Tile.ORE_AXIONITE)
        if sprite is not None:
            surf.blit(sprite, rect.topleft)


def _draw_entry(
    surf: pygame.Surface,
    rect: pygame.Rect,
    scored: Scored,
    alpha: int,
    assets: Assets,
    *,
    team_a: bool,
) -> None:
    sprite = assets.entity(scored.entry.kind, scored.entry.direction, team_a=team_a)
    if sprite is not None:
        s = sprite
        if alpha != 255:
            s = sprite.copy()
            s.set_alpha(alpha)
        surf.blit(s, rect.topleft)
    if scored.unrouted:
        pygame.draw.rect(surf, COLOUR_UNROUTED, rect, 2)


def _draw_bridge_line(
    surf: pygame.Surface,
    ed: Editor,
    src: tuple[int, int],
    tgt: tuple[int, int],
    alpha: int,
) -> None:
    t = ed.tile_px
    sx = ed.pan[0] + src[0] * t + t // 2
    sy = ed.pan[1] + src[1] * t + t // 2
    tx = ed.pan[0] + tgt[0] * t + t // 2
    ty = ed.pan[1] + tgt[1] * t + t // 2
    overlay = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    pygame.draw.line(
        overlay,
        (*COLOUR_BRIDGE_LINE, alpha),
        (sx, sy),
        (tx, ty),
        3,
    )
    surf.blit(overlay, (0, 0))


def _mirror_entry(
    entry: BlueprintEntry,
    w: int,
    h: int,
    sym: Symmetry,
) -> BlueprintEntry:
    mp = mirror_pos(entry.pos, w, h, sym)
    direction = entry.direction
    if direction is not None:
        dx, dy = DIR_DELTA[direction]
        ndx, ndy = mirror_delta(dx, dy, sym)
        direction = DELTA_DIR.get((ndx, ndy), direction)
    bt = entry.bridge_target
    if bt is not None:
        bt = mirror_pos(bt, w, h, sym)
    return replace(entry, pos=mp, direction=direction, bridge_target=bt)


def _draw_sidebar(
    surf: pygame.Surface,
    ed: Editor,
    font: pygame.font.Font,
    small: pygame.font.Font,
    x0: int,
) -> None:
    y = MARGIN_PX
    entries = list(ed.state.entries.values())
    (lo_ti, lo_ax), (hi_ti, hi_ax) = blueprint_cost_range(entries, ed.n_builders)
    init_s = initial_scale(ed.n_builders)
    end_s = final_scale(entries, ed.n_builders)
    lines = [
        f"Map: {ed.mdata.name}  {ed.mdata.w}x{ed.mdata.h}",
        f"Symmetry: {ed.sym.value.upper()}",
        f"Tool: {ed.tool.name}",
        f"Entries: {len(ed.state.entries)}",
        f"Zoom: {ed.zoom:.2f}x",
        "",
        f"Builders: {ed.n_builders}",
        f"Scale: {init_s:.2f}x -> {end_s:.2f}x",
        f"Ti: {lo_ti}-{hi_ti}",
        f"Ax: {lo_ax}-{hi_ax}",
        "[-/+] adjust builders",
        "",
        "[c] conveyor  [a] armoured",
        "[s] splitter  [b] bridge",
        "[h] harvester [f] foundry",
        "[g] gunner    [n] sentinel",
        "[k] breach    [l] launcher",
        "[w] barrier  [r] road",
        "",
        "LMB: place",
        "RMB: rotate",
        "MMB: delete",
        "wheel: zoom",
        "space+drag: pan",
        "u: undo    ctrl-s: save",
        "F11: fullscreen",
        "q: quit",
    ]
    for line in lines:
        t = font.render(line, True, COLOUR_TEXT)
        surf.blit(t, (x0, y))
        y += t.get_height() + 2
    y += 6
    if ed.status:
        t = small.render(ed.status, True, COLOUR_HELP)
        surf.blit(t, (x0, y))


def _set_mode(
    canvas_w: int,
    canvas_h: int,
    *,
    fullscreen: bool,
) -> tuple[pygame.Surface, int, int]:
    win_w = canvas_w + SIDEBAR_PX + MARGIN_PX * 3
    win_h = max(canvas_h + MARGIN_PX * 2, 640)
    if fullscreen:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        return screen, screen.get_width(), screen.get_height()
    screen = pygame.display.set_mode((win_w, win_h), pygame.RESIZABLE)
    return screen, win_w, win_h


def run(map_path: Path) -> None:
    mdata = load_map(map_path)
    sym = detect_symmetry(mdata)

    pygame.init()
    pygame.display.set_caption(f"blueprint editor: {mdata.name}")

    canvas_w = mdata.w * BASE_TILE_PX
    canvas_h = mdata.h * BASE_TILE_PX
    screen, win_w, win_h = _set_mode(canvas_w, canvas_h, fullscreen=False)
    font = pygame.font.SysFont("monospace", 14)
    small = pygame.font.SysFont("monospace", 12)
    assets = load_assets(BASE_TILE_PX)

    ed = Editor(mdata=mdata, sym=sym)
    existing = load_blueprint(mdata.name)
    if existing is not None:
        for entry in existing:
            ed.state.entries[entry.pos] = entry
        ed.state.history.clear()
        ed.state.dirty = False
        ed.status = f"loaded {len(existing)} entries"

    clock = pygame.time.Clock()
    panning = False
    pan_start: tuple[int, int] = (0, 0)
    pan_start_mouse: tuple[int, int] = (0, 0)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE and not ed.fullscreen:
                screen = pygame.display.set_mode(
                    (event.w, event.h),
                    pygame.RESIZABLE,
                )
                win_w, win_h = event.w, event.h
            elif event.type == pygame.KEYDOWN:
                ctrl = bool(pygame.key.get_mods() & pygame.KMOD_CTRL)
                if event.key == pygame.K_s and ctrl:
                    ed.save()
                elif event.key in KEY_TO_ENTITY:
                    ed.tool = KEY_TO_ENTITY[event.key]
                    ed.bridge_source = None
                    ed.status = f"tool = {ed.tool.name}"
                elif event.key == pygame.K_u:
                    ed.state.undo()
                    ed.status = "undo"
                elif event.key in (pygame.K_MINUS, pygame.K_UNDERSCORE):
                    ed.n_builders = max(0, ed.n_builders - 1)
                    ed.status = f"builders = {ed.n_builders}"
                elif event.key in (pygame.K_EQUALS, pygame.K_PLUS):
                    ed.n_builders += 1
                    ed.status = f"builders = {ed.n_builders}"
                elif event.key == pygame.K_F11:
                    ed.fullscreen = not ed.fullscreen
                    screen, win_w, win_h = _set_mode(
                        canvas_w,
                        canvas_h,
                        fullscreen=ed.fullscreen,
                    )
                elif event.key == pygame.K_q:
                    running = False
            elif event.type == pygame.MOUSEWHEEL:
                mx, my = pygame.mouse.get_pos()
                pre = ed.tile_px
                # zoom around cursor
                tile_at = ed.screen_to_tile(mx, my)
                if event.y > 0:
                    ed.zoom = min(MAX_ZOOM, ed.zoom * ZOOM_STEP)
                else:
                    ed.zoom = max(MIN_ZOOM, ed.zoom / ZOOM_STEP)
                if ed.tile_px != pre:
                    assets = load_assets(ed.tile_px)
                    if tile_at is not None:
                        ed.pan = (
                            mx - tile_at[0] * ed.tile_px,
                            my - tile_at[1] * ed.tile_px,
                        )
            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                pos = ed.screen_to_tile(mx, my)
                if (
                    pygame.key.get_mods() & pygame.KMOD_SHIFT
                    or (pygame.key.get_pressed()[pygame.K_SPACE])
                ):
                    panning = True
                    pan_start = ed.pan
                    pan_start_mouse = (mx, my)
                    continue
                if pos is None:
                    continue
                if event.button == 1:
                    ed.place(pos, ed.tool)
                elif event.button == 3:
                    ed.rotate_at(pos, 1)
                elif event.button == 2:
                    ed.erase(pos)
            elif event.type == pygame.MOUSEBUTTONUP:
                panning = False
            elif event.type == pygame.MOUSEMOTION and panning:
                mx, my = event.pos
                ed.pan = (
                    pan_start[0] + (mx - pan_start_mouse[0]),
                    pan_start[1] + (my - pan_start_mouse[1]),
                )

        screen.fill(BG_COLOUR)
        t = ed.tile_px

        # terrain
        for y in range(mdata.h):
            for x in range(mdata.w):
                sx = ed.pan[0] + x * t
                sy = ed.pan[1] + y * t
                rect = pygame.Rect(sx, sy, t, t)
                _draw_tile(screen, rect, mdata.tile(x, y), assets)

        # subtle grid
        for y in range(mdata.h + 1):
            gy = ed.pan[1] + y * t
            pygame.draw.line(
                screen,
                COLOUR_GRID,
                (ed.pan[0], gy),
                (ed.pan[0] + mdata.w * t, gy),
                1,
            )
        for x in range(mdata.w + 1):
            gx = ed.pan[0] + x * t
            pygame.draw.line(
                screen,
                COLOUR_GRID,
                (gx, ed.pan[1]),
                (gx, ed.pan[1] + mdata.h * t),
                1,
            )

        # cores
        for core, team_a_flag, outline in (
            (mdata.core_a, True, COLOUR_CORE_A),
            (mdata.core_b, False, COLOUR_CORE_B),
        ):
            cx_px = ed.pan[0] + (core[0] - 1) * t
            cy_px = ed.pan[1] + (core[1] - 1) * t
            core_rect = pygame.Rect(cx_px, cy_px, t * 3, t * 3)
            core_sprite = assets.core(team_a=team_a_flag, size=t * 3)
            if core_sprite is not None:
                screen.blit(core_sprite, core_rect.topleft)
            pygame.draw.rect(screen, outline, core_rect, 2)

        # entries
        scored_list = sequence(ed.state.entries, mdata.core_a)
        bad_set = {s.entry.pos for s in scored_list if s.unrouted}
        for s in scored_list:
            rect = pygame.Rect(
                ed.pan[0] + s.entry.pos[0] * t,
                ed.pan[1] + s.entry.pos[1] * t,
                t,
                t,
            )
            _draw_entry(screen, rect, s, 255, assets, team_a=True)
            if s.entry.kind == Entity.BRIDGE and s.entry.bridge_target is not None:
                _draw_bridge_line(screen, ed, s.entry.pos, s.entry.bridge_target, 220)

            m_entry = _mirror_entry(s.entry, mdata.w, mdata.h, sym)
            if m_entry.pos == s.entry.pos:
                continue
            m_scored = Scored(entry=m_entry, unrouted=s.unrouted)
            m_rect = pygame.Rect(
                ed.pan[0] + m_entry.pos[0] * t,
                ed.pan[1] + m_entry.pos[1] * t,
                t,
                t,
            )
            _draw_entry(screen, m_rect, m_scored, 140, assets, team_a=False)
            if m_entry.kind == Entity.BRIDGE and m_entry.bridge_target is not None:
                _draw_bridge_line(
                    screen,
                    ed,
                    m_entry.pos,
                    m_entry.bridge_target,
                    140,
                )

        # bridge source marker
        if ed.bridge_source is not None:
            r = pygame.Rect(
                ed.pan[0] + ed.bridge_source[0] * t,
                ed.pan[1] + ed.bridge_source[1] * t,
                t,
                t,
            )
            pygame.draw.rect(screen, (255, 255, 80), r, 3)

        # sidebar
        sidebar_x = win_w - SIDEBAR_PX - MARGIN_PX
        _draw_sidebar(screen, ed, font, small, sidebar_x)

        # bad count
        if bad_set:
            warn = small.render(
                f"{len(bad_set)} unrouted — save disabled", True, COLOUR_UNROUTED
            )
            screen.blit(warn, (MARGIN_PX, win_h - 20))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: blueprint-editor <map_path>", file=sys.stderr)
        sys.exit(1)
    run(Path(sys.argv[1]))
