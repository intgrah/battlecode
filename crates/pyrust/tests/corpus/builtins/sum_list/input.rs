fn main() {
    let xs = pyrust::list![1, 2, 3, 4, 5];
    pyrust::print(&pyrust::sum(&xs));
}
