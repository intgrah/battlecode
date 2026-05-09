struct Point {
    x: i64,
    y: i64,
}

fn main() {
    let p = Point { x: 3, y: 4 };
    pyrust::print(&p.x);
    pyrust::print(&p.y);
}
