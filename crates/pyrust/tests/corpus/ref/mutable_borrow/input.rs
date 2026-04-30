fn add_one(v: &mut pyrust::List<i64>) {
    v.append(1);
}

fn main() {
    let mut xs = pyrust::list![10, 20];
    add_one(&mut xs);
    add_one(&mut xs);
    pyrust::print(&xs);
}
