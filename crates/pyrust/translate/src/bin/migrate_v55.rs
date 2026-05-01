//! Mechanical AST-driven migration of v55 source to use the pyrust DSL
//! macros for Rust builtin operations.
//!
//! Transforms applied per file:
//!   `expr.is_some()`         → `pyrust::is_some!(expr)`
//!   `expr.is_none()`         → `pyrust::is_none!(expr)`
//!   `expr.unwrap()`          → `pyrust::unwrap!(expr)`
//!   `expr.expect(msg)`       → `pyrust::expect!(expr, msg)`
//!   `expr.unwrap_or(d)`      → `pyrust::unwrap_or!(expr, d)`
//!   `expr.iter()`            → `pyrust::iter!(expr)`
//!   `expr.into_iter()`       → `pyrust::into_iter!(expr)`
//!   `expr.copied()`          → `pyrust::copied!(expr)`
//!   `expr.cloned()`          → `pyrust::cloned!(expr)`
//!   `expr.collect()`         → `pyrust::collect!(expr)`
//!   `expr.collect::<T>()`    → `pyrust::collect!(expr)`
//!   `expr.to_string()`       → `pyrust::to_string!(expr)`
//!
//! Does NOT touch:
//!   - Method calls inside a `pyrust::*!` macro body (already DSL'd).
//!   - Method calls on cambc API types (Position, Controller) — they
//!     pass through identically in Python.
//!
//! The migrator uses syn to identify spans, then performs byte-level
//! substitution on the source file. This preserves comments and
//! formatting outside the touched expressions.

use proc_macro2::Span;
use syn::spanned::Spanned;
use syn::visit::Visit;

use std::path::PathBuf;

#[derive(Debug, Clone)]
struct Edit {
    start: usize,
    end: usize,
    replacement: String,
}

struct V55Migrator<'src> {
    src: &'src str,
    line_offsets: Vec<usize>,
    edits: Vec<Edit>,
}

impl<'src> V55Migrator<'src> {
    fn new(src: &'src str) -> Self {
        let mut line_offsets = vec![0usize];
        for (i, b) in src.bytes().enumerate() {
            if b == b'\n' {
                line_offsets.push(i + 1);
            }
        }
        Self {
            src,
            line_offsets,
            edits: Vec::new(),
        }
    }

    /// Convert a `proc_macro2::Span` start/end (line:col, 1-indexed) into
    /// a byte offset in `src`.
    fn span_to_byte_range(&self, span: Span) -> Option<(usize, usize)> {
        let start = span.start();
        let end = span.end();
        let s = *self.line_offsets.get(start.line.checked_sub(1)?)? + start.column;
        let e = *self.line_offsets.get(end.line.checked_sub(1)?)? + end.column;
        if s <= self.src.len() && e <= self.src.len() && s <= e {
            Some((s, e))
        } else {
            None
        }
    }

    fn add_edit(&mut self, start: usize, end: usize, replacement: String) {
        self.edits.push(Edit {
            start,
            end,
            replacement,
        });
    }

    fn apply(self) -> String {
        let mut edits = self.edits;
        edits.sort_by_key(|e| std::cmp::Reverse(e.start));
        let mut out = self.src.to_string();
        for e in &edits {
            out.replace_range(e.start..e.end, &e.replacement);
        }
        out
    }
}

impl<'ast, 'src> Visit<'ast> for V55Migrator<'src> {
    fn visit_expr_method_call(&mut self, mc: &'ast syn::ExprMethodCall) {
        // Recurse first so nested calls get rewritten.
        syn::visit::visit_expr_method_call(self, mc);
        let method = mc.method.to_string();
        // Only rewrite specific method names. Everything else passes through.
        let macro_name = match method.as_str() {
            "is_some" if mc.args.is_empty() => "is_some",
            "is_none" if mc.args.is_empty() => "is_none",
            "unwrap" if mc.args.is_empty() => "unwrap",
            "expect" if mc.args.len() == 1 => "expect",
            "unwrap_or" if mc.args.len() == 1 => "unwrap_or",
            "iter" if mc.args.is_empty() => "iter",
            "into_iter" if mc.args.is_empty() => "into_iter",
            "copied" if mc.args.is_empty() => "copied",
            "cloned" if mc.args.is_empty() => "cloned",
            "collect" if mc.args.is_empty() => "collect",
            "to_string" if mc.args.is_empty() => "to_string",
            _ => return,
        };
        // Compute the receiver's byte range in source.
        let recv_span = mc.receiver.span();
        let (recv_start, _recv_end) = match self.span_to_byte_range(recv_span) {
            Some(r) => r,
            None => return,
        };
        // The whole method-call's byte range.
        let (mc_start, mc_end) = match self.span_to_byte_range(mc.span()) {
            Some(r) => r,
            None => return,
        };
        if mc_start != recv_start {
            // Receiver doesn't start at the method-call's start — likely
            // a parenthesized or borrow-expression head. Skip; bot author
            // can hand-fix.
            return;
        }
        // Receiver text from src.
        let recv_end = match self.span_to_byte_range(recv_span) {
            Some((_, e)) => e,
            None => return,
        };
        let recv_text = &self.src[recv_start..recv_end];
        // Build the replacement text.
        let replacement = if mc.args.is_empty() {
            format!("pyrust::{macro_name}!({recv_text})")
        } else {
            let arg_texts: Vec<String> = mc
                .args
                .iter()
                .filter_map(|a| {
                    let (s, e) = self.span_to_byte_range(a.span())?;
                    Some(self.src[s..e].to_string())
                })
                .collect();
            format!("pyrust::{macro_name}!({recv_text}, {})", arg_texts.join(", "))
        };
        self.add_edit(mc_start, mc_end, replacement);
    }
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
    let mut mig = V55Migrator::new(&src);
    mig.visit_file(&file);
    if mig.edits.is_empty() {
        return Ok(false);
    }
    let out = mig.apply();
    std::fs::write(path, out)?;
    Ok(true)
}

fn main() -> std::io::Result<()> {
    let dir = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "bots/rs/v55/src".to_string());
    let mut total_changed = 0usize;
    let mut total = 0usize;
    let dir = PathBuf::from(dir);
    walk(&dir, &mut |p| {
        total += 1;
        if migrate_file(p).unwrap_or(false) {
            total_changed += 1;
            println!("rewrote {}", p.display());
        }
    })?;
    println!("changed {total_changed}/{total} files");
    Ok(())
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
