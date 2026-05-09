fn main() {
    let xs = pyrust::list![1, 2, 3, 4, 5, 6];
    let evens_doubled = pyrust::comprehension!(x * 2; for x in &xs; if x % 2 == 0);
    pyrust::print(&evens_doubled);
}
