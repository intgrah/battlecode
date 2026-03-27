fn main() -> std::io::Result<()> {
    prost_build::compile_protos(&["../proto/cambc.proto"], &["../proto/"])?;
    Ok(())
}
