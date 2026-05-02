fn main() {
    let xs = pyrust::list!["a", "b", "c"];
    for (i, x) in pyrust::enumerate(&xs) {
        pyrust::print(&i);
        pyrust::print(&x);
    }
}
