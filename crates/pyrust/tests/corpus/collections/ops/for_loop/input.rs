fn main() {
    let xs = pyrust::list![1, 2, 3, 4];
    let mut total = 0;
    for x in &xs {
        total = total + x;
    }
    pyrust::print(&total);
}
