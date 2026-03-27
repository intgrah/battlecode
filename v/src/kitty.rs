use std::io::{self, Write};

use base64::Engine;
use image::RgbaImage;

const CHUNK_SIZE: usize = 4096;

pub fn display_image(img: &RgbaImage, id: u32, col: u16, row: u16) -> io::Result<()> {
    let mut png_buf = Vec::new();
    img.write_to(&mut io::Cursor::new(&mut png_buf), image::ImageFormat::Png)
        .map_err(|e| io::Error::new(io::ErrorKind::Other, e))?;

    let encoded = base64::engine::general_purpose::STANDARD.encode(&png_buf);
    let mut stdout = io::stdout().lock();

    write!(stdout, "\x1b[{};{}H", row + 1, col + 1)?;

    let chunks: Vec<&str> = encoded
        .as_bytes()
        .chunks(CHUNK_SIZE)
        .map(|c| std::str::from_utf8(c).unwrap_or(""))
        .collect();

    for (i, chunk) in chunks.iter().enumerate() {
        let more = u8::from(i + 1 < chunks.len());
        if i == 0 {
            write!(
                stdout,
                "\x1b_Ga=T,f=100,i={id},z=-1,C=1,m={more},q=2;{chunk}\x1b\\"
            )?;
        } else {
            write!(stdout, "\x1b_Gm={more};{chunk}\x1b\\")?;
        }
    }

    stdout.flush()
}

pub fn delete_image(id: u32) -> io::Result<()> {
    let mut stdout = io::stdout().lock();
    write!(stdout, "\x1b_Ga=d,d=I,i={id},q=2;\x1b\\")?;
    stdout.flush()
}
