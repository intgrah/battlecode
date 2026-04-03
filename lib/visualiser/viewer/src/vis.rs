use std::collections::HashMap;

use serde::Deserialize;
use serde::de::{self, SeqAccess, Visitor};

#[derive(Clone, Debug, Deserialize)]
pub struct PaletteDef {
    pub stops: Vec<[f32; 5]>,
    #[serde(default)]
    pub special: HashMap<String, [u8; 4]>,
}

#[derive(Clone, Debug)]
pub enum GridData {
    Ints(Vec<Option<i32>>),
    Floats(Vec<Option<f32>>),
}

impl GridData {
    pub const fn len(&self) -> usize {
        match self {
            Self::Ints(v) => v.len(),
            Self::Floats(v) => v.len(),
        }
    }

    pub fn get_f32(&self, i: usize) -> Option<f32> {
        match self {
            Self::Ints(v) => v.get(i).copied().flatten().map(|x| x as f32),
            Self::Floats(v) => v.get(i).copied().flatten(),
        }
    }
}

impl<'de> Deserialize<'de> for GridData {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct GridDataVisitor;

        impl<'de> Visitor<'de> for GridDataVisitor {
            type Value = GridData;

            fn expecting(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                f.write_str("array of numbers, bools, or nulls")
            }

            fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<GridData, A::Error> {
                let mut ints: Vec<Option<i32>> = Vec::with_capacity(seq.size_hint().unwrap_or(0));

                while let Some(val) = seq.next_element::<serde_json::Value>()? {
                    match &val {
                        serde_json::Value::Null => ints.push(None),
                        serde_json::Value::Bool(b) => ints.push(Some(i32::from(*b))),
                        serde_json::Value::Number(n) => {
                            if let Some(i) = n.as_i64() {
                                ints.push(Some(i as i32));
                            } else {
                                let mut floats: Vec<Option<f32>> = ints
                                    .iter()
                                    .map(|v| v.map(|x| x as f32))
                                    .collect();
                                floats.push(n.as_f64().map(|x| x as f32));
                                while let Some(val) = seq.next_element::<serde_json::Value>()? {
                                    match &val {
                                        serde_json::Value::Null => floats.push(None),
                                        serde_json::Value::Bool(b) => {
                                            floats.push(Some(if *b { 1.0 } else { 0.0 }));
                                        }
                                        serde_json::Value::Number(n) => {
                                            floats.push(n.as_f64().map(|x| x as f32));
                                        }
                                        _ => return Err(de::Error::custom("unexpected value")),
                                    }
                                }
                                return Ok(GridData::Floats(floats));
                            }
                        }
                        _ => return Err(de::Error::custom("unexpected value")),
                    }
                }

                Ok(GridData::Ints(ints))
            }
        }

        deserializer.deserialize_seq(GridDataVisitor)
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
        data: serde_json::Value,
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

pub fn parse_vis(jsons: &[String]) -> VisState {
    let mut merged = VisState::new();
    for json in jsons {
        if let Ok(fields) = serde_json::from_str::<VisState>(json) {
            merged.extend(fields);
        }
    }
    merged
}

pub struct Color {
    pub r: u8,
    pub g: u8,
    pub b: u8,
    pub a: u8,
}

pub fn is_special(palette: &PaletteDef, value: f32) -> bool {
    let key = if (value - value.round()).abs() < 1e-6 {
        format!("{}", value as i32)
    } else {
        format!("{value}")
    };
    palette.special.contains_key(&key)
}

#[allow(clippy::many_single_char_names)]
pub fn sample_palette(palette: &PaletteDef, value: f32, min: f32, max: f32) -> Option<Color> {
    let key = if (value - value.round()).abs() < 1e-6 {
        format!("{}", value as i32)
    } else {
        format!("{value}")
    };
    if let Some(&[r, g, b, a]) = palette.special.get(&key) {
        return Some(Color { r, g, b, a });
    }

    if palette.stops.is_empty() {
        return None;
    }
    if palette.stops.len() == 1 {
        let [_, r, g, b, a] = palette.stops[0];
        return Some(Color {
            r: r as u8,
            g: g as u8,
            b: b as u8,
            a: a as u8,
        });
    }

    let range = max - min;
    let t = if range.abs() < 1e-9 { 0.5 } else { ((value - min) / range).clamp(0.0, 1.0) };

    let last = palette.stops.len() - 1;
    for i in 0..last {
        let [t0, r0, g0, b0, a0] = palette.stops[i];
        let [t1, r1, g1, b1, a1] = palette.stops[i + 1];
        if t >= t0 && (t <= t1 || i == last - 1) {
            let seg = if (t1 - t0).abs() < 1e-9 {
                0.0
            } else {
                (t - t0) / (t1 - t0)
            };
            return Some(Color {
                r: r0.mul_add(1.0 - seg, r1 * seg) as u8,
                g: g0.mul_add(1.0 - seg, g1 * seg) as u8,
                b: b0.mul_add(1.0 - seg, b1 * seg) as u8,
                a: a0.mul_add(1.0 - seg, a1 * seg) as u8,
            });
        }
    }

    let [_, r, g, b, a] = palette.stops[last];
    Some(Color {
        r: r as u8,
        g: g as u8,
        b: b as u8,
        a: a as u8,
    })
}
