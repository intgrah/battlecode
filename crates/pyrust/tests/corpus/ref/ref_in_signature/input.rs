use pyrust::PyStr;

fn shout(s: &str) -> String {
    s.upper()
}

fn main() {
    let greeting = "hello";
    pyrust::print(&shout(greeting));
}
