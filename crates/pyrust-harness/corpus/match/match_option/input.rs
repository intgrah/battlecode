fn describe(opt: Option<i64>) -> &'static str {
    match opt {
        Some(0) => "zero",
        Some(_) => "non-zero",
        None => "nothing",
    }
}

fn main() {
    pyrust::print(&describe(Some(0)));
    pyrust::print(&describe(Some(7)));
    pyrust::print(&describe(None));
}
