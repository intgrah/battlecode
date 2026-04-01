use std::collections::HashMap;

use serde::Deserialize;

#[derive(Clone, Debug, Deserialize)]
#[serde(tag = "type", rename_all = "lowercase")]
pub enum VisField {
    Grid {
        data: Vec<Option<f64>>,
        palette: String,
        null: Option<f64>,
    },
    Scalar {
        data: serde_json::Value,
    },
    Tiles {
        data: Vec<[i32; 2]>,
    },
}

pub type VisState = HashMap<String, VisField>;

pub fn parse_vis(json: &str) -> Option<VisState> {
    serde_json::from_str(json).ok()
}

pub struct PaletteColor {
    pub r: u8,
    pub g: u8,
    pub b: u8,
    pub a: u8,
}

pub fn sample_palette(palette: &str, t: f32) -> PaletteColor {
    let t = t.clamp(0.0, 1.0);
    match palette {
        "green" => PaletteColor {
            r: 0,
            g: (t * 200.0) as u8,
            b: 0,
            a: (t * 160.0) as u8,
        },
        "red" => PaletteColor {
            r: (t * 200.0) as u8,
            g: 0,
            b: 0,
            a: (t * 160.0) as u8,
        },
        "blue" => PaletteColor {
            r: 0,
            g: 0,
            b: (t * 200.0) as u8,
            a: (t * 160.0) as u8,
        },
        "grey" => PaletteColor {
            r: (t * 180.0) as u8,
            g: (t * 180.0) as u8,
            b: (t * 180.0) as u8,
            a: (t * 120.0) as u8,
        },
        "black" => PaletteColor {
            r: 0,
            g: 0,
            b: 0,
            a: (t * 180.0) as u8,
        },
        "red_green" => {
            if t < 0.5 {
                let s = 1.0 - t * 2.0;
                PaletteColor {
                    r: (s * 200.0) as u8,
                    g: 0,
                    b: 0,
                    a: (s * 160.0) as u8,
                }
            } else {
                let s = (t - 0.5) * 2.0;
                PaletteColor {
                    r: 0,
                    g: (s * 200.0) as u8,
                    b: 0,
                    a: (s * 160.0) as u8,
                }
            }
        }
        _ => {
            let r = (t * t)
                .mul_add(0.166f32.mul_add(-t, 0.392), 0.004f32.mul_add(t, 0.267))
                .min(1.0);
            let g = t
                .mul_add(t.mul_add(t.mul_add(1.349, -2.370), 1.513), 0.004)
                .clamp(0.0, 1.0);
            let b = t
                .mul_add(t.mul_add(t.mul_add(1.320, -2.681), 1.442), 0.329)
                .clamp(0.0, 1.0);
            PaletteColor {
                r: (r * 255.0) as u8,
                g: (g * 255.0) as u8,
                b: (b * 255.0) as u8,
                a: (t * 160.0 + 40.0) as u8,
            }
        }
    }
}
