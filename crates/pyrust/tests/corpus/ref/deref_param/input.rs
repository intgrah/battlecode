fn double(n: &i64) -> i64 {
    *n * 2
}

fn main() {
    let x = 7;
    pyrust::print(&double(&x));
}
