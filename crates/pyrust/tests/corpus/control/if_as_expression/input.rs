fn main() {
    let a = 12;
    let b = 7;
    let m = if a > b { a } else { b };
    pyrust::print(&m);
}
