use pyrust::PyStr;

fn main() {
    let s = "   padded   ";
    pyrust::print(&s.strip());
    pyrust::print(&s.lstrip());
    pyrust::print(&s.rstrip());
}
