fn pair(n: i64) -> (i64, i64) {
    (n, n * n)
}

fn main() {
    let (x, sq) = pair(7);
    pyrust::print(&x);
    pyrust::print(&sq);
}
