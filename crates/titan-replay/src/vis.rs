use std::collections::HashMap;
use std::fmt;
use std::sync::Arc;

use serde::Deserialize;
use serde_json::Value;

#[derive(Clone, Debug)]
pub struct PaletteStop {
    pub t: f64,
    pub colour: Colour,
}

#[derive(Clone, Debug, Default)]
pub struct PaletteDef {
    pub stops: Vec<PaletteStop>,
    pub special: HashMap<i64, Colour>,
}

impl<'de> Deserialize<'de> for PaletteDef {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        #[derive(Deserialize)]
        struct Raw {
            stops: Vec<Vec<Value>>,
            #[serde(default)]
            special: HashMap<String, [u8; 4]>,
        }
        fn val_to_f64(v: &Value) -> f64 {
            match v {
                Value::Number(n) => n.as_f64().unwrap_or(0.0),
                Value::Bool(b) => {
                    if *b {
                        1.0
                    } else {
                        0.0
                    }
                }
                _ => 0.0,
            }
        }
        let raw = Raw::deserialize(deserializer)?;
        let stops = raw
            .stops
            .into_iter()
            .filter_map(|v| {
                if v.len() >= 5 {
                    Some(PaletteStop {
                        t: val_to_f64(&v[0]),
                        colour: Colour {
                            r: val_to_f64(&v[1]) as u8,
                            g: val_to_f64(&v[2]) as u8,
                            b: val_to_f64(&v[3]) as u8,
                            a: val_to_f64(&v[4]) as u8,
                        },
                    })
                } else {
                    None
                }
            })
            .collect();
        let special = raw
            .special
            .into_iter()
            .filter_map(|(k, [r, g, b, a])| {
                k.parse::<i64>().ok().map(|k| (k, Colour { r, g, b, a }))
            })
            .collect();
        Ok(Self { stops, special })
    }
}

#[derive(Clone, Debug)]
pub enum GridData {
    Bool(Vec<u8>),
    U8(Vec<u8>),
    I16(Vec<i16>),
    U16(Vec<u16>),
    F32(Vec<f32>),
}

impl GridData {
    #[must_use]
    pub fn get_f64(&self, i: usize) -> Option<f64> {
        match self {
            Self::Bool(v) => v.get(i).map(|&x| f64::from(x)),
            Self::U8(v) => v.get(i).map(|&x| f64::from(x)),
            Self::I16(v) => v.get(i).map(|&x| f64::from(x)),
            Self::U16(v) => v.get(i).map(|&x| f64::from(x)),
            Self::F32(v) => v.get(i).map(|&x| f64::from(x)),
        }
    }

    #[must_use]
    pub fn get_i64(&self, i: usize) -> Option<i64> {
        match self {
            Self::Bool(v) => v.get(i).map(|&x| i64::from(x)),
            Self::U8(v) => v.get(i).map(|&x| i64::from(x)),
            Self::I16(v) => v.get(i).map(|&x| i64::from(x)),
            Self::U16(v) => v.get(i).map(|&x| i64::from(x)),
            Self::F32(v) => v.get(i).map(|&x| x as i64),
        }
    }
}

#[derive(Clone, Debug)]
pub enum ScalarValue {
    Int(i64),
    Float(f64),
    Str(String),
    Bool(bool),
    Null,
    Pos(i32, i32),
    List(Vec<Self>),
    Repr(String),
}

impl fmt::Display for ScalarValue {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Int(v) => write!(f, "{v}"),
            Self::Float(v) => write!(f, "{v}"),
            Self::Str(v) => write!(f, "{v}"),
            Self::Bool(v) => write!(f, "{v}"),
            Self::Null => write!(f, "null"),
            Self::Pos(x, y) => write!(f, "({x}, {y})"),
            Self::List(items) => {
                write!(f, "[")?;
                for (i, it) in items.iter().enumerate() {
                    if i > 0 {
                        write!(f, ", ")?;
                    }
                    write!(f, "{it}")?;
                }
                write!(f, "]")
            }
            Self::Repr(s) => write!(f, "{s}"),
        }
    }
}

/// Parse a tagged value (`{"$type": ..., ...}`) into a `Tagged`.
fn parse_tagged(value: &Value) -> Tagged {
    let Some(obj) = value.as_object() else {
        return Tagged::Scalar(ScalarValue::Str(value.to_string()));
    };
    let typ = obj.get("$type").and_then(|v| v.as_str()).unwrap_or("");
    match typ {
        "scalar" => {
            let v = obj.get("v").cloned().unwrap_or(Value::Null);
            Tagged::Scalar(parse_scalar_value(&v))
        }
        "pos" => {
            let x = obj.get("x").and_then(Value::as_i64).unwrap_or(0) as i32;
            let y = obj.get("y").and_then(Value::as_i64).unwrap_or(0) as i32;
            Tagged::Scalar(ScalarValue::Pos(x, y))
        }
        "set_pos" | "tiles" => {
            let arr = obj
                .get("v")
                .and_then(Value::as_array)
                .map(|a| {
                    a.iter()
                        .filter_map(|p| {
                            let pp = p.as_array()?;
                            let x = pp.first()?.as_i64()? as i32;
                            let y = pp.get(1)?.as_i64()? as i32;
                            Some((x, y))
                        })
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();
            Tagged::Tiles(arr)
        }
        "tile" => {
            let xv = obj.get("x").and_then(Value::as_i64);
            let yv = obj.get("y").and_then(Value::as_i64);
            let pos = match (xv, yv) {
                (Some(x), Some(y)) => Some((x as i32, y as i32)),
                _ => None,
            };
            Tagged::Tile(pos)
        }
        "dot" => {
            let xv = obj.get("x").and_then(Value::as_i64);
            let yv = obj.get("y").and_then(Value::as_i64);
            let pos = match (xv, yv) {
                (Some(x), Some(y)) => Some((x as i32, y as i32)),
                _ => None,
            };
            let colour = parse_colour(obj.get("colour")).unwrap_or(Colour {
                r: 255,
                g: 255,
                b: 255,
                a: 255,
            });
            Tagged::Dot { pos, colour }
        }
        "path" => {
            let points = obj
                .get("v")
                .and_then(Value::as_array)
                .map(|a| {
                    a.iter()
                        .filter_map(|p| {
                            let pp = p.as_array()?;
                            let x = pp.first()?.as_i64()? as i32;
                            let y = pp.get(1)?.as_i64()? as i32;
                            Some((x, y))
                        })
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();
            let colour = parse_colour(obj.get("colour")).unwrap_or(Colour {
                r: 255,
                g: 255,
                b: 255,
                a: 255,
            });
            Tagged::Path { points, colour }
        }
        "uid" => {
            let id = obj.get("v").and_then(Value::as_i64).unwrap_or(0);
            Tagged::Scalar(ScalarValue::Int(id))
        }
        "boolgrid" | "u8grid" | "i16grid" | "u16grid" | "f32grid" => {
            let arr = obj.get("v").and_then(Value::as_array);
            let palette: PaletteDef = obj
                .get("palette")
                .cloned()
                .map(serde_json::from_value)
                .and_then(Result::ok)
                .unwrap_or_default();
            let data = match (typ, arr) {
                ("boolgrid", Some(arr)) => GridData::Bool(
                    arr.iter()
                        .map(|v| u8::from(v.as_bool().unwrap_or(false)))
                        .collect(),
                ),
                ("u8grid", Some(arr)) => {
                    GridData::U8(arr.iter().map(|v| v.as_u64().unwrap_or(0) as u8).collect())
                }
                ("i16grid", Some(arr)) => {
                    GridData::I16(arr.iter().map(|v| v.as_i64().unwrap_or(0) as i16).collect())
                }
                ("u16grid", Some(arr)) => {
                    GridData::U16(arr.iter().map(|v| v.as_u64().unwrap_or(0) as u16).collect())
                }
                ("f32grid", Some(arr)) => GridData::F32(
                    arr.iter()
                        .map(|v| v.as_f64().unwrap_or(0.0) as f32)
                        .collect(),
                ),
                _ => GridData::Bool(Vec::new()),
            };
            Tagged::Grid { data, palette }
        }
        "vectorfield" => {
            let angles: Vec<Option<f32>> = obj
                .get("angles")
                .cloned()
                .map(serde_json::from_value)
                .and_then(Result::ok)
                .unwrap_or_default();
            let magnitudes: Option<Vec<f32>> = obj
                .get("magnitudes")
                .cloned()
                .map(serde_json::from_value)
                .and_then(Result::ok);
            let arrows = angles
                .iter()
                .enumerate()
                .map(|(i, angle)| {
                    angle.map(|a| Arrow {
                        angle: a,
                        magnitude: magnitudes
                            .as_ref()
                            .and_then(|m| m.get(i).copied())
                            .unwrap_or(1.0),
                    })
                })
                .collect();
            Tagged::VectorField(ArrowData { arrows })
        }
        "repr" => {
            let s = obj
                .get("v")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string();
            Tagged::Scalar(ScalarValue::Repr(s))
        }
        "same" => Tagged::Same,
        _ => Tagged::Scalar(ScalarValue::Str(value.to_string())),
    }
}

fn parse_colour(v: Option<&Value>) -> Option<Colour> {
    let arr = v?.as_array()?;
    let r = arr.first()?.as_u64()? as u8;
    let g = arr.get(1)?.as_u64()? as u8;
    let b = arr.get(2)?.as_u64()? as u8;
    let a = arr.get(3).and_then(Value::as_u64).unwrap_or(255) as u8;
    Some(Colour { r, g, b, a })
}

fn parse_scalar_value(v: &Value) -> ScalarValue {
    match v {
        Value::Null => ScalarValue::Null,
        Value::Bool(b) => ScalarValue::Bool(*b),
        Value::Number(n) => n
            .as_i64()
            .map(ScalarValue::Int)
            .or_else(|| n.as_f64().map(ScalarValue::Float))
            .unwrap_or(ScalarValue::Float(0.0)),
        Value::String(s) => ScalarValue::Str(s.clone()),
        Value::Array(arr) => ScalarValue::List(
            arr.iter()
                .map(|item| match parse_tagged(item) {
                    Tagged::Scalar(s) => s,
                    _ => ScalarValue::Str(item.to_string()),
                })
                .collect(),
        ),
        Value::Object(_) => {
            // Either a tagged value embedded as a "scalar" (e.g. nested
            // sets of typed values), or a plain JSON object. Try tagged
            // parse first; on failure, render as a generic map.
            let t = parse_tagged(v);
            if let Tagged::Scalar(s) = t {
                s
            } else {
                ScalarValue::Str(v.to_string())
            }
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Arrow {
    pub angle: f32,
    pub magnitude: f32,
}

#[derive(Clone, Debug, Default)]
pub struct ArrowData {
    pub arrows: Vec<Option<Arrow>>,
}

/// Output of `parse_tagged` — a value found in a `vis.value` slot or a
/// `msg.args[k]` slot.
#[derive(Clone, Debug)]
pub enum Tagged {
    Scalar(ScalarValue),
    Tiles(Vec<(i32, i32)>),
    /// Single tile drawn as a ring around the cell. `None` = no value
    /// this turn (renderer skips).
    Tile(Option<(i32, i32)>),
    /// Single tile drawn as a filled coloured dot. `pos = None` = no
    /// value this turn (renderer skips).
    Dot {
        pos: Option<(i32, i32)>,
        colour: Colour,
    },
    /// Ordered list of tiles drawn as a polyline.
    Path {
        points: Vec<(i32, i32)>,
        colour: Colour,
    },
    Grid {
        data: GridData,
        palette: PaletteDef,
    },
    VectorField(ArrowData),
    /// Reuse the value from the prior turn. Caller resolves.
    Same,
}

/// A flattened vis field — what the existing UI / map renderer
/// consumes. Built by walking the log tree and collecting `vis` nodes.
#[derive(Clone, Debug)]
pub enum VisField {
    Grid {
        data: GridData,
        palette: PaletteDef,
    },
    Scalar {
        data: ScalarValue,
    },
    Tiles {
        data: Vec<(i32, i32)>,
    },
    Tile {
        pos: Option<(i32, i32)>,
    },
    Dot {
        pos: Option<(i32, i32)>,
        colour: Colour,
    },
    Path {
        points: Vec<(i32, i32)>,
        colour: Colour,
    },
    VectorField(ArrowData),
}

impl VisField {
    #[must_use]
    pub fn from_tagged(t: Tagged) -> Option<Self> {
        match t {
            Tagged::Scalar(s) => Some(Self::Scalar { data: s }),
            Tagged::Tiles(d) => Some(Self::Tiles { data: d }),
            Tagged::Tile(pos) => Some(Self::Tile { pos }),
            Tagged::Dot { pos, colour } => Some(Self::Dot { pos, colour }),
            Tagged::Path { points, colour } => Some(Self::Path { points, colour }),
            Tagged::Grid { data, palette } => Some(Self::Grid { data, palette }),
            Tagged::VectorField(a) => Some(Self::VectorField(a)),
            Tagged::Same => None,
        }
    }
}

pub type VisState = HashMap<String, Arc<VisField>>;

/// One entry of `RawVisState` — same shape as `VisField` but keeps the
/// `Same` marker so the state builder can resolve it against the prior
/// turn's value.
#[derive(Clone, Debug)]
pub enum RawVisField {
    Field(VisField),
    Same,
}

pub type RawVisState = HashMap<String, RawVisField>;

/// One node in the log tree.
#[derive(Clone, Debug)]
pub enum LogNode {
    Scope {
        name: String,
        us: Option<i64>,
        children: Vec<Self>,
    },
    Msg {
        tmpl: String,
        args: Vec<(String, Tagged)>,
    },
    Vis {
        name: String,
        value: Tagged,
    },
}

/// Per-builder per-turn log tree. The root is always a scope (typically
/// "turn"); contains all msg / vis / sub-scope nodes.
#[derive(Clone, Debug)]
pub struct LogTree {
    pub root: LogNode,
    pub prev_flush_us: Option<i64>,
}

impl LogTree {
    pub fn parse(raw: &str) -> Option<Self> {
        let value: Value = serde_json::from_str(raw).ok()?;
        let prev_flush_us = value.get("prev_flush_us").and_then(Value::as_i64);
        let root = parse_log_node(&value)?;
        Some(Self {
            root,
            prev_flush_us,
        })
    }

    /// Walk the tree depth-first, collecting all `vis` nodes into a flat
    /// map keyed by name. Inner names override outer (last write wins,
    /// matching the depth-first order). Preserves `Same` markers; the
    /// caller resolves them against the prior turn's `VisState`.
    #[must_use]
    pub fn collect_vis_raw(&self) -> RawVisState {
        let mut out = RawVisState::new();
        collect_vis_into(&self.root, &mut out);
        out
    }
}

/// Resolve `Same` markers against the prior turn's resolved state.
/// Names not present in `prior` whose marker is `Same` are dropped
/// (no value to fall back to).
#[must_use]
pub fn resolve_same(raw: RawVisState, prior: Option<&VisState>) -> VisState {
    let mut out = VisState::new();
    for (name, field) in raw {
        match field {
            RawVisField::Field(v) => {
                out.insert(name, Arc::new(v));
            }
            RawVisField::Same => {
                if let Some(p) = prior.and_then(|p| p.get(&name)) {
                    // Arc::clone — bumps refcount, no data copy.
                    out.insert(name, Arc::clone(p));
                }
            }
        }
    }
    out
}

fn collect_vis_into(node: &LogNode, out: &mut RawVisState) {
    match node {
        LogNode::Scope { children, .. } => {
            for c in children {
                collect_vis_into(c, out);
            }
        }
        LogNode::Vis { name, value } => {
            let entry = match value.clone() {
                Tagged::Same => RawVisField::Same,
                t => match VisField::from_tagged(t) {
                    Some(f) => RawVisField::Field(f),
                    None => return,
                },
            };
            out.insert(name.clone(), entry);
        }
        LogNode::Msg { .. } => {}
    }
}

fn parse_log_node(value: &Value) -> Option<LogNode> {
    let obj = value.as_object()?;
    let typ = obj.get("$type").and_then(Value::as_str)?;
    match typ {
        "scope" => {
            let name = obj
                .get("name")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string();
            let us = obj.get("us").and_then(Value::as_i64);
            let children = obj
                .get("children")
                .and_then(Value::as_array)
                .map(|a| a.iter().filter_map(parse_log_node).collect())
                .unwrap_or_default();
            Some(LogNode::Scope { name, us, children })
        }
        "msg" => {
            let tmpl = obj
                .get("tmpl")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string();
            let args = obj
                .get("args")
                .and_then(Value::as_object)
                .map(|m| {
                    m.iter()
                        .map(|(k, v)| (k.clone(), parse_tagged(v)))
                        .collect()
                })
                .unwrap_or_default();
            Some(LogNode::Msg { tmpl, args })
        }
        "vis" => {
            let name = obj
                .get("name")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string();
            let value = obj.get("value").map_or(Tagged::Same, parse_tagged);
            Some(LogNode::Vis { name, value })
        }
        _ => None,
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Colour {
    pub r: u8,
    pub g: u8,
    pub b: u8,
    pub a: u8,
}

#[must_use]
pub fn sample_palette(palette: &PaletteDef, value: f64) -> Option<Colour> {
    if let Some(i) = i64::try_from(value as i128)
        .ok()
        .filter(|_| (value - value.round()).abs() < 1e-9)
        && let Some(c) = palette.special.get(&i)
    {
        return Some(*c);
    }

    if palette.stops.is_empty() {
        return None;
    }
    if palette.stops.len() == 1 {
        return Some(palette.stops[0].colour);
    }

    let last = palette.stops.len() - 1;

    if value <= palette.stops[0].t {
        return Some(palette.stops[0].colour);
    }
    if value >= palette.stops[last].t {
        return Some(palette.stops[last].colour);
    }

    for i in 0..last {
        let s0 = &palette.stops[i];
        let s1 = &palette.stops[i + 1];
        if value >= s0.t && value <= s1.t {
            let range = s1.t - s0.t;
            let seg = if range.abs() < 1e-9 {
                0.0
            } else {
                ((value - s0.t) / range) as f32
            };
            let c0 = &s0.colour;
            let c1 = &s1.colour;
            return Some(Colour {
                r: (f32::from(c1.r) - f32::from(c0.r)).mul_add(seg, f32::from(c0.r)) as u8,
                g: (f32::from(c1.g) - f32::from(c0.g)).mul_add(seg, f32::from(c0.g)) as u8,
                b: (f32::from(c1.b) - f32::from(c0.b)).mul_add(seg, f32::from(c0.b)) as u8,
                a: (f32::from(c1.a) - f32::from(c0.a)).mul_add(seg, f32::from(c0.a)) as u8,
            });
        }
    }

    Some(palette.stops[last].colour)
}
