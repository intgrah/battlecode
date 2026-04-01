use std::collections::HashMap;
use std::path::Path;

use eframe::egui;
use egui::{ColorImage, TextureHandle, TextureOptions};
use image::{RgbaImage, imageops};

const TILE_SIZE: u32 = 32;
const SPRITE_SIZE: u32 = 128;
const BEAM_SPRITES: &[&str] = &["bridge_gold", "bridge_silver"];

pub struct SpriteAtlas {
    textures: HashMap<String, TextureHandle>,
    pub tile_size: f32,
}

fn rgba_to_color_image(img: &RgbaImage) -> ColorImage {
    ColorImage::from_rgba_unmultiplied([img.width() as usize, img.height() as usize], img.as_raw())
}

impl SpriteAtlas {
    pub fn load(ctx: &egui::Context, assets_dir: &Path) -> Self {
        let mut textures = HashMap::new();
        let opts = TextureOptions::LINEAR;

        let Ok(entries) = std::fs::read_dir(assets_dir) else {
            return Self {
                textures,
                tile_size: TILE_SIZE as f32,
            };
        };

        for entry in entries.flatten() {
            let path = entry.path();
            if !path
                .extension()
                .is_some_and(|e| e == "png" || e == "jpg" || e == "jpeg")
            {
                continue;
            }
            let Ok(img) = image::open(&path) else {
                continue;
            };
            let name = path
                .file_stem()
                .unwrap_or_default()
                .to_string_lossy()
                .to_string();

            let rgba = img.to_rgba8();

            if BEAM_SPRITES.contains(&name.as_str()) {
                let frame_w = rgba.height();
                let frame = imageops::crop_imm(&rgba, 0, 0, frame_w, frame_w).to_image();
                let resized = imageops::resize(
                    &frame,
                    SPRITE_SIZE,
                    SPRITE_SIZE,
                    imageops::FilterType::Lanczos3,
                );
                let color = rgba_to_color_image(&resized);
                textures.insert(name, ctx.load_texture("beam", color, opts));
            } else {
                let resized = imageops::resize(
                    &rgba,
                    SPRITE_SIZE,
                    SPRITE_SIZE,
                    imageops::FilterType::Lanczos3,
                );

                if name == "conveyor_gold"
                    || name == "conveyor_silver"
                    || name == "armoured_conveyor_gold"
                    || name == "armoured_conveyor_silver"
                {
                    #[allow(clippy::option_if_let_else)]
                    for (suffix, rot_fn) in [
                        ("_w", None as Option<fn(&RgbaImage) -> RgbaImage>),
                        (
                            "_s",
                            Some(imageops::rotate270 as fn(&RgbaImage) -> RgbaImage),
                        ),
                        (
                            "_e",
                            Some(imageops::rotate180 as fn(&RgbaImage) -> RgbaImage),
                        ),
                        (
                            "_n",
                            Some(imageops::rotate90 as fn(&RgbaImage) -> RgbaImage),
                        ),
                    ] {
                        let rotated = match rot_fn {
                            Some(f) => f(&resized),
                            None => resized.clone(),
                        };
                        let rname = format!("{name}{suffix}");
                        let color = rgba_to_color_image(&rotated);
                        textures.insert(rname.clone(), ctx.load_texture(rname, color, opts));
                    }
                }

                let color = rgba_to_color_image(&resized);
                textures.insert(name.clone(), ctx.load_texture(name, color, opts));
            }
        }

        Self {
            textures,
            tile_size: TILE_SIZE as f32,
        }
    }

    pub fn get(&self, name: &str) -> Option<&TextureHandle> {
        self.textures.get(name)
    }
}
