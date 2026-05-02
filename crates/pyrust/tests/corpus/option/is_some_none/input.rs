fn main() {
    let a: Option<i64> = Some(7);
    let b: Option<i64> = None;
    pyrust::print(&a.is_some());
    pyrust::print(&a.is_none());
    pyrust::print(&b.is_some());
    pyrust::print(&b.is_none());
}
