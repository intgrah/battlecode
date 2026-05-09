fn fact(n: i64) -> i64 {
    if n <= 1 { 1 } else { n * fact(n - 1) }
}

fn main() {
    pyrust::print(&fact(5));
}
