fn main() {
    let name = "world";
    let count = 3;
    let s = format!("hello {name}, count={count}");
    pyrust::print(&s);
}
