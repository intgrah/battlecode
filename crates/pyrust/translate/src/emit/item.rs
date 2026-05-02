use syn::spanned::Spanned;

use super::docstring;
use super::expr;
use super::stmt::{self, Tail};
use super::types::{self, Ty};
use super::writer::PyWriter;

pub const fn needs_leading_blank(item: &syn::Item) -> bool {
    matches!(
        item,
        syn::Item::Fn(_) | syn::Item::Struct(_) | syn::Item::Enum(_)
    )
}

pub fn produces_output(item: &syn::Item) -> bool {
    if matches!(item, syn::Item::Impl(_)) {
        return false;
    }
    // `mod foo;` produces no output (the file is translated separately).
    if let syn::Item::Mod(m) = item
        && m.content.is_none()
    {
        return false;
    }
    // Some `use` items are dropped (pyrust/std/core); others emit imports.
    if let syn::Item::Use(u) = item {
        let first = first_use_ident(&u.tree);
        return !matches!(first.as_deref(), Some("pyrust" | "std" | "core"));
    }
    // `cambc_bot!(MyBot);` only matters for the native-Rust cdylib build;
    // pyrust translation drops it silently.
    if let syn::Item::Macro(m) = item
        && let Some(name) = m.mac.path.get_ident().map(std::string::ToString::to_string)
        && name == "cambc_bot"
    {
        return false;
    }
    true
}

pub fn emit_item(w: &mut PyWriter, item: &syn::Item, file: &syn::File) -> Result<(), String> {
    match item {
        syn::Item::Fn(f) => emit_fn(w, f),
        syn::Item::Const(c) => emit_const(w, c),
        // Statics translate the same as consts at the module level (Python
        // doesn't distinguish — both are just module-scoped bindings).
        syn::Item::Static(s) => emit_static(w, s),
        syn::Item::Struct(s) => emit_struct(w, s, file),
        syn::Item::Enum(e) => emit_enum_with_file(w, e, file),
        // Impl blocks are folded into their target struct's class body.
        syn::Item::Impl(_) => Ok(()),
        syn::Item::Use(u) => emit_use(w, u),
        // `cambc_bot!(MyBot);` is a Rust-only cdylib export; drop on translation.
        syn::Item::Macro(m)
            if m.mac
                .path
                .segments
                .last()
                .map(|s| s.ident.to_string())
                .as_deref()
                == Some("cambc_bot") =>
        {
            Ok(())
        }
        // `thread_local! { static X: T = init; ... }` — Rust groups several
        // per-thread statics. Each unit runs in its own subinterpreter, so
        // module-level globals are the natural Python translation. Strip
        // the `RefCell<...>` wrapper (Python doesn't need it) and emit each
        // as a plain module-level binding.
        syn::Item::Macro(m) if m.mac.path.is_ident("thread_local") => emit_thread_local(w, &m.mac),
        // `pub type Foo = Bar;` — Python has `type Foo = Bar` (PEP 695)
        // since 3.12. Emit it directly.
        syn::Item::Type(t) => {
            let name = t.ident.to_string();
            let ty = types::type_to_python_str(&t.ty)
                .map_err(|e| w.err(t.ty.span(), format!("type alias: {e}")))?;
            w.line(&format!("type {name} = {ty}"));
            Ok(())
        }
        // Trait declarations don't have a direct Python analog (we lower
        // `impl Trait for Type` into the concrete class). Emit a stub
        // class so cross-module `use crate::unit::Unit;` imports keep
        // working — Python doesn't need the methods, the concrete classes
        // already carry them via the flattened impls.
        // Traits don't get a Python class. Their default methods are
        // folded into the concrete struct's class via `emit_struct` (which
        // consults `cfg.trait_registry`). Emitting an empty trait class
        // would also clash with field-name shadowing in implementors.
        syn::Item::Trait(_) => Ok(()),
        // `extern "C"` / `extern crate` etc. — irrelevant to Python.
        syn::Item::ExternCrate(_) | syn::Item::ForeignMod(_) => Ok(()),
        // `mod foo;` declares a sibling file; --dir mode translates it
        // separately. Inline `mod foo { ... }` has no Python analog.
        syn::Item::Mod(m) => {
            if m.content.is_some() {
                return Err(w.err(
                    m.span(),
                    "inline `mod foo { ... }` not supported (only external `mod foo;`)",
                ));
            }
            // `mod foo;` declares a sibling submodule. We only need a
            // Python import for it when this file actually references
            // `foo::xxx` somewhere in expression position — eagerly
            // importing every declared submodule is what triggers
            // circular-init failures (`builder.tasks.__init__` → all
            // children → back through `chain_routing` etc).
            let name = m.ident.to_string();
            if !w.is_module_referenced(&name) {
                return Ok(());
            }
            if w.is_root_module() {
                w.line(&format!("import {name}"));
            } else {
                w.line(&format!("from . import {name}"));
            }
            Ok(())
        }
        other => Err(w.err(
            other.span(),
            format!("unsupported item: {}", item_kind(other)),
        )),
    }
}

fn emit_use(w: &mut PyWriter, u: &syn::ItemUse) -> Result<(), String> {
    if let Some(first) = first_use_ident(&u.tree)
        && matches!(first.as_str(), "std" | "core" | "serde" | "serde_json")
    {
        return Ok(());
    }
    // `use pyrust::<stdlib>` mirrors Python imports for the modules the
    // shim mirrors (random, math, etc.). Strip the `pyrust::` prefix and
    // emit a regular Python import.
    if let Some(first) = first_use_ident(&u.tree)
        && first == "pyrust"
        && let syn::UseTree::Path(p) = &u.tree
    {
        return emit_pyrust_use(w, &p.tree);
    }
    let mut prefix = Vec::new();
    let mut tree = &u.tree;
    while let syn::UseTree::Path(p) = tree {
        let ident = p.ident.to_string();
        // `crate::` is the project root in Rust; in our flat-module Python
        // output it's empty.
        if !(prefix.is_empty() && ident == "crate") {
            prefix.push(ident);
        }
        tree = &p.tree;
    }
    let path = prefix.join(".");
    match tree {
        syn::UseTree::Name(n) => {
            let name = n.ident.to_string();
            if w.is_transparent_type(&name) {
                return Ok(());
            }
            let mut entries = vec![(name.clone(), name)];
            expand_sum_enum_variants(w, &path, &mut entries);
            emit_import_line(w, &path, &entries);
        }
        syn::UseTree::Rename(r) => {
            let from = r.ident.to_string();
            let alias = r.rename.to_string();
            if w.is_transparent_type(&from) {
                return Ok(());
            }
            emit_import_line(w, &path, &[(format!("{from} as {alias}"), alias)]);
        }
        syn::UseTree::Glob(_) => {
            if path.is_empty() {
                return Err(w.err(u.span(), "glob import requires a module path"));
            }
            w.line(&format!("from {path} import *"));
        }
        syn::UseTree::Group(g) => {
            if path.is_empty() {
                return Err(w.err(u.span(), "grouped import requires a module path"));
            }
            let mut entries: Vec<(String, String)> = Vec::with_capacity(g.items.len());
            for it in &g.items {
                entries.push(use_leaf_pair(w, it)?);
            }
            entries.retain(|(_, alias)| !w.is_transparent_type(alias));
            if entries.is_empty() {
                return Ok(());
            }
            expand_sum_enum_variants(w, &path, &mut entries);
            emit_import_line(w, &path, &entries);
        }
        syn::UseTree::Path(_) => {
            unreachable!("path segments already consumed");
        }
    }
    Ok(())
}

/// Emit a `from {path} import ...` line, splitting into runtime and
/// type-only groups. Type-only entries (those whose alias name appears only
/// in annotations) go under an `if TYPE_CHECKING:` block, with a `from
/// typing import TYPE_CHECKING` import emitted on first use.
fn emit_import_line(w: &mut PyWriter, path: &str, entries: &[(String, String)]) {
    if entries.is_empty() {
        return;
    }
    let mut runtime: Vec<&str> = Vec::new();
    let mut type_only: Vec<&str> = Vec::new();
    for (clause, alias) in entries {
        if w.is_runtime_ident(alias) {
            runtime.push(clause);
        } else {
            type_only.push(clause);
        }
    }
    if !runtime.is_empty() {
        if path.is_empty() {
            for c in &runtime {
                w.line(&format!("import {c}"));
            }
        } else {
            w.line(&format!("from {path} import {}", runtime.join(", ")));
        }
    }
    if !type_only.is_empty() {
        if !w.has_emitted_type_checking_import() {
            w.line("from typing import TYPE_CHECKING");
            w.mark_type_checking_imported();
        }
        w.line("if TYPE_CHECKING:");
        w.enter_indent();
        if path.is_empty() {
            for c in &type_only {
                w.line(&format!("import {c}"));
            }
        } else {
            w.line(&format!("from {path} import {}", type_only.join(", ")));
        }
        w.exit_indent();
    }
}

fn first_use_ident(tree: &syn::UseTree) -> Option<String> {
    match tree {
        syn::UseTree::Path(p) => Some(p.ident.to_string()),
        syn::UseTree::Name(n) => Some(n.ident.to_string()),
        syn::UseTree::Rename(r) => Some(r.ident.to_string()),
        _ => None,
    }
}

/// Translate `use pyrust::<rest>` after the `pyrust::` prefix has been peeled.
/// `pyrust::random` → `import random`. `pyrust::random::Random` → `from random
/// import Random`. `pyrust::random::Random as Rng` → `from random import Random
/// as Rng`. Modules outside the `random`/`math` allowlist are dropped silently.
fn emit_pyrust_use(w: &mut PyWriter, tree: &syn::UseTree) -> Result<(), String> {
    match tree {
        syn::UseTree::Name(n) => {
            let name = n.ident.to_string();
            if matches!(name.as_str(), "random" | "math") {
                w.line(&format!("import {name}"));
            }
            Ok(())
        }
        syn::UseTree::Rename(r) => {
            let from = r.ident.to_string();
            let alias = r.rename.to_string();
            if matches!(from.as_str(), "random" | "math") {
                w.line(&format!("import {from} as {alias}"));
            }
            Ok(())
        }
        syn::UseTree::Path(p) => {
            let module = p.ident.to_string();
            if !matches!(module.as_str(), "random" | "math") {
                return Ok(());
            }
            match &*p.tree {
                syn::UseTree::Name(n) => {
                    w.line(&format!("from {module} import {}", n.ident));
                }
                syn::UseTree::Rename(r) => {
                    w.line(&format!("from {module} import {} as {}", r.ident, r.rename));
                }
                syn::UseTree::Group(g) => {
                    let mut names = Vec::with_capacity(g.items.len());
                    for it in &g.items {
                        names.push(use_leaf_name(w, it)?);
                    }
                    w.line(&format!("from {module} import {}", names.join(", ")));
                }
                _ => {}
            }
            Ok(())
        }
        _ => Ok(()),
    }
}

/// When a `use {path}::Foo` import names a sum-type enum registered for
/// that module, also pull in the per-variant dataclasses (`FooA`, `FooB`,
/// …) so pattern matches and constructors elsewhere in the file can find
/// them.
fn expand_sum_enum_variants(w: &PyWriter, path: &str, entries: &mut Vec<(String, String)>) {
    let module = w.cfg().sum_enum_registry.get(path);
    let Some(module) = module else { return };
    let mut additions: Vec<(String, String)> = Vec::new();
    for (_, alias) in entries.iter() {
        if let Some(variants) = module.get(alias) {
            for v in variants {
                let combined = format!("{alias}{v}");
                additions.push((combined.clone(), combined));
            }
        }
    }
    for add in additions {
        if !entries.iter().any(|(_, a)| *a == add.1) {
            entries.push(add);
        }
    }
}

fn use_leaf_name(w: &PyWriter, tree: &syn::UseTree) -> Result<String, String> {
    match tree {
        syn::UseTree::Name(n) => Ok(n.ident.to_string()),
        syn::UseTree::Rename(r) => Ok(format!("{} as {}", r.ident, r.rename)),
        other => Err(w.err(other.span(), "nested `use` groups not supported")),
    }
}

/// Like `use_leaf_name` but returns `(import-clause, alias-name)`. The clause
/// is what goes after `from {path} import …`; the alias is the local name
/// brought into scope (used to look up runtime usage).
fn use_leaf_pair(w: &PyWriter, tree: &syn::UseTree) -> Result<(String, String), String> {
    match tree {
        syn::UseTree::Name(n) => {
            let s = n.ident.to_string();
            Ok((s.clone(), s))
        }
        syn::UseTree::Rename(r) => {
            let from = r.ident.to_string();
            let alias = r.rename.to_string();
            Ok((format!("{from} as {alias}"), alias))
        }
        other => Err(w.err(other.span(), "nested `use` groups not supported")),
    }
}

fn emit_enum(w: &mut PyWriter, e: &syn::ItemEnum) -> Result<(), String> {
    emit_c_enum_with_impls(w, e, &[])
}

pub fn emit_enum_with_file(
    w: &mut PyWriter,
    e: &syn::ItemEnum,
    file: &syn::File,
) -> Result<(), String> {
    let all_unit = e
        .variants
        .iter()
        .all(|v| matches!(v.fields, syn::Fields::Unit));
    if !all_unit {
        return emit_sum_enum_with_file(w, e, file);
    }
    let name = e.ident.to_string();
    let impls: Vec<&syn::ItemImpl> = file
        .items
        .iter()
        .filter_map(|i| {
            if let syn::Item::Impl(im) = i
                && impl_target_name(&im.self_ty).as_deref() == Some(name.as_str())
            {
                return Some(im);
            }
            None
        })
        .collect();
    emit_c_enum_with_impls(w, e, &impls)
}

fn emit_c_enum_with_impls(
    w: &mut PyWriter,
    e: &syn::ItemEnum,
    impls: &[&syn::ItemImpl],
) -> Result<(), String> {
    let name = e.ident.to_string();
    let all_unit = e
        .variants
        .iter()
        .all(|v| matches!(v.fields, syn::Fields::Unit));
    if !all_unit {
        return emit_sum_enum(w, e);
    }
    // `IntEnum` (not `Enum`) so `int(variant)` and bitwise/comparison ops
    // against ints behave the way Rust's `enum X { A = 0, ... }` does.
    w.line(&format!("class {name}(IntEnum):"));
    w.enter_indent();
    if let Some(text) = docstring::collect(&e.attrs) {
        for line in docstring::format(&text) {
            w.line(&line);
        }
    }
    if e.variants.is_empty() && impls.is_empty() {
        w.line("pass");
    } else {
        for v in &e.variants {
            let var_name = v.ident.to_string();
            let value = match &v.discriminant {
                Some((_, expr)) => expr::emit_expr(w, expr)?.text,
                None => "auto()".to_owned(),
            };
            w.line(&format!("{var_name} = {value}"));
        }
    }
    w.enter_class(name);
    for im in impls {
        // `impl Display for Foo` is debug-only; drop it (Python `__str__`
        // would need a different signature anyway).
        if let Some((_, trait_path, _)) = im.trait_.as_ref() {
            let trait_name = trait_path
                .segments
                .last()
                .map(|s| s.ident.to_string())
                .unwrap_or_default();
            if matches!(trait_name.as_str(), "Display" | "Debug") {
                continue;
            }
        }
        for impl_item in &im.items {
            match impl_item {
                syn::ImplItem::Const(c) => {
                    let cname = c.ident.to_string();
                    let py_ty = types::type_to_python_str(&c.ty)
                        .map_err(|err| w.err(c.ty.span(), format!("const type: {err}")))?;
                    let rhs = expr::emit_expr(w, &c.expr)?;
                    w.line(&format!("{cname}: Final[{py_ty}] = {}", rhs.text));
                }
                syn::ImplItem::Fn(f) => {
                    w.blank_line();
                    emit_method(w, f)?;
                }
                syn::ImplItem::Type(_) => {}
                other => {
                    return Err(w.err(
                        other.span(),
                        format!("unsupported impl item: {}", impl_item_kind(other)),
                    ));
                }
            }
        }
    }
    w.exit_class();
    w.exit_indent();
    Ok(())
}

/// Sum-type enums (variants with data) → one frozen `dataclass` per variant
/// + a `type Foo = FooA | FooB | ...` union alias. Mirrors the convention in
/// `bots/intgrah/v54.7.9/building.py` where `BuildingCore`, `BuildingConveyor`,
/// etc. are dataclasses unioned via a `type` alias.
fn emit_sum_enum_with_file(
    w: &mut PyWriter,
    e: &syn::ItemEnum,
    file: &syn::File,
) -> Result<(), String> {
    let enum_name = e.ident.to_string();
    if let Some(text) = docstring::collect(&e.attrs) {
        for line in docstring::format(&text) {
            w.line(&line);
        }
    }
    // Collect `impl <enum_name> { fn ... }` blocks once — every variant
    // class needs the methods so calls like `MarkerSymmetry(...).encode()`
    // and `b.team()` work directly on the variant instance.
    let impls: Vec<&syn::ItemImpl> = file
        .items
        .iter()
        .filter_map(|i| {
            if let syn::Item::Impl(im) = i
                && im.trait_.is_none()
                && impl_target_name(&im.self_ty).as_deref() == Some(enum_name.as_str())
            {
                return Some(im);
            }
            None
        })
        .collect();
    let mut variant_class_names = Vec::with_capacity(e.variants.len());
    for v in &e.variants {
        let var_name = v.ident.to_string();
        let class_name = format!("{enum_name}{var_name}");
        variant_class_names.push(class_name.clone());
        w.line("@dataclass(frozen=True, slots=True)");
        w.line(&format!("class {class_name}:"));
        w.enter_indent();
        if let Some(text) = docstring::collect(&v.attrs) {
            for line in docstring::format(&text) {
                w.line(&line);
            }
        }
        match &v.fields {
            syn::Fields::Unit => {
                w.line("pass");
            }
            syn::Fields::Named(named) => {
                if named.named.is_empty() {
                    w.line("pass");
                }
                for f in &named.named {
                    let fname = f
                        .ident
                        .as_ref()
                        .ok_or_else(|| w.err(f.span(), "named field missing ident"))?
                        .to_string();
                    let ty = types::type_to_python_str(&f.ty).map_err(|e| w.err(f.ty.span(), e))?;
                    w.line(&format!("{fname}: {ty}"));
                }
            }
            syn::Fields::Unnamed(unnamed) => {
                if unnamed.unnamed.is_empty() {
                    w.line("pass");
                }
                for (i, f) in unnamed.unnamed.iter().enumerate() {
                    let ty = types::type_to_python_str(&f.ty).map_err(|e| w.err(f.ty.span(), e))?;
                    w.line(&format!("_{i}: {ty}"));
                }
            }
        }
        // Fold `impl Enum { fn ... }` methods into THIS variant's class
        // body. Methods that match-extract a same-named field are skipped
        // — the variant already exposes the field directly.
        let variant_field_names: Vec<String> = match &v.fields {
            syn::Fields::Named(named) => named
                .named
                .iter()
                .filter_map(|f| f.ident.as_ref().map(std::string::ToString::to_string))
                .collect(),
            _ => Vec::new(),
        };
        // Variant class body: methods are folded from `impl Enum`, so
        // `Self::Variant` paths in those bodies should resolve through
        // the enum (whose dataclass is `EnumNameVariant`), not through
        // the variant class (which would yield `EnumNameVariantVariant`).
        w.enter_class_with_self(class_name.clone(), enum_name.clone());
        w.set_current_class_fields(variant_field_names.clone());
        let mut emitted_methods = std::collections::HashSet::new();
        for im in &impls {
            for ii in &im.items {
                if let syn::ImplItem::Fn(f) = ii {
                    let name = f.sig.ident.to_string();
                    if emitted_methods.contains(&name) {
                        continue;
                    }
                    if variant_field_names.iter().any(|fn_| fn_ == &name) {
                        // Body would just match-extract the same-named
                        // field; Python field access does the right thing.
                        emitted_methods.insert(name);
                        continue;
                    }
                    w.blank_line();
                    emit_method(w, f)?;
                    emitted_methods.insert(name);
                }
            }
        }
        w.exit_class();
        w.exit_indent();
        w.blank_line();
    }
    // Sum-type enum alias: lower as a runtime binding, not a `type` statement,
    // so static methods on the enum (`EnumName::method`) resolve through the
    // alias. With `type X = Y`, `X` is a `TypeAliasType` whose attribute
    // access doesn't reach the underlying class. With `X = Y | Z`, `X` is a
    // union (no methods) — but a single-variant enum collapses to `X = Y`,
    // which exposes `Y`'s methods via `X.method`.
    if variant_class_names.len() == 1 {
        w.line(&format!("{enum_name} = {}", variant_class_names[0]));
    } else {
        let union = variant_class_names.join(" | ");
        w.line(&format!("type {enum_name} = {union}"));
    }
    Ok(())
}

fn emit_sum_enum(w: &mut PyWriter, e: &syn::ItemEnum) -> Result<(), String> {
    // Without file context, emit without method folding. Used when called
    // from `emit_enum_with_file` for files that don't expose impl context
    // for sum enums (rare; legacy callers).
    let dummy_file = syn::File {
        shebang: None,
        attrs: Vec::new(),
        items: Vec::new(),
    };
    emit_sum_enum_with_file(w, e, &dummy_file)
}

fn emit_struct(w: &mut PyWriter, s: &syn::ItemStruct, file: &syn::File) -> Result<(), String> {
    let class_name = s.ident.to_string();
    let fields = match &s.fields {
        syn::Fields::Named(named) => &named.named,
        syn::Fields::Unit => {
            // Unit struct → class with optional methods from impl blocks.
            w.line(&format!("class {class_name}:"));
            w.enter_indent();
            if let Some(text) = docstring::collect(&s.attrs) {
                for line in docstring::format(&text) {
                    w.line(&line);
                }
            }
            let mut emitted_method = false;
            w.enter_class(class_name.clone());
            for item in &file.items {
                if let syn::Item::Impl(im) = item
                    && impl_target_name(&im.self_ty).as_deref() == Some(class_name.as_str())
                {
                    for impl_item in &im.items {
                        if let syn::ImplItem::Fn(f) = impl_item {
                            if !emitted_method {
                                w.blank_line();
                            }
                            emit_method(w, f)?;
                            emitted_method = true;
                        } else {
                            return Err(w.err(
                                impl_item.span(),
                                format!("unsupported impl item: {}", impl_item_kind(impl_item)),
                            ));
                        }
                    }
                }
            }
            if !emitted_method {
                w.line("pass");
            }
            w.exit_class();
            w.exit_indent();
            return Ok(());
        }
        syn::Fields::Unnamed(_) => {
            return Err(w.err(s.span(), "tuple structs not supported"));
        }
    };

    let mut bases = collect_trait_bases(w, file, &class_name);
    // `#[pyrust::exception]` adds `Exception` so `raise X` and
    // `except X` work as Python exception machinery.
    if w.is_exception_type(&class_name) {
        bases.insert(0, "Exception".to_owned());
    }
    let header = if bases.is_empty() {
        format!("class {class_name}:")
    } else {
        format!("class {class_name}({}):", bases.join(", "))
    };
    w.line(&header);
    w.enter_indent();
    if let Some(text) = docstring::collect(&s.attrs) {
        for line in docstring::format(&text) {
            w.line(&line);
        }
    }

    // Field annotations (PEP 526).
    let mut field_specs = Vec::with_capacity(fields.len());
    for f in fields {
        let name = f.ident.as_ref().expect("named field has ident").to_string();
        let py_ty = types::type_to_python_str(&f.ty)
            .map_err(|e| w.err(f.ty.span(), format!("field type: {e}")))?;
        w.line(&format!("{name}: {py_ty}"));
        field_specs.push((name, py_ty, types::type_from_annotation(&f.ty)));
    }

    // If the user provides `impl fn new(...) -> Self`, that's the
    // constructor — translate its body into __init__. Otherwise, auto-gen
    // __init__ from the struct fields (positional, in declaration order).
    let new_fn = find_new_fn(file, &class_name);
    w.enter_class(class_name.clone());
    w.set_current_class_fields(field_specs.iter().map(|(n, _, _)| n.clone()).collect());
    w.blank_line();
    if let Some(nf) = new_fn {
        emit_init_from_new(w, nf, &class_name)?;
    } else {
        emit_auto_init(w, &field_specs);
    }

    // If the struct has `impl Deref { fn deref(&self) -> &self.field }`,
    // synthesise `__getattr__` that proxies to that field, so Rust's
    // auto-deref `self.x` (when `x` is on the deref target) keeps working
    // in Python.
    let deref_field = find_deref_target_field(file, &class_name);
    if let Some(field) = &deref_field {
        w.blank_line();
        w.line("def __getattr__(self, name):");
        w.enter_indent();
        w.line(&format!("return getattr(self.{field}, name)"));
        w.exit_indent();
    }
    // Track which method names this struct's impls have already emitted so
    // we don't emit a trait default that's been overridden.
    let mut emitted_methods: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut implemented_traits: Vec<String> = Vec::new();
    for item in &file.items {
        if let syn::Item::Impl(im) = item
            && impl_target_name(&im.self_ty).as_deref() == Some(class_name.as_str())
        {
            if let Some((_, trait_path, _)) = im.trait_.as_ref() {
                let trait_name = trait_path
                    .segments
                    .last()
                    .map(|s| s.ident.to_string())
                    .unwrap_or_default();
                // `Deref` / `DerefMut`: no Python analog; field access works.
                if matches!(trait_name.as_str(), "Deref" | "DerefMut") {
                    continue;
                }
                if !trait_name.is_empty() {
                    implemented_traits.push(trait_name);
                }
            }
            for impl_item in &im.items {
                match impl_item {
                    syn::ImplItem::Fn(f) => {
                        if f.sig.ident == "new" {
                            // Already emitted as __init__.
                            continue;
                        }
                        if is_field_accessor(f, fields) {
                            // Trait-accessor methods that forward to a same-
                            // named field — Python's field access does the
                            // right thing; emitting the method would shadow
                            // the field on instance lookup.
                            emitted_methods.insert(f.sig.ident.to_string());
                            continue;
                        }
                        w.blank_line();
                        emit_method(w, f)?;
                        emitted_methods.insert(f.sig.ident.to_string());
                    }
                    syn::ImplItem::Const(c) => {
                        let cname = c.ident.to_string();
                        let py_ty = types::type_to_python_str(&c.ty)
                            .map_err(|err| w.err(c.ty.span(), format!("const type: {err}")))?;
                        let rhs = expr::emit_expr(w, &c.expr)?;
                        w.line(&format!("{cname}: Final[{py_ty}] = {}", rhs.text));
                    }
                    syn::ImplItem::Type(_) => {}
                    other => {
                        return Err(w.err(
                            other.span(),
                            format!("unsupported impl item: {}", impl_item_kind(other)),
                        ));
                    }
                }
            }
        }
    }
    // Fold in default-bodied trait methods for every trait this struct
    // implements (recursively for super-traits). Don't emit names already
    // covered by the concrete impl.
    let mut trait_queue = implemented_traits.clone();
    let mut visited_traits: std::collections::HashSet<String> = std::collections::HashSet::new();
    while let Some(tname) = trait_queue.pop() {
        if !visited_traits.insert(tname.clone()) {
            continue;
        }
        let Some((trait_def, trait_module_path)) = w.cfg().trait_registry.get(&tname).cloned()
        else {
            continue;
        };
        // Super-traits become extra trait queues to fold from.
        for sup in &trait_def.supertraits {
            if let syn::TypeParamBound::Trait(tb) = sup
                && let Some(seg) = tb.path.segments.last()
            {
                trait_queue.push(seg.ident.to_string());
            }
        }
        // Free-function imports for the folded body were already emitted
        // at file top by `emit_folded_trait_imports`.
        let _ = trait_module_path;
        for ti in &trait_def.items {
            let syn::TraitItem::Fn(tf) = ti else {
                continue;
            };
            let Some(body) = &tf.default else { continue };
            let name = tf.sig.ident.to_string();
            if emitted_methods.contains(&name) {
                continue;
            }
            // Trait abstract methods that match a struct field name are
            // also field accessors — skip them too.
            if fields
                .iter()
                .any(|f| f.ident.as_ref().is_some_and(|i| *i == name))
            {
                emitted_methods.insert(name);
                continue;
            }
            // Synthesise an `ImplItemFn` from the trait method's default body.
            let impl_fn = syn::ImplItemFn {
                attrs: tf.attrs.clone(),
                vis: syn::Visibility::Inherited,
                defaultness: None,
                sig: tf.sig.clone(),
                block: body.clone(),
            };
            w.blank_line();
            emit_method(w, &impl_fn)?;
            emitted_methods.insert(name);
        }
    }
    // `#[pyrust::context_manager]`: synthesise `__enter__` (returns self)
    // and `__exit__` (delegates to `drop` if defined). Constructor body
    // (e.g. push_scope) already ran in __init__.
    if w.is_context_manager_type(&class_name) {
        let has_drop = emitted_methods.contains("drop");
        w.blank_line();
        w.line("def __enter__(self):");
        w.enter_indent();
        w.line("return self");
        w.exit_indent();
        w.blank_line();
        w.line("def __exit__(self, exc_type, exc, tb):");
        w.enter_indent();
        if has_drop {
            w.line("self.drop()");
        } else {
            w.line("pass");
        }
        w.exit_indent();
    }
    w.exit_class();
    w.exit_indent();
    Ok(())
}

fn emit_auto_init(w: &mut PyWriter, fields: &[(String, String, Ty)]) {
    let header = if fields.is_empty() {
        "self".to_owned()
    } else {
        let mut parts = vec!["self".to_owned()];
        for (n, t, _) in fields {
            parts.push(format!("{n}: {t}"));
        }
        parts.join(", ")
    };
    w.line(&format!("def __init__({header}):"));
    w.enter_indent();
    if fields.is_empty() {
        w.line("pass");
    } else {
        for (n, _, _) in fields {
            w.line(&format!("self.{n} = {n}"));
        }
    }
    w.exit_indent();
}

fn find_new_fn<'a>(file: &'a syn::File, class_name: &str) -> Option<&'a syn::ImplItemFn> {
    // Inherent `impl Foo { fn new(...) -> Self { ... } }` wins. If absent,
    // accept a trait-impl's `new()` (e.g. `impl Bot for Player { fn new() })
    // — the constructor body is the same regardless of which surface
    // declares it, and Python only cares about `__init__`.
    let mut trait_new: Option<&'a syn::ImplItemFn> = None;
    for item in &file.items {
        if let syn::Item::Impl(im) = item
            && impl_target_name(&im.self_ty).as_deref() == Some(class_name)
        {
            for impl_item in &im.items {
                if let syn::ImplItem::Fn(f) = impl_item
                    && f.sig.ident == "new"
                {
                    if im.trait_.is_none() {
                        return Some(f);
                    }
                    trait_new = Some(f);
                }
            }
        }
    }
    trait_new
}

fn emit_init_from_new(
    w: &mut PyWriter,
    new_fn: &syn::ImplItemFn,
    class_name: &str,
) -> Result<(), String> {
    let (has_self, param_names, param_types) = collect_method_params(w, &new_fn.sig)?;
    if has_self {
        return Err(w.err(new_fn.sig.span(), "`new` should not take a self parameter"));
    }
    let header_params = if param_names.is_empty() {
        "self".to_owned()
    } else {
        let mut p = vec!["self".to_owned()];
        p.extend(param_names.iter().cloned());
        p.join(", ")
    };
    w.line(&format!("def __init__({header_params}):"));
    w.enter_indent();
    w.enter_block();
    if let Some(text) = docstring::collect(&new_fn.attrs) {
        for line in docstring::format(&text) {
            w.line(&line);
        }
    }
    w.declare("self", Ty::Unknown);
    for (n, t) in &param_types {
        w.declare(n, *t);
    }
    let body_emitted = emit_init_body(w, &new_fn.block, class_name)?;
    if !body_emitted {
        w.line("pass");
    }
    w.exit_block();
    w.exit_indent();
    Ok(())
}

fn emit_init_body(w: &mut PyWriter, block: &syn::Block, class_name: &str) -> Result<bool, String> {
    let stmts = &block.stmts;
    let (body, tail) = split_tail(stmts);
    let mut emitted = false;
    for s in body {
        stmt::emit_stmt(w, s)?;
        emitted = true;
    }
    if let Some(tail_expr) = tail {
        match tail_expr {
            syn::Expr::Struct(s) if is_self_struct_path(&s.path, class_name) => {
                if s.rest.is_some() {
                    return Err(w.err(
                        s.span(),
                        "struct update syntax `..base` not supported in `new`",
                    ));
                }
                for fv in &s.fields {
                    let name = match &fv.member {
                        syn::Member::Named(n) => n.to_string(),
                        syn::Member::Unnamed(_) => {
                            return Err(
                                w.err(fv.span(), "tuple struct fields not supported in `new`")
                            );
                        }
                    };
                    let value = expr::emit_expr(w, &fv.expr)?;
                    w.line(&format!("self.{name} = {}", value.text));
                    emitted = true;
                }
            }
            other => {
                return Err(w.err(
                    other.span(),
                    "`new` body must end with `Self { ... }` (canonical constructor)",
                ));
            }
        }
    }
    Ok(emitted)
}

fn is_self_struct_path(path: &syn::Path, class_name: &str) -> bool {
    if path.leading_colon.is_some() || path.segments.len() != 1 {
        return false;
    }
    let ident = path.segments[0].ident.to_string();
    ident == "Self" || ident == class_name
}

fn impl_target_name(ty: &syn::Type) -> Option<String> {
    if let syn::Type::Path(p) = ty
        && p.qself.is_none()
        && p.path.leading_colon.is_none()
        && let Some(last) = p.path.segments.last()
    {
        return Some(last.ident.to_string());
    }
    None
}

const fn impl_item_kind(item: &syn::ImplItem) -> &'static str {
    match item {
        syn::ImplItem::Const(_) => "const",
        syn::ImplItem::Fn(_) => "fn",
        syn::ImplItem::Type(_) => "associated type",
        syn::ImplItem::Macro(_) => "macro",
        _ => "item",
    }
}

fn emit_method(w: &mut PyWriter, f: &syn::ImplItemFn) -> Result<(), String> {
    let name = f.sig.ident.to_string();
    let (has_self, param_names, param_types) = collect_method_params(w, &f.sig)?;
    let return_ty = match &f.sig.output {
        syn::ReturnType::Default => Ty::Unit,
        syn::ReturnType::Type(_, t) => types::type_from_annotation(t),
    };

    if !has_self {
        w.line("@staticmethod");
    }

    let header_params = if has_self {
        let mut p = vec!["self".to_owned()];
        p.extend(param_names.iter().cloned());
        p.join(", ")
    } else {
        param_names.join(", ")
    };
    w.line(&format!("def {name}({header_params}):"));

    w.enter_indent();
    w.enter_block();
    if let Some(text) = docstring::collect(&f.attrs) {
        for line in docstring::format(&text) {
            w.line(&line);
        }
    }
    if has_self {
        w.declare("self", Ty::Unknown);
    }
    for (n, t) in &param_types {
        w.declare(n, *t);
    }
    let tail = if matches!(return_ty, Ty::Unit) {
        Tail::Discard
    } else {
        Tail::Return
    };
    stmt::emit_block_inplace(w, &f.block, tail)?;
    w.exit_block();
    w.exit_indent();
    Ok(())
}

fn collect_method_params(
    w: &PyWriter,
    sig: &syn::Signature,
) -> Result<(bool, Vec<String>, Vec<(String, Ty)>), String> {
    let mut has_self = false;
    let mut names = Vec::new();
    let mut typed = Vec::new();
    for (i, input) in sig.inputs.iter().enumerate() {
        match input {
            syn::FnArg::Receiver(r) => {
                if i != 0 {
                    return Err(w.err(r.span(), "self must be the first parameter"));
                }
                has_self = true;
            }
            syn::FnArg::Typed(pat_ty) => {
                let n = match pat_ty.pat.as_ref() {
                    syn::Pat::Ident(p_ident) => {
                        if p_ident.subpat.is_some() || p_ident.by_ref.is_some() {
                            return Err(
                                w.err(p_ident.span(), "complex parameter patterns not supported")
                            );
                        }
                        p_ident.ident.to_string()
                    }
                    other => {
                        return Err(w.err(other.span(), "parameter must be a plain ident"));
                    }
                };
                let ty = types::type_from_annotation(&pat_ty.ty);
                typed.push((n.clone(), ty));
                names.push(n);
            }
        }
    }
    Ok((has_self, names, typed))
}

fn emit_thread_local(w: &mut PyWriter, mac: &syn::Macro) -> Result<(), String> {
    // The body is a sequence of `[#[attrs]] static NAME: TYPE = INIT;`
    // declarations. We re-parse via syn::ItemStatic since the syntax matches.
    use syn::parse::{Parse, ParseStream};
    struct ThreadLocalBody {
        statics: Vec<syn::ItemStatic>,
    }
    impl Parse for ThreadLocalBody {
        fn parse(input: ParseStream) -> syn::Result<Self> {
            let mut statics = Vec::new();
            while !input.is_empty() {
                statics.push(input.parse()?);
            }
            Ok(Self { statics })
        }
    }
    let body: ThreadLocalBody = syn::parse2(mac.tokens.clone())
        .map_err(|e| w.err(mac.span(), format!("thread_local!: {e}")))?;
    let mut first = true;
    for s in &body.statics {
        if !first {
            w.blank_line();
        }
        first = false;
        // Strip `RefCell<T>` wrapper on the type and `RefCell::new(...)` /
        // `const { ... }` wrappers on the init.
        let ty = strip_refcell_type(&s.ty);
        let init = strip_init_wrappers(&s.expr);
        let py_ty = types::type_to_python_str(ty)
            .map_err(|e| w.err(ty.span(), format!("thread_local type: {e}")))?;
        let init_em = expr::emit_expr(w, init)?;
        w.line(&format!("{}: {py_ty} = {}", s.ident, init_em.text));
        if let Some(text) = docstring::collect(&s.attrs) {
            for line in docstring::format(&text) {
                w.line(&line);
            }
        }
    }
    Ok(())
}

fn strip_refcell_type(ty: &syn::Type) -> &syn::Type {
    if let syn::Type::Path(p) = ty
        && p.qself.is_none()
        && let Some(last) = p.path.segments.last()
        && last.ident == "RefCell"
        && let syn::PathArguments::AngleBracketed(args) = &last.arguments
        && let Some(syn::GenericArgument::Type(inner)) = args.args.first()
    {
        return inner;
    }
    ty
}

fn strip_init_wrappers(e: &syn::Expr) -> &syn::Expr {
    // `const { ... }` — strip to the inner expression.
    if let syn::Expr::Const(c) = e
        && let [syn::Stmt::Expr(inner, None)] = c.block.stmts.as_slice()
    {
        return strip_init_wrappers(inner);
    }
    // `RefCell::new(value)` — strip to `value`.
    if let syn::Expr::Call(c) = e
        && let syn::Expr::Path(p) = c.func.as_ref()
        && let Some(last) = p.path.segments.last()
        && last.ident == "new"
        && p.path.segments.iter().any(|s| s.ident == "RefCell")
        && c.args.len() == 1
    {
        return strip_init_wrappers(&c.args[0]);
    }
    e
}

/// Inspect the file for `impl Deref for {class}` and extract the target
/// field name from `fn deref(&self) -> &self.<field> { &self.<field> }`.
/// Returns the field name (e.g. `"state"`).
fn find_deref_target_field(file: &syn::File, class_name: &str) -> Option<String> {
    for item in &file.items {
        let syn::Item::Impl(im) = item else { continue };
        if impl_target_name(&im.self_ty).as_deref() != Some(class_name) {
            continue;
        }
        let Some((_, trait_path, _)) = im.trait_.as_ref() else {
            continue;
        };
        let trait_name = trait_path
            .segments
            .last()
            .map(|s| s.ident.to_string())
            .unwrap_or_default();
        if trait_name != "Deref" {
            continue;
        }
        for impl_item in &im.items {
            let syn::ImplItem::Fn(f) = impl_item else {
                continue;
            };
            if f.sig.ident != "deref" {
                continue;
            }
            // Body should be a single-expression block returning &self.<field>.
            if f.block.stmts.len() != 1 {
                return None;
            }
            let syn::Stmt::Expr(expr, _) = &f.block.stmts[0] else {
                return None;
            };
            let inner = match expr {
                syn::Expr::Reference(r) => r.expr.as_ref(),
                other => other,
            };
            if let syn::Expr::Field(fe) = inner
                && let syn::Expr::Path(p) = fe.base.as_ref()
                && p.path.segments.len() == 1
                && p.path.segments[0].ident == "self"
                && let syn::Member::Named(name) = &fe.member
            {
                return Some(name.to_string());
            }
        }
    }
    None
}

/// True when the impl method is a no-arg accessor whose name matches a
/// struct field — `fn state(&self) -> &UnitState { &self.state }`. Such
/// methods exist purely to bridge Rust's trait/field separation; in Python
/// the field is already accessible by name, so emitting the method would
/// shadow it.
fn is_field_accessor(
    f: &syn::ImplItemFn,
    fields: &syn::punctuated::Punctuated<syn::Field, syn::Token![,]>,
) -> bool {
    if !f
        .sig
        .inputs
        .iter()
        .all(|inp| matches!(inp, syn::FnArg::Receiver(_)))
    {
        return false;
    }
    let name = f.sig.ident.to_string();
    fields
        .iter()
        .any(|fld| fld.ident.as_ref().is_some_and(|i| i == &name))
}

/// Walk a trait's default-method bodies for the leaf identifiers of
/// function-position paths. These become the auto-import targets when the
/// body is folded into a concrete struct in another module.
fn collect_folded_call_idents(t: &syn::ItemTrait) -> std::collections::HashSet<String> {
    use syn::visit::Visit;
    struct V {
        out: std::collections::HashSet<String>,
    }
    impl<'ast> Visit<'ast> for V {
        fn visit_expr_call(&mut self, c: &'ast syn::ExprCall) {
            if let syn::Expr::Path(p) = c.func.as_ref()
                && let Some(seg) = p.path.segments.last()
                && p.path.segments.len() == 1
            {
                let name = seg.ident.to_string();
                // Built-in Rust prelude items don't need a Python import —
                // they're either Python keywords (`None`) or stripped by
                // the translator (`Some`, `Ok`, `Err`).
                if !matches!(name.as_str(), "Some" | "None" | "Ok" | "Err") {
                    self.out.insert(name);
                }
            }
            syn::visit::visit_expr_call(self, c);
        }
    }
    let mut v = V {
        out: std::collections::HashSet::new(),
    };
    for ti in &t.items {
        if let syn::TraitItem::Fn(tf) = ti
            && let Some(body) = &tf.default
        {
            v.visit_block(body);
        }
    }
    v.out
}

/// Walk `file` for `impl SomeTrait for Class` blocks and return the trait
/// names. Used to make the Python class inherit from each trait class so
/// trait default methods are visible. Standard library traits with no Python
/// analog are filtered out (`Display`, `Debug`, `Default`, `Drop`, `Deref`,
/// `DerefMut`).
fn collect_trait_bases(w: &PyWriter, file: &syn::File, class_name: &str) -> Vec<String> {
    let mut bases = Vec::new();
    for item in &file.items {
        if let syn::Item::Impl(im) = item
            && impl_target_name(&im.self_ty).as_deref() == Some(class_name)
            && let Some((_, trait_path, _)) = im.trait_.as_ref()
        {
            let trait_name = trait_path
                .segments
                .last()
                .map(|s| s.ident.to_string())
                .unwrap_or_default();
            if w.is_transparent_type(&trait_name) {
                continue;
            }
            if matches!(
                trait_name.as_str(),
                "Display" | "Debug" | "Default" | "Drop" | "Deref" | "DerefMut"
            ) {
                continue;
            }
            if !bases.iter().any(|b: &String| b == &trait_name) {
                bases.push(trait_name);
            }
        }
    }
    bases
}

fn emit_trait(w: &mut PyWriter, t: &syn::ItemTrait) -> Result<(), String> {
    let name = t.ident.to_string();
    w.line(&format!("class {name}:"));
    w.enter_indent();
    if let Some(text) = docstring::collect(&t.attrs) {
        for line in docstring::format(&text) {
            w.line(&line);
        }
    }
    w.enter_class(name);
    let mut emitted = false;
    for item in &t.items {
        if let syn::TraitItem::Fn(f) = item
            && f.default.is_some()
        {
            if emitted {
                w.blank_line();
            }
            // Synthesize an `ImplItemFn` from the trait method's default
            // body so we can reuse the existing method emitter.
            let impl_fn = syn::ImplItemFn {
                attrs: f.attrs.clone(),
                vis: syn::Visibility::Inherited,
                defaultness: None,
                sig: f.sig.clone(),
                block: f.default.clone().unwrap(),
            };
            emit_method(w, &impl_fn)?;
            emitted = true;
        }
    }
    if !emitted {
        w.line("pass");
    }
    w.exit_class();
    w.exit_indent();
    Ok(())
}

fn emit_static(w: &mut PyWriter, s: &syn::ItemStatic) -> Result<(), String> {
    let name = s.ident.to_string();
    let py_ty = types::type_to_python_str(&s.ty)
        .map_err(|e| w.err(s.ty.span(), format!("static type: {e}")))?;
    let rhs = expr::emit_expr(w, &s.expr)?;
    w.line(&format!("{name}: {py_ty} = {}", rhs.text));
    if let Some(text) = docstring::collect(&s.attrs) {
        for line in docstring::format(&text) {
            w.line(&line);
        }
    }
    let ty = types::type_from_annotation(&s.ty);
    w.declare(&name, ty);
    Ok(())
}

fn emit_const(w: &mut PyWriter, c: &syn::ItemConst) -> Result<(), String> {
    let name = c.ident.to_string();
    // `#[pyrust::inline]` consts: still emit `NAME: Final[T] = LIT` here
    // so cross-module imports (`from util.constants import MAX_WIDTH`)
    // resolve at runtime. The substitution at use sites is what saves
    // LOAD_GLOBAL inside this file's hot loops; the declaration is
    // unused locally but required for downstream importers.
    let py_ty = types::type_to_python_str(&c.ty)
        .map_err(|e| w.err(c.ty.span(), format!("const type: {e}")))?;
    let rhs = expr::emit_expr(w, &c.expr)?;
    w.line(&format!("{name}: Final[{py_ty}] = {}", rhs.text));
    if let Some(text) = docstring::collect(&c.attrs) {
        for line in docstring::format(&text) {
            w.line(&line);
        }
    }
    let ty = types::type_from_annotation(&c.ty);
    w.declare(&name, ty);
    Ok(())
}

fn emit_fn(w: &mut PyWriter, f: &syn::ItemFn) -> Result<(), String> {
    let name = f.sig.ident.to_string();
    let (param_names, param_types) = collect_params(w, &f.sig)?;

    let return_ty = match &f.sig.output {
        syn::ReturnType::Default => Ty::Unit,
        syn::ReturnType::Type(_, t) => types::type_from_annotation(t),
    };

    if name == "main" {
        if !param_names.is_empty() {
            return Err(w.err(f.sig.span(), "fn main must take no parameters"));
        }
        // main is rendered as flat top-level statements (no def, no extra indent).
        // We do not push an indent level; we still push a scope frame so cross-block
        // shadowing detection works against an empty outer frame (the file scope).
        if let Some(text) = docstring::collect(&f.attrs) {
            for line in docstring::format(&text) {
                w.line(&line);
            }
        }
        emit_top_level_block(w, &f.block)?;
        return Ok(());
    }

    w.declare(&name, return_ty);
    w.line(&format!("def {name}({}):", param_names.join(", ")));
    w.enter_indent();
    w.enter_block();
    if let Some(text) = docstring::collect(&f.attrs) {
        for line in docstring::format(&text) {
            w.line(&line);
        }
    }
    let assigned_globals = collect_assigned_statics(&f.block, w);
    if !assigned_globals.is_empty() {
        w.line(&format!("global {}", assigned_globals.join(", ")));
    }
    for (n, t) in &param_types {
        w.declare(n, *t);
    }
    let tail = if matches!(return_ty, Ty::Unit) {
        Tail::Discard
    } else {
        Tail::Return
    };
    stmt::emit_block_inplace(w, &f.block, tail)?;
    w.exit_block();
    w.exit_indent();
    Ok(())
}

/// Collect names of module-level statics that this block writes to. Used to
/// emit a Python `global X` declaration so the function's assignment hits
/// the module binding rather than creating a local.
fn collect_assigned_statics(block: &syn::Block, w: &PyWriter) -> Vec<String> {
    use syn::visit::Visit;
    struct AssignVisitor<'a> {
        statics: &'a std::collections::HashSet<String>,
        found: std::collections::BTreeSet<String>,
    }
    impl<'ast> Visit<'ast> for AssignVisitor<'_> {
        fn visit_expr_assign(&mut self, a: &'ast syn::ExprAssign) {
            if let syn::Expr::Path(p) = &*a.left
                && let Some(seg) = p.path.segments.last()
            {
                let name = seg.ident.to_string();
                if self.statics.contains(&name) {
                    self.found.insert(name);
                }
            }
            syn::visit::visit_expr_assign(self, a);
        }
    }
    let mut v = AssignVisitor {
        statics: w.statics(),
        found: std::collections::BTreeSet::new(),
    };
    v.visit_block(block);
    v.found.into_iter().collect()
}

fn emit_top_level_block(w: &mut PyWriter, block: &syn::Block) -> Result<(), String> {
    let stmts = &block.stmts;
    let (body, tail) = split_tail(stmts);
    for s in body {
        stmt::emit_stmt(w, s)?;
    }
    if let Some(t) = tail {
        emit_top_level_tail(w, t)?;
    }
    Ok(())
}

const fn split_tail(stmts: &[syn::Stmt]) -> (&[syn::Stmt], Option<&syn::Expr>) {
    if let Some((last, rest)) = stmts.split_last()
        && let syn::Stmt::Expr(e, None) = last
    {
        return (rest, Some(e));
    }
    (stmts, None)
}

fn emit_top_level_tail(w: &mut PyWriter, e: &syn::Expr) -> Result<(), String> {
    stmt::emit_expr_stmt(w, e, Tail::Discard)
}

fn collect_params(
    w: &PyWriter,
    sig: &syn::Signature,
) -> Result<(Vec<String>, Vec<(String, Ty)>), String> {
    let mut names = Vec::new();
    let mut typed = Vec::new();
    for input in &sig.inputs {
        match input {
            syn::FnArg::Receiver(r) => {
                return Err(w.err(r.span(), "self parameters not supported"));
            }
            syn::FnArg::Typed(pat_ty) => {
                let n = match pat_ty.pat.as_ref() {
                    syn::Pat::Ident(i) => {
                        if i.subpat.is_some() || i.by_ref.is_some() {
                            return Err(w.err(i.span(), "complex parameter patterns not supported"));
                        }
                        i.ident.to_string()
                    }
                    other => {
                        return Err(w.err(other.span(), "parameter must be a plain ident"));
                    }
                };
                let ty = types::type_from_annotation(&pat_ty.ty);
                typed.push((n.clone(), ty));
                names.push(n);
            }
        }
    }
    Ok((names, typed))
}

const fn item_kind(item: &syn::Item) -> &'static str {
    match item {
        syn::Item::Const(_) => "const",
        syn::Item::Enum(_) => "enum",
        syn::Item::ExternCrate(_) => "extern crate",
        syn::Item::Fn(_) => "fn",
        syn::Item::ForeignMod(_) => "extern block",
        syn::Item::Impl(_) => "impl",
        syn::Item::Macro(_) => "macro invocation",
        syn::Item::Mod(_) => "mod",
        syn::Item::Static(_) => "static",
        syn::Item::Struct(_) => "struct",
        syn::Item::Trait(_) => "trait",
        syn::Item::TraitAlias(_) => "trait alias",
        syn::Item::Type(_) => "type alias",
        syn::Item::Union(_) => "union",
        syn::Item::Use(_) => "use",
        _ => "item",
    }
}
