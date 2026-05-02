fn main() {
    let mut xs = pyrust::list![1, 2, 3];
    xs[0] = 99;
    xs[2] = xs[0] + xs[1];
    pyrust::print(&xs);
}
