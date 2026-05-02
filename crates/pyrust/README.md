# pyrust

Rust dialect that translates mechanically to Python, plus a translator and corpus harness.

The point: write a bot in Rust, get a typechecked native build *and* a Python build that runs in the cambc sandbox. The two builds must produce byte-identical replays — that is the audit goal.

## Crates

- **`pyrust`** (`shim/`) — Rust library. Macros, functions, and types mirroring Python's stdlib so Rust code can be written in a Python idiom and still compile and run natively. Bot source imports `pyrust::prelude::*`.
- **`pyrust-translate`** (`translate/`) — CLI that reads `.rs` written against the shim and emits `.py`.
- **`pyrust-harness`** (`harness/`) — corpus verification driver. Translates each case, runs the Rust against the shim, runs both Pythons, diffs outputs.
- **`runner/`** — standalone Cargo project (its own workspace) the harness uses to compile and run each corpus input. Kept separate so its `target/` does not collide with the main workspace.

The shim is the language reference: any code that compiles against `pyrust::prelude::*` *and* nothing else is guaranteed to translate.

**For DSL conventions and the full macro surface, see [DSL.md](DSL.md).**

## What round-trips

Translation aims for parity with the natively executed Rust, not surface fidelity. The translator drops, rewrites, or specialises freely.

Supported on the Rust side:

- Functions, free items, top-level `const`, `static`, `thread_local!`.
- C-style enums (all unit variants) → `Enum` + `auto`.
- Sum-type enums (any variant has fields) → one `@dataclass` per variant + `type Foo = A | B` union alias. Variant constructors `Foo::Bar { x, y }` and `Foo::Bar(a, b)` translate to `FooBar(x=x, y=y)` / `FooBar(_0=a, _1=b)`. `match` and pattern bindings follow.
- Structs, methods, `Self::other`, `impl` blocks. Trait `impl`s for a struct are flattened into that struct's class.
- `if`, `if let`, `else if let`, `while let`, `let else`, `match` with guards, let-chains.
- Iterator methods: `map`, `filter`, `filter_map`, `find`, `find_map`, `position`, `any`, `all`, `min/max_by_key`, `sort_by_key`, `iter`, `iter_mut`, `collect`, `enumerate`, `zip`, `chain`.
- Single-expression closures (incl. `|(a, b)|`, `|&x|`, type-ascribed params).
- Range slices (`xs[a..b]`), `..`, inclusive ranges.
- `?`, `.unwrap()`, `Ok(x)`/`Some(x)` collapse where the Result/Option layer is the only error path.
- `serde_json::json!({...})` token tree → Python literal dict / list / scalar.
- `pyrust::random::Random` — bit-exact CPython 3.12 MT19937. Seven tests check `getrandbits`, `random()`, `randint`, `choice`, `shuffle`, `choices` (uniform and weighted).

Deliberately dropped during emit:

- `unsafe` (block and item), lifetimes, type generics on items, `Box`/`Rc`/`Arc`/`RefCell`/`Cell` wrappers.
- `Deref`/`DerefMut` impls (Python uses field access directly).
- Trait declarations and trait-bound generics (the methods come back via flattening).
- `cambc_bot!(Player);` (FFI macro, irrelevant to Python).
- `as` casts (`x as u32` → `x`); leading `&` on call arguments; `mut` bindings; `pyrust::` namespace.

## CLI

```
pyrust-translate <input.rs> [-o output.py]
pyrust-translate --check <input.rs>
pyrust-translate --dir <src> -o <out>
```

`--check` runs the syntactic-rejection pass without writing output. `--dir` walks a tree, skips files marked `#![cfg(not(pyrust))]` and emits one `.py` per `.rs`.

## Corpus

```
tests/
  corpus/<area>/<case>/{input.rs, expected.py, expected.out}
  check/<case>/{input.rs, expected_error.txt}
  errors/<case>/{input.rs, expected_error.txt}
```

Each `tests/corpus/` case must satisfy four equalities:

1. `pyrust-translate input.rs` byte-equals `expected.py`.
2. Run `input.rs` against the shim — stdout equals `expected.out`.
3. `python3 expected.py` — stdout equals `expected.out`.
4. `python3 <translator output>` — stdout equals `expected.out`.

Each `tests/check/` and `tests/errors/` case must be rejected with the matching substring on stderr.

Run the suite from the workspace root:

```
just pyrust-test
```

Adding a case: drop a folder under the appropriate area, write `input.rs`, run the harness once, paste the actual `expected.py` and `expected.out` from the failure diff, re-run.

## Conventions

- Integer `/` between integers → Python `//`.
- `&`, `&mut`, `*`, `mut` are dropped.
- `Vec<T>` / `[T; N]` → `list`; `HashMap` → `dict`; `HashSet` → `set`. Construct via `list!`, `dict!`, `set!`.
- Method names follow Python (`.append`, `.startswith`, …).
- `String` and `&str` → `str`.
- `Self` → class name; `self` stays `self`.
- `pyrust::` prefix dropped at the call site; `&` arguments dropped.

## Rejection list (`--check`)

`unsafe` blocks in expression position other than `unsafe { … }` strip, raw pointers, `async`, ref-capturing closures, multi-statement closures, non-shim macros (other than the recognised ones), pattern guards that bind by reference, `dyn Trait` outside the supported strip positions, `impl Trait` returns from associated methods.

## Status

- Corpus: ~90 cases passing across `corpus/`, `check/`, `errors/`.
- `pyrust::random` parity: 7 unit tests against CPython 3.12 reference output (verified: MT19937 sequence, `random()`, `randint`, `choice`, `shuffle`, `choices` uniform and weighted).
- `bots/rs/v55/` (94 `.py` files emitted) translates without errors. End-to-end replay parity between native Rust and translated Python is the next milestone.
