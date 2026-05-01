enum Shape {
    Circle { radius: i64 },
    Rect { width: i64, height: i64 },
    Square,
}

fn area(s: Shape) -> i64 {
    match s {
        Shape::Circle { radius } => 3 * radius * radius,
        Shape::Rect { width, height } => width * height,
        Shape::Square => 1,
    }
}

fn main() {
    pyrust::print(&area(Shape::Circle { radius: 4 }));
    pyrust::print(&area(Shape::Rect { width: 3, height: 5 }));
    pyrust::print(&area(Shape::Square));
}
