use std::collections::HashMap;
use std::path::Path;

use eframe::{egui, egui_wgpu, wgpu};
use image::{RgbaImage, imageops};
use rayon::prelude::*;

const TILE_SIZE: u32 = 32;
const SPRITE_SIZE: u32 = 512;

/// Per-set configuration for sprites needing non-default handling.
#[derive(Default, Clone, Copy)]
pub struct SpriteConfig<'a> {
    /// Sprites whose source image is a horizontal strip — the first square
    /// frame is cropped and resized to [`SPRITE_SIZE`].
    pub strip_sprites: &'a [&'a str],
    /// Sprites that should be uploaded at their native aspect (no resize).
    pub aspect_sprites: &'a [&'a str],
    /// Sprites that need cardinal rotation variants (`_n`, `_s`, `_e`, `_w`).
    /// Source faces west.
    pub rotatable_sprites: &'a [&'a str],
}

type RotateFn = fn(&RgbaImage) -> RgbaImage;

const ROTATIONS: &[(&str, RotateFn)] = &[
    ("_s", imageops::rotate270),
    ("_e", imageops::rotate180),
    ("_n", imageops::rotate90),
];

/// Holds GPU texture handles keyed by sprite name. Each sprite is its own
/// `TextureId` (this is a per-sprite cache, not a packed texture atlas).
pub struct SpriteSet {
    textures: HashMap<String, egui::TextureId>,
    pub tile_size: f32,
}

fn premultiply_alpha(img: &mut RgbaImage) {
    for pixel in img.pixels_mut() {
        let a = u16::from(pixel[3]);
        pixel[0] = (u16::from(pixel[0]) * a / 255) as u8;
        pixel[1] = (u16::from(pixel[1]) * a / 255) as u8;
        pixel[2] = (u16::from(pixel[2]) * a / 255) as u8;
    }
}

const fn mip_levels(size: u32) -> u32 {
    32 - size.leading_zeros()
}

/// One CPU-decoded sprite ready for GPU upload, with all mipmap levels
/// pre-built. Each level is `(width, height, premultiplied RGBA bytes)`.
struct DecodedSprite {
    name: String,
    levels: Vec<(u32, u32, Vec<u8>)>,
}

fn decode_sprite(name: &str, img: RgbaImage) -> DecodedSprite {
    let mut current = img;
    premultiply_alpha(&mut current);
    let levels_count = mip_levels(current.width().min(current.height()));
    let mut levels = Vec::with_capacity(levels_count as usize);
    levels.push((current.width(), current.height(), current.as_raw().clone()));
    for _ in 1..levels_count {
        let nw = (current.width() / 2).max(1);
        let nh = (current.height() / 2).max(1);
        // Triangle (bilinear) is visually indistinguishable from Lanczos3
        // for ~32-pixel tile rendering and ~5-10× faster.
        current = imageops::resize(&current, nw, nh, imageops::FilterType::Triangle);
        levels.push((nw, nh, current.as_raw().clone()));
    }
    DecodedSprite {
        name: name.to_string(),
        levels,
    }
}

fn upload_decoded(rs: &egui_wgpu::RenderState, sprite: &DecodedSprite) -> egui::TextureId {
    let device = &rs.device;
    let queue = &rs.queue;
    let (w, h, _) = sprite.levels[0];

    let texture = device.create_texture(&wgpu::TextureDescriptor {
        label: Some("sprite"),
        size: wgpu::Extent3d {
            width: w,
            height: h,
            depth_or_array_layers: 1,
        },
        mip_level_count: sprite.levels.len() as u32,
        sample_count: 1,
        dimension: wgpu::TextureDimension::D2,
        format: wgpu::TextureFormat::Rgba8Unorm,
        usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
        view_formats: &[],
    });

    for (level, (lw, lh, data)) in sprite.levels.iter().enumerate() {
        queue.write_texture(
            wgpu::TexelCopyTextureInfo {
                texture: &texture,
                mip_level: level as u32,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            data,
            wgpu::TexelCopyBufferLayout {
                offset: 0,
                bytes_per_row: Some(4 * lw),
                rows_per_image: Some(*lh),
            },
            wgpu::Extent3d {
                width: *lw,
                height: *lh,
                depth_or_array_layers: 1,
            },
        );
    }

    let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
    rs.renderer
        .write()
        .register_native_texture_with_sampler_options(
            device,
            &view,
            wgpu::SamplerDescriptor {
                label: Some("sprite_sampler"),
                mag_filter: wgpu::FilterMode::Linear,
                min_filter: wgpu::FilterMode::Linear,
                mipmap_filter: wgpu::MipmapFilterMode::Linear,
                ..Default::default()
            },
        )
}

fn collect_images(dir: &Path, out: &mut Vec<std::path::PathBuf>) {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            collect_images(&path, out);
        } else if path
            .extension()
            .is_some_and(|e| e == "png" || e == "jpg" || e == "jpeg")
        {
            out.push(path);
        }
    }
}

impl SpriteSet {
    /// Decode every PNG under `assets_dir` in parallel, build mipmaps,
    /// and upload to the GPU. Heavy CPU work runs on rayon's pool;
    /// the wgpu uploads themselves are serialised on the calling thread
    /// (which is what the renderer requires anyway).
    #[must_use]
    pub fn load(rs: &egui_wgpu::RenderState, assets_dir: &Path, config: SpriteConfig<'_>) -> Self {
        let mut image_paths: Vec<std::path::PathBuf> = Vec::new();
        collect_images(assets_dir, &mut image_paths);

        // Parallel decode + resize + mipmap generation. Each path may
        // produce multiple `DecodedSprite`s (a rotatable sprite emits
        // five: the base plus four rotation variants).
        let decoded: Vec<DecodedSprite> = image_paths
            .par_iter()
            .flat_map_iter(|path| decode_one(path, &config))
            .collect();

        let mut textures = HashMap::with_capacity(decoded.len());
        for sprite in &decoded {
            let id = upload_decoded(rs, sprite);
            textures.insert(sprite.name.clone(), id);
        }

        Self {
            textures,
            tile_size: TILE_SIZE as f32,
        }
    }

    #[must_use]
    pub fn get(&self, name: &str) -> Option<egui::TextureId> {
        self.textures.get(name).copied()
    }
}

fn decode_one(path: &Path, config: &SpriteConfig<'_>) -> Vec<DecodedSprite> {
    let Ok(img) = image::open(path) else {
        return Vec::new();
    };
    let name = path
        .file_stem()
        .unwrap_or_default()
        .to_string_lossy()
        .into_owned();
    let rgba = img.to_rgba8();

    let base = if config.strip_sprites.contains(&name.as_str()) {
        let frame_w = rgba.height();
        let frame = imageops::crop_imm(&rgba, 0, 0, frame_w, frame_w).to_image();
        resize_to_sprite(&frame)
    } else if config.aspect_sprites.contains(&name.as_str()) {
        rgba
    } else {
        resize_to_sprite(&rgba)
    };

    let mut out = Vec::new();
    if config.rotatable_sprites.contains(&name.as_str()) {
        out.push(decode_sprite(&format!("{name}_w"), base.clone()));
        for &(suffix, rotate) in ROTATIONS {
            let rotated = rotate(&base);
            out.push(decode_sprite(&format!("{name}{suffix}"), rotated));
        }
    }
    out.push(decode_sprite(&name, base));
    out
}

fn resize_to_sprite(img: &RgbaImage) -> RgbaImage {
    if img.width() == SPRITE_SIZE && img.height() == SPRITE_SIZE {
        // Already at target size — skip the costly Lanczos3/Triangle pass.
        return img.clone();
    }
    imageops::resize(
        img,
        SPRITE_SIZE,
        SPRITE_SIZE,
        imageops::FilterType::Triangle,
    )
}
