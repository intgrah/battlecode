mod collection;
mod docstring;
mod expr;
mod item;
mod pat;
mod shim;
mod stmt;
mod types;
mod writer;

use std::collections::HashSet;
use std::path::Path;

use syn::visit::Visit;

use writer::PyWriter;

use crate::cfg::CfgEnv;

pub fn emit_file(
    file: &syn::File,
    source_path: &Path,
    cfg: &CfgEnv,
    types: &crate::tyctx::FileTyTable,
) -> Result<String, String> {
    let mut w = PyWriter::new(source_path, cfg.clone(), types);
    // Pre-scan: register every sum-type enum declared in the file so
    // `emit_path` and `pat_to_python` know which `Enum::Variant`s should
    // map to dataclass constructors versus C-style `Enum.Variant`.
    // Also register module-level `static` bindings so their assignment
    // sites pick up a Python `global` declaration.
    for item in &file.items {
        if let syn::Item::Enum(e) = item
            && cfg.item_enabled(&e.attrs).unwrap_or(true)
            && e.variants
                .iter()
                .any(|v| !matches!(v.fields, syn::Fields::Unit))
        {
            w.note_sum_enum(&e.ident.to_string());
        }
        if let syn::Item::Static(s) = item {
            w.note_static(&s.ident.to_string());
        }
    }
    // Pre-scan: collect all identifiers referenced from runtime (non-type)
    // positions so emit_use can decide which imports must run at module
    // init versus which can live under `if TYPE_CHECKING:`.
    let mut runtime = RuntimeIdentCollector::default();
    for item in &file.items {
        runtime.visit_item(item);
    }
    w.set_runtime_idents(runtime.idents);
    w.set_module_refs(runtime.module_refs);
    if let Some(text) = docstring::collect(&file.attrs) {
        for line in docstring::format(&text) {
            w.line(&line);
        }
    }
    // Defer annotation evaluation so cross-module type references (e.g.
    // `Builder` in a hooks/ submodule) don't trigger circular imports at
    // module-init time.
    w.line("from __future__ import annotations");
    w.blank_line();
    let imports = required_imports(file, cfg)?;
    if !imports.is_empty() {
        for line in imports {
            w.line(&line);
        }
        w.blank_line();
    }
    // Auto-imports for trait default bodies that get folded into structs
    // in this file. Emit at file top so class bodies stay contiguous.
    emit_folded_trait_imports(&mut w, file);
    let mut first = true;
    for item in &file.items {
        // Drop items whose `#[cfg(...)]` predicates evaluate false.
        let attrs = item_attrs(item);
        if !cfg.item_enabled(attrs)? {
            continue;
        }
        if !item::produces_output(item) {
            item::emit_item(&mut w, item, file)?;
            continue;
        }
        let needs_blank = item::needs_leading_blank(item);
        if needs_blank && !first {
            w.blank_line();
        }
        item::emit_item(&mut w, item, file)?;
        first = false;
    }
    Ok(w.finish())
}

fn item_attrs(item: &syn::Item) -> &[syn::Attribute] {
    match item {
        syn::Item::Fn(f) => &f.attrs,
        syn::Item::Const(c) => &c.attrs,
        syn::Item::Struct(s) => &s.attrs,
        syn::Item::Enum(e) => &e.attrs,
        syn::Item::Impl(i) => &i.attrs,
        syn::Item::Use(u) => &u.attrs,
        syn::Item::Mod(m) => &m.attrs,
        syn::Item::Static(s) => &s.attrs,
        syn::Item::Macro(m) => &m.attrs,
        _ => &[],
    }
}

fn required_imports(file: &syn::File, cfg: &CfgEnv) -> Result<Vec<String>, String> {
    let mut out = Vec::new();
    let mut typing: Vec<&str> = Vec::new();
    let enabled_items: Vec<&syn::Item> = file
        .items
        .iter()
        .filter(|i| cfg.item_enabled(item_attrs(i)).unwrap_or(true))
        .collect();
    let has_const = enabled_items.iter().any(|i| match i {
        syn::Item::Const(_) => true,
        syn::Item::Impl(im) => im
            .items
            .iter()
            .any(|ii| matches!(ii, syn::ImplItem::Const(_))),
        _ => false,
    });
    if has_const {
        typing.push("Final");
    }
    if !typing.is_empty() {
        out.push(format!("from typing import {}", typing.join(", ")));
    }
    // Sum-type enums (any variant has fields) → dataclasses + a `type`
    // alias. C-style enums (all-unit variants) → `Enum`/`auto`. The two
    // need different imports and we may have either, both, or neither.
    let mut has_c_style_enum = false;
    let mut has_c_style_enum_with_explicit = false;
    let mut has_sum_enum = false;
    for i in &enabled_items {
        let syn::Item::Enum(e) = i else { continue };
        let is_sum = e
            .variants
            .iter()
            .any(|v| !matches!(v.fields, syn::Fields::Unit));
        if is_sum {
            has_sum_enum = true;
        } else {
            has_c_style_enum = true;
            if e.variants.iter().all(|v| v.discriminant.is_some()) {
                has_c_style_enum_with_explicit = true;
            }
        }
    }
    if has_c_style_enum {
        let imports = if has_c_style_enum_with_explicit {
            "IntEnum"
        } else {
            "IntEnum, auto"
        };
        out.push(format!("from enum import {imports}"));
    }
    if has_sum_enum {
        out.push("from dataclasses import dataclass".to_owned());
    }
    // `.floor()`, `.ceil()`, `.sqrt()` and friends translate to
    // `math.floor(...)` etc. — pre-emit `import math` whenever any of
    // those method names appears anywhere in the file.
    if file_uses_method_name(
        &enabled_items,
        &["floor", "ceil", "sqrt", "log", "log2", "log10", "exp"],
    ) {
        out.push("import math".to_owned());
    }
    if file_uses_macro_path(&enabled_items, &[&["time", "now_ns"]]) {
        out.push("import time".to_owned());
    }
    if file_uses_call_path(&enabled_items, &[&["serde_json", "to_string"]]) {
        out.push("import json".to_owned());
    }
    Ok(out)
}

/// True if any expression in the file invokes a free-function call
/// whose path matches one of `paths` exactly.
fn file_uses_call_path(items: &[&syn::Item], paths: &[&[&str]]) -> bool {
    use syn::visit::Visit;
    struct V<'a> {
        paths: &'a [&'a [&'a str]],
        hit: bool,
    }
    impl<'ast> Visit<'ast> for V<'_> {
        fn visit_expr_call(&mut self, c: &'ast syn::ExprCall) {
            if let syn::Expr::Path(p) = &*c.func
                && p.qself.is_none()
            {
                let segs: Vec<String> = p
                    .path
                    .segments
                    .iter()
                    .map(|s| s.ident.to_string())
                    .collect();
                let tail: Vec<&str> = segs.iter().map(String::as_str).collect();
                if self
                    .paths
                    .iter()
                    .any(|p| p.len() == tail.len() && p.iter().zip(&tail).all(|(a, b)| a == b))
                {
                    self.hit = true;
                }
            }
            syn::visit::visit_expr_call(self, c);
        }
        fn visit_expr_macro(&mut self, em: &'ast syn::ExprMacro) {
            // Calls buried inside macro bodies (`pyrust::expect!(...)`,
            // `vec![...]`, `format!(...)`) still count.
            let parser = syn::punctuated::Punctuated::<syn::Expr, syn::Token![,]>::parse_terminated;
            if let Ok(args) = syn::parse::Parser::parse2(parser, em.mac.tokens.clone()) {
                for arg in args {
                    self.visit_expr(&arg);
                }
            }
        }
    }
    let mut v = V { paths, hit: false };
    for item in items {
        v.visit_item(item);
        if v.hit {
            return true;
        }
    }
    false
}

/// True if any expression in the file invokes a `pyrust::*!` DSL macro
/// whose path tail (after `pyrust::`) matches one of `paths`. Used at
/// file level to gate stdlib imports.
fn file_uses_macro_path(items: &[&syn::Item], paths: &[&[&str]]) -> bool {
    use syn::visit::Visit;
    struct V<'a> {
        paths: &'a [&'a [&'a str]],
        hit: bool,
    }
    impl<'ast> Visit<'ast> for V<'_> {
        fn visit_expr_macro(&mut self, em: &'ast syn::ExprMacro) {
            let segs: Vec<String> = em
                .mac
                .path
                .segments
                .iter()
                .map(|s| s.ident.to_string())
                .collect();
            // Strip leading `pyrust` segment.
            let tail: Vec<&str> = if segs.first().map(String::as_str) == Some("pyrust") {
                segs[1..].iter().map(String::as_str).collect()
            } else {
                segs.iter().map(String::as_str).collect()
            };
            if self
                .paths
                .iter()
                .any(|p| p.len() == tail.len() && p.iter().zip(&tail).all(|(a, b)| a == b))
            {
                self.hit = true;
            }
            let parser = syn::punctuated::Punctuated::<syn::Expr, syn::Token![,]>::parse_terminated;
            if let Ok(args) = syn::parse::Parser::parse2(parser, em.mac.tokens.clone()) {
                for arg in args {
                    self.visit_expr(&arg);
                }
            }
        }
    }
    let mut v = V { paths, hit: false };
    for item in items {
        v.visit_item(item);
        if v.hit {
            return true;
        }
    }
    false
}

/// True if any expression in the file calls a method whose ident matches
/// one of `names`. Cheap textual walk — covers method-call sites whose
/// receiver type the translator can't determine but whose method name
/// alone unambiguously requires `import math`.
fn file_uses_method_name(items: &[&syn::Item], names: &[&str]) -> bool {
    use syn::visit::Visit;
    struct V<'a> {
        names: &'a [&'a str],
        hit: bool,
    }
    impl<'ast> Visit<'ast> for V<'_> {
        fn visit_expr_method_call(&mut self, mc: &'ast syn::ExprMethodCall) {
            let n = mc.method.to_string();
            if self.names.iter().any(|x| *x == n) {
                self.hit = true;
            }
            syn::visit::visit_expr_method_call(self, mc);
        }
        fn visit_expr_macro(&mut self, em: &'ast syn::ExprMacro) {
            // Also recognise the math operations when wrapped in
            // pyrust DSL macros (e.g. `pyrust::sqrt!(x)`). Descend
            // into the macro body too — chains like
            // `pyrust::abs!(pyrust::sqrt!(x))` only show the inner
            // macro after parsing the body.
            if let Some(last) = em.mac.path.segments.last() {
                let n = last.ident.to_string();
                if self.names.iter().any(|x| *x == n) {
                    self.hit = true;
                }
            }
            let parser = syn::punctuated::Punctuated::<syn::Expr, syn::Token![,]>::parse_terminated;
            if let Ok(args) = syn::parse::Parser::parse2(parser, em.mac.tokens.clone()) {
                for arg in args {
                    self.visit_expr(&arg);
                }
            }
        }
    }
    let mut v = V { names, hit: false };
    for item in items {
        v.visit_item(item);
        if v.hit {
            return true;
        }
    }
    false
}

/// For each `impl Trait for X` in the file, look up Trait in the project
/// registry and emit auto-imports for any free-function references in
/// Trait's default-method bodies. Run at file top so the class body stays
/// contiguous.
fn emit_folded_trait_imports(w: &mut PyWriter, file: &syn::File) {
    use syn::visit::Visit;
    let mut traits_to_fold: std::collections::BTreeSet<String> = std::collections::BTreeSet::new();
    for item in &file.items {
        if let syn::Item::Impl(im) = item
            && let Some((_, trait_path, _)) = &im.trait_
            && let Some(seg) = trait_path.segments.last()
        {
            traits_to_fold.insert(seg.ident.to_string());
        }
    }
    let mut visited: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut queue: Vec<String> = traits_to_fold.into_iter().collect();
    while let Some(tname) = queue.pop() {
        if !visited.insert(tname.clone()) {
            continue;
        }
        let Some((trait_def, trait_module)) = w.cfg().trait_registry.get(&tname).cloned() else {
            continue;
        };
        for sup in &trait_def.supertraits {
            if let syn::TypeParamBound::Trait(tb) = sup
                && let Some(seg) = tb.path.segments.last()
            {
                queue.push(seg.ident.to_string());
            }
        }
        struct V {
            out: std::collections::BTreeSet<String>,
        }
        impl<'ast> Visit<'ast> for V {
            fn visit_expr_call(&mut self, c: &'ast syn::ExprCall) {
                if let syn::Expr::Path(p) = c.func.as_ref()
                    && let Some(seg) = p.path.segments.last()
                    && p.path.segments.len() == 1
                {
                    let name = seg.ident.to_string();
                    if !matches!(name.as_str(), "Some" | "None" | "Ok" | "Err") {
                        self.out.insert(name);
                    }
                }
                syn::visit::visit_expr_call(self, c);
            }
        }
        let mut v = V {
            out: std::collections::BTreeSet::new(),
        };
        for ti in &trait_def.items {
            if let syn::TraitItem::Fn(tf) = ti
                && let Some(body) = &tf.default
            {
                v.visit_block(body);
            }
        }
        for ident in v.out {
            w.emit_folded_import(&trait_module, &ident);
        }
    }
}

/// Walks a file's syntax tree collecting identifiers referenced from runtime
/// (non-type) positions. Type annotations are skipped — anything appearing
/// only inside a `syn::Type` doesn't need a runtime import once
/// `from __future__ import annotations` is in effect.
#[derive(Default)]
struct RuntimeIdentCollector {
    idents: HashSet<String>,
    /// First-segment identifiers from multi-segment paths in expression
    /// position (e.g. `build_foundry::build_foundry` records `build_foundry`).
    /// Lower-case heuristic distinguishes module references from type paths.
    module_refs: HashSet<String>,
}

impl RuntimeIdentCollector {
    fn record_path(
        &mut self,
        segs: &syn::punctuated::Punctuated<syn::PathSegment, syn::Token![::]>,
    ) {
        let names: Vec<String> = segs.iter().map(|s| s.ident.to_string()).collect();
        for n in &names {
            self.idents.insert(n.clone());
        }
        // For two-segment paths like `Policy::Leaf` also record the
        // dataclass-style combined name `PolicyLeaf` — that's how the sum
        // enum lowering emits the constructor in Python, and the import
        // gate consults this set when deciding runtime vs TYPE_CHECKING.
        if names.len() >= 2 {
            let head = &names[names.len() - 2];
            let tail = &names[names.len() - 1];
            if head.chars().next().is_some_and(char::is_uppercase)
                && tail.chars().next().is_some_and(char::is_uppercase)
            {
                self.idents.insert(format!("{head}{tail}"));
            }
            // First segment of a multi-segment path — record as a module
            // reference. Used by `emit_file` to decide which `pub mod X;`
            // declarations need a `from . import X` line.
            if names[0].chars().next().is_some_and(char::is_lowercase) {
                self.module_refs.insert(names[0].clone());
            }
        }
    }
}

impl<'ast> Visit<'ast> for RuntimeIdentCollector {
    fn visit_type(&mut self, _t: &'ast syn::Type) {
        // Stop descent — anything inside a type annotation is annotation-only.
    }

    fn visit_expr_path(&mut self, p: &'ast syn::ExprPath) {
        self.record_path(&p.path.segments);
    }

    fn visit_expr_struct(&mut self, s: &'ast syn::ExprStruct) {
        self.record_path(&s.path.segments);
        for fv in &s.fields {
            self.visit_expr(&fv.expr);
        }
    }

    fn visit_pat_tuple_struct(&mut self, ts: &'ast syn::PatTupleStruct) {
        self.record_path(&ts.path.segments);
        for elem in &ts.elems {
            self.visit_pat(elem);
        }
    }

    fn visit_pat_struct(&mut self, ps: &'ast syn::PatStruct) {
        self.record_path(&ps.path.segments);
        for f in &ps.fields {
            self.visit_pat(&f.pat);
        }
    }

    fn visit_pat(&mut self, p: &'ast syn::Pat) {
        if let syn::Pat::Path(pp) = p {
            self.record_path(&pp.path.segments);
        }
        syn::visit::visit_pat(self, p);
    }

    /// `impl SomeTrait for Class` — the trait path becomes a Python class
    /// base, so its name is needed at runtime.
    fn visit_item_impl(&mut self, im: &'ast syn::ItemImpl) {
        if let Some((_, trait_path, _)) = &im.trait_ {
            for seg in &trait_path.segments {
                self.idents.insert(seg.ident.to_string());
            }
        }
        syn::visit::visit_item_impl(self, im);
    }

    /// Re-parse macro bodies as expression streams so identifiers used
    /// inside `vec![...]`, `format!(...)`, etc. count toward the runtime
    /// set. We don't know the macro's semantics, but most pyrust shim
    /// macros take comma-separated expressions.
    fn visit_macro(&mut self, m: &'ast syn::Macro) {
        let tokens = m.tokens.clone();
        if let Ok(parsed) = syn::parse2::<MacroExprList>(tokens.clone()) {
            for e in &parsed.0 {
                self.visit_expr(e);
            }
        }
        // Also walk the tokens looking for bare identifiers — the parser
        // above stops at the first `;` or unparseable spot, so a macro
        // like `vec![X; N]` only got `X`. Pick up `N` and friends here
        // to keep the runtime set conservatively complete. Recurses into
        // nested `Group`s for things like `matches!(x, Some(Foo::Bar))`.
        self.collect_idents_from_tokens(tokens);
    }
}

impl RuntimeIdentCollector {
    fn collect_idents_from_tokens(&mut self, tokens: proc_macro2::TokenStream) {
        let tts: Vec<proc_macro2::TokenTree> = tokens.into_iter().collect();
        for (idx, tt) in tts.iter().enumerate() {
            match tt {
                proc_macro2::TokenTree::Ident(id) => {
                    let name = id.to_string();
                    self.idents.insert(name.clone());
                    // Recognise `Foo :: Bar` token sequences and synthesise
                    // the dataclass-style combined name `FooBar` (used by
                    // sum-type variant lowering).
                    if idx + 2 < tts.len()
                        && let proc_macro2::TokenTree::Punct(p1) = &tts[idx + 1]
                        && p1.as_char() == ':'
                        && let proc_macro2::TokenTree::Punct(p2) = &tts[idx + 2]
                        && p2.as_char() == ':'
                        && idx + 3 < tts.len()
                        && let proc_macro2::TokenTree::Ident(tail) = &tts[idx + 3]
                    {
                        let tail_s = tail.to_string();
                        if name.chars().next().is_some_and(char::is_uppercase)
                            && tail_s.chars().next().is_some_and(char::is_uppercase)
                        {
                            self.idents.insert(format!("{name}{tail_s}"));
                        }
                    }
                }
                proc_macro2::TokenTree::Group(g) => {
                    self.collect_idents_from_tokens(g.stream());
                }
                _ => {}
            }
        }
    }
}

/// Best-effort macro body re-parse: a comma-separated list of expressions,
/// optionally with a trailing `; expr` (the `vec![value; count]` form).
struct MacroExprList(Vec<syn::Expr>);

impl syn::parse::Parse for MacroExprList {
    fn parse(input: syn::parse::ParseStream) -> syn::Result<Self> {
        let mut out = Vec::new();
        while !input.is_empty() {
            // Stop on `;` (vec!-with-count form).
            if input.peek(syn::Token![;]) {
                break;
            }
            match input.parse::<syn::Expr>() {
                Ok(e) => out.push(e),
                Err(_) => break,
            }
            if !input.peek(syn::Token![,]) {
                break;
            }
            let _: syn::Token![,] = input.parse()?;
        }
        Ok(Self(out))
    }
}
