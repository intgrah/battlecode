fn name(n: i64) -> &'static str {
    match n {
        0 => "zero",
        1 => "one",
        _ => "many",
    }
}

fn main() {
    pyrust::print(&name(0));
    pyrust::print(&name(1));
    pyrust::print(&name(7));
}
