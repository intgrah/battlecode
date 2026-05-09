fn main() {
    let xs: pyrust::List<i64> = pyrust::list![1, 2, 3];
    pyrust::print(&xs);
    let m: pyrust::Dict<&str, i64> = pyrust::dict! { "a" => 1, "b" => 2 };
    pyrust::print(&m["b"]);
}
