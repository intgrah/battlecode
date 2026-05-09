fn greet(prefix: Option<&str>, name: &str) {
    let p = prefix.unwrap_or("hello");
    pyrust::print(&p);
    pyrust::print(&name);
}

fn main() {
    greet(Some("hi"), "alice");
    greet(None, "bob");
}
