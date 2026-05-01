//! pyrust DSL macros. Each macro:
//!
//! - Expands at the Rust call site to a natural Rust expression
//!   (zero-cost beyond what plain Rust would incur).
//! - The pyrust translator recognizes the macro's path and emits the
//!   matching Python expression directly. The translator NEVER inspects
//!   types or pattern-matches on bare method names: a macro path is the
//!   only signal it accepts. Anything not wrapped in a `pyrust::*!` macro
//!   passes through to Python literally.
//!
//! Macros are exposed under module paths in `lib.rs`, so callers write
//! `pyrust::vec::push!(v, x)`, `pyrust::sum!(xs)`, `pyrust::iter!(xs)`,
//! etc. The `__pyrust_*` underscore-prefixed names are implementation
//! details — the path-qualified surface is the public API.

// =====================================================================
// Top-level — language-level / control-flow / type-cast
// =====================================================================

/// `pyrust::try_!(expr)` — propagate Some(rej) out of an Option-shape
/// failure-result function. Replaces Rust's `?` on `Option<E>` (whose
/// native semantics are the wrong direction for this use).
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

/// `pyrust::unwrap!(opt)` — `opt.unwrap()`. Python: pass-through (the
/// Some-branch erasure means an Option<T> on Rust side becomes a bare
/// T or None on Python side; `.unwrap()` is a no-op on both, modulo a
/// runtime check).
#[macro_export]
macro_rules! __pyrust_unwrap {
    ($e:expr) => {
        $e.unwrap()
    };
}

/// `pyrust::expect!(opt, msg)` — `opt.expect(msg)`.
#[macro_export]
macro_rules! __pyrust_expect {
    ($e:expr, $m:expr) => {
        $e.expect($m)
    };
}

/// `pyrust::unwrap_or!(opt, default)` — `opt.unwrap_or(default)`.
#[macro_export]
macro_rules! __pyrust_unwrap_or {
    ($e:expr, $d:expr) => {
        $e.unwrap_or($d)
    };
}

/// `pyrust::is_some!(opt)` — Python `x is not None`.
#[macro_export]
macro_rules! __pyrust_is_some {
    ($e:expr) => {
        $e.is_some()
    };
}

/// `pyrust::is_none!(opt)` — Python `x is None`.
#[macro_export]
macro_rules! __pyrust_is_none {
    ($e:expr) => {
        $e.is_none()
    };
}

/// `pyrust::is_some_and!(opt, closure)`.
#[macro_export]
macro_rules! __pyrust_is_some_and {
    ($e:expr, $f:expr) => {
        $e.is_some_and($f)
    };
}

/// `pyrust::int!(x)` — Python `int(x)`.
#[macro_export]
macro_rules! __pyrust_cast_int {
    ($x:expr) => {
        ($x) as i64
    };
}

/// `pyrust::float!(x)` — Python `float(x)`.
#[macro_export]
macro_rules! __pyrust_cast_float {
    ($x:expr) => {
        ($x) as f64
    };
}

/// `pyrust::abs!(x)` — Python `abs(x)`.
#[macro_export]
macro_rules! __pyrust_abs {
    ($x:expr) => {
        ($x).abs()
    };
}

/// `pyrust::clone!(x)` — Rust `x.clone()`, Python `list(x)` (default
/// to Vec-shaped clone). For HashSet/HashMap clones use the
/// type-specific `pyrust::set::clone!` / `pyrust::dict::clone!`.
#[macro_export]
macro_rules! __pyrust_clone {
    ($x:expr) => {
        ($x).clone()
    };
}

/// `pyrust::drop!(x)` — Rust prelude `drop(x)`. In Python we emit
/// `x.drop()` so a user-defined `Drop` impl runs explicitly (the
/// translator emits `impl Drop for T` as `def drop(self)`).
#[macro_export]
macro_rules! __pyrust_drop {
    ($x:expr) => {
        ::std::mem::drop($x)
    };
}

/// `pyrust::round!(x)` — Python `round(x)` (returns float in Rust,
/// but Python's `round` on float returns int by default).
#[macro_export]
macro_rules! __pyrust_round {
    ($x:expr) => {
        ($x).round()
    };
}

/// `pyrust::sqrt!(x)` — Python `math.sqrt(x)`.
#[macro_export]
macro_rules! __pyrust_sqrt {
    ($x:expr) => {
        ($x).sqrt()
    };
}

/// `pyrust::floor!(x)` — Python `math.floor(x)`.
#[macro_export]
macro_rules! __pyrust_floor {
    ($x:expr) => {
        ($x).floor()
    };
}

/// `pyrust::ceil!(x)` — Python `math.ceil(x)`.
#[macro_export]
macro_rules! __pyrust_ceil {
    ($x:expr) => {
        ($x).ceil()
    };
}

// =====================================================================
// Iterator — chains / adapters / consumers (top-level macros)
// =====================================================================

/// `pyrust::iter!(xs)` — Rust `xs.iter()` adapter, Python no-op
/// (lists/tuples/dicts are already iterable).
#[macro_export]
macro_rules! __pyrust_iter {
    ($e:expr) => {
        $e.iter()
    };
}

/// `pyrust::into_iter!(xs)` — same as iter for translation purposes.
#[macro_export]
macro_rules! __pyrust_into_iter {
    ($e:expr) => {
        $e.into_iter()
    };
}

/// `pyrust::copied!(it)` — no-op in Python; in Rust elements become owned.
#[macro_export]
macro_rules! __pyrust_copied {
    ($e:expr) => {
        $e.copied()
    };
}

/// `pyrust::cloned!(it)` — no-op in Python; in Rust elements become owned.
#[macro_export]
macro_rules! __pyrust_cloned {
    ($e:expr) => {
        $e.cloned()
    };
}

/// `pyrust::collect!(it)` — terminal `.collect()` (target type
/// inferred from binding context). Python emits the inner expr (a
/// generator) directly when target is a list comprehension; for
/// HashSet/HashMap targets the bot author should use the right
/// ranges-comprehension equivalent.
#[macro_export]
macro_rules! __pyrust_collect {
    ($e:expr) => {
        $e.collect()
    };
}

/// `pyrust::enumerate!(it)` — Python `enumerate(it)`. Receiver must
/// already be an iterator (wrap collections in `pyrust::iter!` first).
#[macro_export]
macro_rules! __pyrust_enumerate {
    ($e:expr) => {
        $e.enumerate()
    };
}

/// `pyrust::zip!(a, b)` — Python `zip(a, b)`. Both args must be iterators.
#[macro_export]
macro_rules! __pyrust_zip {
    ($a:expr, $b:expr) => {
        $a.zip($b)
    };
}

/// `pyrust::take!(it, n)` — Python `itertools.islice(it, n)`.
#[macro_export]
macro_rules! __pyrust_take {
    ($e:expr, $n:expr) => {
        $e.take($n)
    };
}

/// `pyrust::skip!(it, n)` — Python `itertools.islice(it, n, None)`.
#[macro_export]
macro_rules! __pyrust_skip {
    ($e:expr, $n:expr) => {
        $e.skip($n)
    };
}

/// `pyrust::rev!(xs)` — Python `reversed(xs)`.
#[macro_export]
macro_rules! __pyrust_rev {
    ($e:expr) => {
        $e.rev()
    };
}

/// `pyrust::chain!(a, b)` — Python `itertools.chain(a, b)`.
#[macro_export]
macro_rules! __pyrust_chain {
    ($a:expr, $b:expr) => {
        $a.chain($b)
    };
}

/// `pyrust::map!(it, closure)` — Python `(body for x in it)`.
#[macro_export]
macro_rules! __pyrust_map {
    ($e:expr, $f:expr) => {
        $e.map($f)
    };
}

/// `pyrust::filter!(it, closure)` — Python `(x for x in it if pred)`.
#[macro_export]
macro_rules! __pyrust_filter {
    ($e:expr, $f:expr) => {
        $e.filter($f)
    };
}

/// `pyrust::filter_map!(it, closure)`.
#[macro_export]
macro_rules! __pyrust_filter_map {
    ($e:expr, $f:expr) => {
        $e.filter_map($f)
    };
}

/// `pyrust::find!(it, closure)`. Returns `Option<T>` (or whatever
/// `Iterator::find` would; bot author adds `.copied()` if needed).
#[macro_export]
macro_rules! __pyrust_find {
    ($e:expr, $f:expr) => {
        $e.find($f)
    };
}

/// `pyrust::position!(it, closure)` — `Iterator::position`. Returns
/// `Option<usize>`; Python emits `next((i for i, x in enumerate(it)
/// if pred(x)), None)`.
#[macro_export]
macro_rules! __pyrust_position {
    ($e:expr, $f:expr) => {
        $e.position($f)
    };
}

/// `pyrust::any!(it, closure)`. Receiver must be an iterator.
#[macro_export]
macro_rules! __pyrust_any {
    ($e:expr, $f:expr) => {
        $e.any($f)
    };
}

/// `pyrust::all!(it, closure)`. Receiver must be an iterator.
#[macro_export]
macro_rules! __pyrust_all {
    ($e:expr, $f:expr) => {
        $e.all($f)
    };
}

/// `pyrust::count!(it)` — Python `sum(1 for _ in it)` or `len(it)` if known-len.
#[macro_export]
macro_rules! __pyrust_count {
    ($e:expr) => {
        $e.count()
    };
}

/// `pyrust::next!(it)` — `Iterator::next` returning `Option<T>`.
/// Receiver must be an iterator (wrap collection in `pyrust::iter!`).
#[macro_export]
macro_rules! __pyrust_next {
    ($e:expr) => {
        $e.next()
    };
}

/// Sum of an iterator's elements. Receiver must already be an iterator.
/// Item type inferred from binding context.
#[macro_export]
macro_rules! __pyrust_iter_sum {
    ($it:expr) => {
        $it.sum()
    };
}

/// `pyrust::min!(it)` on an iterator — `min(...)`; `None` for empty.
#[macro_export]
macro_rules! __pyrust_iter_min {
    ($it:expr) => {
        $it.min()
    };
    ($a:expr, $b:expr) => {
        ($a).min($b)
    };
}

/// `pyrust::max!(it)` on an iterator — `max(...)`; `None` for empty.
#[macro_export]
macro_rules! __pyrust_iter_max {
    ($it:expr) => {
        $it.max()
    };
    ($a:expr, $b:expr) => {
        ($a).max($b)
    };
}

/// `pyrust::min_by!(it, closure)`. Receiver must be an iterator.
#[macro_export]
macro_rules! __pyrust_iter_min_by {
    ($it:expr, $f:expr) => {
        $it.min_by_key($f)
    };
}

/// `pyrust::max_by!(it, closure)`. Receiver must be an iterator.
#[macro_export]
macro_rules! __pyrust_iter_max_by {
    ($it:expr, $f:expr) => {
        $it.max_by_key($f)
    };
}

// =====================================================================
// Sort macros — operate on a Vec in place (no return value).
// =====================================================================

/// `pyrust::sort!(v)` — `v.sort()` ⟷ Python `v.sort()`.
#[macro_export]
macro_rules! __pyrust_sort {
    ($v:expr) => {
        $v.sort()
    };
}

/// `pyrust::sort_by_key!(v, closure)` ⟷ `v.sort(key=lambda x: key)`.
#[macro_export]
macro_rules! __pyrust_sort_by_key {
    ($v:expr, $f:expr) => {
        $v.sort_by_key($f)
    };
}

/// `pyrust::sorted!(xs)` — Python `sorted(xs)`. Useful as the
/// canonical "sort hash-collection contents" idiom.
#[macro_export]
macro_rules! __pyrust_sorted {
    ($xs:expr) => {{
        let mut __v: ::std::vec::Vec<_> = $xs.iter().copied().collect();
        __v.sort();
        __v
    }};
}

/// `pyrust::sorted_by_key!(xs, |x| key)` — Python `sorted(xs, key=...)`.
#[macro_export]
macro_rules! __pyrust_sorted_by_key {
    ($xs:expr, |$x:ident| $key:expr) => {{
        let mut __v: ::std::vec::Vec<_> = $xs.iter().copied().collect();
        __v.sort_by_key(|$x| $key);
        __v
    }};
}

// =====================================================================
// Free Python builtins
// =====================================================================

/// `pyrust::print!(args...)` — Python `print(args)`.
#[macro_export]
macro_rules! __pyrust_print {
    ($($a:expr),* $(,)?) => {
        println!("{}", format!("{:?}", ($($a,)*)))
    };
}

/// `pyrust::len!(x)` — Python `len(x)`.
#[macro_export]
macro_rules! __pyrust_len {
    ($x:expr) => {
        $x.len()
    };
}

// =====================================================================
// vec::* — Vec / List
// =====================================================================

/// `pyrust::vec::new!()` — Python `[]`. Rust expansion uses
/// `Default::default()` so it works for `Vec<T>`, `VecDeque<T>`, or any
/// other ordered collection the surrounding type context fixes.
#[macro_export]
macro_rules! __pyrust_vec_new {
    () => {
        ::std::default::Default::default()
    };
}

#[macro_export]
macro_rules! __pyrust_vec_push {
    ($v:expr, $x:expr) => {
        $v.push($x)
    };
}

/// `pyrust::vec::push_back!(v, x)` — Rust `VecDeque::push_back`, Python `v.append(x)`.
#[macro_export]
macro_rules! __pyrust_vec_push_back {
    ($v:expr, $x:expr) => {
        $v.push_back($x)
    };
}

/// `pyrust::vec::push_front!(v, x)` — Rust `VecDeque::push_front`,
/// Python `v.insert(0, x)`.
#[macro_export]
macro_rules! __pyrust_vec_push_front {
    ($v:expr, $x:expr) => {
        $v.push_front($x)
    };
}

/// `pyrust::vec::pop_front!(v)` — Rust `VecDeque::pop_front`, Python
/// `(v.pop(0) if v else None)`.
#[macro_export]
macro_rules! __pyrust_vec_pop_front {
    ($v:expr) => {
        $v.pop_front()
    };
}

/// `pyrust::vec::pop_back!(v)` — Rust `VecDeque::pop_back`, Python
/// `(v.pop() if v else None)`.
#[macro_export]
macro_rules! __pyrust_vec_pop_back {
    ($v:expr) => {
        $v.pop_back()
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

#[macro_export]
macro_rules! __pyrust_vec_len {
    ($v:expr) => {
        $v.len()
    };
}

#[macro_export]
macro_rules! __pyrust_vec_is_empty {
    ($v:expr) => {
        $v.is_empty()
    };
}

/// `pyrust::vec::contains!(v, x)` — the arg is passed verbatim to
/// `Vec::contains`. The bot's source typically has `&x` already, so
/// we don't add another reference.
#[macro_export]
macro_rules! __pyrust_vec_contains {
    ($v:expr, $x:expr) => {
        $v.contains($x)
    };
}

#[macro_export]
macro_rules! __pyrust_vec_extend {
    ($v:expr, $other:expr) => {
        $v.extend($other)
    };
}

// =====================================================================
// set::* — HashSet / BTreeSet
// =====================================================================

/// `pyrust::set::new!()` — Python `set()`. Rust expansion uses
/// `Default::default()` so it works for `HashSet<T>` / `BTreeSet<T>`.
#[macro_export]
macro_rules! __pyrust_set_new {
    () => {
        ::std::default::Default::default()
    };
}

#[macro_export]
macro_rules! __pyrust_set_add {
    ($s:expr, $x:expr) => {
        $s.insert($x)
    };
}

/// `pyrust::set::contains!(s, x)` — arg passed verbatim.
#[macro_export]
macro_rules! __pyrust_set_contains {
    ($s:expr, $x:expr) => {
        $s.contains($x)
    };
}

#[macro_export]
macro_rules! __pyrust_set_remove {
    ($s:expr, $x:expr) => {
        $s.remove(&$x)
    };
}

#[macro_export]
macro_rules! __pyrust_set_len {
    ($s:expr) => {
        $s.len()
    };
}

#[macro_export]
macro_rules! __pyrust_set_is_empty {
    ($s:expr) => {
        $s.is_empty()
    };
}

#[macro_export]
macro_rules! __pyrust_set_clear {
    ($s:expr) => {
        $s.clear()
    };
}

/// `pyrust::set::difference!(a, b)` — Python `a - b` (returns set).
#[macro_export]
macro_rules! __pyrust_set_difference {
    ($a:expr, $b:expr) => {
        $a.difference($b)
    };
}

// =====================================================================
// dict::* — HashMap / BTreeMap
// =====================================================================

/// `pyrust::dict::new!()` — Python `{}`. Rust expansion uses
/// `Default::default()` so it works for `HashMap<K,V>`, `BTreeMap<K,V>`,
/// or `serde_json::Map<String, Value>`.
#[macro_export]
macro_rules! __pyrust_dict_new {
    () => {
        ::std::default::Default::default()
    };
}

#[macro_export]
macro_rules! __pyrust_dict_insert {
    ($m:expr, $k:expr, $v:expr) => {
        $m.insert($k, $v)
    };
}

/// `pyrust::dict::contains!(m, k)` — arg passed verbatim.
#[macro_export]
macro_rules! __pyrust_dict_contains {
    ($m:expr, $k:expr) => {
        $m.contains_key($k)
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

#[macro_export]
macro_rules! __pyrust_dict_len {
    ($m:expr) => {
        $m.len()
    };
}

#[macro_export]
macro_rules! __pyrust_dict_is_empty {
    ($m:expr) => {
        $m.is_empty()
    };
}

#[macro_export]
macro_rules! __pyrust_dict_clear {
    ($m:expr) => {
        $m.clear()
    };
}

/// `pyrust::dict::items!(m)` — iteration as (k, v) pairs.
/// Rust: `m.iter()` yielding `(&K, &V)`.
/// Python: `m.items()` yielding `(K, V)`.
#[macro_export]
macro_rules! __pyrust_dict_items {
    ($m:expr) => {
        $m.iter()
    };
}

/// `pyrust::dict::keys!(m)`.
#[macro_export]
macro_rules! __pyrust_dict_keys {
    ($m:expr) => {
        $m.keys()
    };
}

/// `pyrust::dict::values!(m)`.
#[macro_export]
macro_rules! __pyrust_dict_values {
    ($m:expr) => {
        $m.values()
    };
}

// =====================================================================
// string::*
// =====================================================================

/// `pyrust::string::new!()` — Python `""`. Rust expansion uses
/// `Default::default()` for type-context inference (works for `String`).
#[macro_export]
macro_rules! __pyrust_string_new {
    () => {
        ::std::default::Default::default()
    };
}

/// Reset a `String` to empty. Rust calls `clear()`; Python assigns
/// `s = ""` because Python strings are immutable.
#[macro_export]
macro_rules! __pyrust_string_clear {
    ($s:expr) => {
        $s.clear()
    };
}

#[macro_export]
macro_rules! __pyrust_string_len {
    ($s:expr) => {
        $s.len()
    };
}

#[macro_export]
macro_rules! __pyrust_string_is_empty {
    ($s:expr) => {
        $s.is_empty()
    };
}

/// `pyrust::to_string!(x)` — Python `str(x)` or no-op when already str.
#[macro_export]
macro_rules! __pyrust_to_string {
    ($x:expr) => {
        $x.to_string()
    };
}
