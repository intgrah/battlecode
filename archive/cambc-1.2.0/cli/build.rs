use std::fs;
use std::path::PathBuf;

fn main() {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let dest = manifest_dir.join("python/cambc/_types.py");

    // In the monorepo, copy from the engine's source of truth
    let source = manifest_dir
        .parent()
        .unwrap()
        .join("engine/py/cambc.py");

    if source.exists() {
        println!("cargo:rerun-if-changed={}", source.display());
        fs::copy(&source, &dest).expect("copy cambc.py to _types.py");
    }

    // When building from sdist, the file is already included in the archive
    assert!(
        dest.exists(),
        "python/cambc/_types.py not found — build from the monorepo or use a prebuilt wheel"
    );
}
