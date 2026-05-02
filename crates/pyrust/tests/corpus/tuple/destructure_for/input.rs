fn main() {
    let pairs = pyrust::list![(1, 10), (2, 20), (3, 30)];
    for (k, v) in &pairs {
        pyrust::print(&(k + v));
    }
}
