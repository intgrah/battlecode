fn main() -> std::io::Result<()> {
    let manifest_dir = std::env::var("CARGO_MANIFEST_DIR").unwrap();
    let proto_path = format!("{manifest_dir}/../../pkg/proto/src/proto");
    prost_build::compile_protos(&[format!("{proto_path}/cambc.proto")], &[&proto_path])?;
    Ok(())
}
