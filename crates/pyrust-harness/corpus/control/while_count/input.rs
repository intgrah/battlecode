fn main() {
    let mut i = 0;
    while i < 4 {
        pyrust::print(&i);
        i = i + 1;
    }
}
