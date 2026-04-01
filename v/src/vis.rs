use std::collections::HashMap;

use serde::Deserialize;

#[derive(Clone, Debug, Deserialize)]
pub struct PaletteDef {
    pub stops: Vec<[f32; 5]>,
    #[serde(default)]
    pub special: HashMap<String, [u8; 4]>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(tag = "type", rename_all = "lowercase")]
pub enum VisField {
    Grid {
        data: Vec<Option<f64>>,
        palette: PaletteDef,
    },
    Scalar {
        data: serde_json::Value,
    },
    Tiles {
        data: Vec<[i32; 2]>,
    },
    #[serde(rename = "vectorfield")]
    VectorField {
        angles: Vec<Option<f64>>,
        magnitudes: Option<Vec<f64>>,
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

#[allow(clippy::many_single_char_names)]
pub fn sample_palette(palette: &PaletteDef, value: f64, min: f64, max: f64) -> Option<Color> {
    let key = format!("{value}");
    if let Some(&[r, g, b, a]) = palette.special.get(&key) {
        return Some(Color { r, g, b, a });
    }
    let key_int = format!("{}", value as i64);
    if (value - value.round()).abs() < 1e-9
        && let Some(&[r, g, b, a]) = palette.special.get(&key_int)
    {
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
    let t = if range.abs() < 1e-12 {
        0.5
    } else {
        ((value - min) / range).clamp(0.0, 1.0)
    };

    let t = t as f32;
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

pub fn is_special(palette: &PaletteDef, value: f64) -> bool {
    let key = format!("{value}");
    if palette.special.contains_key(&key) {
        return true;
    }
    if (value - value.round()).abs() < 1e-9 {
        let key_int = format!("{}", value as i64);
        if palette.special.contains_key(&key_int) {
            return true;
        }
    }
    false
}
