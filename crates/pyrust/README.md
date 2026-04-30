# pyrust

Rust dialect that translates mechanically to Python.

Two components:

- **`pyrust`** (`shim/`) — Rust library. Macros, functions, types mirroring Python builtins. Bot code imports `pyrust::prelude::*`.
- **`pyrust-translate`** (`translate/`) — CLI that reads `.rs` written against the shim and emits `.py`.

The shim is the language reference: any code that compiles using `pyrust::prelude::*` only is guaranteed to translate.

## Layout

```
shim/        crate `pyrust` (Python builtins as Rust)
translate/   bin  `pyrust-translate`
harness/     bin  `pyrust-harness` (corpus verification)
runner/      generic Cargo project; harness drops corpus inputs into it
tests/
  corpus/<area>/<case>/{input.rs, expected.py, expected.out}
  check/<case>/{input.rs, expected_error.txt}
  errors/<case>/{input.rs, expected_error.txt}
```

`runner/` is a standalone Cargo project (its own workspace) so its build state does not collide with the main workspace's `target/` while the harness runs.

## CLI

```
pyrust-translate <input.rs> [-o output.py]
pyrust-translate --check <input.rs>
pyrust-translate --dir <src> -o <out>
```

## Verification

Each `tests/corpus/` case must pass four steps:

1. `pyrust-translate input.rs` byte-equals `expected.py`.
2. Run `input.rs` against the shim → stdout equals `expected.out`.
3. `python3 expected.py` → stdout equals `expected.out`.
4. `python3 <translated output>` → stdout equals `expected.out`.

Each `tests/check/` case must be rejected by `--check` with the matching `expected_error.txt` substring on stderr.

## Conventions

- Integer `/` between integers translates to Python `//`.
- `&`, `&mut`, `*`, `mut` are dropped in the Python output.
- `Vec<T>` / `[T; N]` → `list`; `HashMap` → `dict`; `HashSet` → `set`. Construct via `list!`, `dict!`, `set!`.
- Method names follow Python: `.append`, `.startswith`, etc.
- `String` and `&str` → `str`.
- `Self` → class name; `self` stays `self`.
- `pyrust::` prefix dropped at the call site; `&` arguments dropped.

## Rejection list (`--check`)

`unsafe`, lifetimes, traits, generics, ref-capturing closures, multi-statement closures, non-shim macros, async, raw pointers, `Box`/`Rc`/`Arc`/`RefCell`/`Cell`, pattern guards in `match`, `if let`/`while let`, enum variants with data, `dyn Trait`, `impl Trait` returns, direct `std::collections` use.
