//! Wrapper types around `Vec`/`HashMap`/`HashSet` exposing Python-shaped APIs.
//!
//! The shim insists on Python method names (`.append`, not `.push`; `.contains_key`
//! exists on `Dict` because Python's `in` on a dict checks keys). User code in the
//! pyrust dialect always uses these wrappers, never `Vec`/`HashMap`/`HashSet` directly
//! — the rejection list (Phase 17) enforces this.

use std::borrow::Borrow;
use std::collections::{HashMap, HashSet};
use std::fmt;
use std::hash::Hash;
use std::ops::{Index, IndexMut};

use crate::prelude::PyDisplay;

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct List<T>(pub Vec<T>);

impl<T> List<T> {
    #[must_use]
    pub const fn new() -> Self {
        Self(Vec::new())
    }

    pub fn append(&mut self, value: T) {
        self.0.push(value);
    }

    pub fn pop(&mut self) -> T {
        self.0.pop().expect("pop from empty list")
    }

    #[must_use]
    pub const fn len(&self) -> usize {
        self.0.len()
    }

    #[must_use]
    pub const fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    pub fn clear(&mut self) {
        self.0.clear();
    }
}

impl<T: PartialEq> List<T> {
    pub fn contains(&self, value: &T) -> bool {
        self.0.contains(value)
    }
}

impl<T> Index<usize> for List<T> {
    type Output = T;
    fn index(&self, i: usize) -> &T {
        &self.0[i]
    }
}

impl<T> IndexMut<usize> for List<T> {
    fn index_mut(&mut self, i: usize) -> &mut T {
        &mut self.0[i]
    }
}

impl<T> IntoIterator for List<T> {
    type Item = T;
    type IntoIter = std::vec::IntoIter<T>;
    fn into_iter(self) -> Self::IntoIter {
        self.0.into_iter()
    }
}

impl<'a, T> IntoIterator for &'a List<T> {
    type Item = &'a T;
    type IntoIter = std::slice::Iter<'a, T>;
    fn into_iter(self) -> Self::IntoIter {
        self.0.iter()
    }
}

impl<'a, T> IntoIterator for &'a mut List<T> {
    type Item = &'a mut T;
    type IntoIter = std::slice::IterMut<'a, T>;
    fn into_iter(self) -> Self::IntoIter {
        self.0.iter_mut()
    }
}

impl<T> FromIterator<T> for List<T> {
    fn from_iter<I: IntoIterator<Item = T>>(iter: I) -> Self {
        Self(Vec::from_iter(iter))
    }
}

impl<T> Extend<T> for List<T> {
    fn extend<I: IntoIterator<Item = T>>(&mut self, iter: I) {
        self.0.extend(iter);
    }
}

impl<T: PyDisplay> PyDisplay for List<T> {
    fn fmt_py(&self, f: &mut fmt::Formatter<'_>, repr: bool) -> fmt::Result {
        self.0.fmt_py(f, repr)
    }
}

#[derive(Clone, Debug, Default)]
pub struct Dict<K, V>(pub HashMap<K, V>);

impl<K, V> Dict<K, V> {
    #[must_use]
    pub fn new() -> Self {
        Self(HashMap::new())
    }

    #[must_use]
    pub fn len(&self) -> usize {
        self.0.len()
    }

    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    pub fn clear(&mut self) {
        self.0.clear();
    }
}

impl<K: Eq + Hash, V> Dict<K, V> {
    pub fn insert(&mut self, key: K, value: V) -> Option<V> {
        self.0.insert(key, value)
    }

    pub fn contains_key<Q>(&self, key: &Q) -> bool
    where
        K: Borrow<Q>,
        Q: ?Sized + Hash + Eq,
    {
        self.0.contains_key(key)
    }

    pub fn get<Q>(&self, key: &Q) -> Option<&V>
    where
        K: Borrow<Q>,
        Q: ?Sized + Hash + Eq,
    {
        self.0.get(key)
    }
}

impl<K, V, Q> Index<&Q> for Dict<K, V>
where
    K: Eq + Hash + Borrow<Q>,
    Q: ?Sized + Eq + Hash,
{
    type Output = V;
    fn index(&self, key: &Q) -> &V {
        &self.0[key]
    }
}

impl<'a, K, V> IntoIterator for &'a Dict<K, V> {
    type Item = (&'a K, &'a V);
    type IntoIter = std::collections::hash_map::Iter<'a, K, V>;
    fn into_iter(self) -> Self::IntoIter {
        self.0.iter()
    }
}

impl<K: PyDisplay, V: PyDisplay> PyDisplay for Dict<K, V> {
    fn fmt_py(&self, f: &mut fmt::Formatter<'_>, repr: bool) -> fmt::Result {
        self.0.fmt_py(f, repr)
    }
}

#[derive(Clone, Debug, Default)]
pub struct Set<T>(pub HashSet<T>);

impl<T> Set<T> {
    #[must_use]
    pub fn new() -> Self {
        Self(HashSet::new())
    }

    #[must_use]
    pub fn len(&self) -> usize {
        self.0.len()
    }

    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    pub fn clear(&mut self) {
        self.0.clear();
    }
}

impl<T: Eq + Hash> Set<T> {
    pub fn add(&mut self, value: T) {
        self.0.insert(value);
    }

    pub fn contains<Q>(&self, value: &Q) -> bool
    where
        T: Borrow<Q>,
        Q: ?Sized + Hash + Eq,
    {
        self.0.contains(value)
    }
}

impl<'a, T> IntoIterator for &'a Set<T> {
    type Item = &'a T;
    type IntoIter = std::collections::hash_set::Iter<'a, T>;
    fn into_iter(self) -> Self::IntoIter {
        self.0.iter()
    }
}

impl<T: PyDisplay> PyDisplay for Set<T> {
    fn fmt_py(&self, f: &mut fmt::Formatter<'_>, repr: bool) -> fmt::Result {
        self.0.fmt_py(f, repr)
    }
}
