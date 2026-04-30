fn main() {
    let xs = pyrust::list![1, 2, 3, 4];
    let squares = pyrust::comprehension!(x * x; for x in &xs);
    pyrust::print(&squares);
}
