fn main() {
    let xs = pyrust::list![3, 1, 4, 1, 5, 9, 2, 6];
    pyrust::print(&pyrust::sorted(&xs));
}
