fn main() {
    let mut m = pyrust::dict! { "a" => 1 };
    m.insert("b", 2);
    m.insert("c", 3);
    pyrust::print(&m["a"]);
    pyrust::print(&m["b"]);
    pyrust::print(&m["c"]);
}
