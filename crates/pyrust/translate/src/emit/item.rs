use syn::spanned::Spanned;

use super::docstring;
use super::expr;
use super::stmt::{self, Tail};
use super::types::{self, Ty};
use super::writer::PyWriter;

pub fn needs_leading_blank(item: &syn::Item) -> bool {
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
    if let syn::Item::Macro(m) = item {
        if let Some(name) = m.mac.path.get_ident().map(|i| i.to_string())
            && name == "cambc_bot"
        {
            return false;
        }
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
        syn::Item::Enum(e) => emit_enum(w, e),
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
        // Trait declarations have no direct Python analog (we lower
        // `impl Trait for Type` into the concrete class). Drop the trait
        // signature entirely; default-method bodies are picked up via the
        // concrete impls.
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
        && matches!(first.as_str(), "pyrust" | "std" | "core")
    {
        // `use pyrust::<stdlib>;` mirrors Python's `import <stdlib>`
        // for known modules (random, math, etc.). Other shim/stdlib
        // imports have no Python analog and are dropped.
        if first == "pyrust"
            && let syn::UseTree::Path(p) = &u.tree
            && let syn::UseTree::Name(n) = &*p.tree
        {
            let name = n.ident.to_string();
            if matches!(name.as_str(), "random" | "math") {
                w.line(&format!("import {name}"));
            }
        }
        return Ok(());
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
            if path.is_empty() {
                w.line(&format!("import {name}"));
            } else {
                w.line(&format!("from {path} import {name}"));
            }
        }
        syn::UseTree::Rename(r) => {
            let from = r.ident.to_string();
            let alias = r.rename.to_string();
            if path.is_empty() {
                w.line(&format!("import {from} as {alias}"));
            } else {
                w.line(&format!("from {path} import {from} as {alias}"));
            }
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
            let mut names = Vec::with_capacity(g.items.len());
            for item in &g.items {
                names.push(use_leaf_name(w, item)?);
            }
            w.line(&format!("from {path} import {}", names.join(", ")));
        }
        syn::UseTree::Path(_) => {
            unreachable!("path segments already consumed");
        }
    }
    Ok(())
}

fn first_use_ident(tree: &syn::UseTree) -> Option<String> {
    match tree {
        syn::UseTree::Path(p) => Some(p.ident.to_string()),
        syn::UseTree::Name(n) => Some(n.ident.to_string()),
        syn::UseTree::Rename(r) => Some(r.ident.to_string()),
        _ => None,
    }
}

fn use_leaf_name(w: &PyWriter, tree: &syn::UseTree) -> Result<String, String> {
    match tree {
        syn::UseTree::Name(n) => Ok(n.ident.to_string()),
        syn::UseTree::Rename(r) => Ok(format!("{} as {}", r.ident, r.rename)),
        other => Err(w.err(other.span(), "nested `use` groups not supported")),
    }
}

fn emit_enum(w: &mut PyWriter, e: &syn::ItemEnum) -> Result<(), String> {
    let name = e.ident.to_string();
    let all_unit = e
        .variants
        .iter()
        .all(|v| matches!(v.fields, syn::Fields::Unit));
    if !all_unit {
        return emit_sum_enum(w, e);
    }
    w.line(&format!("class {name}(Enum):"));
    w.enter_indent();
    if let Some(text) = docstring::collect(&e.attrs) {
        for line in docstring::format(&text) {
            w.line(&line);
        }
    }
    if e.variants.is_empty() {
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
    w.exit_indent();
    Ok(())
}

/// Sum-type enums (variants with data) → one frozen `dataclass` per variant
/// + a `type Foo = FooA | FooB | ...` union alias. Mirrors the convention in
/// `bots/intgrah/v54.7.9/building.py` where `BuildingCore`, `BuildingConveyor`,
/// etc. are dataclasses unioned via a `type` alias.
fn emit_sum_enum(w: &mut PyWriter, e: &syn::ItemEnum) -> Result<(), String> {
    let enum_name = e.ident.to_string();
    if let Some(text) = docstring::collect(&e.attrs) {
        for line in docstring::format(&text) {
            w.line(&line);
        }
    }
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
        w.exit_indent();
        w.blank_line();
    }
    let union = variant_class_names.join(" | ");
    w.line(&format!("type {enum_name} = {union}"));
    Ok(())
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

    w.line(&format!("class {class_name}:"));
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
    w.blank_line();
    if let Some(nf) = new_fn {
        emit_init_from_new(w, nf, &class_name)?;
    } else {
        emit_auto_init(w, &field_specs);
    }

    for item in &file.items {
        if let syn::Item::Impl(im) = item
            && impl_target_name(&im.self_ty).as_deref() == Some(class_name.as_str())
        {
            // Skip the entire block if it's `impl Deref/DerefMut for ...`.
            // These have no Python analog (Python uses normal attribute
            // access, no transparent dereference). Their associated `type
            // Target = ...` and the `deref` fn would otherwise force
            // method-level errors.
            if let Some((_, trait_path, _)) = im.trait_.as_ref() {
                let trait_name = trait_path
                    .segments
                    .last()
                    .map(|s| s.ident.to_string())
                    .unwrap_or_default();
                if matches!(trait_name.as_str(), "Deref" | "DerefMut") {
                    continue;
                }
            }
            for impl_item in &im.items {
                match impl_item {
                    syn::ImplItem::Fn(f) => {
                        if f.sig.ident == "new" {
                            // Already emitted as __init__.
                            continue;
                        }
                        w.blank_line();
                        emit_method(w, f)?;
                    }
                    // Associated types and consts are erased during
                    // translation — Python has no analog for `type Target
                    // = X;`, and `const FOO: T = expr;` is already emitted
                    // as a class-level attribute by the struct-init path.
                    syn::ImplItem::Type(_) | syn::ImplItem::Const(_) => {}
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
    for item in &file.items {
        if let syn::Item::Impl(im) = item
            && im.trait_.is_none()
            && impl_target_name(&im.self_ty).as_deref() == Some(class_name)
        {
            for impl_item in &im.items {
                if let syn::ImplItem::Fn(f) = impl_item
                    && f.sig.ident == "new"
                {
                    return Some(f);
                }
            }
        }
    }
    None
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

fn impl_item_kind(item: &syn::ImplItem) -> &'static str {
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
            Ok(ThreadLocalBody { statics })
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

fn split_tail(stmts: &[syn::Stmt]) -> (&[syn::Stmt], Option<&syn::Expr>) {
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

fn item_kind(item: &syn::Item) -> &'static str {
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
