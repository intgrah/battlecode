//! pyrust DSL macros. Each macro:
//!
//! - Expands at the Rust call site to the natural Rust expression
//!   (zero-cost, no allocation overhead beyond what plain Rust would
//!   incur).
//! - The pyrust translator recognizes the macro's path and emits the
//!   matching Python expression directly. The translator never inspects
//!   types: the macro name carries the language's intended semantics.
//!
//! Macros are exposed under module paths in `lib.rs`, so callers write
//! `pyrust::vec::push!(v, x)`, `pyrust::iter::sum!(xs)`, etc. The
//! `__pyrust_*` underscore-prefixed names below are implementation
//! details — the path-qualified surface is the public API.

// ---- Result / Option propagation ----

/// `pyrust::result::try_!(expr)` — propagate the failure value out of
/// the enclosing function. Used in place of Rust's `?` operator on
/// `Option<E>` (the pyrust convention for "may fail with reason E").
///
/// Rust expansion: if `expr` is `Some(rej)`, `return Some(rej)`. If
/// `None`, fall through.
///
/// Python emission: `_r = expr; if _r is not None: return _r`.
#[macro_export]
macro_rules! __pyrust_try {
    ($e:expr) => {
        match $e {
            ::std::option::Option::Some(__rej) => {
                return ::std::option::Option::Some(__rej);
            }
            ::std::option::Option::None => {}
        }
    };
}

// ---- iter::* (deterministic iteration over Vec / sorted) ----

/// Sum of an iterable's elements. Iterable must be an ordered
/// collection (Vec, slice, range, etc.) — never a HashSet/HashMap.
#[macro_export]
macro_rules! __pyrust_iter_sum {
    ($it:expr) => {
        $it.iter().copied().sum::<i64>()
    };
}

/// `min(xs)` — returns `Option<T>`; `None` for an empty iterable.
#[macro_export]
macro_rules! __pyrust_iter_min {
    ($it:expr) => {
        $it.iter().copied().min()
    };
}

/// `max(xs)` — returns `Option<T>`.
#[macro_export]
macro_rules! __pyrust_iter_max {
    ($it:expr) => {
        $it.iter().copied().max()
    };
}

/// `min_by_key(xs, |x| key)` — returns `Option<T>`. Caller is
/// responsible for the key being globally unique to avoid
/// iteration-order dependence on ties.
#[macro_export]
macro_rules! __pyrust_iter_min_by {
    ($it:expr, |$x:ident| $key:expr) => {
        $it.iter().min_by_key(|$x| $key).copied()
    };
}

/// `max_by_key(xs, |x| key)` — same as `min_by` but maximised.
#[macro_export]
macro_rules! __pyrust_iter_max_by {
    ($it:expr, |$x:ident| $key:expr) => {
        $it.iter().max_by_key(|$x| $key).copied()
    };
}

// ---- vec::* (ordered, mutable list) ----

#[macro_export]
macro_rules! __pyrust_vec_push {
    ($v:expr, $x:expr) => {
        $v.push($x)
    };
}

/// Pop the last element. Returns `Option<T>` — `None` on empty.
/// Translator emits `(v.pop() if v else None)` for Python parity.
#[macro_export]
macro_rules! __pyrust_vec_pop {
    ($v:expr) => {
        $v.pop()
    };
}

#[macro_export]
macro_rules! __pyrust_vec_clear {
    ($v:expr) => {
        $v.clear()
    };
}

// ---- set::* (HashSet / BTreeSet — point ops only, NEVER iterated) ----

#[macro_export]
macro_rules! __pyrust_set_add {
    ($s:expr, $x:expr) => {
        $s.insert($x)
    };
}

#[macro_export]
macro_rules! __pyrust_set_contains {
    ($s:expr, $x:expr) => {
        $s.contains(&$x)
    };
}

#[macro_export]
macro_rules! __pyrust_set_remove {
    ($s:expr, $x:expr) => {
        $s.remove(&$x)
    };
}

// ---- dict::* (HashMap / BTreeMap — point ops only) ----

#[macro_export]
macro_rules! __pyrust_dict_insert {
    ($m:expr, $k:expr, $v:expr) => {
        $m.insert($k, $v)
    };
}

#[macro_export]
macro_rules! __pyrust_dict_contains {
    ($m:expr, $k:expr) => {
        $m.contains_key(&$k)
    };
}

#[macro_export]
macro_rules! __pyrust_dict_get {
    ($m:expr, $k:expr) => {
        $m.get(&$k).copied()
    };
    ($m:expr, $k:expr, $default:expr) => {
        $m.get(&$k).copied().unwrap_or($default)
    };
}

#[macro_export]
macro_rules! __pyrust_dict_remove {
    ($m:expr, $k:expr) => {
        $m.remove(&$k)
    };
}

// ---- string::* ----

/// Reset a `String` to empty. Rust calls `clear()`; Python assigns
/// `s = ""` because Python strings are immutable.
#[macro_export]
macro_rules! __pyrust_string_clear {
    ($s:expr) => {
        $s.clear()
    };
}

// ---- cast::* ----

#[macro_export]
macro_rules! __pyrust_cast_int {
    ($x:expr) => {
        ($x) as i64
    };
}

#[macro_export]
macro_rules! __pyrust_cast_float {
    ($x:expr) => {
        ($x) as f64
    };
}
