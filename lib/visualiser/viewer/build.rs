fn main() -> std::io::Result<()> {
    prost_build::compile_protos(&["../../proto/src/proto/cambc.proto"], &["../../proto/src/proto/"])?;
    Ok(())
}
