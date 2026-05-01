//! Mirror of Python's `random` module — bit-exact.
//!
//! The pyrust translator emits `import random` for `use pyrust::random` and
//! `random.X(...)` for `random::X(...)` calls. For the audit goal
//! (v55-native and v55-translated-Python producing identical replays),
//! the underlying PRNG and every consumer (`choice`, `randint`, `random`,
//! `choices`, `shuffle`, `getrandbits`) must match CPython byte-for-byte.
//!
//! The CPython algorithm is fully specified:
//!   - Mersenne Twister MT19937 as the core 32-bit generator.
//!   - `Random.seed(n)` derives the MT state via `init_by_array` over the
//!     32-bit limbs of `n` (positive form, with the sign-bit handling
//!     CPython documents).
//!   - `getrandbits(k)` reads `ceil(k/32)` 32-bit words and trims to k bits.
//!   - `_randbelow(n)` uses reject sampling on `getrandbits(bit_length(n))`.
//!   - `choice`, `randint`, `shuffle` all build on `_randbelow`.
//!   - `random()` is `(a >> 5) * 67108864 + (b >> 6)` then `* (1.0 / 2^53)`,
//!     where `a` and `b` are two consecutive 32-bit MT outputs.
//!
//! This module implements all of those exactly. The free functions operate
//! on a process-local default `Random` (analogous to Python's
//! `random._inst`); concrete bots construct `Random::new(seed)` per unit.

use std::cell::RefCell;

const MT_N: usize = 624;
const MT_M: usize = 397;
const MATRIX_A: u32 = 0x9908_b0df;
const UPPER_MASK: u32 = 0x8000_0000;
const LOWER_MASK: u32 = 0x7fff_ffff;

/// CPython-compatible Mersenne Twister 19937. Each `Random` instance owns
/// its own state.
#[derive(Clone)]
pub struct Random {
    mt: [u32; MT_N],
    index: usize,
}

impl Random {
    /// Construct a `Random` and seed it with `seed`. Mirrors
    /// `random.Random(seed)` in Python.
    #[must_use]
    pub fn new(seed: i64) -> Self {
        let mut r = Self {
            mt: [0; MT_N],
            index: MT_N,
        };
        r.seed(seed);
        r
    }

    /// CPython `Random.seed(n)` for an integer `n`. The integer is
    /// converted to its absolute value's little-endian 32-bit limb array
    /// (CPython does the same — Python signs are absorbed into magnitude
    /// for seeding) and fed to `init_by_array`.
    pub fn seed(&mut self, seed: i64) {
        let mag = seed.unsigned_abs();
        // Limbs in little-endian, dropping trailing zero limbs but keeping
        // at least one. Matches CPython's `_PyLong_AsByteArray` + reshape.
        let mut limbs: Vec<u32> = Vec::new();
        let mut x = mag;
        while x > 0 {
            limbs.push(x as u32);
            x >>= 32;
        }
        if limbs.is_empty() {
            limbs.push(0);
        }
        self.init_by_array(&limbs);
    }

    /// Standard MT19937 `init_by_array` (Matsumoto/Nishimura reference). Same
    /// constants as CPython's `_random.Random` C module.
    fn init_by_array(&mut self, key: &[u32]) {
        self.init_genrand(19650218);
        let mut i = 1usize;
        let mut j = 0usize;
        let k = MT_N.max(key.len());
        for _ in 0..k {
            let prev = self.mt[i - 1];
            self.mt[i] = (self.mt[i] ^ ((prev ^ (prev >> 30)).wrapping_mul(1664525)))
                .wrapping_add(key[j])
                .wrapping_add(j as u32);
            i += 1;
            j += 1;
            if i >= MT_N {
                self.mt[0] = self.mt[MT_N - 1];
                i = 1;
            }
            if j >= key.len() {
                j = 0;
            }
        }
        for _ in 0..(MT_N - 1) {
            let prev = self.mt[i - 1];
            self.mt[i] = (self.mt[i] ^ ((prev ^ (prev >> 30)).wrapping_mul(1566083941)))
                .wrapping_sub(i as u32);
            i += 1;
            if i >= MT_N {
                self.mt[0] = self.mt[MT_N - 1];
                i = 1;
            }
        }
        self.mt[0] = 0x8000_0000;
        self.index = MT_N;
    }

    fn init_genrand(&mut self, seed: u32) {
        self.mt[0] = seed;
        for i in 1..MT_N {
            let prev = self.mt[i - 1];
            self.mt[i] = (1812433253u32.wrapping_mul(prev ^ (prev >> 30))).wrapping_add(i as u32);
        }
        self.index = MT_N;
    }

    /// Return one 32-bit word from the MT stream.
    fn genrand_uint32(&mut self) -> u32 {
        if self.index >= MT_N {
            for i in 0..(MT_N - MT_M) {
                let y = (self.mt[i] & UPPER_MASK) | (self.mt[i + 1] & LOWER_MASK);
                let mag = if y & 1 == 1 { MATRIX_A } else { 0 };
                self.mt[i] = self.mt[i + MT_M] ^ (y >> 1) ^ mag;
            }
            for i in (MT_N - MT_M)..(MT_N - 1) {
                let y = (self.mt[i] & UPPER_MASK) | (self.mt[i + 1] & LOWER_MASK);
                let mag = if y & 1 == 1 { MATRIX_A } else { 0 };
                // Reference C: `mt[i] = mt[i + (M - N)] ^ ...`. With usize
                // we rewrite as `i - (N - M)`, which is the same value
                // because the loop range guarantees `i >= N - M`.
                self.mt[i] = self.mt[i - (MT_N - MT_M)] ^ (y >> 1) ^ mag;
            }
            let y = (self.mt[MT_N - 1] & UPPER_MASK) | (self.mt[0] & LOWER_MASK);
            let mag = if y & 1 == 1 { MATRIX_A } else { 0 };
            self.mt[MT_N - 1] = self.mt[MT_M - 1] ^ (y >> 1) ^ mag;
            self.index = 0;
        }
        let mut y = self.mt[self.index];
        self.index += 1;
        // Tempering.
        y ^= y >> 11;
        y ^= (y << 7) & 0x9d2c_5680;
        y ^= (y << 15) & 0xefc6_0000;
        y ^= y >> 18;
        y
    }

    /// CPython `Random.getrandbits(k)`: produce a non-negative integer with
    /// `k` random bits, reading `ceil(k/32)` 32-bit words and trimming the
    /// top word to `k mod 32` bits.
    pub fn getrandbits(&mut self, k: u32) -> u128 {
        assert!(k > 0 && k <= 128, "getrandbits k must be in 1..=128");
        let words = k.div_ceil(32) as usize;
        let mut out: u128 = 0;
        for i in 0..words {
            let mut w = self.genrand_uint32();
            if i == words - 1 {
                let bits_in_top = k - 32 * (words as u32 - 1);
                w >>= 32 - bits_in_top;
            }
            out |= (w as u128) << (32 * i);
        }
        out
    }

    /// CPython `Random._randbelow(n)`: a uniform integer in `[0, n)` via
    /// reject sampling on `getrandbits(bit_length(n))`.
    pub fn randbelow(&mut self, n: u128) -> u128 {
        assert!(n > 0, "randbelow on n=0");
        let k = 128 - n.leading_zeros();
        loop {
            let r = self.getrandbits(k);
            if r < n {
                return r;
            }
        }
    }

    /// CPython `Random.random()`: a 53-bit float in [0, 1).
    pub fn random(&mut self) -> f64 {
        let a = self.genrand_uint32() >> 5; // 27 bits
        let b = self.genrand_uint32() >> 6; // 26 bits
        (a as f64 * 67108864.0 + b as f64) * (1.0 / 9007199254740992.0)
    }

    /// CPython `Random.randint(a, b)`: uniform integer in `[a, b]` (inclusive).
    pub fn randint(&mut self, a: i64, b: i64) -> i64 {
        assert!(a <= b, "randint requires a <= b");
        let span = (b - a) as u128 + 1;
        a + self.randbelow(span) as i64
    }

    /// CPython `Random.choice(seq)`: uniform pick from a non-empty slice.
    pub fn choice<'a, T>(&mut self, seq: &'a [T]) -> &'a T {
        assert!(!seq.is_empty(), "choice on empty");
        &seq[self.randbelow(seq.len() as u128) as usize]
    }

    /// CPython `Random.shuffle(x)`: in-place Fisher–Yates using `_randbelow`.
    pub fn shuffle<T>(&mut self, x: &mut [T]) {
        let n = x.len();
        for i in (1..n).rev() {
            let j = self.randbelow((i + 1) as u128) as usize;
            x.swap(i, j);
        }
    }

    /// CPython `Random.choices(population, weights, k)`. With `weights = None`,
    /// CPython uses `population[floor(random() * n)]` per draw — not
    /// `_randbelow` — so we mirror that. Otherwise build cumulative weights
    /// and `bisect_right` per draw using `random() * total`.
    pub fn choices<'a, T>(
        &mut self,
        population: &'a [T],
        weights: Option<&[f64]>,
        k: usize,
    ) -> Vec<&'a T> {
        let n = population.len();
        assert!(n > 0, "choices on empty population");
        if weights.is_none() {
            let n_f = n as f64;
            return (0..k)
                .map(|_| {
                    let idx = (self.random() * n_f).floor() as usize;
                    &population[idx.min(n - 1)]
                })
                .collect();
        }
        let weights = weights.unwrap();
        assert_eq!(weights.len(), n, "choices weights length mismatch");
        let mut cum = Vec::with_capacity(n);
        let mut acc = 0.0f64;
        for &w in weights {
            acc += w;
            cum.push(acc);
        }
        let total = *cum.last().expect("non-empty");
        assert!(total > 0.0, "choices weights sum must be positive");
        (0..k)
            .map(|_| {
                let r = self.random() * total;
                // bisect_right semantics: first cum[i] > r.
                let mut lo = 0;
                let mut hi = n;
                while lo < hi {
                    let mid = (lo + hi) / 2;
                    if r < cum[mid] {
                        hi = mid;
                    } else {
                        lo = mid + 1;
                    }
                }
                &population[lo]
            })
            .collect()
    }
}

thread_local! {
    /// Process-local default RNG used by the free `random.X(...)` shim
    /// functions, mirroring CPython's `random._inst`. Initialised lazily
    /// from a fixed seed so behaviour is reproducible if no `seed()` call
    /// has happened; bots that want their own deterministic stream
    /// construct `Random::new(my_id)` directly.
    static DEFAULT: RefCell<Random> = RefCell::new(Random::new(0));
}

pub fn seed(s: i64) {
    DEFAULT.with(|r| r.borrow_mut().seed(s));
}

pub fn random() -> f64 {
    DEFAULT.with(|r| r.borrow_mut().random())
}

pub fn randint(a: i64, b: i64) -> i64 {
    DEFAULT.with(|r| r.borrow_mut().randint(a, b))
}

pub fn choice<T: Clone>(items: &[T]) -> T {
    DEFAULT.with(|r| r.borrow_mut().choice(items).clone())
}

pub fn shuffle<T>(items: &mut [T]) {
    DEFAULT.with(|r| r.borrow_mut().shuffle(items));
}

pub fn getrandbits(k: u32) -> u128 {
    DEFAULT.with(|r| r.borrow_mut().getrandbits(k))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Reference values from CPython 3.12: `random.Random(42)` then
    /// `[r.getrandbits(32) for _ in range(4)]`.
    #[test]
    fn cpython_seed_42_first_four_words() {
        let mut r = Random::new(42);
        let xs = [
            r.getrandbits(32),
            r.getrandbits(32),
            r.getrandbits(32),
            r.getrandbits(32),
        ];
        assert_eq!(
            xs,
            [2_746_317_213_u128, 478_163_327, 107_420_369, 3_184_935_163]
        );
    }

    /// `random.Random(0).random()` in CPython 3.12.
    #[test]
    fn cpython_seed_0_random() {
        let mut r = Random::new(0);
        let v = r.random();
        // CPython: 0.8444218515250481
        assert!((v - 0.8444218515250481).abs() < 1e-15);
    }

    /// `random.Random(123).choice(['a'..'e'])` x5 in CPython.
    #[test]
    fn cpython_seed_123_choice() {
        let mut r = Random::new(123);
        let items = ['a', 'b', 'c', 'd', 'e'];
        let picks: Vec<char> = (0..5).map(|_| *r.choice(&items)).collect();
        assert_eq!(picks, vec!['a', 'c', 'a', 'd', 'c']);
    }

    /// `random.Random(123).randint(0, 99)` x5 in CPython.
    #[test]
    fn cpython_seed_123_randint() {
        let mut r = Random::new(123);
        let picks: Vec<i64> = (0..5).map(|_| r.randint(0, 99)).collect();
        assert_eq!(picks, vec![6, 34, 11, 98, 52]);
    }

    /// `random.Random(123).shuffle(list(range(10)))` in CPython.
    #[test]
    fn cpython_seed_123_shuffle() {
        let mut r = Random::new(123);
        let mut xs: Vec<i32> = (0..10).collect();
        r.shuffle(&mut xs);
        assert_eq!(xs, vec![8, 7, 5, 9, 2, 3, 6, 1, 4, 0]);
    }

    /// `random.Random(123).choices(['a','b','c'], k=5)` (uniform) in CPython.
    #[test]
    fn cpython_seed_123_choices_uniform() {
        let mut r = Random::new(123);
        let items = ['a', 'b', 'c'];
        let picks: Vec<char> = r.choices(&items, None, 5).into_iter().copied().collect();
        assert_eq!(picks, vec!['a', 'a', 'b', 'a', 'c']);
    }

    /// `random.Random(123).choices(['a','b','c'], weights=[1,5,2], k=5)` in CPython.
    #[test]
    fn cpython_seed_123_choices_weighted() {
        let mut r = Random::new(123);
        let items = ['a', 'b', 'c'];
        let weights = [1.0, 5.0, 2.0];
        let picks: Vec<char> = r
            .choices(&items, Some(&weights), 5)
            .into_iter()
            .copied()
            .collect();
        assert_eq!(picks, vec!['a', 'a', 'b', 'a', 'c']);
    }
}
