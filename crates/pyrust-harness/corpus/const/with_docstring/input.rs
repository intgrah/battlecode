/// Maximum tries before giving up.
const MAX_TRIES: i64 = 5;

/// Whether the feature is enabled.
const FLAG: bool = true;

fn main() {
    pyrust::print(&MAX_TRIES);
    pyrust::print(&FLAG);
}
