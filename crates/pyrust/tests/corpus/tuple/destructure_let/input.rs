fn main() {
    let (a, b, c) = (3, 5, 7);
    pyrust::print(&(a + b + c));
    let (x, _, z) = (100, 200, 300);
    pyrust::print(&(x + z));
}
