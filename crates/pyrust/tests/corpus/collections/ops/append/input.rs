fn main() {
    let mut xs = pyrust::list![1, 2];
    xs.append(3);
    xs.append(4);
    pyrust::print(&xs);
}
