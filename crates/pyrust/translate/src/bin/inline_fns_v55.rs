//! One-shot edit pass: prepend `#[pyrust::inline]` to every
//! single-expression `fn` or `&self` method in the v55 source tree.
//!
//! Single-expression body = exactly one tail expression with no
//! semicolon, optionally inside `{ expr }`. Multi-statement bodies,
//! early-return forms, and `&mut self` methods are skipped — the
//! translator's substitution machinery doesn't yet handle them.
//!
//! Idempotent: skips items that already carry the attribute.
use std::path::PathBuf;
use syn::spanned::Spanned;

fn is_single_expr_body(b: &syn::Block) -> bool {
    if b.stmts.len() != 1 {
        return false;
    }
    let syn::Stmt::Expr(e, None) = &b.stmts[0] else {
        return false;
    };
    body_is_supported(e)
}

/// Whitelist of expression shapes the inliner handles correctly.
///
/// The substitution path in `emit_inline_call` walks the body via
/// `syn::visit_mut` and replaces leaf single-segment `Path` matches
/// (including the `self` keyword) with the caller's expression. The
/// rewritten body is then re-emitted via the regular `emit_expr`
/// machinery, so DSL macros, method-renaming, and field/index
/// emission all behave as if the body had been written at the call
/// site.
///
/// Two classes of expression are NOT safe to inline:
///
/// 1. `Self::*` — emit_expr resolves `Self` to the *current* impl
///    context, which is the call site, not the inlinee's impl.
///    `Self::Push` from a Marker method would emit as `Builder.Push`
///    when called from a Builder method.
/// 2. Macro invocations — `visit_mut` does not descend into
///    macro token streams, so formals referenced inside a macro
///    (e.g. `pyrust::vec::push!(self.x, y)`) would emit literally
///    rather than being substituted.
fn body_is_supported(e: &syn::Expr) -> bool {
    match e {
        syn::Expr::Path(p) => {
            if p.qself.is_some() || p.path.leading_colon.is_some() {
                return false;
            }
            // Reject `Self::...` paths: meaning is impl-context-bound.
            // Bare `self` is fine — it's substituted with the receiver.
            if let Some(first) = p.path.segments.first()
                && first.ident == "Self"
            {
                return false;
            }
            true
        }
        syn::Expr::Lit(_) => true,
        syn::Expr::Field(f) => {
            matches!(&f.member, syn::Member::Named(_)) && body_is_supported(&f.base)
        }
        syn::Expr::Index(i) => body_is_supported(&i.expr) && body_is_supported(&i.index),
        syn::Expr::Binary(b) => {
            let op_ok = matches!(
                b.op,
                syn::BinOp::Add(_)
                    | syn::BinOp::Sub(_)
                    | syn::BinOp::Mul(_)
                    | syn::BinOp::Div(_)
                    | syn::BinOp::Rem(_)
                    | syn::BinOp::Eq(_)
                    | syn::BinOp::Ne(_)
                    | syn::BinOp::Lt(_)
                    | syn::BinOp::Le(_)
                    | syn::BinOp::Gt(_)
                    | syn::BinOp::Ge(_)
                    | syn::BinOp::And(_)
                    | syn::BinOp::Or(_)
            );
            op_ok && body_is_supported(&b.left) && body_is_supported(&b.right)
        }
        syn::Expr::Unary(u) => {
            let op_ok = matches!(
                u.op,
                syn::UnOp::Neg(_) | syn::UnOp::Not(_) | syn::UnOp::Deref(_)
            );
            op_ok && body_is_supported(&u.expr)
        }
        syn::Expr::Reference(r) => body_is_supported(&r.expr),
        syn::Expr::Paren(p) => body_is_supported(&p.expr),
        syn::Expr::Cast(c) => body_is_supported(&c.expr),
        syn::Expr::Tuple(t) => t.elems.iter().all(body_is_supported),
        syn::Expr::MethodCall(mc) => {
            body_is_supported(&mc.receiver) && mc.args.iter().all(body_is_supported)
        }
        syn::Expr::Call(c) => {
            // Reject `Self::foo()` calls — the func path would resolve
            // against the call-site impl, not the inlinee's.
            if let syn::Expr::Path(p) = c.func.as_ref()
                && let Some(first) = p.path.segments.first()
                && first.ident == "Self"
            {
                return false;
            }
            body_is_supported(&c.func) && c.args.iter().all(body_is_supported)
        }
        // Macro/Struct/Match/If/Block/Loop/Closure/Return/Try/Async/Range etc.
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

/// Reject &mut self methods (substitution would duplicate mutation).
fn signature_is_inlinable(sig: &syn::Signature) -> bool {
    if let Some(syn::FnArg::Receiver(r)) = sig.inputs.first()
        && r.mutability.is_some()
    {
        return false;
    }
    // All non-self params must be plain Pat::Ident so substitution
    // has a name to replace.
    let has_self = matches!(sig.inputs.first(), Some(syn::FnArg::Receiver(_)));
    for arg in sig.inputs.iter().skip(if has_self { 1 } else { 0 }) {
        let syn::FnArg::Typed(pt) = arg else {
            return false;
        };
        if !matches!(pt.pat.as_ref(), syn::Pat::Ident(_)) {
            return false;
        }
    }
    true
}

#[derive(Debug, Clone)]
struct Edit {
    line: usize,   // 1-based line where the item starts
    column: usize, // 0-based byte offset within line
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

fn migrate_file(path: &std::path::Path) -> std::io::Result<usize> {
    let src = std::fs::read_to_string(path)?;
    let file: syn::File = match syn::parse_file(&src) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("parse error in {}: {e}", path.display());
            return Ok(0);
        }
    };
    let mut edits: Vec<Edit> = Vec::new();
    for item in &file.items {
        match item {
            syn::Item::Fn(f) => {
                if already_inlined(&f.attrs) {
                    continue;
                }
                if !signature_is_inlinable(&f.sig) {
                    continue;
                }
                if !is_single_expr_body(&f.block) {
                    continue;
                }
                let span = item.span().start();
                edits.push(Edit {
                    line: span.line,
                    column: span.column,
                });
            }
            syn::Item::Impl(im) => {
                for ii in &im.items {
                    let syn::ImplItem::Fn(f) = ii else { continue };
                    if already_inlined(&f.attrs) {
                        continue;
                    }
                    if !signature_is_inlinable(&f.sig) {
                        continue;
                    }
                    if !is_single_expr_body(&f.block) {
                        continue;
                    }
                    let span = ii.span().start();
                    edits.push(Edit {
                        line: span.line,
                        column: span.column,
                    });
                }
            }
            _ => {}
        }
    }
    if edits.is_empty() {
        return Ok(0);
    }
    let offsets = line_offsets(&src);
    edits.sort_by_key(|e| std::cmp::Reverse(e.line));
    let mut out = src;
    for e in &edits {
        let line_start = offsets[e.line - 1];
        let indent = " ".repeat(e.column);
        out.insert_str(line_start, &format!("{indent}#[pyrust::inline]\n"));
    }
    std::fs::write(path, out)?;
    eprintln!("{}: {} fn(s) annotated", path.display(), edits.len());
    Ok(edits.len())
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
    let mut annotated = 0usize;
    walk(&PathBuf::from(dir), &mut |p| {
        match migrate_file(p) {
            Ok(0) => {}
            Ok(n) => annotated += n,
            Err(e) => eprintln!("{}: {e}", p.display()),
        }
        total += 1;
    })?;
    println!("annotated {annotated} fn(s) across {total} file(s)");
    Ok(())
}
