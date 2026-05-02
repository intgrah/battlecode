fn main() {
    let a = 2;
    let b = 3;
    let c = 4;
    pyrust::print(&(a + b * c));
    pyrust::print(&((a + b) * c));
    pyrust::print(&(a * b + c));
    pyrust::print(&(a - b - c));
}
