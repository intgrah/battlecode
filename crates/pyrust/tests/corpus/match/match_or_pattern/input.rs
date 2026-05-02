fn parity(n: i64) -> &'static str {
    match n {
        0 | 2 | 4 | 6 | 8 => "even-low",
        1 | 3 | 5 | 7 | 9 => "odd-low",
        _ => "big",
    }
}

fn main() {
    pyrust::print(&parity(2));
    pyrust::print(&parity(7));
    pyrust::print(&parity(42));
}
