//! Translation of `bots/intgrah/v54.7.9/util/visualiser.py`.
//!
//! Visualisation primitives. Defines the `Dump` enum (each variant a typed
//! payload the viewer knows how to render) and the `Dumper` struct that bots
//! use to emit a per-turn JSON tree of named dump nodes.

use cambc::Position;
use serde::Serialize;
use std::collections::HashMap;

#[derive(Clone, Copy, Debug, Serialize)]
pub struct Colour {
    pub r: u8,
    pub g: u8,
    pub b: u8,
    pub a: u8,
}

impl Colour {
    #[must_use]
    pub const fn new(r: u8, g: u8, b: u8, a: u8) -> Self {
        Self { r, g, b, a }
    }

    fn as_array(&self) -> [u8; 4] {
        [self.r, self.g, self.b, self.a]
    }
}

pub const TRANSPARENT: Colour = Colour::new(0, 0, 0, 0);

/// One stop in a `Palette`, generic over the scalar type `T` (bool / int / float).
#[derive(Clone, Debug, Serialize)]
pub struct PaletteStop<T> {
    pub t: T,
    pub colour: Colour,
}

/// Linearly interpolated colour palette over scalar values of type `T`.
#[derive(Clone, Debug, Serialize)]
pub struct Palette<T> {
    pub stops: Vec<PaletteStop<T>>,
    pub special: Vec<(T, Colour)>,
}

impl<T> Palette<T> {
    #[must_use]
    pub fn new(stops: Vec<PaletteStop<T>>) -> Self {
        Self {
            stops,
            special: Vec::new(),
        }
    }
}

impl<T: Clone + PartialEq> Palette<T> {
    /// Return a copy of the palette with additional special values merged in.
    #[must_use]
    pub fn with_special(&self, special: &[(T, Colour)]) -> Self {
        let mut merged: Vec<(T, Colour)> = self.special.clone();
        for (k, c) in special {
            if let Some(slot) = merged.iter_mut().find(|(kk, _)| kk == k) {
                slot.1 = *c;
            } else {
                merged.push((k.clone(), *c));
            }
        }
        Self {
            stops: self.stops.clone(),
            special: merged,
        }
    }
}

// Pre-built palettes. Python defines these as module constants; Rust needs
// `Vec`s so they are functions instead.
#[must_use]
pub fn green_red() -> Palette<i64> {
    Palette::new(vec![
        PaletteStop {
            t: 0,
            colour: Colour::new(50, 200, 50, 140),
        },
        PaletteStop {
            t: 100,
            colour: Colour::new(200, 50, 50, 140),
        },
    ])
}

#[must_use]
pub fn blue_red() -> Palette<i64> {
    Palette::new(vec![
        PaletteStop {
            t: 0,
            colour: Colour::new(50, 50, 200, 140),
        },
        PaletteStop {
            t: 100,
            colour: Colour::new(200, 50, 50, 140),
        },
    ])
}

#[must_use]
pub fn fog() -> Palette<bool> {
    Palette::new(vec![
        PaletteStop {
            t: false,
            colour: TRANSPARENT,
        },
        PaletteStop {
            t: true,
            colour: Colour::new(0, 0, 0, 180),
        },
    ])
}

// ---------------------------------------------------------------------
// Dump variants: every value passed to `Dumper::dump` is one of these.
// ---------------------------------------------------------------------

/// A scalar value carried by a `DumpScalar` node.
#[derive(Clone, Debug, Serialize)]
#[serde(untagged)]
pub enum ScalarValue {
    Int(i64),
    Float(f64),
    Bool(bool),
    Str(String),
    Null,
}

/// All dumpable payload types. Each variant matches one Python `Dump*`
/// dataclass; serialisation produces the exact `{"$type": "...", ...}` shape
/// the Python viewer expects.
#[derive(Clone, Debug)]
pub enum Dump {
    BoolGrid {
        data: Vec<bool>,
        palette: Palette<bool>,
    },
    U8Grid {
        data: Vec<u8>,
        palette: Palette<i64>,
    },
    I16Grid {
        data: Vec<i16>,
        palette: Palette<i64>,
    },
    U16Grid {
        data: Vec<u16>,
        palette: Palette<i64>,
    },
    F32Grid {
        data: Vec<f32>,
        palette: Palette<f64>,
    },
    /// Unordered set of tiles, rendered as cell rings.
    Tiles { data: Vec<Position> },
    /// Single tile rendered as a ring around the cell. `pos = None` renders
    /// as nothing so callers can dump unconditionally.
    Tile { pos: Option<Position> },
    /// Single tile rendered as a filled coloured dot.
    Dot {
        pos: Option<Position>,
        colour: Colour,
    },
    /// Ordered list of tiles rendered as a polyline.
    Path {
        points: Vec<Position>,
        colour: Colour,
    },
    VectorField {
        angles: Vec<Option<f64>>,
        magnitudes: Option<Vec<f64>>,
    },
    /// Plain value (int / float / bool / str / None) shown verbatim.
    Scalar { value: ScalarValue },
}

fn serialise_palette_t<T: Serialize + Clone>(p: &Palette<T>) -> serde_json::Value {
    let stops: Vec<serde_json::Value> = p
        .stops
        .iter()
        .map(|s| {
            serde_json::json!([
                serde_json::to_value(&s.t).unwrap_or(serde_json::Value::Null),
                s.colour.as_array()[0],
                s.colour.as_array()[1],
                s.colour.as_array()[2],
                s.colour.as_array()[3],
            ])
        })
        .collect();
    let mut special_obj = serde_json::Map::new();
    for (k, c) in &p.special {
        let v = serde_json::to_value(k).unwrap_or(serde_json::Value::Null);
        let key = if let Some(s) = v.as_str() {
            s.to_string()
        } else {
            v.to_string()
        };
        special_obj.insert(
            key,
            serde_json::json!([
                c.as_array()[0],
                c.as_array()[1],
                c.as_array()[2],
                c.as_array()[3],
            ]),
        );
    }
    let mut obj = serde_json::Map::new();
    obj.insert("stops".to_string(), serde_json::Value::Array(stops));
    obj.insert(
        "special".to_string(),
        serde_json::Value::Object(special_obj),
    );
    serde_json::Value::Object(obj)
}

fn pos_xy(p: Position) -> serde_json::Value {
    serde_json::Value::Array(vec![
        serde_json::Value::Number(p.x.into()),
        serde_json::Value::Number(p.y.into()),
    ])
}

/// Convert a `Dump` value to its tagged dict representation. Mirrors the
/// `_serialise_dump` function in the Python source.
#[must_use]
pub fn serialise_dump(v: &Dump) -> serde_json::Value {
    match v {
        Dump::BoolGrid { data, palette } => serde_json::json!({
            "$type": "boolgrid",
            "v": data,
            "palette": serialise_palette_t(palette),
        }),
        Dump::U8Grid { data, palette } => serde_json::json!({
            "$type": "u8grid",
            "v": data,
            "palette": serialise_palette_t(palette),
        }),
        Dump::I16Grid { data, palette } => serde_json::json!({
            "$type": "i16grid",
            "v": data,
            "palette": serialise_palette_t(palette),
        }),
        Dump::U16Grid { data, palette } => serde_json::json!({
            "$type": "u16grid",
            "v": data,
            "palette": serialise_palette_t(palette),
        }),
        Dump::F32Grid { data, palette } => serde_json::json!({
            "$type": "f32grid",
            "v": data,
            "palette": serialise_palette_t(palette),
        }),
        Dump::Tiles { data } => serde_json::json!({
            "$type": "tiles",
            "v": data.iter().copied().map(pos_xy).collect::<Vec<_>>(),
        }),
        Dump::Tile { pos } => match pos {
            None => serde_json::json!({"$type": "tile", "x": null, "y": null}),
            Some(p) => serde_json::json!({"$type": "tile", "x": p.x, "y": p.y}),
        },
        Dump::Dot { pos, colour } => {
            let arr = colour.as_array();
            let c = serde_json::json!([arr[0], arr[1], arr[2], arr[3]]);
            match pos {
                None => serde_json::json!({
                    "$type": "dot",
                    "x": null,
                    "y": null,
                    "colour": c,
                }),
                Some(p) => serde_json::json!({
                    "$type": "dot",
                    "x": p.x,
                    "y": p.y,
                    "colour": c,
                }),
            }
        }
        Dump::Path { points, colour } => {
            let arr = colour.as_array();
            serde_json::json!({
                "$type": "path",
                "v": points.iter().copied().map(pos_xy).collect::<Vec<_>>(),
                "colour": [arr[0], arr[1], arr[2], arr[3]],
            })
        }
        Dump::VectorField { angles, magnitudes } => {
            let mut obj = serde_json::Map::new();
            obj.insert("$type".to_string(), serde_json::json!("vectorfield"));
            obj.insert(
                "angles".to_string(),
                serde_json::to_value(angles).unwrap_or(serde_json::Value::Null),
            );
            if let Some(m) = magnitudes {
                obj.insert(
                    "magnitudes".to_string(),
                    serde_json::to_value(m).unwrap_or(serde_json::Value::Null),
                );
            }
            serde_json::Value::Object(obj)
        }
        Dump::Scalar { value } => {
            let v = match value {
                ScalarValue::Int(i) => serde_json::json!(i),
                ScalarValue::Float(f) => serde_json::json!(f),
                ScalarValue::Bool(b) => serde_json::json!(b),
                ScalarValue::Str(s) => serde_json::json!(s),
                ScalarValue::Null => serde_json::Value::Null,
            };
            serde_json::json!({"$type": "scalar", "v": v})
        }
    }
}

/// Auto-wrap a raw value into a tagged dict for use in `debug()` message args.
/// Mirrors the Python `_auto_wrap`. Position values become hoverable cell rings;
/// `Dump` values are used as-is; anything else is a scalar.
#[must_use]
pub fn auto_wrap_position(p: Position) -> serde_json::Value {
    serde_json::json!({"$type": "tile", "x": p.x, "y": p.y})
}

#[must_use]
pub fn auto_wrap_scalar(v: ScalarValue) -> serde_json::Value {
    serialise_dump(&Dump::Scalar { value: v })
}

#[must_use]
pub fn auto_wrap_dump(d: &Dump) -> serde_json::Value {
    serialise_dump(d)
}

// ---------------------------------------------------------------------
// Dumper: per-unit (per-subinterpreter) state and tree builder.
// ---------------------------------------------------------------------

/// Per-unit same-elision dump emitter. Mirrors the Python `Dumper` class.
///
/// Holds a per-name cache of the most recently emitted serialised payload.
/// `dump(name, value)` either appends a fresh node to the current scope's
/// `children`, or emits a `{"$type": "same"}` marker if the payload is
/// byte-identical to the last value emitted under `name`.
///
/// The scope stack is owned externally; `Dumper` only mutates the top frame's
/// `children` list.
pub struct Dumper {
    same_cache: HashMap<String, serde_json::Value>,
}

impl Dumper {
    #[must_use]
    pub fn new() -> Self {
        Self {
            same_cache: HashMap::new(),
        }
    }

    /// Append a vis node to `scope_children`. If the payload equals the last
    /// value emitted under `name`, write a `{"$type": "same"}` marker so the
    /// viewer can reuse the previous turn's value.
    pub fn dump(&mut self, scope_children: &mut Vec<serde_json::Value>, name: &str, value: &Dump) {
        let payload = serialise_dump(value);
        let same = self.same_cache.get(name) == Some(&payload);
        if !same {
            self.same_cache.insert(name.to_string(), payload.clone());
        }
        let value_field = if same {
            serde_json::json!({"$type": "same"})
        } else {
            payload
        };
        let node = serde_json::json!({
            "$type": "vis",
            "name": name,
            "value": value_field,
        });
        scope_children.push(node);
    }
}

impl Default for Dumper {
    fn default() -> Self {
        Self::new()
    }
}
