//! Mirror of Python's `random` module. The pyrust translator emits
//! `import random` for `use pyrust::random` and `random.X(...)` for
//! `random::X(...)` calls.

use rand::seq::IndexedRandom;

pub fn choice<T: Clone>(items: &[T]) -> T {
    let mut rng = rand::rng();
    items.choose(&mut rng).cloned().expect("choice on empty")
}

pub fn randint(low: i64, high: i64) -> i64 {
    use rand::RngExt;
    rand::rng().random_range(low..=high)
}

pub fn seed(s: u64) {
    // Native Rust seeding uses a thread-local rand-rng; our `choice`
    // uses `rand::rng()` (auto-seeded). This is a no-op on the native
    // side. For deterministic native bots, supply your own `StdRng`.
    let _ = s;
}
