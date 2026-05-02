fn main() {
    let m = pyrust::dict_comprehension!(x => x * x; for x in pyrust::range!(1, 4));
    pyrust::print(&m[&1]);
    pyrust::print(&m[&2]);
    pyrust::print(&m[&3]);
}
