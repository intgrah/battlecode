struct Cell {
    row: i64,
    col: i64,
    weight: i64,
}

fn main() {
    let r = 2;
    let c = 5;
    let cell = Cell { row: r, col: c, weight: 100 };
    pyrust::print(&cell.row);
    pyrust::print(&cell.col);
    pyrust::print(&cell.weight);
}
