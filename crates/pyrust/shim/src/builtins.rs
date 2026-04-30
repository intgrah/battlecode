//! Python-style builtin functions, mirroring `len`, `min`, `max`, `sum`, `abs`,
//! `sorted`, `reversed`, `any`, `all`, `enumerate`, `zip`.
//!
//! All take `&T` so that user call sites match the translator rule
//! "drop `pyrust::` prefix and `&` on arguments".

use crate::collections::{Dict, List, Set};

pub trait PyLen {
    fn py_len(&self) -> usize;
}

impl<T> PyLen for List<T> {
    fn py_len(&self) -> usize {
        self.len()
    }
}

impl<K, V> PyLen for Dict<K, V> {
    fn py_len(&self) -> usize {
        self.len()
    }
}

impl<T> PyLen for Set<T> {
    fn py_len(&self) -> usize {
        self.len()
    }
}

impl PyLen for str {
    fn py_len(&self) -> usize {
        // Python's `len(str)` counts code points, not bytes.
        self.chars().count()
    }
}

impl PyLen for String {
    fn py_len(&self) -> usize {
        self.chars().count()
    }
}

impl<T> PyLen for [T] {
    fn py_len(&self) -> usize {
        <[T]>::len(self)
    }
}

impl<T, const N: usize> PyLen for [T; N] {
    fn py_len(&self) -> usize {
        N
    }
}

pub fn len<T: PyLen + ?Sized>(value: &T) -> usize {
    value.py_len()
}

pub trait PyMin {
    type Item;
    fn py_min(&self) -> Self::Item;
    fn py_max(&self) -> Self::Item;
}

impl<T: Ord + Copy> PyMin for List<T> {
    type Item = T;
    fn py_min(&self) -> T {
        self.0
            .iter()
            .copied()
            .min()
            .expect("min() arg is an empty sequence")
    }
    fn py_max(&self) -> T {
        self.0
            .iter()
            .copied()
            .max()
            .expect("max() arg is an empty sequence")
    }
}

impl<T: Ord + Copy> PyMin for [T] {
    type Item = T;
    fn py_min(&self) -> T {
        self.iter()
            .copied()
            .min()
            .expect("min() arg is an empty sequence")
    }
    fn py_max(&self) -> T {
        self.iter()
            .copied()
            .max()
            .expect("max() arg is an empty sequence")
    }
}

impl<T: Ord + Copy, const N: usize> PyMin for [T; N] {
    type Item = T;
    fn py_min(&self) -> T {
        self.iter()
            .copied()
            .min()
            .expect("min() arg is an empty sequence")
    }
    fn py_max(&self) -> T {
        self.iter()
            .copied()
            .max()
            .expect("max() arg is an empty sequence")
    }
}

pub fn min<T: PyMin + ?Sized>(value: &T) -> T::Item {
    value.py_min()
}

pub fn max<T: PyMin + ?Sized>(value: &T) -> T::Item {
    value.py_max()
}

pub trait PySum {
    type Out;
    fn py_sum(&self) -> Self::Out;
}

impl<T> PySum for List<T>
where
    T: Copy + std::iter::Sum<T>,
{
    type Out = T;
    fn py_sum(&self) -> T {
        self.0.iter().copied().sum()
    }
}

impl<T> PySum for [T]
where
    T: Copy + std::iter::Sum<T>,
{
    type Out = T;
    fn py_sum(&self) -> T {
        self.iter().copied().sum()
    }
}

impl<T, const N: usize> PySum for [T; N]
where
    T: Copy + std::iter::Sum<T>,
{
    type Out = T;
    fn py_sum(&self) -> T {
        self.iter().copied().sum()
    }
}

pub fn sum<T: PySum + ?Sized>(value: &T) -> T::Out {
    value.py_sum()
}

pub trait PyAbs: Copy {
    fn py_abs(self) -> Self;
}

macro_rules! impl_abs {
    ($($t:ty),*) => { $(
        impl PyAbs for $t {
            fn py_abs(self) -> Self { self.abs() }
        }
    )* };
}
impl_abs!(i8, i16, i32, i64, i128, isize, f32, f64);

pub fn abs<T: PyAbs>(x: &T) -> T {
    (*x).py_abs()
}

pub trait PySorted {
    type Owned;
    fn py_sorted(&self) -> Self::Owned;
    fn py_reversed(&self) -> Self::Owned;
}

impl<T: Ord + Clone> PySorted for List<T> {
    type Owned = List<T>;
    fn py_sorted(&self) -> List<T> {
        let mut v = self.0.clone();
        v.sort();
        List(v)
    }
    fn py_reversed(&self) -> List<T> {
        let mut v = self.0.clone();
        v.reverse();
        List(v)
    }
}

pub fn sorted<T: PySorted + ?Sized>(value: &T) -> T::Owned {
    value.py_sorted()
}

pub fn reversed<T: PySorted + ?Sized>(value: &T) -> T::Owned {
    value.py_reversed()
}

pub fn any(value: &List<bool>) -> bool {
    value.0.iter().copied().any(|x| x)
}

pub fn all(value: &List<bool>) -> bool {
    value.0.iter().copied().all(|x| x)
}

pub fn enumerate<T: Clone>(value: &List<T>) -> impl Iterator<Item = (i64, T)> + '_ {
    value
        .0
        .iter()
        .cloned()
        .enumerate()
        .map(|(i, x)| (i as i64, x))
}

pub fn zip<'a, A: Clone, B: Clone>(
    a: &'a List<A>,
    b: &'a List<B>,
) -> impl Iterator<Item = (A, B)> + 'a {
    a.0.iter().cloned().zip(b.0.iter().cloned())
}

/// Extension trait giving `str` Python's string method names.
///
/// Only Python-only names live here; methods that already exist on `str` with
/// matching semantics (e.g. `replace`) are used directly.
pub trait PyStr {
    fn startswith(&self, prefix: &str) -> bool;
    fn endswith(&self, suffix: &str) -> bool;
    fn upper(&self) -> String;
    fn lower(&self) -> String;
    fn strip(&self) -> &str;
    fn lstrip(&self) -> &str;
    fn rstrip(&self) -> &str;
}

impl PyStr for str {
    fn startswith(&self, prefix: &str) -> bool {
        self.starts_with(prefix)
    }
    fn endswith(&self, suffix: &str) -> bool {
        self.ends_with(suffix)
    }
    fn upper(&self) -> String {
        self.to_uppercase()
    }
    fn lower(&self) -> String {
        self.to_lowercase()
    }
    fn strip(&self) -> &str {
        self.trim()
    }
    fn lstrip(&self) -> &str {
        self.trim_start()
    }
    fn rstrip(&self) -> &str {
        self.trim_end()
    }
}
