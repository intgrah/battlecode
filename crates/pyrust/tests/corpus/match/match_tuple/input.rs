fn quadrant(p: (i64, i64)) -> &'static str {
    match p {
        (0, 0) => "origin",
        (0, _) => "y-axis",
        (_, 0) => "x-axis",
        _ => "elsewhere",
    }
}

fn main() {
    pyrust::print(&quadrant((0, 0)));
    pyrust::print(&quadrant((0, 5)));
    pyrust::print(&quadrant((3, 0)));
    pyrust::print(&quadrant((1, 1)));
}
