use std::collections::HashMap;
use std::path::Path;

use eframe::{egui, wgpu};
use image::{RgbaImage, imageops};

const TILE_SIZE: u32 = 32;
const SPRITE_SIZE: u32 = 512;

/// Per-atlas configuration for sprites needing non-default handling.
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

pub struct SpriteAtlas {
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

fn mip_levels(size: u32) -> u32 {
    (size as f32).log2().floor() as u32 + 1
}

fn upload_mipmapped(cc: &eframe::CreationContext<'_>, img: &RgbaImage) -> Option<egui::TextureId> {
    let mut img = img.clone();
    premultiply_alpha(&mut img);
    let rs = cc.wgpu_render_state.as_ref()?;
    let device = &rs.device;
    let queue = &rs.queue;

    let (w, h) = (img.width(), img.height());
    let levels = mip_levels(w.min(h));

    let texture = device.create_texture(&wgpu::TextureDescriptor {
        label: Some("sprite"),
        size: wgpu::Extent3d {
            width: w,
            height: h,
            depth_or_array_layers: 1,
        },
        mip_level_count: levels,
        sample_count: 1,
        dimension: wgpu::TextureDimension::D2,
        format: wgpu::TextureFormat::Rgba8Unorm,
        usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
        view_formats: &[],
    });

    let write = |tex: &wgpu::Texture, level: u32, data: &[u8], tw: u32, th: u32| {
        queue.write_texture(
            wgpu::TexelCopyTextureInfo {
                texture: tex,
                mip_level: level,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            data,
            wgpu::TexelCopyBufferLayout {
                offset: 0,
                bytes_per_row: Some(4 * tw),
                rows_per_image: Some(th),
            },
            wgpu::Extent3d {
                width: tw,
                height: th,
                depth_or_array_layers: 1,
            },
        );
    };

    write(&texture, 0, img.as_raw(), w, h);

    let mut current = img;
    for level in 1..levels {
        let nw = (current.width() / 2).max(1);
        let nh = (current.height() / 2).max(1);
        current = imageops::resize(&current, nw, nh, imageops::FilterType::Lanczos3);
        write(&texture, level, current.as_raw(), nw, nh);
    }

    let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
    Some(
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
            ),
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

impl SpriteAtlas {
    pub fn load(
        cc: &eframe::CreationContext<'_>,
        assets_dir: &Path,
        config: SpriteConfig<'_>,
    ) -> Self {
        let mut textures = HashMap::new();

        let mut image_paths: Vec<std::path::PathBuf> = Vec::new();
        collect_images(assets_dir, &mut image_paths);

        for path in image_paths {
            let Ok(img) = image::open(&path) else {
                continue;
            };
            let name = path
                .file_stem()
                .unwrap_or_default()
                .to_string_lossy()
                .to_string();

            let rgba = img.to_rgba8();

            let base = if config.strip_sprites.contains(&name.as_str()) {
                let frame_w = rgba.height();
                let frame = imageops::crop_imm(&rgba, 0, 0, frame_w, frame_w).to_image();
                imageops::resize(
                    &frame,
                    SPRITE_SIZE,
                    SPRITE_SIZE,
                    imageops::FilterType::Lanczos3,
                )
            } else if config.aspect_sprites.contains(&name.as_str()) {
                rgba
            } else {
                imageops::resize(
                    &rgba,
                    SPRITE_SIZE,
                    SPRITE_SIZE,
                    imageops::FilterType::Lanczos3,
                )
            };

            if config.rotatable_sprites.contains(&name.as_str()) {
                if let Some(id) = upload_mipmapped(cc, &base) {
                    textures.insert(format!("{name}_w"), id);
                }
                for &(suffix, rotate) in ROTATIONS {
                    let rotated = rotate(&base);
                    if let Some(id) = upload_mipmapped(cc, &rotated) {
                        textures.insert(format!("{name}{suffix}"), id);
                    }
                }
            }

            if let Some(id) = upload_mipmapped(cc, &base) {
                textures.insert(name, id);
            }
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
