enum Light {
    Red,
    Yellow,
    Green,
}

fn action(l: Light) -> &'static str {
    match l {
        Light::Red => "stop",
        Light::Yellow => "slow",
        Light::Green => "go",
    }
}

fn main() {
    pyrust::print(&action(Light::Red));
    pyrust::print(&action(Light::Yellow));
    pyrust::print(&action(Light::Green));
}
