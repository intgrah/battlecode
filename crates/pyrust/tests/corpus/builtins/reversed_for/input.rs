fn main() {
    let xs = pyrust::list![1, 2, 3];
    for x in &pyrust::reversed(&xs) {
        pyrust::print(x);
    }
}
