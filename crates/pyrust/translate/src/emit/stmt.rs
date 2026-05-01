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
    let attrs: &[syn::Attribute] = match stmt {
        syn::Stmt::Local(l) => &l.attrs,
        syn::Stmt::Expr(e, _) => expr_attrs(e),
        syn::Stmt::Item(_) => &[],
        syn::Stmt::Macro(m) => &m.attrs,
    };
    if !w
        .cfg()
        .item_enabled(attrs)
        .map_err(|e| w.err(stmt.span(), e))?
    {
        return Ok(());
    }
    match stmt {
        syn::Stmt::Local(l) => emit_local(w, l),
        // Stmt::Expr without a semi only reaches here for block-like exprs in
        // non-tail position (the actual block tail is split off by emit_block /
        // emit_top_level_block before iterating). Treat both forms identically.
        syn::Stmt::Expr(e, _) => emit_expr_stmt(w, e, Tail::Discard),
        // Nested items: most are unsupported, but `use X::Y;` inside a
        // function body just brings a name into scope. The Python module
        // already imports the name at the top, so we can drop nested uses
        // silently.
        syn::Stmt::Item(syn::Item::Use(_)) => Ok(()),
        syn::Stmt::Item(i) => Err(w.err(i.span(), "nested items are not supported")),
        syn::Stmt::Macro(m) => emit_stmt_macro(w, m),
    }
}

fn expr_attrs(e: &syn::Expr) -> &[syn::Attribute] {
    match e {
        syn::Expr::Array(x) => &x.attrs,
        syn::Expr::Assign(x) => &x.attrs,
        syn::Expr::Async(x) => &x.attrs,
        syn::Expr::Await(x) => &x.attrs,
        syn::Expr::Binary(x) => &x.attrs,
        syn::Expr::Block(x) => &x.attrs,
        syn::Expr::Break(x) => &x.attrs,
        syn::Expr::Call(x) => &x.attrs,
        syn::Expr::Cast(x) => &x.attrs,
        syn::Expr::Closure(x) => &x.attrs,
        syn::Expr::Const(x) => &x.attrs,
        syn::Expr::Continue(x) => &x.attrs,
        syn::Expr::Field(x) => &x.attrs,
        syn::Expr::ForLoop(x) => &x.attrs,
        syn::Expr::Group(x) => &x.attrs,
        syn::Expr::If(x) => &x.attrs,
        syn::Expr::Index(x) => &x.attrs,
        syn::Expr::Infer(x) => &x.attrs,
        syn::Expr::Let(x) => &x.attrs,
        syn::Expr::Lit(x) => &x.attrs,
        syn::Expr::Loop(x) => &x.attrs,
        syn::Expr::Macro(x) => &x.attrs,
        syn::Expr::Match(x) => &x.attrs,
        syn::Expr::MethodCall(x) => &x.attrs,
        syn::Expr::Paren(x) => &x.attrs,
        syn::Expr::Path(x) => &x.attrs,
        syn::Expr::Range(x) => &x.attrs,
        syn::Expr::RawAddr(x) => &x.attrs,
        syn::Expr::Reference(x) => &x.attrs,
        syn::Expr::Repeat(x) => &x.attrs,
        syn::Expr::Return(x) => &x.attrs,
        syn::Expr::Struct(x) => &x.attrs,
        syn::Expr::Try(x) => &x.attrs,
        syn::Expr::TryBlock(x) => &x.attrs,
        syn::Expr::Tuple(x) => &x.attrs,
        syn::Expr::Unary(x) => &x.attrs,
        syn::Expr::Unsafe(x) => &x.attrs,
        syn::Expr::While(x) => &x.attrs,
        syn::Expr::Yield(x) => &x.attrs,
        _ => &[],
    }
}

fn emit_stmt_macro(w: &mut PyWriter, sm: &syn::StmtMacro) -> Result<(), String> {
    let path = &sm.mac.path;
    if path.leading_colon.is_none() && path.segments.len() == 1 {
        let name = path.segments[0].ident.to_string();
        match name.as_str() {
            "println" => {
                let inner = super::collection::emit_format(w, sm.mac.tokens.clone(), &sm.mac)?;
                w.line(&format!("print({})", inner.text));
                return Ok(());
            }
            "eprintln" => {
                let inner = super::collection::emit_format(w, sm.mac.tokens.clone(), &sm.mac)?;
                w.line(&format!("print({}, file=sys.stderr)", inner.text));
                return Ok(());
            }
            "panic" => {
                let inner = if sm.mac.tokens.is_empty() {
                    String::from("\"panic\"")
                } else {
                    super::collection::emit_format(w, sm.mac.tokens.clone(), &sm.mac)?.text
                };
                w.line(&format!("raise Exception({inner})"));
                return Ok(());
            }
            "unimplemented" => {
                let inner = if sm.mac.tokens.is_empty() {
                    String::new()
                } else {
                    super::collection::emit_format(w, sm.mac.tokens.clone(), &sm.mac)?.text
                };
                if inner.is_empty() {
                    w.line("raise NotImplementedError");
                } else {
                    w.line(&format!("raise NotImplementedError({inner})"));
                }
                return Ok(());
            }
            "unreachable" => {
                let inner = if sm.mac.tokens.is_empty() {
                    String::from("\"unreachable\"")
                } else {
                    super::collection::emit_format(w, sm.mac.tokens.clone(), &sm.mac)?.text
                };
                w.line(&format!("raise AssertionError({inner})"));
                return Ok(());
            }
            _ => {}
        }
    }
    Err(w.err(
        sm.span(),
        format!(
            "unsupported macro statement: {}!",
            super::expr::path_to_string(&sm.mac.path),
        ),
    ))
}

/// Public re-export of `emit_local` so `emit::expr::emit_block_expr` can hoist
/// let bindings out of a multi-statement block in expression position.
pub fn emit_local_public(w: &mut PyWriter, l: &syn::Local) -> Result<(), String> {
    emit_local(w, l)
}

/// True if any branch of the if-chain diverges (return / break / continue)
/// rather than yielding a value. Used to decide whether `let pat = if ...`
/// must be lifted to a statement form.
fn if_has_divergent_branch(i: &syn::ExprIf) -> bool {
    fn branch_diverges(stmts: &[syn::Stmt]) -> bool {
        let Some(last) = stmts.last() else {
            return false;
        };
        match last {
            syn::Stmt::Expr(e, _) => matches!(
                e,
                syn::Expr::Return(_) | syn::Expr::Break(_) | syn::Expr::Continue(_)
            ),
            _ => false,
        }
    }
    if branch_diverges(&i.then_branch.stmts) {
        return true;
    }
    if let Some((_, else_branch)) = &i.else_branch {
        match else_branch.as_ref() {
            syn::Expr::Block(b) => {
                if branch_diverges(&b.block.stmts) {
                    return true;
                }
            }
            syn::Expr::If(nested) => {
                if if_has_divergent_branch(nested) {
                    return true;
                }
            }
            _ => {}
        }
    }
    false
}

/// Emit `let pat = if cond { x } else { y };` as an if-statement that
/// assigns to `pat` in each non-divergent branch.
fn emit_if_into_let(w: &mut PyWriter, bind_pat: &syn::Pat, i: &syn::ExprIf) -> Result<(), String> {
    declare_pat(w, bind_pat, Ty::Unknown);
    let bind_text = pat_to_text(w, bind_pat)?;
    emit_if_chain_into_target(w, &bind_text, i)
}

fn emit_if_chain_into_target(
    w: &mut PyWriter,
    bind_text: &str,
    i: &syn::ExprIf,
) -> Result<(), String> {
    if let Some(cond_text) = emit_let_or_chain(w, &i.cond)? {
        w.line(&format!("if {cond_text}:"));
    } else {
        let cond = expr::emit_expr(w, &i.cond)?;
        w.line(&format!("if {}:", cond.text));
    }
    w.enter_indent();
    w.enter_block();
    emit_branch_into_target(w, bind_text, &i.then_branch.stmts)?;
    w.exit_block();
    w.exit_indent();
    if let Some((_, else_branch)) = &i.else_branch {
        match else_branch.as_ref() {
            syn::Expr::If(nested) => {
                w.line("else:");
                w.enter_indent();
                w.enter_block();
                emit_if_chain_into_target(w, bind_text, nested)?;
                w.exit_block();
                w.exit_indent();
            }
            syn::Expr::Block(b) => {
                w.line("else:");
                w.enter_indent();
                w.enter_block();
                emit_branch_into_target(w, bind_text, &b.block.stmts)?;
                w.exit_block();
                w.exit_indent();
            }
            other => {
                return Err(w.err(other.span(), "else branch must be a block or if-chain"));
            }
        }
    }
    Ok(())
}

fn emit_branch_into_target(
    w: &mut PyWriter,
    bind_text: &str,
    stmts: &[syn::Stmt],
) -> Result<(), String> {
    let (body, tail) = split_tail(stmts);
    for s in body {
        emit_stmt(w, s)?;
    }
    match tail {
        Some(t) => {
            // Divergent tails (return/break/continue) emit as statements;
            // value tails assign to the target.
            match t {
                syn::Expr::Return(_) | syn::Expr::Break(_) | syn::Expr::Continue(_) => {
                    emit_tail(w, t, Tail::Discard)?;
                }
                _ => {
                    let em = expr::emit_expr(w, t)?;
                    w.line(&format!("{bind_text} = {}", em.text));
                }
            }
        }
        None => {}
    }
    Ok(())
}

/// Emit `let pat = match scrut { arm => value, ... };` as a Python `match`
/// statement that assigns into `pat` from each arm's tail expression. Walks
/// the same arm-emit machinery as `emit_match_stmt` but with the binding
/// pattern as the assignment target rather than discarding the value.
fn emit_match_into_let(
    w: &mut PyWriter,
    bind_pat: &syn::Pat,
    m: &syn::ExprMatch,
) -> Result<(), String> {
    // Forward-declare the bindings so they're visible to subsequent
    // statements (Python doesn't have block scoping, so this matches Rust's
    // post-let visibility).
    declare_pat(w, bind_pat, Ty::Unknown);
    let bind_text = pat_to_text(w, bind_pat)?;
    let scrut = expr::emit_expr(w, &m.expr)?;
    w.line(&format!("match {}:", scrut.text));
    w.enter_indent();
    if m.arms.is_empty() {
        w.line("case _:");
        w.enter_indent();
        w.line("pass");
        w.exit_indent();
    }
    // Reorder None-arms first so a catch-all `case x` (the collapsed
    // `Some(x)` pattern) doesn't shadow them. Mirrors `emit_match_stmt`.
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
    for arm in ordered {
        let pat_text = super::pat::pat_to_python(w, &arm.pat)?;
        let some_check = some_binding_check(&arm.pat);
        let case_line = if let Some((_, guard)) = &arm.guard {
            super::pat::declare_pat_bindings(w, &arm.pat);
            let guard_em = expr::emit_expr(w, guard)?;
            let combined = match some_check {
                Some(ck) => format!("{ck} and ({})", guard_em.text),
                None => guard_em.text,
            };
            format!("case {pat_text} if {combined}:")
        } else if let Some(ck) = some_check {
            format!("case {pat_text} if {ck}:")
        } else {
            format!("case {pat_text}:")
        };
        w.line(&case_line);
        w.enter_indent();
        w.enter_block();
        super::pat::declare_pat_bindings(w, &arm.pat);
        // Block bodies may have leading statements (early-return guards)
        // before their tail value. Emit them inline, then assign the tail
        // expression to the outer binding (like emit_branch_into_target).
        match arm.body.as_ref() {
            syn::Expr::Block(b) => {
                emit_branch_into_target(w, &bind_text, &b.block.stmts)?;
            }
            syn::Expr::Return(_) | syn::Expr::Break(_) | syn::Expr::Continue(_) => {
                emit_tail(w, arm.body.as_ref(), Tail::Discard)?;
            }
            other => {
                let body_em = expr::emit_expr(w, other)?;
                if body_em.text.is_empty() {
                    w.line("pass");
                } else {
                    w.line(&format!("{bind_text} = {}", body_em.text));
                }
            }
        }
        w.exit_block();
        w.exit_indent();
    }
    w.exit_indent();
    Ok(())
}

fn emit_local(w: &mut PyWriter, l: &syn::Local) -> Result<(), String> {
    // `let name;` (no initialiser) — Rust forward-declares for later
    // assignment. Python doesn't need pre-declaration; just declare in
    // the writer's scope so subsequent assignments aren't flagged as
    // shadowing, and emit nothing.
    let Some(init) = l.init.as_ref() else {
        if let syn::Pat::Ident(pi) = &l.pat {
            w.declare(&pi.ident.to_string(), Ty::Unknown);
        } else if let syn::Pat::Type(pt) = &l.pat
            && let syn::Pat::Ident(pi) = pt.pat.as_ref()
        {
            w.declare(&pi.ident.to_string(), types::type_from_annotation(&pt.ty));
        }
        return Ok(());
    };
    if let Some((_, diverge)) = init.diverge.as_ref().map(|(t, e)| (t, &**e)) {
        // `let Some(x) = expr else { ... };` — bind x to the unwrapped value;
        // if the expr was None, run the divergent block. Python equivalent:
        //   x = expr
        //   if x is None: <diverge>
        // Single `let Some(x) = expr else { ... };`
        if let syn::Pat::TupleStruct(ts) = &l.pat
            && super::expr::path_to_string(&ts.path).split("::").last() == Some("Some")
            && ts.elems.len() == 1
        {
            let inner = ts.elems.first().unwrap();
            // `let Some(x) = expr else { diverge };`
            if let syn::Pat::Ident(pi) = inner {
                let name = pi.ident.to_string();
                let rhs = expr::emit_expr(w, &init.expr)?;
                w.declare(&name, Ty::Unknown);
                w.line(&format!("{name} = {}", rhs.text));
                w.line(&format!("if {name} is None:"));
                w.enter_indent();
                w.enter_block();
                match diverge {
                    syn::Expr::Block(b) => emit_block_inplace(w, &b.block, Tail::Discard)?,
                    other => {
                        let em = expr::emit_expr(w, other)?;
                        w.line(&em.text);
                    }
                }
                w.exit_block();
                w.exit_indent();
                return Ok(());
            }
            // `let Some((a, b)) = expr else { diverge };` — bind to a tmp,
            // diverge if None, then unpack the tuple components.
            if let syn::Pat::Tuple(t) = inner {
                let mut names: Vec<String> = Vec::new();
                for elem in &t.elems {
                    let name = match elem {
                        syn::Pat::Ident(pi) => pi.ident.to_string(),
                        syn::Pat::Wild(_) => "_".to_string(),
                        _ => {
                            return Err(w.err(
                                elem.span(),
                                "let-else Some((<tuple>)) only supports ident/wildcard sub-patterns",
                            ));
                        }
                    };
                    names.push(name);
                }
                let tmp = "__opt_tuple".to_string();
                let rhs = expr::emit_expr(w, &init.expr)?;
                w.line(&format!("{tmp} = {}", rhs.text));
                w.line(&format!("if {tmp} is None:"));
                w.enter_indent();
                w.enter_block();
                match diverge {
                    syn::Expr::Block(b) => emit_block_inplace(w, &b.block, Tail::Discard)?,
                    other => {
                        let em = expr::emit_expr(w, other)?;
                        w.line(&em.text);
                    }
                }
                w.exit_block();
                w.exit_indent();
                let bind = names.join(", ");
                for n in &names {
                    if n != "_" {
                        w.declare(n, Ty::Unknown);
                    }
                }
                w.line(&format!("{bind} = {tmp}"));
                return Ok(());
            }
            // `let Some(Foo::Bar { f1, f2 }) = expr else { diverge };` — bind
            // the value to a tmp, diverge if None or wrong variant, then
            // unpack the variant fields.
            if let syn::Pat::Struct(s) = inner {
                let class = super::expr::struct_pat_class_for_let(w, s)?;
                let tmp = format!("__opt_{class}");
                let rhs = expr::emit_expr(w, &init.expr)?;
                w.line(&format!("{tmp} = {}", rhs.text));
                w.line(&format!("if not isinstance({tmp}, {class}):"));
                w.enter_indent();
                w.enter_block();
                match diverge {
                    syn::Expr::Block(b) => emit_block_inplace(w, &b.block, Tail::Discard)?,
                    other => {
                        let em = expr::emit_expr(w, other)?;
                        w.line(&em.text);
                    }
                }
                w.exit_block();
                w.exit_indent();
                for fp in &s.fields {
                    let field = match &fp.member {
                        syn::Member::Named(n) => n.to_string(),
                        syn::Member::Unnamed(_) => {
                            return Err(w.err(fp.span(), "unnamed field in let-else struct"));
                        }
                    };
                    let bind_name = match fp.pat.as_ref() {
                        syn::Pat::Ident(pi) => pi.ident.to_string(),
                        _ => continue, // `..` rest or non-ident sub-pattern
                    };
                    w.declare(&bind_name, Ty::Unknown);
                    w.line(&format!("{bind_name} = {tmp}.{field}"));
                }
                return Ok(());
            }
        }
        // Tuple let-else: `let (Some(a), Some(b), ...) = (e1, e2, ...) else { ... };`
        if let syn::Pat::Tuple(pat_tup) = &l.pat
            && let syn::Expr::Tuple(rhs_tup) = &*init.expr
            && pat_tup.elems.len() == rhs_tup.elems.len()
        {
            let mut bindings: Vec<(String, &syn::Expr)> = Vec::new();
            let mut ok = true;
            for (p, e) in pat_tup.elems.iter().zip(rhs_tup.elems.iter()) {
                let syn::Pat::TupleStruct(ts) = p else {
                    ok = false;
                    break;
                };
                if super::expr::path_to_string(&ts.path).split("::").last() != Some("Some")
                    || ts.elems.len() != 1
                {
                    ok = false;
                    break;
                }
                let syn::Pat::Ident(pi) = ts.elems.first().unwrap() else {
                    ok = false;
                    break;
                };
                bindings.push((pi.ident.to_string(), e));
            }
            if ok {
                for (name, e) in &bindings {
                    let em = expr::emit_expr(w, e)?;
                    w.declare(name, Ty::Unknown);
                    w.line(&format!("{name} = {}", em.text));
                }
                let cond = bindings
                    .iter()
                    .map(|(n, _)| format!("{n} is None"))
                    .collect::<Vec<_>>()
                    .join(" or ");
                w.line(&format!("if {cond}:"));
                w.enter_indent();
                w.enter_block();
                match diverge {
                    syn::Expr::Block(b) => emit_block_inplace(w, &b.block, Tail::Discard)?,
                    other => {
                        let em = expr::emit_expr(w, other)?;
                        w.line(&em.text);
                    }
                }
                w.exit_block();
                w.exit_indent();
                return Ok(());
            }
        }
        return Err(w.err(l.span(), "let-else: only `let Some(x) = ... else { ... }` and `let (Some(a), Some(b)) = (e1, e2) else { ... }` are supported"));
    }

    // `let pat = match scrutinee { ... };` — Python has no match-expression,
    // so emit a Python match statement and assign to `pat` inside each arm.
    if let syn::Expr::Match(m) = init.expr.as_ref() {
        return emit_match_into_let(w, &l.pat, m);
    }
    // `let Foo { field1, field2: rename, .. } = expr;` — destructure into
    // separate Python attribute reads. The RHS is evaluated once into a
    // temporary so multi-call/side-effect expressions don't repeat.
    if let syn::Pat::Struct(s) = &l.pat {
        let rhs = expr::emit_expr(w, &init.expr)?;
        let tmp = "__destr".to_string();
        // Avoid the temp when RHS is a simple ident — write attributes
        // directly off the original.
        let base = if matches!(init.expr.as_ref(), syn::Expr::Path(_)) {
            rhs.text.clone()
        } else {
            w.line(&format!("{tmp} = {}", rhs.text));
            tmp
        };
        for fp in &s.fields {
            let field = match &fp.member {
                syn::Member::Named(n) => n.to_string(),
                syn::Member::Unnamed(_) => {
                    return Err(w.err(fp.span(), "unnamed field in let-destructure"));
                }
            };
            let bind_name = match fp.pat.as_ref() {
                syn::Pat::Ident(pi) => pi.ident.to_string(),
                other => {
                    return Err(w.err(other.span(), "let-destructure sub-pattern must be an ident"));
                }
            };
            w.declare(&bind_name, Ty::Unknown);
            w.line(&format!("{bind_name} = {base}.{field}"));
        }
        return Ok(());
    }
    // `let pat = if cond { x } else { y };` — emit as an if-statement that
    // assigns to `pat` in each branch. Necessary when a branch diverges
    // (return / break) and so the if-as-expression form rejects.
    if let syn::Expr::If(i) = init.expr.as_ref()
        && if_has_divergent_branch(i)
    {
        return emit_if_into_let(w, &l.pat, i);
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
            // Rust's `let` introduces a new binding; Python has no block
            // scoping, so the equivalent is plain reassignment. We emit
            // `name = expr` either way and let downstream Python see the
            // last write. (Pyrust used to reject inner-block shadowing as
            // a hard error; in practice the auto-generated dp_step code
            // uses sibling shadowing extensively and the resulting Python
            // is fine because shadowed values aren't read post-scope.)
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
                // `return Err(X)` and `return Err(X.into())` translate to
                // `raise X` — the Python form uses exceptions for the
                // error path that Rust expresses through Result.
                if let Some(inner) = strip_err_call(v) {
                    let em = expr::emit_expr(w, inner)?;
                    w.line(&format!("raise {}", em.text));
                    return Ok(());
                }
                let em = expr::emit_expr(w, v)?;
                w.line(&format!("return {}", em.text));
            } else {
                w.line("return");
            }
            Ok(())
        }
        syn::Expr::Assign(a) => emit_assign_stmt(w, a),
        // `unsafe { ... }` in statement position: emit the inner block's
        // statements directly (the `unsafe` marker has no Python analog).
        syn::Expr::Unsafe(u) => emit_block(w, &u.block, tail),
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
        syn::Expr::Unary(u) if matches!(u.op, syn::UnOp::Deref(_)) => {
            // `*ptr = rhs` — Python has no deref. Treat as plain assignment
            // through the underlying name; the borrow semantics don't carry
            // across to Python so this is a faithful textual translation.
            expr::emit_expr(w, &u.expr)?.text
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
        syn::Expr::Assign(a) => {
            emit_assign_stmt(w, a)?;
            if matches!(tail, Tail::Return) {
                w.line("return");
            }
            Ok(())
        }
        syn::Expr::Continue(_) => {
            w.line("continue");
            Ok(())
        }
        syn::Expr::Break(b) => {
            if b.label.is_some() {
                return Err(w.err(b.span(), "labeled break not supported"));
            }
            if let Some(_v) = &b.expr {
                return Err(w.err(b.span(), "break with value not supported"));
            }
            w.line("break");
            Ok(())
        }
        syn::Expr::Return(r) => {
            if let Some(v) = &r.expr {
                if let Some(inner) = strip_err_call(v) {
                    let em = expr::emit_expr(w, inner)?;
                    w.line(&format!("raise {}", em.text));
                    return Ok(());
                }
                let em = expr::emit_expr(w, v)?;
                w.line(&format!("return {}", em.text));
            } else {
                w.line("return");
            }
            Ok(())
        }
        other => {
            // Tail expression `Err(X)` in a function returning Result —
            // translate to `raise X`.
            if matches!(tail, Tail::Return)
                && let Some(inner) = strip_err_call(other)
            {
                let em = expr::emit_expr(w, inner)?;
                w.line(&format!("raise {}", em.text));
                return Ok(());
            }
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
    if let Some(cond_text) = emit_let_or_chain(w, &i.cond)? {
        w.line(&format!("if {cond_text}:"));
        w.enter_indent();
        emit_block(w, &i.then_branch, tail)?;
        w.exit_indent();
        if let Some((_, else_branch)) = &i.else_branch {
            emit_else(w, else_branch, tail)?;
        }
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

/// Handle `if let Some(p) = expr { ... }` and let-chains
/// `if let Some(p) = expr && cond { ... }`. Emits the binding(s) on
/// preceding lines and returns a Python condition string. Returns Ok(None)
/// if the condition contains no `let` clause.
fn emit_let_or_chain(w: &mut PyWriter, cond: &syn::Expr) -> Result<Option<String>, String> {
    let parts = collect_let_chain(cond);
    if parts.is_empty() {
        return Ok(None);
    }
    // Walk parts: each is either a Let clause or a plain bool expression.
    // Lower the Lets into `__opt = expr` + `__opt is not None` and bind the
    // inner pattern to a fresh local on the same conditional surface.
    let mut conds: Vec<String> = Vec::new();
    for part in parts {
        match part {
            ChainPart::Let { pat, value } => {
                let val_em = expr::emit_expr(w, value)?;
                match pat {
                    syn::Pat::TupleStruct(ts) if some_pat(ts) => {
                        // Strip leading `&` references and `(...)` parens —
                        // they're a Rust source detail, not semantically
                        // meaningful for Python.
                        fn unwrap_ref(p: &syn::Pat) -> &syn::Pat {
                            match p {
                                syn::Pat::Reference(r) => unwrap_ref(&r.pat),
                                syn::Pat::Paren(pp) => unwrap_ref(&pp.pat),
                                _ => p,
                            }
                        }
                        let inner = unwrap_ref(ts.elems.first().unwrap());
                        match inner {
                            syn::Pat::Ident(pi) => {
                                let name = pi.ident.to_string();
                                w.declare(&name, Ty::Unknown);
                                w.line(&format!("{name} = {}", val_em.text));
                                conds.push(format!("{name} is not None"));
                            }
                            syn::Pat::Wild(_) => {
                                conds.push(format!("({}) is not None", val_em.text));
                            }
                            syn::Pat::Path(p) => {
                                // `if let Some(EnumName::Variant) = expr` —
                                // check expr equals EnumName.Variant.
                                let segs: Vec<String> = p
                                    .path
                                    .segments
                                    .iter()
                                    .map(|s| s.ident.to_string())
                                    .collect();
                                let s: Vec<&str> = segs.iter().map(String::as_str).collect();
                                let py_path = match s.as_slice() {
                                    [single] => single.to_string(),
                                    [class, variant] => format!("{class}.{variant}"),
                                    _ => {
                                        return Err(w.err(
                                            p.span(),
                                            format!(
                                                "unsupported if let Some(<path>): {}",
                                                segs.join("::")
                                            ),
                                        ));
                                    }
                                };
                                conds.push(format!("({}) == {py_path}", val_em.text));
                            }
                            syn::Pat::Struct(s) => {
                                // `if let Some(Foo::Bar { team, direction }) = expr`
                                // — emit an isinstance check + per-field bindings.
                                let class = super::expr::struct_pat_class_for_let(w, s)?;
                                let tmp = format!("__opt_{class}");
                                w.line(&format!("{tmp} = {}", val_em.text));
                                let mut field_names = Vec::new();
                                for fp in &s.fields {
                                    let field = match &fp.member {
                                        syn::Member::Named(n) => n.to_string(),
                                        syn::Member::Unnamed(_) => {
                                            return Err(w.err(
                                                fp.span(),
                                                "unnamed field in struct pattern not supported",
                                            ));
                                        }
                                    };
                                    if let syn::Pat::Ident(pi) = &*fp.pat {
                                        let bind_name = pi.ident.to_string();
                                        w.declare(&bind_name, Ty::Unknown);
                                        w.line(&format!(
                                            "{bind_name} = {tmp}.{field} if isinstance({tmp}, {class}) else None"
                                        ));
                                        field_names.push(bind_name);
                                    } else {
                                        return Err(w.err(
                                            fp.span(),
                                            "non-ident sub-pattern in if-let struct pattern",
                                        ));
                                    }
                                }
                                conds.push(format!("isinstance({tmp}, {class})"));
                            }
                            syn::Pat::Or(or_pat) => {
                                // `if let Some(A {f, g} | B {f, g}) = expr` — all alternatives must
                                // be struct-style with the same field names. Emit isinstance check
                                // against `A | B` and bind each shared field by attribute access.
                                let mut classes: Vec<String> = Vec::new();
                                let mut shared_fields: Option<Vec<String>> = None;
                                for case in &or_pat.cases {
                                    let s = match case {
                                        syn::Pat::Struct(s) => s,
                                        other => {
                                            return Err(w.err(
                                                other.span(),
                                                "or-patterns inside Some(...) must all be struct patterns",
                                            ));
                                        }
                                    };
                                    classes.push(super::expr::struct_pat_class_for_let(w, s)?);
                                    let mut these = Vec::new();
                                    for fp in &s.fields {
                                        let field = match &fp.member {
                                            syn::Member::Named(n) => n.to_string(),
                                            syn::Member::Unnamed(_) => {
                                                return Err(w.err(
                                                    fp.span(),
                                                    "unnamed field in struct pattern not supported",
                                                ));
                                            }
                                        };
                                        these.push(field);
                                    }
                                    these.sort();
                                    if let Some(prev) = &shared_fields {
                                        if prev != &these {
                                            return Err(w.err(
                                                or_pat.span(),
                                                "or-pattern struct branches must bind the same field names",
                                            ));
                                        }
                                    } else {
                                        shared_fields = Some(these);
                                    }
                                }
                                let union = classes.join(" | ");
                                let tmp = "__opt_or".to_string();
                                w.line(&format!("{tmp} = {}", val_em.text));
                                let fields = shared_fields.unwrap_or_default();
                                for f in &fields {
                                    w.declare(f, Ty::Unknown);
                                    w.line(&format!(
                                        "{f} = {tmp}.{f} if isinstance({tmp}, {union}) else None"
                                    ));
                                }
                                conds.push(format!("isinstance({tmp}, {union})"));
                            }
                            syn::Pat::Tuple(t) => {
                                // `if let Some((a, b)) = expr` — bind each
                                // component before the if, conditional on
                                // expr not being None.
                                let mut names: Vec<String> = Vec::new();
                                for elem in &t.elems {
                                    if let syn::Pat::Ident(pi) = elem {
                                        names.push(pi.ident.to_string());
                                    } else {
                                        return Err(w.err(
                                            elem.span(),
                                            "if let Some((<tuple>)) only supports ident sub-patterns",
                                        ));
                                    }
                                }
                                let tmp = format!("__opt_{}", names.join("_"));
                                w.line(&format!("{tmp} = {}", val_em.text));
                                for (idx, n) in names.iter().enumerate() {
                                    w.declare(n, Ty::Unknown);
                                    w.line(&format!(
                                        "{n} = {tmp}[{idx}] if {tmp} is not None else None"
                                    ));
                                }
                                conds.push(format!("{tmp} is not None"));
                            }
                            other => {
                                return Err(w.err(
                                    other.span(),
                                    "if let Some(<pattern>) where pattern is not an ident, wildcard, path, or struct not supported",
                                ));
                            }
                        }
                    }
                    syn::Pat::Ident(pi) => {
                        // `if let x = expr` (rare): just bind.
                        let name = pi.ident.to_string();
                        w.declare(&name, Ty::Unknown);
                        w.line(&format!("{name} = {}", val_em.text));
                        conds.push("True".to_string());
                    }
                    other => {
                        return Err(w.err(
                            other.span(),
                            "if let with non-Some pattern not supported (use a match)",
                        ));
                    }
                }
            }
            ChainPart::Cond(e) => {
                let em = expr::emit_expr(w, e)?;
                // Parenthesise: subsequent join with `" and "` would otherwise
                // bind tighter than any inner `or` (Python `and > or`).
                conds.push(format!("({})", em.text));
            }
        }
    }
    Ok(Some(conds.join(" and ")))
}

enum ChainPart<'a> {
    Let {
        pat: &'a syn::Pat,
        value: &'a syn::Expr,
    },
    Cond(&'a syn::Expr),
}

fn collect_let_chain(cond: &syn::Expr) -> Vec<ChainPart<'_>> {
    let mut out = Vec::new();
    fn walk<'a>(e: &'a syn::Expr, out: &mut Vec<ChainPart<'a>>) -> bool {
        match e {
            syn::Expr::Let(l) => {
                out.push(ChainPart::Let {
                    pat: &l.pat,
                    value: &l.expr,
                });
                true
            }
            syn::Expr::Binary(b) if matches!(b.op, syn::BinOp::And(_)) => {
                let l_has = walk(&b.left, out);
                let r_has = walk(&b.right, out);
                l_has || r_has
            }
            syn::Expr::Paren(p) => walk(&p.expr, out),
            other => {
                out.push(ChainPart::Cond(other));
                false
            }
        }
    }
    let saw_let = walk(cond, &mut out);
    if !saw_let {
        return Vec::new();
    }
    out
}

fn some_pat(ts: &syn::PatTupleStruct) -> bool {
    let segs: Vec<String> = ts
        .path
        .segments
        .iter()
        .map(|s| s.ident.to_string())
        .collect();
    let s: Vec<&str> = segs.iter().map(String::as_str).collect();
    matches!(s.as_slice(), ["Some"] | ["Option", "Some"]) && ts.elems.len() == 1
}

fn emit_else(w: &mut PyWriter, else_branch: &syn::Expr, tail: Tail) -> Result<(), String> {
    match else_branch {
        syn::Expr::If(nested) => {
            // `else if let ... = ...` — the let chain emit needs to lay
            // bindings down on lines BEFORE the elif. Python doesn't
            // support a single-line let-chain elif; the cleanest form is:
            //   else:
            //       <bindings>
            //       if <cond>:
            //           ...
            // We get there by pushing a plain "else:", then recursing into
            // the nested if as a normal statement.
            if !collect_let_chain(&nested.cond).is_empty() {
                w.line("else:");
                w.enter_indent();
                w.enter_block();
                emit_if_stmt(w, nested, tail)?;
                w.exit_block();
                w.exit_indent();
                return Ok(());
            }
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
    // `if let ... = ...` can't fold into a ternary because we need to bind
    // a name on a preceding line. Force the full if/else path.
    if !collect_let_chain(&i.cond).is_empty() {
        return Ok(None);
    }
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
    // `while let Some(name) = recv.pop() { body }` — the most common Rust
    // queue-drain idiom — translates to Python's natural form:
    //   while recv:
    //       name = recv.pop()
    //       body
    if let syn::Expr::Let(let_expr) = wh.cond.as_ref()
        && let syn::Pat::TupleStruct(ts) = let_expr.pat.as_ref()
        && super::expr::path_to_string(&ts.path).split("::").last() == Some("Some")
        && ts.elems.len() == 1
        && let syn::Pat::Ident(pi) = ts.elems.first().unwrap()
        && let syn::Expr::MethodCall(mc) = let_expr.expr.as_ref()
        && (mc.method == "pop" || mc.method == "pop_back" || mc.method == "pop_front")
        && mc.args.is_empty()
    {
        let name = pi.ident.to_string();
        let recv = expr::emit_expr(w, &mc.receiver)?;
        // Map `pop_front` to `popleft` for collections.deque parity.
        let pop_method = if mc.method == "pop_front" {
            "popleft"
        } else {
            "pop"
        };
        w.line(&format!("while {}:", recv.text));
        w.enter_indent();
        w.enter_block();
        w.declare(&name, Ty::Unknown);
        w.line(&format!("{name} = {}.{pop_method}()", recv.text));
        emit_block_inplace(w, &wh.body, Tail::Discard)?;
        w.exit_block();
        w.exit_indent();
        if matches!(tail, Tail::Return) {
            w.line("return");
        }
        return Ok(());
    }
    // Generic `while let Some(x) = expr { body }` — guard against None
    // each iteration, breaking out when expr returns None. Uses Python's
    // walrus operator so the condition is also the binding.
    if let syn::Expr::Let(let_expr) = wh.cond.as_ref()
        && let syn::Pat::TupleStruct(ts) = let_expr.pat.as_ref()
        && super::expr::path_to_string(&ts.path).split("::").last() == Some("Some")
        && ts.elems.len() == 1
        && let syn::Pat::Ident(pi) = ts.elems.first().unwrap()
    {
        let name = pi.ident.to_string();
        let val = expr::emit_expr(w, &let_expr.expr)?;
        w.declare(&name, Ty::Unknown);
        w.line(&format!("while ({name} := {}) is not None:", val.text));
        w.enter_indent();
        w.enter_block();
        emit_block_inplace(w, &wh.body, Tail::Discard)?;
        w.exit_block();
        w.exit_indent();
        if matches!(tail, Tail::Return) {
            w.line("return");
        }
        return Ok(());
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
    use syn::spanned::Spanned;
    if fl.label.is_some() {
        return Err(w.err(fl.span(), "labeled for not supported"));
    }
    let iter_expr = unwrap_iterable(&fl.expr);
    // Look up the ra_ap-resolved kind of the iterable BEFORE emitting it,
    // so HashMap/BTreeMap iteration over a 2-tuple pattern picks up
    // `.items()` even when the legacy `Ty` plumbing reports `Unknown`.
    let iter_ra_kind = w.ty_at(iter_expr.span()).cloned();
    let iter = expr::emit_expr(w, iter_expr)?;
    let pat_text = pat_to_text(w, &fl.pat)?;
    let is_tuple_pat = matches!(unwrap_pat_ref(&fl.pat), syn::Pat::Tuple(t) if t.elems.len() == 2);
    let iter_is_map = matches!(iter.ty, Ty::Dict)
        || matches!(
            iter_ra_kind,
            Some(crate::tyctx::TyKind::HashMap | crate::tyctx::TyKind::BTreeMap)
        );
    let iter_text = if is_tuple_pat && iter_is_map {
        format!("{}.items()", iter.text)
    } else {
        iter.text
    };
    w.line(&format!("for {pat_text} in {}:", iter_text));
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

/// Recognise `(Ok-arm, Err-arm)` ordering on a 2-arm match's patterns.
/// Returns `(ok_arm, err_arm)` regardless of source ordering.
fn identify_result_arms<'a>(
    a0: &'a syn::Arm,
    a1: &'a syn::Arm,
) -> Option<(&'a syn::Arm, &'a syn::Arm)> {
    let kind0 = result_arm_kind(&a0.pat);
    let kind1 = result_arm_kind(&a1.pat);
    match (kind0, kind1) {
        (Some("Ok"), Some("Err")) => Some((a0, a1)),
        (Some("Err"), Some("Ok")) => Some((a1, a0)),
        _ => None,
    }
}

fn result_arm_kind(p: &syn::Pat) -> Option<&'static str> {
    let syn::Pat::TupleStruct(ts) = p else {
        return None;
    };
    let segs: Vec<String> = ts
        .path
        .segments
        .iter()
        .map(|s| s.ident.to_string())
        .collect();
    let slice: Vec<&str> = segs.iter().map(String::as_str).collect();
    match slice.as_slice() {
        ["Ok"] | ["Result", "Ok"] => Some("Ok"),
        ["Err"] | ["Result", "Err"] => Some("Err"),
        _ => None,
    }
}

fn emit_result_match_as_try(
    w: &mut PyWriter,
    scrut_expr: &syn::Expr,
    ok_arm: &syn::Arm,
    err_arm: &syn::Arm,
    tail: Tail,
) -> Result<(), String> {
    let err_binding = match &err_arm.pat {
        syn::Pat::TupleStruct(ts) if ts.elems.len() == 1 => match ts.elems.first().unwrap() {
            syn::Pat::Ident(i) => Some(i.ident.to_string()),
            syn::Pat::Wild(_) => None,
            _ => None,
        },
        _ => None,
    };
    // The cambc sandbox's AST validator only allows specific exception
    // names. We use ra_ap to confirm the err type exists for pre-pass
    // bookkeeping, but the emitted handler is `except Exception` so the
    // sandbox accepts the file regardless of the err type's name.
    let scrut = expr::emit_expr(w, scrut_expr)?;
    w.line("try:");
    w.enter_indent();
    w.enter_block();
    if !scrut.text.is_empty() {
        w.line(&scrut.text);
    }
    super::pat::declare_pat_bindings(w, &ok_arm.pat);
    emit_match_arm_body(w, &ok_arm.body, tail)?;
    w.exit_block();
    w.exit_indent();
    let bind = err_binding.clone().unwrap_or_else(|| "_e".to_owned());
    w.line(&format!("except Exception as {bind}:"));
    w.enter_indent();
    w.enter_block();
    if let Some(name) = &err_binding {
        w.declare(name, Ty::Unknown);
    }
    super::pat::declare_pat_bindings(w, &err_arm.pat);
    emit_match_arm_body(w, &err_arm.body, tail)?;
    w.exit_block();
    w.exit_indent();
    Ok(())
}

/// `Err(x)` / `Result::Err(x)` → return `Some(x)` for the inner expression.
/// Used by `return Err(...)` to lower to `raise ...`.
fn strip_err_call(e: &syn::Expr) -> Option<&syn::Expr> {
    let syn::Expr::Call(c) = e else { return None };
    let syn::Expr::Path(p) = c.func.as_ref() else {
        return None;
    };
    if p.qself.is_some() {
        return None;
    }
    let segs: Vec<String> = p
        .path
        .segments
        .iter()
        .map(|s| s.ident.to_string())
        .collect();
    let slice: Vec<&str> = segs.iter().map(String::as_str).collect();
    if !matches!(slice.as_slice(), ["Err"] | ["Result", "Err"]) {
        return None;
    }
    if c.args.len() != 1 {
        return None;
    }
    Some(c.args.first().unwrap())
}

fn unwrap_pat_ref(p: &syn::Pat) -> &syn::Pat {
    match p {
        syn::Pat::Reference(r) => unwrap_pat_ref(&r.pat),
        syn::Pat::Paren(p) => unwrap_pat_ref(&p.pat),
        other => other,
    }
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
        syn::Pat::Reference(r) => pat_to_text(w, &r.pat),
        syn::Pat::Paren(p) => pat_to_text(w, &p.pat),
        // Type-annotated patterns: `(a, b): (T, U)` — strip the annotation.
        syn::Pat::Type(pt) => pat_to_text(w, &pt.pat),
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
        syn::Pat::Reference(r) => declare_pat(w, &r.pat, ty),
        syn::Pat::Paren(p) => declare_pat(w, &p.pat, ty),
        syn::Pat::Type(pt) => declare_pat(w, &pt.pat, ty),
        _ => {}
    }
}

fn emit_match_stmt(w: &mut PyWriter, m: &syn::ExprMatch, tail: Tail) -> Result<(), String> {
    // Special case: `match expr { Ok(...) => ..., Err(e) => ... }` translates
    // to `try: ... except Exception as e: ...` because Result/Err are erased
    // in favour of Python exceptions.
    if m.arms.len() == 2
        && let Some((ok_arm, err_arm)) = identify_result_arms(&m.arms[0], &m.arms[1])
    {
        return emit_result_match_as_try(w, &m.expr, ok_arm, err_arm, tail);
    }
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
        let pat_text = super::pat::pat_to_python(w, &arm.pat)?;
        // `Some(<binding>)` collapses to a bare ident in pat_to_python, but
        // Python's bare ident is a capture that always matches (including
        // `None`). Restore the `is not None` semantics by injecting it into
        // the case's guard.
        let some_check = some_binding_check(&arm.pat);
        let case_line = if let Some((_, guard)) = &arm.guard {
            // Declare any pattern bindings before emitting the guard so
            // the guard expression can refer to them.
            super::pat::declare_pat_bindings(w, &arm.pat);
            let guard_em = expr::emit_expr(w, guard)?;
            let combined = match some_check {
                Some(ck) => format!("{ck} and ({})", guard_em.text),
                None => guard_em.text,
            };
            format!("case {pat_text} if {combined}:")
        } else if let Some(ck) = some_check {
            format!("case {pat_text} if {ck}:")
        } else {
            format!("case {pat_text}:")
        };
        w.line(&case_line);
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

/// `Some(<ident>)` collapses to a bare-ident capture in Python's pattern
/// language, which matches any value including `None`. Recover the
/// not-None check so the arm only fires when the scrutinee was `Some`.
/// Returns the check string (e.g. `"ec is not None"`) or `None` when the
/// pattern doesn't begin with a `Some(<ident>)` shape.
fn some_binding_check(pat: &syn::Pat) -> Option<String> {
    let syn::Pat::TupleStruct(ts) = pat else {
        return None;
    };
    let segs: Vec<String> = ts
        .path
        .segments
        .iter()
        .map(|s| s.ident.to_string())
        .collect();
    let slice: Vec<&str> = segs.iter().map(String::as_str).collect();
    if !matches!(slice.as_slice(), ["Some"] | ["Option", "Some"]) {
        return None;
    }
    if ts.elems.len() != 1 {
        return None;
    }
    let inner = ts.elems.first().unwrap();
    if let syn::Pat::Ident(pi) = inner {
        Some(format!("{} is not None", pi.ident))
    } else {
        None
    }
}

fn emit_match_arm_body(w: &mut PyWriter, body: &syn::Expr, tail: Tail) -> Result<(), String> {
    match body {
        syn::Expr::Block(b) => emit_block(w, &b.block, tail),
        // Match arms whose body is a statement-shaped expression (assignment,
        // method call to a void function, return, etc.) must be emitted as
        // a statement, not wrapped in a `return ...` value.
        syn::Expr::Assign(_)
        | syn::Expr::Return(_)
        | syn::Expr::Break(_)
        | syn::Expr::Continue(_) => emit_expr_stmt(w, body, tail),
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
