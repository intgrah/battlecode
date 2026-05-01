//! One-shot edit pass: prepend `#[pyrust::inline]` to every
//! literal-RHS `const` declaration in the v55 source tree.
//!
//! Literal-RHS = `const NAME: T = LIT;` where LIT is `Lit::Int`,
//! `Lit::Float`, `Lit::Bool`, `Lit::Str`, optionally wrapped in
//! `Unary::Neg`. `const NAME: T = expr;` for any other expression
//! (e.g. function call, computed expression, struct literal) is
//! left alone — `#[pyrust::inline]` rejects non-literal RHS.
//!
//! Idempotent: skips items that already carry the attribute.
use std::path::PathBuf;
use syn::spanned::Spanned;

fn is_literal_rhs(expr: &syn::Expr) -> bool {
    match expr {
        syn::Expr::Lit(l) => matches!(
            l.lit,
            syn::Lit::Int(_) | syn::Lit::Float(_) | syn::Lit::Bool(_) | syn::Lit::Str(_)
        ),
        syn::Expr::Unary(u) if matches!(u.op, syn::UnOp::Neg(_)) => is_literal_rhs(&u.expr),
        _ => false,
    }
}

fn already_inlined(attrs: &[syn::Attribute]) -> bool {
    attrs.iter().any(|a| {
        let segs: Vec<String> = a
            .path()
            .segments
            .iter()
            .map(|s| s.ident.to_string())
            .collect();
        segs == ["pyrust", "inline"]
    })
}

#[derive(Debug, Clone)]
struct Edit {
    line: usize,    // 1-based line where the const item starts
    column: usize,  // 0-based column (byte offset within line)
}

fn line_offsets(src: &str) -> Vec<usize> {
    let mut out = vec![0];
    for (i, b) in src.bytes().enumerate() {
        if b == b'\n' {
            out.push(i + 1);
        }
    }
    out
}

fn migrate_file(path: &std::path::Path) -> std::io::Result<bool> {
    let src = std::fs::read_to_string(path)?;
    let file: syn::File = match syn::parse_file(&src) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("parse error in {}: {e}", path.display());
            return Ok(false);
        }
    };
    let mut edits: Vec<Edit> = Vec::new();
    for item in &file.items {
        let syn::Item::Const(c) = item else { continue };
        if !is_literal_rhs(&c.expr) {
            continue;
        }
        if already_inlined(&c.attrs) {
            continue;
        }
        // The item's span starts at `pub` / `const`. Insert the attribute
        // line just before that, preserving the indentation.
        let span = item.span();
        let start = span.start();
        edits.push(Edit {
            line: start.line,
            column: start.column,
        });
    }
    if edits.is_empty() {
        return Ok(false);
    }
    let offsets = line_offsets(&src);
    // Apply edits from bottom to top so earlier edits don't shift
    // later line offsets.
    edits.sort_by_key(|e| std::cmp::Reverse(e.line));
    let mut out = src;
    for e in &edits {
        let line_start = offsets[e.line - 1];
        let insert_at = line_start;
        let indent = " ".repeat(e.column);
        out.insert_str(insert_at, &format!("{indent}#[pyrust::inline]\n"));
    }
    std::fs::write(path, out)?;
    eprintln!("{}: {} const(s) annotated", path.display(), edits.len());
    Ok(true)
}

fn walk(dir: &std::path::Path, f: &mut impl FnMut(&std::path::Path)) -> std::io::Result<()> {
    for entry in std::fs::read_dir(dir)? {
        let entry = entry?;
        let p = entry.path();
        if p.is_dir() {
            walk(&p, f)?;
        } else if p.extension().and_then(|x| x.to_str()) == Some("rs") {
            f(&p);
        }
    }
    Ok(())
}

fn main() -> std::io::Result<()> {
    let dir = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "bots/rs/v55/src".to_string());
    let mut total = 0usize;
    let mut changed = 0usize;
    walk(&PathBuf::from(dir), &mut |p| {
        total += 1;
        if migrate_file(p).unwrap_or(false) {
            changed += 1;
        }
    })?;
    println!("changed {changed}/{total} files");
    Ok(())
}
