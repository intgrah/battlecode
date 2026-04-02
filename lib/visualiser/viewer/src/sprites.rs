use std::collections::HashMap;
use std::path::Path;

use eframe::{egui, wgpu};
use image::{RgbaImage, imageops};

const TILE_SIZE: u32 = 32;
const SPRITE_SIZE: u32 = 512;
const BEAM_SPRITES: &[&str] = &["bridge_gold", "bridge_silver"];

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
    let img = &img;
    let rs = cc.wgpu_render_state.as_ref()?;
    let device = &rs.device;
    let queue = &rs.queue;

    let w = img.width();
    let h = img.height();
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

    queue.write_texture(
        wgpu::TexelCopyTextureInfo {
            texture: &texture,
            mip_level: 0,
            origin: wgpu::Origin3d::ZERO,
            aspect: wgpu::TextureAspect::All,
        },
        img.as_raw(),
        wgpu::TexelCopyBufferLayout {
            offset: 0,
            bytes_per_row: Some(4 * w),
            rows_per_image: Some(h),
        },
        wgpu::Extent3d {
            width: w,
            height: h,
            depth_or_array_layers: 1,
        },
    );

    let mut current = img.clone();
    for level in 1..levels {
        let nw = (current.width() / 2).max(1);
        let nh = (current.height() / 2).max(1);
        current = imageops::resize(&current, nw, nh, imageops::FilterType::Lanczos3);
        queue.write_texture(
            wgpu::TexelCopyTextureInfo {
                texture: &texture,
                mip_level: level,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            current.as_raw(),
            wgpu::TexelCopyBufferLayout {
                offset: 0,
                bytes_per_row: Some(4 * nw),
                rows_per_image: Some(nh),
            },
            wgpu::Extent3d {
                width: nw,
                height: nh,
                depth_or_array_layers: 1,
            },
        );
    }

    let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
    let id = rs
        .renderer
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
        );
    Some(id)
}

impl SpriteAtlas {
    pub fn load(cc: &eframe::CreationContext<'_>, assets_dir: &Path) -> Self {
        let mut textures = HashMap::new();

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
                if let Some(id) = upload_mipmapped(cc, &resized) {
                    textures.insert(name, id);
                }
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
                        if let Some(id) = upload_mipmapped(cc, &rotated) {
                            textures.insert(rname, id);
                        }
                    }
                }

                if let Some(id) = upload_mipmapped(cc, &resized) {
                    textures.insert(name, id);
                }
            }
        }

        Self {
            textures,
            tile_size: TILE_SIZE as f32,
        }
    }

    pub fn get(&self, name: &str) -> Option<egui::TextureId> {
        self.textures.get(name).copied()
    }
}
