fn classify(n: i64) -> i64 {
    if n < 0 {
        return -1;
    }
    if n == 0 {
        return 0;
    }
    1
}

fn main() {
    pyrust::print(&classify(-5));
    pyrust::print(&classify(0));
    pyrust::print(&classify(7));
}
