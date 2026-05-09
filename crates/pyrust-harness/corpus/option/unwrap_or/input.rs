fn lookup(found: bool) -> Option<i64> {
    if found { Some(99) } else { None }
}

fn main() {
    pyrust::print(&lookup(true).unwrap_or(0));
    pyrust::print(&lookup(false).unwrap_or(-1));
}
