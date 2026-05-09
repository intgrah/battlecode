use pyrust::PyStr;

fn main() {
    let s = "hello, world";
    if s.startswith("hello") {
        pyrust::print(&"hi-prefix");
    }
    if s.endswith("world") {
        pyrust::print(&"world-suffix");
    }
    if !s.startswith("xyz") {
        pyrust::print(&"no xyz");
    }
}
