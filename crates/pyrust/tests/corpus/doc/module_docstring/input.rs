//! A two-line module.
//!
//! Greets the world.

/// Greets the named recipient.
///
/// The greeting is fixed; only the name varies.
fn greet(name: &str) {
    pyrust::print(&name);
}

fn main() {
    greet("world");
}
