fn main() {
    let s = pyrust::set_comprehension!(x % 3; for x in pyrust::range!(20));
    pyrust::print(&s.len());
}
