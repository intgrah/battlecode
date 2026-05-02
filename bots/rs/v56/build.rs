fn main() {
    println!("cargo:rerun-if-env-changed=DEBUG_LOG");
    println!("cargo:rerun-if-env-changed=DEBUG_DUMP");
    println!("cargo:rerun-if-env-changed=DEBUG_INVARIANTS");
    println!("cargo:rerun-if-env-changed=DEBUG_RESIGN");
    println!("cargo:rustc-check-cfg=cfg(debug_log)");
    println!("cargo:rustc-check-cfg=cfg(debug_dump)");
    println!("cargo:rustc-check-cfg=cfg(debug_invariants)");
    println!("cargo:rustc-check-cfg=cfg(debug_resign)");
    let dump = std::env::var_os("DEBUG_DUMP").is_some();
    let log = std::env::var_os("DEBUG_LOG").is_some() || dump;
    if log {
        println!("cargo:rustc-cfg=debug_log");
    }
    if dump {
        println!("cargo:rustc-cfg=debug_dump");
    }
    if std::env::var_os("DEBUG_INVARIANTS").is_some() {
        println!("cargo:rustc-cfg=debug_invariants");
    }
    if std::env::var_os("DEBUG_RESIGN").is_some() {
        println!("cargo:rustc-cfg=debug_resign");
    }
}
