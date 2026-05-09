// Default `cargo run` is a debug build, so `debug_assertions` is set
// natively. `pyrust-translate` defaults to the same env. Both paths
// execute the "debug" branches; release-mode behaviour is exercised by
// release-mode unit checks elsewhere.

#[cfg(debug_assertions)]
fn marker() {
    pyrust::print(&"debug");
}

#[cfg(not(debug_assertions))]
fn marker() {
    pyrust::print(&"release");
}

fn main() {
    marker();
    if cfg!(debug_assertions) {
        pyrust::print(&"if-debug");
    } else {
        pyrust::print(&"if-release");
    }
    #[cfg(debug_assertions)]
    let banner = "[debug-stmt]";
    #[cfg(not(debug_assertions))]
    let banner = "[release-stmt]";
    pyrust::print(&banner);
}
