fn main() {
    let a: Option<i64> = Some(3);
    let b: Option<i64> = None;
    if a == None {
        pyrust::print(&"a is none");
    } else {
        pyrust::print(&"a is some");
    }
    if b != None {
        pyrust::print(&"b is some");
    } else {
        pyrust::print(&"b is none");
    }
}
