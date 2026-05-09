mod helper;

use crate::helper::{double, greet};

fn main() {
    pyrust::print(&double(7));
    greet("alice");
}
