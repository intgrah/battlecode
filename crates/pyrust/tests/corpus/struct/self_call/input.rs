struct Point {
    x: i64,
    y: i64,
}

impl Point {
    fn at(n: i64) -> Self {
        Self { x: n, y: n }
    }

    fn doubled(&self) -> Self {
        Self::at(self.x * 2)
    }
}

fn main() {
    let p = Point::at(7);
    let q = p.doubled();
    pyrust::print(&q.x);
    pyrust::print(&q.y);
}
