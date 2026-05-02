/// Doubles a number.
fn double(x: i64) -> i64 {
    x * 2
}

fn main() {
    pyrust::print(&double(7));
}
