fn main() {
    let m = pyrust::dict! { "alpha" => 1, "beta" => 2, "gamma" => 3 };
    pyrust::print(&m["beta"]);
}
