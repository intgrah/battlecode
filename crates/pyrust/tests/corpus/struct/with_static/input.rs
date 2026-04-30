struct Point {
    x: i64,
    y: i64,
}

impl Point {
    fn origin() -> Self {
        Self { x: 0, y: 0 }
    }
}

fn main() {
    let o = Point::origin();
    pyrust::print(&o.x);
    pyrust::print(&o.y);
}
