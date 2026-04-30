use syn::spanned::Spanned;

use super::expr::{self, Emitted};
use super::types::{self, Ty};
use super::writer::PyWriter;

#[derive(Clone, Copy, Debug)]
pub enum Tail {
    Discard,
    Return,
}

pub fn emit_block(w: &mut PyWriter, block: &syn::Block, tail: Tail) -> Result<(), String> {
    w.enter_block();
    let r = emit_block_inplace(w, block, tail);
    w.exit_block();
    r
}

/// Same as [`emit_block`] but does not push or pop a scope frame. The caller is
/// expected to enter and exit the frame (used by item::emit_fn so that fn
/// parameters share the body's frame).
pub fn emit_block_inplace(w: &mut PyWriter, block: &syn::Block, tail: Tail) -> Result<(), String> {
    let stmts = &block.stmts;
    let (body, tail_expr) = split_tail(stmts);
    let mut emitted_anything = false;
    for s in body {
        emit_stmt(w, s)?;
        emitted_anything = true;
    }
    match tail_expr {
        Some(t) => {
            emit_tail(w, t, tail)?;
            emitted_anything = true;
        }
        None => {
            if matches!(tail, Tail::Return) {
                w.line("return");
                emitted_anything = true;
            }
        }
    }
    if !emitted_anything {
        w.line("pass");
    }
    Ok(())
}

fn split_tail(stmts: &[syn::Stmt]) -> (&[syn::Stmt], Option<&syn::Expr>) {
    if let Some((last, rest)) = stmts.split_last() {
        if let syn::Stmt::Expr(e, None) = last {
            return (rest, Some(e));
        }
    }
    (stmts, None)
}

pub fn emit_stmt(w: &mut PyWriter, stmt: &syn::Stmt) -> Result<(), String> {
    match stmt {
        syn::Stmt::Local(l) => emit_local(w, l),
        // Stmt::Expr without a semi only reaches here for block-like exprs in
        // non-tail position (the actual block tail is split off by emit_block /
        // emit_top_level_block before iterating). Treat both forms identically.
        syn::Stmt::Expr(e, _) => emit_expr_stmt(w, e, Tail::Discard),
        syn::Stmt::Item(i) => Err(w.err(i.span(), "nested items are not supported")),
        syn::Stmt::Macro(m) => emit_stmt_macro(w, m),
    }
}

fn emit_stmt_macro(w: &mut PyWriter, sm: &syn::StmtMacro) -> Result<(), String> {
    let path = &sm.mac.path;
    if path.leading_colon.is_none()
        && path.segments.len() == 1
        && path.segments[0].ident == "println"
    {
        let inner = super::collection::emit_format(w, sm.mac.tokens.clone(), &sm.mac)?;
        w.line(&format!("print({})", inner.text));
        return Ok(());
    }
    Err(w.err(
        sm.span(),
        "macro statements are not supported (only println! is recognized at statement level)",
    ))
}

fn emit_local(w: &mut PyWriter, l: &syn::Local) -> Result<(), String> {
    let init = l
        .init
        .as_ref()
        .ok_or_else(|| w.err(l.span(), "let without initializer not supported"))?;
    if init.diverge.is_some() {
        return Err(w.err(l.span(), "let-else not supported"));
    }

    let binding = bind_name_and_type(w, &l.pat)?;
    let ann_src = pat_annotation(&l.pat);
    let rhs = expr::emit_expr(w, &init.expr)?;
    match binding {
        Binding::Wild => {
            // `let _ = expr;` evaluates the expression and discards. If the
            // expression has no observable side effects (a path, literal,
            // pure read), elide it — Python would just emit a stray
            // identifier that linters flag.
            if !is_pure_read(&init.expr) {
                w.line(&rhs.text);
            }
        }
        Binding::Named { name, ann_ty } => {
            if w.is_outer_binding(&name) && !w.is_current_binding(&name) {
                return Err(w.err(
                    l.span(),
                    format!(
                        "cross-block shadowing of `{name}` is not supported (would diverge from Python's scoping)"
                    ),
                ));
            }
            let ty = match ann_ty {
                Some(t) if t != Ty::Unknown => t,
                _ => rhs.ty,
            };
            w.declare(&name, ty);
            let line = match ann_src {
                Some(t) => {
                    let py_ty = types::type_to_python_str(t)
                        .map_err(|e| w.err(t.span(), format!("let type: {e}")))?;
                    format!("{name}: {py_ty} = {}", rhs.text)
                }
                None => format!("{name} = {}", rhs.text),
            };
            w.line(&line);
        }
        Binding::Tuple { names } => {
            for n in &names {
                if n == "_" {
                    continue;
                }
                if w.is_outer_binding(n) && !w.is_current_binding(n) {
                    return Err(w.err(
                        l.span(),
                        format!(
                            "cross-block shadowing of `{n}` is not supported (would diverge from Python's scoping)"
                        ),
                    ));
                }
            }
            for n in &names {
                if n != "_" {
                    w.declare(n, Ty::Unknown);
                }
            }
            // Python rejects `(a, b): tuple[...] = ...`, so type annotations on
            // tuple-pattern lets are dropped.
            w.line(&format!("{} = {}", names.join(", "), rhs.text));
        }
    }
    Ok(())
}

fn pat_annotation(pat: &syn::Pat) -> Option<&syn::Type> {
    match pat {
        syn::Pat::Type(pt) => Some(&pt.ty),
        _ => None,
    }
}

/// Whether the expression is a side-effect-free read.
fn is_pure_read(e: &syn::Expr) -> bool {
    match e {
        syn::Expr::Path(_) | syn::Expr::Lit(_) => true,
        syn::Expr::Reference(r) => is_pure_read(&r.expr),
        syn::Expr::Paren(p) => is_pure_read(&p.expr),
        syn::Expr::Field(f) => is_pure_read(&f.base),
        syn::Expr::Tuple(t) => t.elems.iter().all(is_pure_read),
        _ => false,
    }
}

enum Binding {
    Wild,
    Named { name: String, ann_ty: Option<Ty> },
    Tuple { names: Vec<String> },
}

fn bind_name_and_type(w: &PyWriter, pat: &syn::Pat) -> Result<Binding, String> {
    match pat {
        syn::Pat::Wild(_) => Ok(Binding::Wild),
        syn::Pat::Ident(i) => {
            if i.subpat.is_some() {
                return Err(w.err(
                    i.span(),
                    "subpatterns in let bindings not supported",
                ));
            }
            if i.by_ref.is_some() {
                return Err(w.err(i.span(), "ref bindings not supported"));
            }
            Ok(Binding::Named {
                name: i.ident.to_string(),
                ann_ty: None,
            })
        }
        syn::Pat::Tuple(pt) => {
            let mut names = Vec::with_capacity(pt.elems.len());
            for elem in &pt.elems {
                names.push(tuple_pat_name(w, elem)?);
            }
            Ok(Binding::Tuple { names })
        }
        syn::Pat::Type(pt) => {
            let inner = bind_name_and_type(w, &pt.pat)?;
            let ty = types::type_from_annotation(&pt.ty);
            match inner {
                Binding::Wild => Ok(Binding::Wild),
                Binding::Named { name, .. } => Ok(Binding::Named {
                    name,
                    ann_ty: Some(ty),
                }),
                Binding::Tuple { names } => Ok(Binding::Tuple { names }),
            }
        }
        other => Err(w.err(
            other.span(),
            "complex let patterns not supported (only `let name`/`let mut name`/`let _`/`let (a, b)` for now)",
        )),
    }
}

fn tuple_pat_name(w: &PyWriter, pat: &syn::Pat) -> Result<String, String> {
    match pat {
        syn::Pat::Ident(i) => {
            if i.subpat.is_some() || i.by_ref.is_some() {
                return Err(w.err(i.span(), "complex tuple element pattern"));
            }
            Ok(i.ident.to_string())
        }
        syn::Pat::Wild(_) => Ok("_".to_owned()),
        other => Err(w.err(
            other.span(),
            "tuple pattern element must be an ident or `_`",
        )),
    }
}

pub fn emit_expr_stmt(w: &mut PyWriter, e: &syn::Expr, tail: Tail) -> Result<(), String> {
    match e {
        syn::Expr::If(i) => emit_if_stmt(w, i, tail),
        syn::Expr::While(wh) => emit_while_stmt(w, wh, tail),
        syn::Expr::Loop(lo) => emit_loop_stmt(w, lo, tail),
        syn::Expr::ForLoop(fl) => emit_for_stmt(w, fl, tail),
        syn::Expr::Match(m) => emit_match_stmt(w, m, tail),
        syn::Expr::Block(b) => emit_block(w, &b.block, tail),
        syn::Expr::Break(b) => {
            if b.expr.is_some() {
                return Err(w.err(b.span(), "break with value not supported"));
            }
            if b.label.is_some() {
                return Err(w.err(b.span(), "labeled break not supported"));
            }
            w.line("break");
            Ok(())
        }
        syn::Expr::Continue(c) => {
            if c.label.is_some() {
                return Err(w.err(c.span(), "labeled continue not supported"));
            }
            w.line("continue");
            Ok(())
        }
        syn::Expr::Return(r) => {
            if let Some(v) = &r.expr {
                let em = expr::emit_expr(w, v)?;
                w.line(&format!("return {}", em.text));
            } else {
                w.line("return");
            }
            Ok(())
        }
        syn::Expr::Assign(a) => emit_assign_stmt(w, a),
        syn::Expr::MethodCall(mc) if try_emit_dict_insert(w, mc)?.is_some() => Ok(()),
        other => {
            let em = expr::emit_expr(w, other)?;
            match tail {
                Tail::Discard => w.line(&em.text),
                Tail::Return => w.line(&format!("return {}", em.text)),
            }
            Ok(())
        }
    }
}

fn try_emit_dict_insert(w: &mut PyWriter, mc: &syn::ExprMethodCall) -> Result<Option<()>, String> {
    if mc.method != "insert" || mc.args.len() != 2 {
        return Ok(None);
    }
    let recv = expr::emit_expr(w, &mc.receiver)?;
    if recv.ty != Ty::Dict {
        return Ok(None);
    }
    let mut args = mc.args.iter();
    let k = expr::emit_expr(w, args.next().unwrap())?;
    let v = expr::emit_expr(w, args.next().unwrap())?;
    w.line(&format!("{}[{}] = {}", recv.text, k.text, v.text));
    Ok(Some(()))
}

fn emit_assign_stmt(w: &mut PyWriter, a: &syn::ExprAssign) -> Result<(), String> {
    let lhs_text = match a.left.as_ref() {
        syn::Expr::Path(p)
            if p.qself.is_none()
                && p.path.leading_colon.is_none()
                && p.path.segments.len() == 1 =>
        {
            p.path.segments[0].ident.to_string()
        }
        syn::Expr::Index(i) => {
            let recv = expr::emit_expr(w, &i.expr)?;
            let idx = expr::emit_expr(w, &i.index)?;
            format!("{}[{}]", recv.text, idx.text)
        }
        syn::Expr::Field(_) => {
            // `obj.field = rhs` — emit the field access as an expression and
            // use it as the LHS.
            expr::emit_expr(w, a.left.as_ref())?.text
        }
        other => {
            return Err(w.err(
                other.span(),
                "assignment LHS must be an ident, index, or field expression",
            ));
        }
    };
    let rhs = expr::emit_expr(w, &a.right)?;
    w.line(&format!("{lhs_text} = {}", rhs.text));
    Ok(())
}

fn emit_tail(w: &mut PyWriter, e: &syn::Expr, tail: Tail) -> Result<(), String> {
    match e {
        syn::Expr::If(i) => emit_if_stmt(w, i, tail),
        syn::Expr::While(wh) => emit_while_stmt(w, wh, tail),
        syn::Expr::Loop(lo) => emit_loop_stmt(w, lo, tail),
        syn::Expr::ForLoop(fl) => emit_for_stmt(w, fl, tail),
        syn::Expr::Match(m) => emit_match_stmt(w, m, tail),
        syn::Expr::Block(b) => emit_block(w, &b.block, tail),
        syn::Expr::Return(r) => {
            if let Some(v) = &r.expr {
                let em = expr::emit_expr(w, v)?;
                w.line(&format!("return {}", em.text));
            } else {
                w.line("return");
            }
            Ok(())
        }
        other => {
            let em = expr::emit_expr(w, other)?;
            match tail {
                Tail::Discard => {
                    if !em.text.is_empty() {
                        w.line(&em.text);
                    }
                }
                Tail::Return => w.line(&format!("return {}", em.text)),
            }
            Ok(())
        }
    }
}

fn emit_if_stmt(w: &mut PyWriter, i: &syn::ExprIf, tail: Tail) -> Result<(), String> {
    if matches!(tail, Tail::Return)
        && let Some(ternary) = ternary_if_simple(w, i)?
    {
        w.line(&format!("return {ternary}"));
        return Ok(());
    }
    let cond = expr::emit_expr(w, &i.cond)?;
    w.line(&format!("if {}:", cond.text));
    w.enter_indent();
    emit_block(w, &i.then_branch, tail)?;
    w.exit_indent();
    if let Some((_, else_branch)) = &i.else_branch {
        emit_else(w, else_branch, tail)?;
    }
    Ok(())
}

fn emit_else(w: &mut PyWriter, else_branch: &syn::Expr, tail: Tail) -> Result<(), String> {
    match else_branch {
        syn::Expr::If(nested) => {
            let cond = expr::emit_expr(w, &nested.cond)?;
            w.line(&format!("elif {}:", cond.text));
            w.enter_indent();
            emit_block(w, &nested.then_branch, tail)?;
            w.exit_indent();
            if let Some((_, deep_else)) = &nested.else_branch {
                emit_else(w, deep_else, tail)?;
            }
            Ok(())
        }
        syn::Expr::Block(b) => {
            w.line("else:");
            w.enter_indent();
            emit_block(w, &b.block, tail)?;
            w.exit_indent();
            Ok(())
        }
        other => Err(w.err(other.span(), "else branch must be a block or another if")),
    }
}

fn ternary_if_simple(w: &mut PyWriter, i: &syn::ExprIf) -> Result<Option<String>, String> {
    let Some((_, else_branch)) = &i.else_branch else {
        return Ok(None);
    };
    let Some(then_inner) = expr::single_tail(&i.then_branch.stmts) else {
        return Ok(None);
    };
    let else_inner: &syn::Expr = match else_branch.as_ref() {
        syn::Expr::Block(b) => match expr::single_tail(&b.block.stmts) {
            Some(e) => e,
            None => return Ok(None),
        },
        syn::Expr::If(_) => return Ok(None),
        other => other,
    };
    let cond = expr::emit_expr(w, &i.cond)?;
    let then_e = expr::emit_expr(w, then_inner)?;
    let else_e = expr::emit_expr(w, else_inner)?;
    Ok(Some(format!(
        "{} if {} else {}",
        ternary_atom(&then_e),
        ternary_atom(&cond),
        ternary_atom(&else_e),
    )))
}

fn ternary_atom(e: &Emitted) -> String {
    if e.prec <= super::expr::Prec::Lambda {
        format!("({})", e.text)
    } else {
        e.text.clone()
    }
}

fn emit_while_stmt(w: &mut PyWriter, wh: &syn::ExprWhile, tail: Tail) -> Result<(), String> {
    if wh.label.is_some() {
        return Err(w.err(wh.span(), "labeled while not supported"));
    }
    let cond = expr::emit_expr(w, &wh.cond)?;
    w.line(&format!("while {}:", cond.text));
    w.enter_indent();
    emit_block(w, &wh.body, Tail::Discard)?;
    w.exit_indent();
    if matches!(tail, Tail::Return) {
        w.line("return");
    }
    Ok(())
}

fn emit_loop_stmt(w: &mut PyWriter, lo: &syn::ExprLoop, tail: Tail) -> Result<(), String> {
    if lo.label.is_some() {
        return Err(w.err(lo.span(), "labeled loop not supported"));
    }
    w.line("while True:");
    w.enter_indent();
    emit_block(w, &lo.body, Tail::Discard)?;
    w.exit_indent();
    if matches!(tail, Tail::Return) {
        w.line("return");
    }
    Ok(())
}

fn emit_for_stmt(w: &mut PyWriter, fl: &syn::ExprForLoop, tail: Tail) -> Result<(), String> {
    if fl.label.is_some() {
        return Err(w.err(fl.span(), "labeled for not supported"));
    }
    let iter_expr = unwrap_iterable(&fl.expr);
    let iter = expr::emit_expr(w, iter_expr)?;
    let pat_text = pat_to_text(w, &fl.pat)?;
    w.line(&format!("for {pat_text} in {}:", iter.text));
    w.enter_indent();
    w.enter_block();
    declare_pat(w, &fl.pat, Ty::Unknown);
    emit_block_inplace(w, &fl.body, Tail::Discard)?;
    w.exit_block();
    w.exit_indent();
    if matches!(tail, Tail::Return) {
        w.line("return");
    }
    Ok(())
}

fn unwrap_iterable(e: &syn::Expr) -> &syn::Expr {
    if let syn::Expr::Reference(r) = e {
        return unwrap_iterable(&r.expr);
    }
    if let syn::Expr::MethodCall(mc) = e
        && mc.method == "iter"
        && mc.args.is_empty()
    {
        return unwrap_iterable(&mc.receiver);
    }
    e
}

fn pat_to_text(w: &PyWriter, pat: &syn::Pat) -> Result<String, String> {
    match pat {
        syn::Pat::Ident(i) => Ok(i.ident.to_string()),
        syn::Pat::Wild(_) => Ok("_".to_owned()),
        syn::Pat::Tuple(t) => {
            let mut parts = Vec::with_capacity(t.elems.len());
            for elem in &t.elems {
                parts.push(pat_to_text(w, elem)?);
            }
            Ok(parts.join(", "))
        }
        other => Err(w.err(
            other.span(),
            "for-loop pattern must be an ident, wildcard, or tuple of those",
        )),
    }
}

fn declare_pat(w: &mut PyWriter, pat: &syn::Pat, ty: Ty) {
    match pat {
        syn::Pat::Ident(i) => w.declare(&i.ident.to_string(), ty),
        syn::Pat::Tuple(t) => {
            for elem in &t.elems {
                declare_pat(w, elem, Ty::Unknown);
            }
        }
        _ => {}
    }
}

fn emit_match_stmt(w: &mut PyWriter, m: &syn::ExprMatch, tail: Tail) -> Result<(), String> {
    let scrutinee = expr::emit_expr(w, &m.expr)?;
    // Reorder: any arm whose pattern matches `None` must come before catch-all
    // `Some(_)` / ident-binding arms, otherwise Python's `case _` will swallow
    // None first. Order is preserved within each group.
    let mut none_arms: Vec<&syn::Arm> = Vec::new();
    let mut other_arms: Vec<&syn::Arm> = Vec::new();
    for arm in &m.arms {
        if super::pat::is_none_pattern(&arm.pat) {
            none_arms.push(arm);
        } else {
            other_arms.push(arm);
        }
    }
    let ordered: Vec<&syn::Arm> = none_arms
        .into_iter()
        .chain(other_arms.into_iter())
        .collect();

    w.line(&format!("match {}:", scrutinee.text));
    w.enter_indent();
    for arm in ordered {
        if arm.guard.is_some() {
            return Err(w.err(
                arm.span(),
                "pattern guards in match are rejected (per spec); pull the condition outside the match",
            ));
        }
        let pat_text = super::pat::pat_to_python(w, &arm.pat)?;
        w.line(&format!("case {pat_text}:"));
        w.enter_indent();
        w.enter_block();
        super::pat::declare_pat_bindings(w, &arm.pat);
        emit_match_arm_body(w, &arm.body, tail)?;
        w.exit_block();
        w.exit_indent();
    }
    w.exit_indent();
    Ok(())
}

fn emit_match_arm_body(w: &mut PyWriter, body: &syn::Expr, tail: Tail) -> Result<(), String> {
    match body {
        syn::Expr::Block(b) => emit_block(w, &b.block, tail),
        other => {
            let em = expr::emit_expr(w, other)?;
            match tail {
                Tail::Discard => {
                    if em.text.is_empty() {
                        w.line("pass");
                    } else {
                        w.line(&em.text);
                    }
                }
                Tail::Return => w.line(&format!("return {}", em.text)),
            }
            Ok(())
        }
    }
}
