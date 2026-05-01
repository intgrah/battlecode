# pyrust DSL reference

How to write Rust that the translator can convert to Python, and what the
translator does and does not support. If you're touching a bot under
`bots/rs/v55/` or extending the translator, read this first.

## The single rule

> **Anything not wrapped in a `pyrust::*!` macro passes through to Python literally.**

The translator does not type-check, has no name resolution, does not know
which types live behind a method call. Everything it does is a syntactic
match on macro paths, item attributes, and a small whitelist of Rust
language constructs. There is no fallback for "I'll just emit `.foo()` and
hope Python has a `.foo()` method" — that's how `'list' object has no
attribute 'dedup'` happens.

If a Rust expression doesn't translate, it's because it isn't wrapped.
Wrap it. If a wrapper doesn't exist for what you need, add one to
`shim/src/dsl.rs` + `shim/src/lib.rs` + `translate/src/emit/expr.rs`,
and wire the migrator in `translate/src/bin/migrate_v55.rs`.

## Mental model

- Rust-side: every macro is zero-cost. `pyrust::sum!(xs)` expands to
  `xs.sum()`. Native compilation is identical to plain Rust.
- Python-side: each macro path has a hand-written emitter that produces
  the target idiom directly. `pyrust::sum!(xs)` becomes `sum(xs)`.

The macro path is the only signal the translator accepts. It will
**never** look at receiver types, method names, or trait impls to decide
how to translate.

## Composition

Iterator chains compose by **nesting macros**, not method-chaining:

```rust
// Rust idiom that does not translate:
xs.iter().map(|x| x * 2).filter(|y| *y > 0).sum::<i64>()

// pyrust DSL — nested function-call form:
pyrust::sum!(pyrust::filter!(
    pyrust::map!(pyrust::iter!(xs), |x| x * 2),
    |y| *y > 0
))
```

The outermost macro is the terminal operation. Each macro takes the
iterator/value as its first argument. This corresponds 1:1 with the
Python idiom (`sum(filter(map(...)))`).

Migrator (`migrate_v55`) does this rewrite automatically for the methods
listed in its `dsl_macro` table, so you can write `xs.iter()...` and
`just pyrust-translate` after running the migrator. New methods need a
new entry in that table.

## What the translator supports

### Rust language constructs (no DSL wrapping required)

- Functions, free items, top-level `const`, `static`, `thread_local!`.
- Structs (named-field only), `impl Foo`, `impl Trait for Foo`. Trait
  impls are flattened into the struct class.
- C-style enums (all unit variants) → `IntEnum`.
- Sum-type enums (variants with fields) → one `@dataclass` per variant
  + `type Foo = A | B` union alias.
- `if`, `if let`, `else if let`, `while`, `while let`, `for x in iter`,
  `let else`, `match` with guards, let-chains.
- Single-expression closures, including `|&x|`, `|(a, b)|`, type-ascribed
  params. **Multi-statement closures are not supported** — refactor to a
  named function or move logic into the surrounding expression.
- `?`, `.unwrap()`, `Ok(x)` / `Some(x)` constructor collapse — but only
  in tail positions; see "Option / Result handling" below for limits.
- `serde_json::json!({...})` macro bodies — the translator has a
  hand-written walker for the JSON-like syntax. Method calls inside
  `json!` bodies are migrated by `migrate_v55` (it descends via the same
  walker).
- `Vec<T>`, `[T; N]`, `HashMap`, `HashSet` literal types.

### Stripped during emit (write them, they vanish in Python)

- `unsafe` blocks, lifetimes, type generics on items.
- `Box<T>`, `Rc<T>`, `Arc<T>`, `RefCell<T>`, `Cell<T>`, `Cow<T>` — the
  wrappers are erased; the inner value is what survives.
- `Deref` / `DerefMut` impls (Python uses field access directly).
- Trait declarations (the methods come back via flattening).
- `cambc_bot!(Player);` (FFI macro, irrelevant to Python).
- `as` casts; leading `&` on call arguments; `mut` bindings; the
  `pyrust::` path prefix at call sites.

### Hard rejections (`--check` and the corpus error cases catch these)

- `dyn Trait` outside specific strip positions, raw pointers, `async`,
  ref-capturing closures, ref-binding pattern guards.
- Multi-statement closures.
- `impl Trait` returns from associated methods.

## DSL surface

All macros are exported from `pyrust::*` (top-level) or namespaced
under `pyrust::<type>::*`. Path matters — that's how the translator
identifies them.

### Top-level (free functions / language-level builtins)

| Macro | Rust | Python |
| --- | --- | --- |
| `pyrust::print!(args…)` | `println!(args…)` | `print(args…)` |
| `pyrust::len!(x)` | `x.len()` | `len(x)` |
| `pyrust::int!(x)` | `x as i64` | `int(x)` |
| `pyrust::float!(x)` | `x as f64` | `float(x)` |
| `pyrust::abs!(x)` | `x.abs()` | `abs(x)` |
| `pyrust::round!(x)` | `x.round()` | `round(x)` |
| `pyrust::sqrt!(x)` | `x.sqrt()` | `math.sqrt(x)` |
| `pyrust::floor!(x)` | `x.floor()` | `math.floor(x)` |
| `pyrust::ceil!(x)` | `x.ceil()` | `math.ceil(x)` |
| `pyrust::powf!(x, y)` | `x.powf(y)` | `(x ** y)` |
| `pyrust::powi!(x, y)` | `x.powi(y)` | `(x ** y)` |
| `pyrust::signum!(x)` | `x.signum()` | `((x > 0) - (x < 0))` |
| `pyrust::rem_euclid!(a, b)` | `a.rem_euclid(b)` | `a % b` |
| `pyrust::mul_add!(a, b, c)` | `a.mul_add(b, c)` | `(a * b + c)` |
| `pyrust::to_string!(x)` | `x.to_string()` | `str(x)` |
| `pyrust::clone!(x)` | `x.clone()` | `list(x)` (vec-shaped) |
| `pyrust::to_vec!(x)` | `x.to_vec()` | `list(x)` |
| `pyrust::into!(x)` | `x.into()` | identity |
| `pyrust::as_ref!(x)` / `as_mut!` | `x.as_ref()` / `x.as_mut()` | identity |
| `pyrust::drop!(x)` | `std::mem::drop(x)` | `x.drop()` (calls user Drop body) |

### Iterator chain (top-level)

These assume the receiver is already an iterator; wrap the source in
`pyrust::iter!` first if it isn't.

| Macro | Rust | Python |
| --- | --- | --- |
| `pyrust::iter!(xs)` | `xs.iter()` | identity |
| `pyrust::into_iter!(xs)` | `xs.into_iter()` | identity |
| `pyrust::copied!(it)` / `cloned!` | `.copied()` / `.cloned()` | identity |
| `pyrust::collect!(it)` | `it.collect()` (Vec) | `list(it)` |
| `pyrust::collect!(it, T)` | `it.collect::<T>()` | `list(it)` (T ignored) |
| `pyrust::map!(it, |x| body)` | `it.map(\|x\| body)` | `(body for x in it)` |
| `pyrust::map!(it, fn_ref)` | `it.map(fn_ref)` | `(fn_ref(__x) for __x in it)` |
| `pyrust::filter!(it, |x| pred)` | `it.filter(...)` | `(x for x in it if pred)` |
| `pyrust::filter_map!(it, |x| opt)` | `it.filter_map(...)` | `(__v for x in it if (__v := body) is not None)` |
| `pyrust::find!(it, |x| pred)` | `it.find(...)` | `next((x for ... if pred), None)` |
| `pyrust::find_map!(it, |x| opt)` | `it.find_map(...)` | similar |
| `pyrust::position!(it, |x| pred)` | `it.position(...)` | manual index loop |
| `pyrust::any!(it, |x| pred)` / `all!` | `it.any(...)` / `all(...)` | `any(...)` / `all(...)` |
| `pyrust::count!(it)` | `it.count()` | `sum(1 for _ in it)` |
| `pyrust::sum!(it)` | `it.sum()` | `sum(it)` |
| `pyrust::min!(it)` / `max!(it)` | `.min()` / `.max()` | `min(it, default=None)` etc. |
| `pyrust::min!(a, b)` / `max!(a, b)` | `a.min(b)` (pairwise) | `min(a, b)` |
| `pyrust::min_by!(it, |x| key)` / `max_by!` | `.min_by_key(...)` etc. | `min(it, key=lambda x: key)` |
| `pyrust::take!(it, n)` / `skip!(it, n)` | `.take(n)` / `.skip(n)` | `itertools.islice(...)` |
| `pyrust::rev!(it)` | `it.rev()` | `reversed(list(it))` |
| `pyrust::enumerate!(it)` | `it.enumerate()` | `enumerate(it)` |
| `pyrust::zip!(a, b)` | `a.zip(b)` | `zip(a, b)` |
| `pyrust::chain!(a, b)` | `a.chain(b)` | `itertools.chain(a, b)` |
| `pyrust::next!(it)` | `it.next()` | `next(it, None)` |
| `pyrust::sort!(v)` / `sort_by_key!(v, |x| key)` | `v.sort()` / `v.sort_by_key(...)` | `v.sort()` / `v.sort(key=lambda x: key)` |
| `pyrust::sorted!(it)` / `sorted_by_key!(it, |x| key)` | `Vec::from_iter(it).sort()` | `sorted(it[, key=...])` |

### Option / Result helpers

| Macro | Rust | Python |
| --- | --- | --- |
| `pyrust::is_some!(opt)` | `opt.is_some()` | `(x is not None)` |
| `pyrust::is_none!(opt)` | `opt.is_none()` | `(x is None)` |
| `pyrust::unwrap!(opt)` | `opt.unwrap()` | identity (Option layer erased) |
| `pyrust::expect!(opt, msg)` | `opt.expect(msg)` | identity (msg dropped) |
| `pyrust::unwrap_or!(opt, dflt)` | `opt.unwrap_or(dflt)` | `(x if x is not None else dflt)` |
| `pyrust::is_some_and!(opt, |x| pred)` | `opt.is_some_and(...)` | `(x is not None and pred(x))` |
| `pyrust::is_none_or!(opt, |x| pred)` | `opt.is_none_or(...)` | `(x is None or pred(x))` |
| **`pyrust::opt_map!(opt, |x| body)`** | `opt.map(...)` | `((lambda x: body)(opt) if opt is not None else None)` |
| `pyrust::opt_take!(field)` | `field.take()` | walrus + setattr to clear field |
| `pyrust::try_!(expr)` | `?` for Option-shape failure | early-return on Some |

### `pyrust::vec::*` — Vec / list

| Macro | Rust | Python |
| --- | --- | --- |
| `pyrust::vec::new!()` | `Vec::new()` | `[]` |
| `pyrust::vec::push!(v, x)` | `v.push(x)` | `v.append(x)` |
| `pyrust::vec::pop!(v)` | `v.pop()` | `(v.pop() if v else None)` |
| `pyrust::vec::push_back/front!`, `pop_back/front!` | VecDeque ops | list ops |
| `pyrust::vec::extend!(v, it)` | `v.extend(it)` | `v.extend(it)` |
| `pyrust::vec::contains!(v, x)` | `v.contains(x)` | `(x in v)` |
| `pyrust::vec::len!(v)` / `is_empty!` | `v.len()` / `v.is_empty()` | `len(v)` / `(not v)` |
| `pyrust::vec::clear!(v)` | `v.clear()` | `v.clear()` |
| `pyrust::vec::first!(v)` / `last!(v)` | `v.first()` / `.last()` | `(v[0] if v else None)` etc. |
| `pyrust::vec::dedup!(v)` | `v.dedup()` | rebuild list keeping non-consec-duplicates |
| `pyrust::vec::retain!(v, |x| pred)` | `v.retain(...)` | `v[:] = [x for x in v if pred]` |
| `pyrust::vec::reverse!(v)` | `v.reverse()` | `v.reverse()` |
| `pyrust::vec::truncate!(v, n)` | `v.truncate(n)` | `del v[n:]` |
| `pyrust::vec::fill!(v, x)` | `v.fill(x)` | broadcast assign |
| `pyrust::vec::swap_remove!(v, i)` | `v.swap_remove(i)` | manual swap+pop |
| `pyrust::vec::take!(obj.field)` | `std::mem::take(&mut obj.field)` | walrus + setattr |

### `pyrust::set::*` — HashSet / set

`new`, `clear`, `len`, `is_empty`, `contains`, `add`, `remove`,
`difference`, `clone`, `collect`. Use `set::collect!` (not the bare
`pyrust::collect!`) when the result type is HashSet — `collect!` emits
`list(...)` and will silently turn a set field into a list.

### `pyrust::dict::*` — HashMap / dict

`new`, `clear`, `len`, `is_empty`, `contains`, `get`, `insert`, `remove`,
`items`, `keys`, `values`, `collect`. **`dict::items!` is required when
iterating a HashMap to get (k, v) pairs** — the bare `pyrust::iter!`
emits `for x in d` (keys only) on the Python side. Same applies to
`dict::collect!` for HashMap rebuilds.

### `pyrust::string::*`

`new`, `clear`, `len`, `is_empty`. Strings are immutable in Python; the
translator handles writes via reassignment.

### `pyrust::time::*`

`now_ns!()` — monotonic clock for instrumentation. Rust:
`Instant`-relative-to-epoch nanoseconds via `OnceLock`. Python:
`time.perf_counter_ns()`. Used for debug-tree timing; values are
inherently non-deterministic and excluded from replay-parity checks.

### `pyrust::serde::*`

`array_mut!(value)` — `serde_json::Value::as_array_mut().unwrap()` on
Rust side, identity on Python (`Value` is just `dict` / `list`).

## Attribute markers

Three inert attributes the translator scans for. They compile to no-ops
on the Rust side; they steer Python emit.

### `#[pyrust::transparent]`

Mark an enum or struct as "wrapper, not a class". The translator drops
the wrapper:

- Unit variant `Foo::None` → Python `None`.
- 1-tuple variant `Foo::Var(x)` → Python `x`.
- 1-named-field variant `Foo::Var { f: x }` → Python `x`.

Used for Rust-side enums whose Python equivalent is a `A | B | None`
union — Python doesn't need the wrapper.

### `#[pyrust::exception]`

Mark a struct/enum as a Python exception. The emitted class gets
`Exception` in its base list so `raise` / `except` work.

### `#[pyrust::context_manager]`

Mark a struct as a Python `with`-block context manager. Effects:

1. `let _NAME = T::CTOR(args);` *inside a block* (where `T` is the
   marked type) becomes `with T(args) as _NAME:` and the **rest of the
   block becomes the indented body**. Multiple consecutive
   context-manager `let`s nest naturally.
2. The emitted Python class gets synthesised `__enter__(self): return
   self` and `__exit__(self, *exc): self.drop()`. The struct's `Drop`
   impl provides the body.
3. Inside a value-returning block expression
   `let path = { let _g = T::new(...); tail };`, the translator
   emits a `with` block, captures `tail` into `__block_value`, and
   evaluates to `__block_value`.

The constructor body (e.g. `push_scope`) runs at `__init__` time, **not**
at `__enter__` time. `with` semantics map onto: object creation pushes,
exit pops. This matches Rust's RAII `Scope` pattern with no gymnastics.

**Self-construction inside a non-`new` constructor**: when a method like
`Scope::new_timed` returns `Self { f: v, ... }`, the translator emits a
`__new__`-bypass + setattr chain instead of `Cls(f=v)` — calling
`Cls(...)` would re-trigger `__init__`'s side effects (e.g.
`push_scope`). The bypass: `__self = Cls.__new__(Cls); __self.f = v;
return __self`.

## Common gotchas

### `Iterator::map` vs `Option::map`

These are different methods that share a name in Rust. The translator
cannot tell them apart syntactically — receiver type info isn't
available. Use `pyrust::map!` for iterators, `pyrust::opt_map!` for
`Option<T>`. Mixing them up surfaces as `'int' object is not iterable`
(the iterator emit `for x in opt` runs `for x in <bare value>`).

### `HashMap` iteration

In Rust, `for (k, v) in &map` desugars to `for (k, v) in map.iter()`,
which yields `(&K, &V)` pairs. In Python, `for x in dict` yields keys
only. Use **`pyrust::dict::items!(map)`** to iterate `(k, v)` pairs on
both sides. Plain `pyrust::iter!(map)` translates to keys-only Python.

### `HashMap::collect` / `HashSet::collect`

The bare `pyrust::collect!(it)` always emits `list(...)` in Python. If
your binding type is `HashMap` or `HashSet`, use `pyrust::dict::collect!`
or `pyrust::set::collect!` respectively. Otherwise the field gets
re-typed at runtime and later `.add()` / `.items()` calls will fail.

### Enum variants in cambc

The cambc Python API uses `SCREAMING_SNAKE` (`Direction.NORTH`); the
Rust enum uses `PascalCase` (`Direction::North`). The cambc Python shim
adds PascalCase aliases via `_add_pascal_aliases` so both forms work.
Don't fight this — write Rust variants in PascalCase and the translation
just works.

### `Self { ... }` outside `new`

`Self { f: v }` is a Rust struct literal — pure field assignment, no
constructor call. In Python, `Cls(f=v)` calls `__init__` and re-runs its
side effects. The translator recognises `Self { ... }` in **method
return-tail** position and emits `__new__` + setattr instead.

If you write `let x = Self { f: v };` in a non-tail position inside a
non-`new` method that has `__init__` side effects, you may get a
double-init. Restructure to put `Self { ... }` at the function tail.

### Rust `?` on `Option`

The `?` operator propagates `None` early — `Some((x?, y?))` is `None` if
either inner is `None`. The translator's emit of `?` is **identity**
(it strips the `?` and pretends the layer is gone), so `?` on a
non-tail-position `Option` doesn't do early-return semantically. Either
fix the source by expanding to an explicit `if x.is_none() { ... }`
check, or avoid `?` outside of `Result` exception-shaped error paths.

### `mul_add` precision

`f64::mul_add(b, c)` is fused multiply-add. The translator emits
`(a * b + c)` with parens around `a` and `b` if their precedence is
below `Mul`. This is precise enough for the bot's heuristics; if you
need exact IEEE 754 fused rounding you have to write the Python yourself.

### Rust `Drop` execution order

Inside a `with`-mapped block, Rust's "drop in reverse declaration order
at end of block" maps cleanly to nested `with` blocks. **Do not** call
`pyrust::drop!(_g)` to release a context-manager guard early — the
translator's `with` block has no early-release. Use an inner
`{ ... block ... }` to scope the guard's lifetime instead.

## Adding a new DSL macro

1. **`shim/src/dsl.rs`**: write the macro as `__pyrust_<name>` with
   `#[macro_export]`. Body should expand to the natural Rust expression.
2. **`shim/src/lib.rs`**: re-export under the public path
   (`pub use crate::__pyrust_<name> as <name>`, possibly inside a
   `pub mod` for namespaced macros).
3. **`translate/src/emit/expr.rs`**: in `emit_pyrust_dsl`, add a
   `["<path>", "<components>"] => { ... }` arm that emits the Python
   form. Use `Prec::*` to handle operator precedence — `Emitted::atomic`
   is correct only when the result wraps in something or is a single
   token.
4. **`translate/src/bin/migrate_v55.rs`**: if the DSL macro replaces a
   bare Rust method call, add an entry to `dsl_macro` so the migrator
   rewrites existing call sites. Re-run `cargo run --bin migrate_v55 --
   bots/rs/v55/src` and review the diff.
5. **Test**: add a corpus case under `crates/pyrust/tests/corpus/<area>/`
   with `input.rs`, `expected.py`, `expected.out`. The harness verifies
   four-way parity.

## Adding a new Rust language construct

Avoid this. The DSL is designed so most extensions live as macros, not
language features. If you genuinely need a new pattern (e.g. a new kind
of pattern match), the translator emit lives in
`translate/src/emit/{stmt,expr,pat,item}.rs`. Add a corpus case first;
it forces you to specify the expected Python and catches edge cases the
implementation misses.
