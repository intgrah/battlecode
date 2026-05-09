use pyrust::PyStr;

fn main() {
    let s = "Hello";
    pyrust::print(&s.upper());
    pyrust::print(&s.lower());
}
