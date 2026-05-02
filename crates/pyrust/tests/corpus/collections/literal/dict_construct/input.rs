fn main() {
    let _ = pyrust::dict! { "a" => 1, "b" => 2, "c" => 3 };
    pyrust::print(&"ok");
}
