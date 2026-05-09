fn main() {
    let mut i = 0;
    loop {
        if i >= 3 {
            break;
        }
        pyrust::print(&i);
        i = i + 1;
    }
}
