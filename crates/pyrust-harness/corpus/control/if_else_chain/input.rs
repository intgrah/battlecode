fn main() {
    let n = 7;
    if n < 5 {
        pyrust::print(&"small");
    } else if n < 10 {
        pyrust::print(&"medium");
    } else {
        pyrust::print(&"large");
    }
}
