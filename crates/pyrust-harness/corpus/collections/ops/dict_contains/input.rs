fn main() {
    let m = pyrust::dict! { "a" => 1, "b" => 2 };
    if m.contains_key(&"a") {
        pyrust::print(&"has a");
    }
    if !m.contains_key(&"z") {
        pyrust::print(&"no z");
    }
}
