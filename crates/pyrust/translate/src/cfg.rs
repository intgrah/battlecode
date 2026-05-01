//! Compile-time configuration evaluator for `#[cfg(...)]` attributes and
//! `cfg!(...)` macro invocations.
//!
//! Mirrors `cargo`'s convention:
//! - `debug_assertions` is set by default (matches `cargo build`).
//! - `--cfg NAME` sets a flag; `--cfg NAME=false` clears one; `--release`
//!   sugar clears `debug_assertions`.
//!
//! Predicates: `cfg(name)`, `cfg(not(predicate))`, `cfg(any(p, ...))`,
//! `cfg(all(p, ...))`. Key-value form `cfg(key = "value")` is parsed but
//! treated as truthy iff `key=value` was passed on the CLI.

use std::collections::HashMap;

use proc_macro2::Span;
use syn::spanned::Spanned;

#[derive(Debug, Clone, Default)]
pub struct CfgEnv {
    /// Boolean flags. Unset names evaluate to false.
    flags: HashMap<String, bool>,
    /// Key=value pairs (e.g. `target_os = "linux"`). Set explicitly via
    /// `--cfg key=value`. `cfg(key = "v")` matches iff `flags_kv[key] == "v"`.
    kv: HashMap<String, String>,
    /// Project-wide sum-type enum registry. Key is the Python module path
    /// the enum lives in (e.g. `builder.tasks._policy`). Value is a map of
    /// `EnumName` → list of variant names. Built by the `--dir` driver
    /// during pre-scan; used by `emit_use` to import variant dataclasses
    /// alongside the enum type itself.
    pub sum_enum_registry: HashMap<String, HashMap<String, Vec<String>>>,
    /// Project-wide trait registry: trait name → (`ItemTrait` def, Python
    /// module path of the trait's source file). Lets `emit_struct` fold
    /// the trait's default-method bodies into the concrete class, and
    /// auto-import any free functions the body references from the
    /// trait's defining module.
    pub trait_registry: HashMap<String, (syn::ItemTrait, String)>,
    /// Method names that we know are field accessors by convention —
    /// at least one `impl X for Struct` in the workspace has `fn <name>`
    /// where `Struct` also has a `<name>` field. The translator emits
    /// `obj.<name>()` calls as `obj.<name>` (attribute access) for these
    /// names, bypassing the field-shadowing problem in folded trait
    /// default bodies (where `ra_ap` can't see through the generic).
    pub field_accessor_names: std::collections::HashSet<String>,
    /// Names of types/traits carrying `#[pyrust::transparent]`. Found by a
    /// syntactic walk of the workspace's `.rs` files. Translator drops
    /// imports of these names and erases their variant constructors
    /// (`Foo::None` → `None`, `Foo::Bar(x)` → `x`).
    pub transparent_def_names: std::collections::HashSet<String>,
    /// Names of types carrying `#[pyrust::exception]`. The struct emitter
    /// adds `Exception` to the type's Python base list so `raise X` works.
    pub exception_def_names: std::collections::HashSet<String>,
    /// Names of types carrying `#[pyrust::context_manager]`. The struct
    /// emitter adds `__enter__`/`__exit__` methods, and `let _g = T::CTOR(..)`
    /// inside a block translates to `with T(..) as _g:` wrapping the rest.
    pub context_manager_def_names: std::collections::HashSet<String>,
    /// Workspace-wide `#[pyrust::inline]` literal-RHS consts: name →
    /// Python literal text. Single-segment ident references resolve
    /// directly to the literal (CPython LOAD_CONST instead of
    /// LOAD_GLOBAL). Conflicting names (same name, different literal
    /// across files) are absent from this map.
    pub inline_consts: std::collections::HashMap<String, String>,
    /// Workspace-wide `#[pyrust::inline]` single-expression functions
    /// and `&self` methods, keyed by function name. Call sites that
    /// resolve to one of these get the body substituted in place of
    /// the call (parameter ↔ argument with walrus binding for
    /// non-atomic args). Same conflict policy as `inline_consts`:
    /// duplicate names with different bodies drop from the map.
    pub inline_fns: std::collections::HashMap<String, InlineFn>,
}

/// A single-expression function or `&self` method registered as
/// inlinable via `#[pyrust::inline]`. Stored at file pre-scan; consumed
/// by the call-site emit path.
#[derive(Debug, Clone)]
pub struct InlineFn {
    /// Parameter names in order, NOT including `self`.
    pub params: Vec<String>,
    /// True iff the function takes `&self` as its first arg.
    pub has_self: bool,
    /// The single-expression body (the tail expression of `{ expr }`,
    /// or the bare expression if the source uses `=> expr` form).
    pub body: syn::Expr,
}

impl CfgEnv {
    /// Default environment: `debug_assertions` is set, nothing else.
    #[must_use]
    pub fn debug() -> Self {
        let mut env = Self::default();
        env.flags.insert("debug_assertions".into(), true);
        env
    }

    /// Parse a single `--cfg` argument. Forms:
    /// - `name` → flags[name] = true
    /// - `name=true` / `name=false` → flags[name] = bool
    /// - `name="value"` or `name=value` → kv[name] = value, flags[name] = true
    pub fn apply_cfg_arg(&mut self, arg: &str) -> Result<(), String> {
        let (name, value) = match arg.split_once('=') {
            None => (arg.trim(), None),
            Some((k, v)) => (k.trim(), Some(v.trim())),
        };
        if name.is_empty() {
            return Err(format!("--cfg arg has empty name: {arg:?}"));
        }
        match value {
            None => {
                self.flags.insert(name.into(), true);
            }
            Some("true") => {
                self.flags.insert(name.into(), true);
            }
            Some("false") => {
                self.flags.insert(name.into(), false);
            }
            Some(v) => {
                let unquoted = v.trim_matches('"').to_string();
                self.kv.insert(name.into(), unquoted);
                self.flags.insert(name.into(), true);
            }
        }
        Ok(())
    }

    #[must_use]
    pub fn is_set(&self, name: &str) -> bool {
        self.flags.get(name).copied().unwrap_or(false)
    }

    #[must_use]
    pub fn kv_matches(&self, name: &str, value: &str) -> bool {
        self.kv.get(name).is_some_and(|v| v == value)
    }

    /// Evaluate a `cfg(...)` predicate inside a `#[cfg(...)]` attribute.
    pub fn eval_meta(&self, meta: &syn::Meta) -> Result<bool, String> {
        match meta {
            // `cfg(name)` — single ident => flag set?
            syn::Meta::Path(p) => {
                let name = path_ident(p).ok_or_else(|| {
                    format!("cfg path must be a single ident: {}", path_to_string(p))
                })?;
                Ok(self.is_set(&name))
            }
            // `cfg(key = "value")` — explicit kv match
            syn::Meta::NameValue(nv) => {
                let key = path_ident(&nv.path)
                    .ok_or_else(|| "cfg name=value: name must be a single ident".to_string())?;
                let value = expr_to_string_lit(&nv.value)?;
                Ok(self.kv_matches(&key, &value))
            }
            // `cfg(not(...))`, `cfg(any(...))`, `cfg(all(...))`
            syn::Meta::List(list) => {
                let kind = path_ident(&list.path).ok_or_else(|| {
                    format!(
                        "cfg combinator must be a single ident: {}",
                        path_to_string(&list.path)
                    )
                })?;
                let inner = parse_meta_list(&list.tokens)?;
                match kind.as_str() {
                    "not" => {
                        if inner.len() != 1 {
                            return Err(format!(
                                "cfg(not(...)) takes one predicate, got {}",
                                inner.len()
                            ));
                        }
                        Ok(!self.eval_meta(&inner[0])?)
                    }
                    "all" => {
                        for m in &inner {
                            if !self.eval_meta(m)? {
                                return Ok(false);
                            }
                        }
                        Ok(true)
                    }
                    "any" => {
                        for m in &inner {
                            if self.eval_meta(m)? {
                                return Ok(true);
                            }
                        }
                        Ok(false)
                    }
                    other => Err(format!("unknown cfg combinator: {other}")),
                }
            }
        }
    }

    /// True iff every `#[cfg(predicate)]` attribute on `attrs` evaluates true
    /// (i.e. the item should be kept). An item with no `#[cfg]` attrs is kept.
    pub fn item_enabled(&self, attrs: &[syn::Attribute]) -> Result<bool, String> {
        for attr in attrs {
            if !attr.path().is_ident("cfg") {
                continue;
            }
            let meta = parse_cfg_arg(attr)?;
            if !self.eval_meta(&meta)? {
                return Ok(false);
            }
        }
        Ok(true)
    }
}

fn path_ident(p: &syn::Path) -> Option<String> {
    p.get_ident().map(std::string::ToString::to_string)
}

fn path_to_string(p: &syn::Path) -> String {
    p.segments
        .iter()
        .map(|s| s.ident.to_string())
        .collect::<Vec<_>>()
        .join("::")
}

fn expr_to_string_lit(e: &syn::Expr) -> Result<String, String> {
    if let syn::Expr::Lit(syn::ExprLit {
        lit: syn::Lit::Str(s),
        ..
    }) = e
    {
        Ok(s.value())
    } else {
        Err("cfg name=value expects a string literal on the right".into())
    }
}

/// Parse the inner of `#[cfg(...)]` — i.e. the single `Meta` argument.
fn parse_cfg_arg(attr: &syn::Attribute) -> Result<syn::Meta, String> {
    match &attr.meta {
        syn::Meta::List(list) => {
            // `cfg(predicate)` — re-parse the inner tokens as a Meta.
            syn::parse2::<syn::Meta>(list.tokens.clone()).map_err(|e| {
                format!(
                    "cannot parse cfg predicate at {:?}: {e}",
                    span_str(list.span())
                )
            })
        }
        _ => Err("cfg attribute must be of the form #[cfg(...)]".into()),
    }
}

/// Parse a comma-separated list of `Meta` predicates from inside
/// `not(...)` / `all(...)` / `any(...)`.
fn parse_meta_list(tokens: &proc_macro2::TokenStream) -> Result<Vec<syn::Meta>, String> {
    use syn::parse::Parser;
    let parser = syn::punctuated::Punctuated::<syn::Meta, syn::Token![,]>::parse_terminated;
    parser
        .parse2(tokens.clone())
        .map(|p| p.into_iter().collect())
        .map_err(|e| format!("cannot parse cfg predicate list: {e}"))
}

fn span_str(_s: Span) -> String {
    "<span>".into()
}

#[cfg(test)]
mod tests {
    use super::*;
    use syn::parse_quote;

    fn meta(s: proc_macro2::TokenStream) -> syn::Meta {
        syn::parse2(s).expect("parse meta")
    }

    #[test]
    fn debug_default_sets_debug_assertions() {
        let env = CfgEnv::debug();
        assert!(env.is_set("debug_assertions"));
        assert!(!env.is_set("release"));
        assert!(!env.is_set("nonexistent"));
    }

    #[test]
    fn cfg_arg_bool_forms() {
        let mut env = CfgEnv::default();
        env.apply_cfg_arg("foo").unwrap();
        env.apply_cfg_arg("bar=true").unwrap();
        env.apply_cfg_arg("baz=false").unwrap();
        assert!(env.is_set("foo"));
        assert!(env.is_set("bar"));
        assert!(!env.is_set("baz"));
    }

    #[test]
    fn cfg_arg_kv_form() {
        let mut env = CfgEnv::default();
        env.apply_cfg_arg("target_os=linux").unwrap();
        env.apply_cfg_arg("opt_level=\"3\"").unwrap();
        assert!(env.kv_matches("target_os", "linux"));
        assert!(env.kv_matches("opt_level", "3"));
        assert!(!env.kv_matches("target_os", "macos"));
        // KV form also marks the flag as set.
        assert!(env.is_set("target_os"));
    }

    #[test]
    fn cfg_arg_release_clears_debug() {
        let mut env = CfgEnv::debug();
        env.apply_cfg_arg("debug_assertions=false").unwrap();
        assert!(!env.is_set("debug_assertions"));
    }

    #[test]
    fn eval_path_predicate() {
        let mut env = CfgEnv::default();
        env.apply_cfg_arg("foo").unwrap();
        let m = meta(quote::quote!(foo));
        assert!(env.eval_meta(&m).unwrap());
        let m = meta(quote::quote!(missing));
        assert!(!env.eval_meta(&m).unwrap());
    }

    #[test]
    fn eval_not() {
        let env = CfgEnv::debug();
        let m = meta(quote::quote!(not(debug_assertions)));
        assert!(!env.eval_meta(&m).unwrap());
        let m = meta(quote::quote!(not(release)));
        assert!(env.eval_meta(&m).unwrap());
    }

    #[test]
    fn eval_all() {
        let mut env = CfgEnv::debug();
        env.apply_cfg_arg("foo").unwrap();
        let m = meta(quote::quote!(all(debug_assertions, foo)));
        assert!(env.eval_meta(&m).unwrap());
        let m = meta(quote::quote!(all(debug_assertions, missing)));
        assert!(!env.eval_meta(&m).unwrap());
        // empty all() == true (vacuously)
        let m = meta(quote::quote!(all()));
        assert!(env.eval_meta(&m).unwrap());
    }

    #[test]
    fn eval_any() {
        let env = CfgEnv::debug();
        let m = meta(quote::quote!(any(debug_assertions, missing)));
        assert!(env.eval_meta(&m).unwrap());
        let m = meta(quote::quote!(any(missing1, missing2)));
        assert!(!env.eval_meta(&m).unwrap());
        // empty any() == false (vacuously)
        let m = meta(quote::quote!(any()));
        assert!(!env.eval_meta(&m).unwrap());
    }

    #[test]
    fn eval_kv_predicate() {
        let mut env = CfgEnv::default();
        env.apply_cfg_arg("target_os=linux").unwrap();
        let m = meta(quote::quote!(target_os = "linux"));
        assert!(env.eval_meta(&m).unwrap());
        let m = meta(quote::quote!(target_os = "macos"));
        assert!(!env.eval_meta(&m).unwrap());
    }

    #[test]
    fn eval_nested() {
        let env = CfgEnv::debug();
        let m = meta(quote::quote!(any(
            not(release),
            all(debug_assertions, missing)
        )));
        assert!(env.eval_meta(&m).unwrap());
    }

    #[test]
    fn item_enabled_kept_when_no_cfg_attrs() {
        let env = CfgEnv::debug();
        let attrs: Vec<syn::Attribute> = vec![];
        assert!(env.item_enabled(&attrs).unwrap());
    }

    #[test]
    fn item_enabled_kept_when_cfg_true() {
        let env = CfgEnv::debug();
        let attrs: Vec<syn::Attribute> = vec![parse_quote!(#[cfg(debug_assertions)])];
        assert!(env.item_enabled(&attrs).unwrap());
    }

    #[test]
    fn item_enabled_dropped_when_cfg_false() {
        let env = CfgEnv::debug();
        let attrs: Vec<syn::Attribute> = vec![parse_quote!(#[cfg(not(debug_assertions))])];
        assert!(!env.item_enabled(&attrs).unwrap());
    }

    #[test]
    fn item_enabled_release_drops_debug_assertions_block() {
        // simulate `--release`
        let mut env = CfgEnv::debug();
        env.apply_cfg_arg("debug_assertions=false").unwrap();
        let dbg_attrs: Vec<syn::Attribute> = vec![parse_quote!(#[cfg(debug_assertions)])];
        let rel_attrs: Vec<syn::Attribute> = vec![parse_quote!(#[cfg(not(debug_assertions))])];
        assert!(!env.item_enabled(&dbg_attrs).unwrap());
        assert!(env.item_enabled(&rel_attrs).unwrap());
    }

    #[test]
    fn item_enabled_multiple_cfg_attrs_all_must_pass() {
        let mut env = CfgEnv::debug();
        env.apply_cfg_arg("feature_a").unwrap();
        let attrs: Vec<syn::Attribute> = vec![
            parse_quote!(#[cfg(debug_assertions)]),
            parse_quote!(#[cfg(feature_a)]),
        ];
        assert!(env.item_enabled(&attrs).unwrap());
        let attrs: Vec<syn::Attribute> = vec![
            parse_quote!(#[cfg(debug_assertions)]),
            parse_quote!(#[cfg(missing)]),
        ];
        assert!(!env.item_enabled(&attrs).unwrap());
    }

    #[test]
    fn cfg_arg_empty_name_rejected() {
        let mut env = CfgEnv::default();
        assert!(env.apply_cfg_arg("=foo").is_err());
        assert!(env.apply_cfg_arg("").is_err());
    }
}
