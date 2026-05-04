//! Generate the Python `blueprint.py` module that bots import.
//!
//! Single source of truth for Entity/Direction enum values, derived from
//! the Rust `blueprint.rs` types via the `ALL_ENTITIES`/`ALL_DIRECTIONS`
//! tables. Mirror helpers are inlined as static Python text since they
//! have no Rust counterpart.

use crate::blueprint::{ALL_DIRECTIONS, ALL_ENTITIES, Entity};

const PREAMBLE: &str = r#""""Blueprint client library — GENERATED from titan-blueprint.

Do not edit by hand. Regenerate with:
    cargo run -p titan-blueprint --bin gen-blueprint-py -- <out.py>
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

__all__ = [
    "DELTA_DIR",
    "DIRECTIONAL",
    "DIR_DELTA",
    "TURRET",
    "BlueprintEntry",
    "Direction",
    "Entity",
    "mirror_delta",
    "mirror_entry",
    "mirror_pos",
]
"#;

const SUFFIX: &str = r#"
DELTA_DIR: dict[tuple[int, int], Direction] = {d: k for k, d in DIR_DELTA.items()}


@dataclass(frozen=True, slots=True)
class BlueprintEntry:
    pos: tuple[int, int]
    kind: Entity
    phase: int
    direction: Direction | None = None
    bridge_target: tuple[int, int] | None = None


def mirror_pos(pos: tuple[int, int], w: int, h: int, sym: str) -> tuple[int, int]:
    x, y = pos
    if sym == "hor":
        return (x, h - 1 - y)
    if sym == "ver":
        return (w - 1 - x, y)
    if sym == "rot":
        return (w - 1 - x, h - 1 - y)
    msg = f"unknown symmetry: {sym!r}"
    raise ValueError(msg)


def mirror_delta(dx: int, dy: int, sym: str) -> tuple[int, int]:
    if sym == "hor":
        return (dx, -dy)
    if sym == "ver":
        return (-dx, dy)
    if sym == "rot":
        return (-dx, -dy)
    msg = f"unknown symmetry: {sym!r}"
    raise ValueError(msg)


def mirror_entry(entry: BlueprintEntry, w: int, h: int, sym: str) -> BlueprintEntry:
    direction = entry.direction
    if direction is not None:
        dx, dy = DIR_DELTA[direction]
        direction = DELTA_DIR.get(mirror_delta(dx, dy, sym), direction)
    bt = entry.bridge_target
    if bt is not None:
        bt = mirror_pos(bt, w, h, sym)
    return BlueprintEntry(
        pos=mirror_pos(entry.pos, w, h, sym),
        kind=entry.kind,
        phase=entry.phase,
        direction=direction,
        bridge_target=bt,
    )
"#;

pub fn generate() -> String {
    let mut out = String::from(PREAMBLE);

    out.push_str("\nclass Entity(IntEnum):\n");
    for e in ALL_ENTITIES {
        out.push_str(&format!("    {} = {}\n", e.name(), e as u32));
    }

    out.push_str("\n\nclass Direction(IntEnum):\n");
    for d in ALL_DIRECTIONS {
        out.push_str(&format!("    {} = {}\n", d.name(), d as u32));
    }

    out.push_str("\n\nDIR_DELTA: dict[Direction, tuple[int, int]] = {\n");
    for d in ALL_DIRECTIONS {
        let (dx, dy) = d.delta();
        out.push_str(&format!("    Direction.{}: ({dx}, {dy}),\n", d.name()));
    }
    out.push_str("}\n");

    out.push_str("\nDIRECTIONAL: frozenset[Entity] = frozenset({\n");
    for e in ALL_ENTITIES {
        if e.is_directional() {
            out.push_str(&format!("    Entity.{},\n", e.name()));
        }
    }
    out.push_str("})\n");

    out.push_str("\nTURRET: frozenset[Entity] = frozenset({\n");
    for e in ALL_ENTITIES {
        if matches!(
            e,
            Entity::Gunner | Entity::Sentinel | Entity::Breach | Entity::Launcher
        ) {
            out.push_str(&format!("    Entity.{},\n", e.name()));
        }
    }
    out.push_str("})\n");

    out.push_str(SUFFIX);
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generates_valid_python_outline() {
        let s = generate();
        assert!(s.contains("class Entity(IntEnum):"));
        assert!(s.contains("class Direction(IntEnum):"));
        assert!(s.contains("CONVEYOR = 4"));
        assert!(s.contains("NORTH = 1"));
        assert!(s.contains("def mirror_entry"));
    }
}
