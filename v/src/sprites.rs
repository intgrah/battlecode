use std::collections::HashMap;
use std::path::Path;

use image::{RgbaImage, imageops};

const TILE_SIZE: u32 = 32;
const CORE_SPRITES: &[&str] = &["base_gold", "base_silver"];
const BEAM_SPRITES: &[&str] = &["bridge_gold", "bridge_silver"];

pub struct SpriteAtlas {
    sprites: HashMap<String, RgbaImage>,
    pub tile_size: u32,
}

impl SpriteAtlas {
    pub fn load(assets_dir: &Path) -> Self {
        let mut sprites = HashMap::new();
        if let Ok(entries) = std::fs::read_dir(assets_dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path
                    .extension()
                    .is_some_and(|e| e == "png" || e == "jpg" || e == "jpeg")
                    && let Ok(img) = image::open(&path)
                {
                    let name = path
                        .file_stem()
                        .unwrap_or_default()
                        .to_string_lossy()
                        .to_string();
                    if BEAM_SPRITES.contains(&name.as_str()) {
                        let rgba = img.to_rgba8();
                        let frame_w = rgba.height();
                        let frame = imageops::crop_imm(&rgba, 0, 0, frame_w, frame_w).to_image();
                        sprites.insert(name, frame);
                    } else {
                        let size = if CORE_SPRITES.contains(&name.as_str()) {
                            TILE_SIZE * 3
                        } else {
                            TILE_SIZE
                        };
                        let resized = imageops::resize(
                            &img.to_rgba8(),
                            size,
                            size,
                            imageops::FilterType::Lanczos3,
                        );
                        sprites.insert(name, resized);
                    }
                }
            }
        }
        Self {
            sprites,
            tile_size: TILE_SIZE,
        }
    }

    pub fn get(&self, name: &str) -> Option<&RgbaImage> {
        self.sprites.get(name)
    }
}
