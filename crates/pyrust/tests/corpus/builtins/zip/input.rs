fn main() {
    let xs = pyrust::list![1, 2, 3];
    let ys = pyrust::list![10, 20, 30];
    for (x, y) in pyrust::zip(&xs, &ys) {
        pyrust::print(&(x + y));
    }
}
