use std::collections::HashMap;
use std::fmt;

use serde::Deserialize;

#[derive(Clone, Debug)]
pub struct PaletteStop {
    pub t: f64,
    pub colour: Colour,
}

#[derive(Clone, Debug)]
pub struct PaletteDef {
    pub stops: Vec<PaletteStop>,
    pub special: HashMap<i64, Colour>,
}

impl<'de> Deserialize<'de> for PaletteDef {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        #[derive(Deserialize)]
        struct Raw {
            stops: Vec<Vec<serde_json::Value>>,
            #[serde(default)]
            special: HashMap<String, [u8; 4]>,
        }
        fn val_to_f64(v: &serde_json::Value) -> f64 {
            match v {
                serde_json::Value::Number(n) => n.as_f64().unwrap_or(0.0),
                serde_json::Value::Bool(b) => {
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
    pub fn get_f64(&self, i: usize) -> Option<f64> {
        match self {
            Self::Bool(v) => v.get(i).map(|&x| f64::from(x)),
            Self::U8(v) => v.get(i).map(|&x| f64::from(x)),
            Self::I16(v) => v.get(i).map(|&x| f64::from(x)),
            Self::U16(v) => v.get(i).map(|&x| f64::from(x)),
            Self::F32(v) => v.get(i).map(|&x| f64::from(x)),
        }
    }

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
}

impl fmt::Display for ScalarValue {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Int(v) => write!(f, "{v}"),
            Self::Float(v) => write!(f, "{v}"),
            Self::Str(v) => write!(f, "{v}"),
            Self::Bool(v) => write!(f, "{v}"),
        }
    }
}

impl<'de> Deserialize<'de> for ScalarValue {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let v = serde_json::Value::deserialize(deserializer)?;
        match v {
            serde_json::Value::Number(n) => n
                .as_i64()
                .map(Self::Int)
                .or_else(|| n.as_f64().map(Self::Float))
                .ok_or_else(|| serde::de::Error::custom("invalid number")),
            serde_json::Value::String(s) => Ok(Self::Str(s)),
            serde_json::Value::Bool(b) => Ok(Self::Bool(b)),
            _ => Err(serde::de::Error::custom("expected number, string, or bool")),
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Arrow {
    pub angle: f32,
    pub magnitude: f32,
}

#[derive(Clone, Debug)]
pub struct ArrowData {
    pub arrows: Vec<Option<Arrow>>,
}

impl<'de> Deserialize<'de> for ArrowData {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        #[derive(Deserialize)]
        struct Raw {
            angles: Vec<Option<f32>>,
            magnitudes: Option<Vec<f32>>,
        }
        let raw = Raw::deserialize(deserializer)?;
        let arrows = raw
            .angles
            .iter()
            .enumerate()
            .map(|(i, angle)| {
                angle.map(|a| Arrow {
                    angle: a,
                    magnitude: raw
                        .magnitudes
                        .as_ref()
                        .and_then(|m| m.get(i).copied())
                        .unwrap_or(1.0),
                })
            })
            .collect();
        Ok(Self { arrows })
    }
}

#[derive(Clone, Debug)]
pub enum VisField {
    Grid { data: GridData, palette: PaletteDef },
    Scalar { data: ScalarValue },
    Tiles { data: Vec<(i32, i32)> },
    VectorField(ArrowData),
}

impl<'de> Deserialize<'de> for VisField {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let raw = serde_json::Value::deserialize(deserializer)?;
        let obj = raw
            .as_object()
            .ok_or_else(|| serde::de::Error::custom("expected object"))?;
        let typ = obj.get("type").and_then(|v| v.as_str()).unwrap_or("");
        match typ {
            "grid" => {
                let dtype = obj.get("dtype").and_then(|v| v.as_str()).unwrap_or("i16");
                let palette: PaletteDef = serde_json::from_value(
                    obj.get("palette")
                        .cloned()
                        .unwrap_or(serde_json::Value::Null),
                )
                .map_err(serde::de::Error::custom)?;
                let arr = obj
                    .get("data")
                    .and_then(|v| v.as_array())
                    .ok_or_else(|| serde::de::Error::custom("missing data"))?;
                let data = match dtype {
                    "bool" => GridData::Bool(
                        arr.iter()
                            .map(|v| u8::from(v.as_bool().unwrap_or(false)))
                            .collect(),
                    ),
                    "u8" => {
                        GridData::U8(arr.iter().map(|v| v.as_u64().unwrap_or(0) as u8).collect())
                    }
                    "i16" => {
                        GridData::I16(arr.iter().map(|v| v.as_i64().unwrap_or(0) as i16).collect())
                    }
                    "u16" => {
                        GridData::U16(arr.iter().map(|v| v.as_u64().unwrap_or(0) as u16).collect())
                    }
                    "f32" => GridData::F32(
                        arr.iter()
                            .map(|v| v.as_f64().unwrap_or(0.0) as f32)
                            .collect(),
                    ),
                    _ => return Err(serde::de::Error::custom(format!("unknown dtype: {dtype}"))),
                };
                Ok(Self::Grid { data, palette })
            }
            "scalar" => {
                let data: ScalarValue = serde_json::from_value(
                    obj.get("data").cloned().unwrap_or(serde_json::Value::Null),
                )
                .map_err(serde::de::Error::custom)?;
                Ok(Self::Scalar { data })
            }
            "tiles" => {
                let data: Vec<(i32, i32)> = serde_json::from_value(
                    obj.get("data").cloned().unwrap_or(serde_json::Value::Null),
                )
                .map_err(serde::de::Error::custom)?;
                Ok(Self::Tiles { data })
            }
            "vectorfield" => {
                let arrow_data: ArrowData =
                    serde_json::from_value(raw).map_err(serde::de::Error::custom)?;
                Ok(Self::VectorField(arrow_data))
            }
            _ => Err(serde::de::Error::custom(format!("unknown vis type: {typ}"))),
        }
    }
}

pub type VisState = HashMap<String, VisField>;

#[derive(Clone, Copy, Debug)]
pub struct Colour {
    pub r: u8,
    pub g: u8,
    pub b: u8,
    pub a: u8,
}

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

    // Clamp below first stop
    if value <= palette.stops[0].t {
        return Some(palette.stops[0].colour);
    }
    // Clamp above last stop
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
