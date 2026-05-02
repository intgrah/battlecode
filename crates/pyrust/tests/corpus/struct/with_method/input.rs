struct Counter {
    n: i64,
}

impl Counter {
    fn increment(&mut self) {
        self.n = self.n + 1;
    }

    fn value(&self) -> i64 {
        self.n
    }
}

fn main() {
    let mut c = Counter { n: 10 };
    c.increment();
    c.increment();
    c.increment();
    pyrust::print(&c.value());
}
