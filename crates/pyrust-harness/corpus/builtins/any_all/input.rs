fn main() {
    let truthy = pyrust::list![false, false, true];
    let allyes = pyrust::list![true, true, true];
    pyrust::print(&pyrust::any(&truthy));
    pyrust::print(&pyrust::all(&allyes));
    pyrust::print(&pyrust::any(&pyrust::list![false, false, false]));
}
