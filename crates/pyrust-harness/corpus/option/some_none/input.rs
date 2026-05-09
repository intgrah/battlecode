fn maybe(n: i64) -> Option<i64> {
    if n >= 0 { Some(n) } else { None }
}

fn main() {
    let a = maybe(5);
    let b = maybe(-1);
    pyrust::print(&a.unwrap());
    if b.is_none() {
        pyrust::print(&"none");
    }
}
