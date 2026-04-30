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

pub fn emit_file(file: &syn::File, source_path: &Path) -> Result<String, String> {
    let mut w = PyWriter::new(source_path);
    if let Some(text) = docstring::collect(&file.attrs) {
        for line in docstring::format(&text) {
            w.line(&line);
        }
    }
    let imports = required_imports(file);
    if !imports.is_empty() {
        for line in imports {
            w.line(&line);
        }
        w.blank_line();
    }
    let mut first = true;
    for item in &file.items {
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

fn required_imports(file: &syn::File) -> Vec<String> {
    let mut out = Vec::new();
    let mut typing: Vec<&str> = Vec::new();
    if file.items.iter().any(|i| matches!(i, syn::Item::Const(_))) {
        typing.push("Final");
    }
    if !typing.is_empty() {
        out.push(format!("from typing import {}", typing.join(", ")));
    }
    let has_enum_with_explicit = file.items.iter().any(|i| {
        if let syn::Item::Enum(e) = i {
            e.variants.iter().all(|v| v.discriminant.is_some())
        } else {
            false
        }
    });
    let has_enum = file.items.iter().any(|i| matches!(i, syn::Item::Enum(_)));
    if has_enum {
        let imports = if has_enum_with_explicit {
            "Enum"
        } else {
            "Enum, auto"
        };
        out.push(format!("from enum import {imports}"));
    }
    out
}
