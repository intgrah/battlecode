use std::collections::HashMap;
use std::fmt;

use serde::Deserialize;

#[derive(Clone, Debug)]
pub struct PaletteStop {
    pub t: f32,
    pub r: f32,
    pub g: f32,
    pub b: f32,
    pub a: f32,
}

#[derive(Clone, Debug)]
pub struct PaletteDef {
    pub stops: Vec<PaletteStop>,
    pub special: HashMap<i64, Color>,
}

impl<'de> Deserialize<'de> for PaletteDef {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        #[derive(Deserialize)]
        struct Raw {
            stops: Vec<[f32; 5]>,
            #[serde(default)]
            special: HashMap<String, [u8; 4]>,
        }
        let raw = Raw::deserialize(deserializer)?;
        let stops = raw
            .stops
            .into_iter()
            .map(|[t, r, g, b, a]| PaletteStop { t, r, g, b, a })
            .collect();
        let special = raw
            .special
            .into_iter()
            .filter_map(|(k, [r, g, b, a])| k.parse::<i64>().ok().map(|k| (k, Color { r, g, b, a })))
            .collect();
        Ok(PaletteDef { stops, special })
    }
}

#[derive(Clone, Debug)]
pub enum GridData {
    Ints(Vec<Option<i64>>),
    Floats(Vec<Option<f64>>),
}

impl GridData {
    pub const fn len(&self) -> usize {
        match self {
            Self::Ints(v) => v.len(),
            Self::Floats(v) => v.len(),
        }
    }

    pub fn get_f64(&self, i: usize) -> Option<f64> {
        match self {
            Self::Ints(v) => v.get(i).copied().flatten().map(|x| x as f64),
            Self::Floats(v) => v.get(i).copied().flatten(),
        }
    }

    pub fn get_i64(&self, i: usize) -> Option<i64> {
        match self {
            Self::Ints(v) => v.get(i).copied().flatten(),
            Self::Floats(v) => v.get(i).copied().flatten().map(|x| x as i64),
        }
    }
}

impl<'de> Deserialize<'de> for GridData {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let values: Vec<Option<serde_json::Number>> = Vec::deserialize(deserializer)?;
        let mut has_float = false;
        for v in &values {
            if let Some(n) = v {
                if n.as_i64().is_none() {
                    has_float = true;
                    break;
                }
            }
        }
        if has_float {
            Ok(GridData::Floats(
                values
                    .into_iter()
                    .map(|v| v.and_then(|n| n.as_f64()))
                    .collect(),
            ))
        } else {
            Ok(GridData::Ints(
                values
                    .into_iter()
                    .map(|v| v.and_then(|n| n.as_i64()))
                    .collect(),
            ))
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
            serde_json::Value::Number(n) => {
                if let Some(i) = n.as_i64() {
                    Ok(Self::Int(i))
                } else if let Some(f) = n.as_f64() {
                    Ok(Self::Float(f))
                } else {
                    Err(serde::de::Error::custom("invalid number"))
                }
            }
            serde_json::Value::String(s) => Ok(Self::Str(s)),
            serde_json::Value::Bool(b) => Ok(Self::Bool(b)),
            _ => Err(serde::de::Error::custom("expected number, string, or bool")),
        }
    }
}

#[derive(Clone, Debug, Deserialize)]
#[serde(tag = "type", rename_all = "lowercase")]
pub enum VisField {
    Grid {
        data: GridData,
        palette: PaletteDef,
    },
    Scalar {
        data: ScalarValue,
    },
    Tiles {
        data: Vec<[i32; 2]>,
    },
    VectorField {
        angles: Vec<Option<f32>>,
        magnitudes: Option<Vec<f32>>,
    },
}

pub type VisState = HashMap<String, VisField>;

#[derive(Clone, Copy, Debug)]
pub struct Color {
    pub r: u8,
    pub g: u8,
    pub b: u8,
    pub a: u8,
}

pub fn sample_palette(palette: &PaletteDef, value: f64, min: f64, max: f64) -> Option<Color> {
    if let Some(i) = i64::try_from(value as i128).ok().filter(|_| (value - value.round()).abs() < 1e-9) {
        if let Some(c) = palette.special.get(&i) {
            return Some(*c);
        }
    }

    if palette.stops.is_empty() {
        return None;
    }
    if palette.stops.len() == 1 {
        let s = &palette.stops[0];
        return Some(Color {
            r: s.r as u8,
            g: s.g as u8,
            b: s.b as u8,
            a: s.a as u8,
        });
    }

    let range = max - min;
    let t = if range.abs() < 1e-9 {
        0.5
    } else {
        ((value - min) / range).clamp(0.0, 1.0) as f32
    };

    let last = palette.stops.len() - 1;
    for i in 0..last {
        let s0 = &palette.stops[i];
        let s1 = &palette.stops[i + 1];
        if t >= s0.t && (t <= s1.t || i == last - 1) {
            let seg = if (s1.t - s0.t).abs() < 1e-9 {
                0.0
            } else {
                (t - s0.t) / (s1.t - s0.t)
            };
            return Some(Color {
                r: s0.r.mul_add(1.0 - seg, s1.r * seg) as u8,
                g: s0.g.mul_add(1.0 - seg, s1.g * seg) as u8,
                b: s0.b.mul_add(1.0 - seg, s1.b * seg) as u8,
                a: s0.a.mul_add(1.0 - seg, s1.a * seg) as u8,
            });
        }
    }

    let s = &palette.stops[last];
    Some(Color {
        r: s.r as u8,
        g: s.g as u8,
        b: s.b as u8,
        a: s.a as u8,
    })
}

pub fn is_special(palette: &PaletteDef, value: f64) -> bool {
    if let Some(i) = i64::try_from(value as i128).ok().filter(|_| (value - value.round()).abs() < 1e-9) {
        palette.special.contains_key(&i)
    } else {
        false
    }
}
