mod collection;
mod docstring;
mod expr;
mod item;
mod pat;
mod shim;
mod stmt;
mod types;
mod writer;

use std::path::Path;

use writer::PyWriter;

use crate::cfg::CfgEnv;

pub fn emit_file(file: &syn::File, source_path: &Path, cfg: &CfgEnv) -> Result<String, String> {
    let mut w = PyWriter::new(source_path, cfg.clone());
    if let Some(text) = docstring::collect(&file.attrs) {
        for line in docstring::format(&text) {
            w.line(&line);
        }
    }
    let imports = required_imports(file, cfg)?;
    if !imports.is_empty() {
        for line in imports {
            w.line(&line);
        }
        w.blank_line();
    }
    let mut first = true;
    for item in &file.items {
        // Drop items whose `#[cfg(...)]` predicates evaluate false.
        let attrs = item_attrs(item);
        if !cfg.item_enabled(attrs).map_err(|e| e)? {
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
    if enabled_items
        .iter()
        .any(|i| matches!(i, syn::Item::Const(_)))
    {
        typing.push("Final");
    }
    if !typing.is_empty() {
        out.push(format!("from typing import {}", typing.join(", ")));
    }
    let has_enum_with_explicit = enabled_items.iter().any(|i| {
        if let syn::Item::Enum(e) = i {
            e.variants.iter().all(|v| v.discriminant.is_some())
        } else {
            false
        }
    });
    let has_enum = enabled_items
        .iter()
        .any(|i| matches!(i, syn::Item::Enum(_)));
    if has_enum {
        let imports = if has_enum_with_explicit {
            "Enum"
        } else {
            "Enum, auto"
        };
        out.push(format!("from enum import {imports}"));
    }
    Ok(out)
}
