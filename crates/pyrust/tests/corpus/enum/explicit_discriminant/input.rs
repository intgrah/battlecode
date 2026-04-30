enum HttpStatus {
    Ok = 200,
    NotFound = 404,
    ServerError = 500,
}

fn main() {
    let s = HttpStatus::NotFound;
    pyrust::print(&"ok");
}
