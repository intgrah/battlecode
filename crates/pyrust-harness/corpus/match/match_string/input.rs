fn cardinal(s: &str) -> i64 {
    match s {
        "north" => 0,
        "east" => 1,
        "south" => 2,
        "west" => 3,
        _ => -1,
    }
}

fn main() {
    pyrust::print(&cardinal("north"));
    pyrust::print(&cardinal("east"));
    pyrust::print(&cardinal("nowhere"));
}
