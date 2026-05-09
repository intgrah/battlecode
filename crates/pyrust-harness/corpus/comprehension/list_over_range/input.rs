fn main() {
    let cubes = pyrust::comprehension!(i * i * i; for i in pyrust::range!(1, 5));
    pyrust::print(&cubes);
}
