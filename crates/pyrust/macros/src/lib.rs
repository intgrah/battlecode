//! Proc-macro attributes recognised by `pyrust-translate`.
//!
//! These macros are no-ops at compile time — the attached items pass through
//! unchanged. Their purpose is to be visible to the translator when it walks
//! the source via `ra_ap_*`. The translator looks for the attribute path
//! `pyrust::transparent` on `enum` definitions and erases their variant
//! constructors in the emitted Python.

use proc_macro::TokenStream;

/// Mark an enum (or struct) as semantically transparent for translation.
///
/// On a Rust-only enum whose variants represent a Python `A | B | None`
/// union, applying `#[pyrust::transparent]` tells `pyrust-translate` to
/// drop the constructor wrapper:
///
/// - `Foo::None` (unit variant) → Python `None`.
/// - `Foo::Var(x)` (1-tuple variant) → Python `x`.
/// - `Foo::Var { f: x }` (1-named-field variant) → Python `x`.
///
/// The attribute itself is a no-op at compile time.
#[proc_macro_attribute]
pub fn transparent(_attr: TokenStream, item: TokenStream) -> TokenStream {
    item
}

/// Mark a struct or enum as an exception type. The translator emits the
/// corresponding Python class with `Exception` as a base, so `raise X` and
/// `except X` work as expected. No-op at compile time.
#[proc_macro_attribute]
pub fn exception(_attr: TokenStream, item: TokenStream) -> TokenStream {
    item
}
