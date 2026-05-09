fn main() {
    let xs = pyrust::list![10, 20, 30];
    if xs.contains(&20) {
        pyrust::print(&"found 20");
    }
    if !xs.contains(&99) {
        pyrust::print(&"99 missing");
    }
}
