use proc_macro2::Span;
use syn::spanned::Spanned;

use super::collection;
use super::types::{Ty, promote_numeric};
use super::writer::PyWriter;

#[derive(Clone, Debug)]
pub struct Emitted {
    pub text: String,
    pub ty: Ty,
    pub prec: Prec,
}

impl Emitted {
    pub fn atomic(text: impl Into<String>, ty: Ty) -> Self {
        Self {
            text: text.into(),
            ty,
            prec: Prec::Atom,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum Prec {
    Lambda,
    Or,
    And,
    Not,
    Cmp,
    BitOr,
    BitXor,
    BitAnd,
    Shift,
    Add,
    Mul,
    Unary,
    Atom,
}

pub fn emit_expr(w: &mut PyWriter, expr: &syn::Expr) -> Result<Emitted, String> {
    match expr {
        syn::Expr::Lit(lit) => emit_lit(w, &lit.lit, expr.span()),
        syn::Expr::Reference(r) => {
            // `&x` and `&mut x` both translate to the inner expression
            // (Python has no concept of borrowing).
            emit_expr(w, &r.expr)
        }
        syn::Expr::Paren(p) => emit_expr(w, &p.expr),
        syn::Expr::Path(p) => emit_path(w, p),
        syn::Expr::Call(c) => emit_call(w, c),
        syn::Expr::Binary(b) => emit_binary(w, b),
        syn::Expr::Unary(u) => emit_unary(w, u),
        syn::Expr::If(i) => emit_if_expr(w, i),
        syn::Expr::Block(b) => emit_block_expr(w, b),
        syn::Expr::Macro(m) => emit_macro_expr(w, m),
        syn::Expr::Array(a) => emit_array_expr(w, a),
        syn::Expr::Repeat(r) => emit_repeat_expr(w, r),
        syn::Expr::Index(i) => emit_index_expr(w, i),
        syn::Expr::MethodCall(m) => emit_method_call(w, m),
        syn::Expr::Tuple(t) => emit_tuple_expr(w, t),
        syn::Expr::Field(f) => emit_field_expr(w, f),
        syn::Expr::Struct(s) => emit_struct_expr(w, s),
        // `expr?` propagates Result errors in Rust; in Python the equivalent
        // GameError just bubbles up as an exception, so the operator drops.
        syn::Expr::Try(t) => emit_expr(w, &t.expr),
        // `x as T` integer/float casts have no Python analog at the value
        // level (Python ints are unbounded). Drop the cast at the text
        // level, but propagate the cast target's type so downstream code
        // (like `/` vs `//` selection) sees Int/Float instead of Unknown.
        syn::Expr::Cast(c) => {
            let inner = emit_expr(w, &c.expr)?;
            let cast_ty = super::types::type_from_annotation(&c.ty);
            // `enum_value as u32` → `int(enum_value)`. Plain `int as u32`
            // round-trips since `int(int)` is identity. We only wrap when
            // the target is a Python-int / Python-float type, which avoids
            // wrapping struct casts (`Foo as Bar` — usually meaningless and
            // already passes through identity).
            let py_target = match super::types::type_to_python_str(&c.ty).ok().as_deref() {
                Some("int") => Some("int"),
                Some("float") => Some("float"),
                _ => None,
            };
            if let Some(name) = py_target {
                return Ok(Emitted {
                    text: format!("{name}({})", inner.text),
                    ty: cast_ty,
                    prec: Prec::Atom,
                });
            }
            Ok(Emitted {
                ty: cast_ty,
                ..inner
            })
        }
        syn::Expr::Range(r) => emit_range_expr(w, r),
        syn::Expr::Closure(c) => emit_closure(w, c),
        syn::Expr::Match(m) => emit_match_expr(w, m),
        // `unsafe { expr }` — Rust marker, no Python analog. Emit the
        // inner expression verbatim. (Statement-position unsafe blocks are
        // handled in `emit_expr_stmt` so prelude let-bindings are hoisted.)
        syn::Expr::Unsafe(u) => emit_block_expr(
            w,
            &syn::ExprBlock {
                attrs: Vec::new(),
                label: None,
                block: u.block.clone(),
            },
        ),
        other => Err(w.err(
            other.span(),
            format!("unsupported expression: {}", expr_kind(other)),
        )),
    }
}

fn emit_struct_expr(w: &mut PyWriter, s: &syn::ExprStruct) -> Result<Emitted, String> {
    if s.rest.is_some() {
        return Err(w.err(s.span(), "struct update syntax `..base` not supported"));
    }
    if s.qself.is_some() {
        return Err(w.err(s.span(), "qualified struct path not supported"));
    }
    let class_name = struct_path_name(w, &s.path)?;
    let mut parts = Vec::with_capacity(s.fields.len());
    for fv in &s.fields {
        let name = match &fv.member {
            syn::Member::Named(n) => n.to_string(),
            syn::Member::Unnamed(_) => {
                return Err(w.err(fv.span(), "tuple struct literals not supported"));
            }
        };
        let value = emit_expr(w, &fv.expr)?;
        parts.push(format!("{name}={}", value.text));
    }
    Ok(Emitted::atomic(
        format!("{class_name}({})", parts.join(", ")),
        Ty::Unknown,
    ))
}

fn struct_path_name(w: &PyWriter, path: &syn::Path) -> Result<String, String> {
    if path.segments.is_empty() {
        return Err(w.err(path.span(), "empty struct path"));
    }
    let segs: Vec<String> = path.segments.iter().map(|s| s.ident.to_string()).collect();
    // 1-segment: identity (with Self → current class).
    if segs.len() == 1 {
        let ident = &segs[0];
        if ident == "Self" {
            return w
                .current_class()
                .map(String::from)
                .ok_or_else(|| w.err(path.span(), "`Self` outside of an impl block"));
        }
        return Ok(ident.clone());
    }
    // 2-segment with non-`crate`/`super` head: sum-type enum variant
    // `Foo::Bar { ... }` → dataclass `FooBar(...)`.
    if segs.len() == 2 && !matches!(segs[0].as_str(), "crate" | "super" | "self") {
        let head = if segs[0] == "Self" {
            w.current_class()
                .map(String::from)
                .ok_or_else(|| w.err(path.span(), "`Self::` outside of an impl block"))?
        } else {
            segs[0].clone()
        };
        return Ok(format!("{head}{}", segs[1]));
    }
    // Longer fully-qualified path (e.g. `crate::a::b::Foo`): emit the leaf
    // name, on the assumption the user's `use` brings it into scope.
    Ok(segs.last().unwrap().clone())
}

fn emit_field_expr(w: &mut PyWriter, f: &syn::ExprField) -> Result<Emitted, String> {
    let recv = emit_expr(w, &f.base)?;
    let recv_text = if recv.prec < Prec::Atom {
        format!("({})", recv.text)
    } else {
        recv.text
    };
    match &f.member {
        syn::Member::Unnamed(idx) => {
            // Tuple field access `t.0` → `t[0]`.
            Ok(Emitted::atomic(
                format!("{recv_text}[{}]", idx.index),
                Ty::Unknown,
            ))
        }
        syn::Member::Named(name) => {
            // Struct field access `obj.field` → `obj.field`.
            Ok(Emitted::atomic(
                format!("{recv_text}.{name}"),
                Ty::Unknown,
            ))
        }
    }
}

fn emit_array_expr(w: &mut PyWriter, a: &syn::ExprArray) -> Result<Emitted, String> {
    let mut parts = Vec::with_capacity(a.elems.len());
    for e in &a.elems {
        parts.push(emit_expr(w, e)?.text);
    }
    Ok(Emitted::atomic(format!("[{}]", parts.join(", ")), Ty::List))
}

fn emit_repeat_expr(w: &mut PyWriter, r: &syn::ExprRepeat) -> Result<Emitted, String> {
    // `[const { expr }; N]` → `[<expr> for _ in range(N)]`. Each iteration
    // evaluates the inner expression freshly, matching Rust's per-slot
    // copy of the const value. Plain `[V] * N` would alias N references
    // to the same Python object, which is wrong for any mutable type.
    if let syn::Expr::Const(c) = r.expr.as_ref() {
        // The const block is a `{ stmts; tail-expr }` body; pull the
        // tail expression out. If the block has multiple statements,
        // we need a more elaborate lowering — bail to single-expr form.
        let block = &c.block;
        if block.stmts.len() == 1
            && let syn::Stmt::Expr(inner_expr, None) = &block.stmts[0]
        {
            let val = emit_expr(w, inner_expr)?;
            let len = emit_expr(w, &r.len)?;
            return Ok(Emitted {
                text: format!("[{} for _ in range({})]", val.text, len.text),
                ty: Ty::List,
                prec: Prec::Atom,
            });
        }
        return Err(w.err(
            r.span(),
            "const-block in array repeat must contain a single expression",
        ));
    }
    let val = emit_expr(w, &r.expr)?;
    let len = emit_expr(w, &r.len)?;
    let val_text = if val.prec < Prec::Mul {
        format!("({})", val.text)
    } else {
        val.text
    };
    let len_text = if len.prec < Prec::Mul {
        format!("({})", len.text)
    } else {
        len.text
    };
    Ok(Emitted {
        text: format!("[{val_text}] * {len_text}"),
        ty: Ty::List,
        prec: Prec::Mul,
    })
}

fn emit_index_expr(w: &mut PyWriter, i: &syn::ExprIndex) -> Result<Emitted, String> {
    let recv = emit_expr(w, &i.expr)?;
    let recv_text = if recv.prec < Prec::Atom {
        format!("({})", recv.text)
    } else {
        recv.text
    };
    // `arr[a..b]` / `arr[a..]` / `arr[..b]` → Python slice syntax `arr[a:b]`.
    if let syn::Expr::Range(r) = i.index.as_ref() {
        let start = match &r.start {
            Some(s) => emit_expr(w, s)?.text,
            None => String::new(),
        };
        let end = match &r.end {
            Some(e) => {
                let t = emit_expr(w, e)?.text;
                if matches!(r.limits, syn::RangeLimits::Closed(_)) {
                    format!("({t}) + 1")
                } else {
                    t
                }
            }
            None => String::new(),
        };
        return Ok(Emitted::atomic(
            format!("{recv_text}[{start}:{end}]"),
            Ty::Unknown,
        ));
    }
    let idx = emit_expr(w, &i.index)?;
    Ok(Emitted::atomic(
        format!("{recv_text}[{}]", idx.text),
        Ty::Unknown,
    ))
}

fn emit_method_call(w: &mut PyWriter, m: &syn::ExprMethodCall) -> Result<Emitted, String> {
    // Method calls pass through verbatim. The translator never inspects
    // method names or guesses receiver types — anything the bot wants
    // rewritten for Python (Vec::push, HashSet::contains, Iterator::map,
    // etc.) must be wrapped in a `pyrust::*!` macro at the call site.
    let recv = emit_expr(w, &m.receiver)?;
    let method = m.method.to_string();
    let arg_exprs: Vec<&syn::Expr> = m.args.iter().collect();
    let mut arg_texts = Vec::with_capacity(arg_exprs.len());
    for a in &arg_exprs {
        arg_texts.push(emit_expr(w, a)?.text);
    }
    let recv_text = if recv.prec < Prec::Atom {
        format!("({})", recv.text)
    } else {
        recv.text
    };
    // Rust-keyword renames: `move_` → `move` (Python keyword in pattern
    // position only; method name is fine in Python).
    let py_method: &str = match method.as_str() {
        "move_" => "move",
        other => other,
    };
    Ok(Emitted::atomic(
        format!("{recv_text}.{py_method}({})", arg_texts.join(", ")),
        Ty::Unknown,
    ))
}

fn paren_at_least(e: &Emitted, ctx: Prec) -> String {
    if e.prec <= ctx {
        format!("({})", e.text)
    } else {
        e.text.clone()
    }
}

fn emit_tuple_expr(w: &mut PyWriter, t: &syn::ExprTuple) -> Result<Emitted, String> {
    let mut parts = Vec::with_capacity(t.elems.len());
    for e in &t.elems {
        parts.push(emit_expr(w, e)?.text);
    }
    let text = match parts.len() {
        0 => "()".to_owned(),
        1 => format!("({},)", parts[0]),
        _ => format!("({})", parts.join(", ")),
    };
    Ok(Emitted::atomic(text, Ty::Unknown))
}

fn else_pat_for_expr(e: &syn::Expr) -> syn::Pat {
    // Synthesize a `Pat::Path` from an expression if it's `None`/`Option::None`,
    // otherwise return a wildcard. Used to detect the "else None" arm of a
    // `find_map`-style closure body.
    if let syn::Expr::Path(p) = e {
        let segs: Vec<String> = p
            .path
            .segments
            .iter()
            .map(|s| s.ident.to_string())
            .collect();
        let s: Vec<&str> = segs.iter().map(String::as_str).collect();
        if matches!(s.as_slice(), ["None"] | ["Option", "None"]) {
            return syn::parse_quote!(None);
        }
    }
    syn::parse_quote!(_)
}

fn is_some_call(c: &syn::ExprCall) -> bool {
    if let syn::Expr::Path(p) = c.func.as_ref() {
        let segs: Vec<String> = p
            .path
            .segments
            .iter()
            .map(|s| s.ident.to_string())
            .collect();
        let s: Vec<&str> = segs.iter().map(String::as_str).collect();
        return matches!(s.as_slice(), ["Some"] | ["Option", "Some"]);
    }
    false
}

fn closure_param_name(pat: &syn::Pat) -> Option<String> {
    match pat {
        syn::Pat::Ident(pi) => Some(pi.ident.to_string()),
        syn::Pat::Type(pt) => closure_param_name(&pt.pat),
        _ => None,
    }
}

fn closure_param_text(pat: &syn::Pat) -> Option<String> {
    match pat {
        syn::Pat::Ident(pi) => Some(pi.ident.to_string()),
        syn::Pat::Wild(_) => Some("_".to_string()),
        syn::Pat::Type(pt) => closure_param_text(&pt.pat),
        syn::Pat::Tuple(t) => {
            // `(x, y)` — Python's for-loop / generator-expr handles tuple
            // unpacking natively as `for x, y in ...`. Emit "x, y" with no
            // parens (the surrounding generator syntax already wraps).
            let mut parts = Vec::with_capacity(t.elems.len());
            for elem in &t.elems {
                parts.push(closure_param_text(elem)?);
            }
            Some(parts.join(", "))
        }
        syn::Pat::Reference(r) => closure_param_text(&r.pat),
        syn::Pat::Paren(p) => closure_param_text(&p.pat),
        _ => None,
    }
}

fn closure_body_expr(c: &syn::ExprClosure) -> Option<&syn::Expr> {
    match c.body.as_ref() {
        syn::Expr::Block(b) => match &b.block.stmts[..] {
            [syn::Stmt::Expr(e, None)] => Some(e),
            _ => None,
        },
        other => Some(other),
    }
}

/// `Option::map(|x| body)` → `((x := opt) is not None and (body)) or None` is
/// wrong (loses falsy-but-non-None bodies). Use the conditional expression:
/// `((x := opt), body)[1] if opt is not None else None`.
/// Walrus + tuple-index keeps it expression-shaped without re-evaluating
/// `opt`.
fn emit_option_map(
    w: &mut PyWriter,
    recv: &Emitted,
    c: &syn::ExprClosure,
) -> Result<Emitted, String> {
    if c.inputs.len() != 1 {
        return Err(w.err(c.span(), "map closure must take exactly one parameter"));
    }
    let param_text = closure_param_text(&c.inputs[0]).ok_or_else(|| {
        w.err(
            c.inputs[0].span(),
            "map closure parameter pattern not supported",
        )
    })?;
    declare_closure_pat_idents(w, &c.inputs[0]);
    let body = closure_body_expr(c)
        .ok_or_else(|| w.err(c.span(), "map closure needs single-expr body"))?;
    let body_em = emit_expr(w, body)?;
    Ok(Emitted::atomic(
        format!(
            "({} if ({param_text} := {}) is not None else None)",
            body_em.text, recv.text
        ),
        Ty::Unknown,
    ))
}

fn emit_iter_map(
    w: &mut PyWriter,
    recv: &Emitted,
    c: &syn::ExprClosure,
) -> Result<Emitted, String> {
    if c.inputs.len() != 1 {
        return Err(w.err(c.span(), "map closure must take exactly one parameter"));
    }
    let param_text = closure_param_text(&c.inputs[0]).ok_or_else(|| {
        w.err(
            c.inputs[0].span(),
            "map closure parameter pattern not supported",
        )
    })?;
    declare_closure_pat_idents(w, &c.inputs[0]);
    let body = closure_body_expr(c)
        .ok_or_else(|| w.err(c.span(), "map closure needs single-expr body"))?;
    let body_em = emit_expr(w, body)?;
    Ok(Emitted::atomic(
        format!("({} for {param_text} in {})", body_em.text, recv.text),
        Ty::Unknown,
    ))
}

fn declare_closure_pat_idents(w: &mut PyWriter, pat: &syn::Pat) {
    match pat {
        syn::Pat::Ident(pi) => w.declare(&pi.ident.to_string(), Ty::Unknown),
        syn::Pat::Type(pt) => declare_closure_pat_idents(w, &pt.pat),
        syn::Pat::Tuple(t) => {
            for elem in &t.elems {
                declare_closure_pat_idents(w, elem);
            }
        }
        syn::Pat::Reference(r) => declare_closure_pat_idents(w, &r.pat),
        syn::Pat::Paren(p) => declare_closure_pat_idents(w, &p.pat),
        _ => {}
    }
}

fn emit_closure(w: &mut PyWriter, c: &syn::ExprClosure) -> Result<Emitted, String> {
    if c.constness.is_some() || c.movability.is_some() || c.asyncness.is_some() {
        return Err(w.err(c.span(), "non-plain closure modifiers not supported"));
    }
    let mut params: Vec<String> = Vec::with_capacity(c.inputs.len());
    let mut declared: Vec<String> = Vec::new();
    fn unwrap_param(pat: &syn::Pat) -> Option<String> {
        match pat {
            syn::Pat::Ident(pi) => Some(pi.ident.to_string()),
            syn::Pat::Wild(_) => Some("_".to_string()),
            syn::Pat::Type(pt) => unwrap_param(&pt.pat),
            syn::Pat::Reference(r) => unwrap_param(&r.pat),
            syn::Pat::Paren(p) => unwrap_param(&p.pat),
            _ => None,
        }
    }
    for input in &c.inputs {
        let name = unwrap_param(input)
            .ok_or_else(|| w.err(input.span(), "closure parameter pattern not supported"))?;
        if name != "_" {
            declared.push(name.clone());
        }
        params.push(name);
    }
    // Closure body: must be a single expression (Python lambda restriction).
    // Multi-statement bodies would need a named def emitted alongside; we
    // reject for now.
    let body_expr: &syn::Expr = c.body.as_ref();
    if let syn::Expr::Block(b) = body_expr {
        let stmts = &b.block.stmts;
        if stmts.len() != 1 {
            return Err(w.err(
                c.span(),
                "multi-statement closure body not supported (only single-expr lambdas)",
            ));
        }
        if let syn::Stmt::Expr(inner, None) = &stmts[0] {
            return emit_lambda(w, &params, &declared, inner);
        }
        return Err(w.err(
            c.span(),
            "closure body block must contain a single tail expression",
        ));
    }
    emit_lambda(w, &params, &declared, body_expr)
}

fn emit_lambda(
    w: &mut PyWriter,
    params: &[String],
    declared: &[String],
    body: &syn::Expr,
) -> Result<Emitted, String> {
    // Closures capture the surrounding scope, so we don't push a frame —
    // but we DO need the parameter names to resolve as locals during body
    // emission. Declare them, emit, then forget (no scope unwind needed —
    // declarations stay in the current frame, but parameter shadowing
    // inside lambdas is rare enough that this is OK in practice).
    for n in declared {
        w.declare(n, Ty::Unknown);
    }
    let body_em = emit_expr(w, body)?;
    let head = if params.is_empty() {
        "lambda: ".to_string()
    } else {
        format!("lambda {}: ", params.join(", "))
    };
    Ok(Emitted {
        text: format!("{head}{}", body_em.text),
        ty: Ty::Unknown,
        prec: Prec::Lambda,
    })
}

/// Translate a `match` expression in value position. Limited to the
/// Some/None two-arm shape that's common in v55: emit as a ternary using
/// the walrus operator to bind the unwrapped value.
fn emit_match_expr(w: &mut PyWriter, m: &syn::ExprMatch) -> Result<Emitted, String> {
    if m.arms.len() == 2 {
        let (some_arm, none_arm) = match (&m.arms[0].pat, &m.arms[1].pat) {
            (syn::Pat::TupleStruct(ts), p)
                if some_pat_path(ts) && super::pat::is_none_pattern(p) =>
            {
                (&m.arms[0], &m.arms[1])
            }
            (p, syn::Pat::TupleStruct(ts))
                if some_pat_path(ts) && super::pat::is_none_pattern(p) =>
            {
                (&m.arms[1], &m.arms[0])
            }
            _ => {
                return Err(w.err(
                    m.span(),
                    "match in expression position must be Some/None or be lifted to a let",
                ));
            }
        };
        if let syn::Pat::TupleStruct(ts) = &some_arm.pat
            && ts.elems.len() == 1
        {
            let inner = ts.elems.first().unwrap();
            let scrut = emit_expr(w, &m.expr)?;
            // Bind the unwrapped value via walrus inside the condition. For
            // ident sub-patterns the bound name is observable in `then`.
            let binding = match inner {
                syn::Pat::Ident(pi) => Some(pi.ident.to_string()),
                syn::Pat::Wild(_) => None,
                other => {
                    return Err(w.err(
                        other.span(),
                        "match Some(<pattern>) only supports ident or wildcard sub-patterns",
                    ));
                }
            };
            if let Some(name) = &binding {
                w.declare(name, Ty::Unknown);
            }
            let then_em = emit_expr(w, &some_arm.body)?;
            let else_em = emit_expr(w, &none_arm.body)?;
            let cond = if let Some(name) = &binding {
                format!("({name} := {}) is not None", scrut.text)
            } else {
                format!("({}) is not None", scrut.text)
            };
            return Ok(Emitted {
                text: format!("({} if {cond} else {})", then_em.text, else_em.text),
                ty: Ty::Unknown,
                prec: Prec::Lambda,
            });
        }
    }
    Err(w.err(
        m.span(),
        "match in expression position not supported (lift to a `let pat = match ...;` statement)",
    ))
}

fn emit_range_expr(w: &mut PyWriter, r: &syn::ExprRange) -> Result<Emitted, String> {
    use syn::RangeLimits;
    let inclusive = matches!(r.limits, RangeLimits::Closed(_));
    let start_text = match &r.start {
        Some(s) => emit_expr(w, s)?.text,
        None => "0".to_string(),
    };
    let end_text = match &r.end {
        Some(e) => {
            let t = emit_expr(w, e)?.text;
            if inclusive { format!("({t}) + 1") } else { t }
        }
        None => {
            return Err(w.err(
                r.span(),
                "unbounded range without upper limit not supported",
            ));
        }
    };
    Ok(Emitted::atomic(
        format!("range({start_text}, {end_text})"),
        Ty::Unknown,
    ))
}

/// Translate `matches!(expr, Pat)` to a Python boolean expression. Common
/// cases:
///   matches!(x, `EnumName::A` | `EnumName::B`)           → `x in (EnumName.A, EnumName.B)`
///   matches!(x, `EnumName::Variant` { .. })            → `isinstance(x, EnumNameVariant)`
///   matches!(x, `EnumName::A` { .. } | `EnumName::B` {.}) → `isinstance(x, EnumNameA | EnumNameB)`
///   matches!(x, Some(_))                              → `x is not None`
///   matches!(x, None)                                 → `x is None`
///   matches!(x, Pat if guard)                         → `(matches expr) and guard`
fn emit_matches(w: &mut PyWriter, em: &syn::ExprMacro) -> Result<Emitted, String> {
    // matches! syntax: `matches!(scrutinee, pattern [if guard])`
    let span = em.span();
    struct MatchesArgs {
        scrutinee: syn::Expr,
        pat: syn::Pat,
        guard: Option<syn::Expr>,
    }
    impl syn::parse::Parse for MatchesArgs {
        fn parse(input: syn::parse::ParseStream) -> syn::Result<Self> {
            let scrutinee: syn::Expr = input.parse()?;
            let _: syn::Token![,] = input.parse()?;
            let pat = syn::Pat::parse_multi_with_leading_vert(input)?;
            let guard = if input.peek(syn::Token![if]) {
                let _: syn::Token![if] = input.parse()?;
                Some(input.parse()?)
            } else {
                None
            };
            // Tolerate a trailing comma — `matches!(x, A | B,)` is valid Rust.
            if input.peek(syn::Token![,]) {
                let _: syn::Token![,] = input.parse()?;
            }
            Ok(Self {
                scrutinee,
                pat,
                guard,
            })
        }
    }
    let args: MatchesArgs =
        syn::parse2(em.mac.tokens.clone()).map_err(|e| w.err(span, format!("matches!: {e}")))?;
    let scrut_em = emit_expr(w, &args.scrutinee)?;
    let scrut = paren_at_least(&scrut_em, Prec::Cmp);
    // When the pattern carries field bindings the guard refers to (e.g.
    // `matches!(x, Some(A {team, ..} | B {team, ..}) if team != my)`), the
    // boolean lowering alone loses the binding. Walrus-bind the inspected
    // value, then call the guard as a lambda receiving each captured field
    // by attribute access. Only the `Some(struct | struct | …)` shape with
    // identical binding names across all alternatives is supported.
    if let Some(g) = &args.guard
        && let Some((classes, bindings)) = some_or_struct_bindings(&args.pat)
    {
        let g_em = emit_expr(w, g)?;
        let class_union = classes.join(" | ");
        let tmp = w.fresh_tmp();
        let attrs: Vec<String> = bindings.iter().map(|b| format!("{tmp}.{b}")).collect();
        let lam_args = bindings.join(", ");
        let lam = format!("(lambda {lam_args}: {})({})", g_em.text, attrs.join(", "));
        let body = format!(
            "(({tmp} := {scrut}) is not None and isinstance({tmp}, {class_union}) and {lam})"
        );
        return Ok(Emitted::atomic(body, Ty::Bool));
    }
    let body = matches_pat_to_bool(w, &scrut, &args.pat)?;
    let with_guard = if let Some(g) = &args.guard {
        let g_em = emit_expr(w, g)?;
        format!("({body}) and ({})", g_em.text)
    } else {
        body
    };
    Ok(Emitted::atomic(format!("({with_guard})"), Ty::Bool))
}

/// Detect `Some(StructPat | StructPat | ...)` where every alternative is a
/// struct pattern that binds the same set of field names. Returns the list
/// of class names (for `isinstance`) and the shared binding names (in the
/// order they appear in the first alternative). Used by `emit_matches` to
/// surface guard-referenced field bindings as lambda parameters.
fn some_or_struct_bindings(pat: &syn::Pat) -> Option<(Vec<String>, Vec<String>)> {
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
    let inner = strip_pat_wrappers(ts.elems.first().unwrap());
    let cases: Vec<&syn::Pat> = match inner {
        syn::Pat::Or(o) => o.cases.iter().collect(),
        other => vec![other],
    };
    let mut classes = Vec::with_capacity(cases.len());
    let mut shared: Option<Vec<String>> = None;
    for c in cases {
        let s = match strip_pat_wrappers(c) {
            syn::Pat::Struct(s) => s,
            _ => return None,
        };
        let last = s.path.segments.last()?.ident.to_string();
        let class_name = match s.path.segments.len() {
            1 => last,
            2 => format!("{}{}", s.path.segments[0].ident, last),
            _ => return None,
        };
        classes.push(class_name);
        let mut these = Vec::new();
        for fp in &s.fields {
            let field = match &fp.member {
                syn::Member::Named(n) => n.to_string(),
                syn::Member::Unnamed(_) => return None,
            };
            // Only collect fields whose binding is a plain ident with the
            // same name as the field — these can be lifted to lambda args.
            if let syn::Pat::Ident(pi) = &*fp.pat
                && pi.ident == field
            {
                these.push(field);
            }
        }
        these.sort();
        match &shared {
            None => shared = Some(these),
            Some(prev) => {
                if prev != &these {
                    return None;
                }
            }
        }
    }
    let shared = shared?;
    if shared.is_empty() {
        return None;
    }
    Some((classes, shared))
}

fn strip_pat_wrappers(p: &syn::Pat) -> &syn::Pat {
    match p {
        syn::Pat::Paren(pp) => strip_pat_wrappers(&pp.pat),
        syn::Pat::Reference(r) => strip_pat_wrappers(&r.pat),
        other => other,
    }
}

fn matches_pat_to_bool(w: &mut PyWriter, scrut: &str, pat: &syn::Pat) -> Result<String, String> {
    match pat {
        syn::Pat::Wild(_) => Ok("True".to_string()),
        syn::Pat::Or(o) => {
            // If every alternative is a "type" pattern (struct-style), join
            // with `|` inside a single isinstance(). Otherwise OR the per-arm
            // booleans.
            let all_struct = o.cases.iter().all(is_struct_pattern);
            if all_struct {
                let mut classes = Vec::with_capacity(o.cases.len());
                for c in &o.cases {
                    classes.push(struct_pat_class(w, c)?);
                }
                Ok(format!("isinstance({scrut}, {})", classes.join(" | ")))
            } else {
                let mut parts = Vec::with_capacity(o.cases.len());
                for c in &o.cases {
                    parts.push(matches_pat_to_bool(w, scrut, c)?);
                }
                Ok(parts.join(" or "))
            }
        }
        syn::Pat::Path(p) => {
            let segs: Vec<String> = p
                .path
                .segments
                .iter()
                .map(|s| s.ident.to_string())
                .collect();
            let s: Vec<&str> = segs.iter().map(String::as_str).collect();
            match s.as_slice() {
                ["None"] | ["Option", "None"] => Ok(format!("{scrut} is None")),
                [single] => Ok(format!("{scrut} == {single}")),
                [class, variant] => Ok(format!("{scrut} == {class}.{variant}")),
                _ => Err(w.err(
                    p.span(),
                    format!("unsupported matches! path pattern: {}", segs.join("::")),
                )),
            }
        }
        syn::Pat::TupleStruct(ts) => {
            let segs: Vec<String> = ts
                .path
                .segments
                .iter()
                .map(|s| s.ident.to_string())
                .collect();
            let s: Vec<&str> = segs.iter().map(String::as_str).collect();
            // matches!(x, Some(_)) → `x is not None`. The inner pattern's
            // structural detail isn't checked — same as Rust's `_`.
            if matches!(s.as_slice(), ["Some"] | ["Option", "Some"]) {
                if ts.elems.len() != 1 {
                    return Err(w.err(ts.span(), "Some(...) pattern needs one element"));
                }
                // Recurse: `Some(pat)` is true iff scrut is not None AND
                // the inner pattern matches the unwrapped value.
                let inner = matches_pat_to_bool(w, scrut, ts.elems.first().unwrap())?;
                if inner == "True" {
                    return Ok(format!("{scrut} is not None"));
                }
                return Ok(format!("({scrut} is not None) and ({inner})"));
            }
            Err(w.err(
                ts.span(),
                format!(
                    "unsupported matches! tuple-struct pattern: {} (only Some(...) is recognized)",
                    segs.join("::")
                ),
            ))
        }
        syn::Pat::Struct(_) => {
            let class = struct_pat_class(w, pat)?;
            Ok(format!("isinstance({scrut}, {class})"))
        }
        syn::Pat::Lit(lit) => {
            let em = emit_expr(w, &syn::Expr::Lit(lit.clone()))?;
            Ok(format!("{scrut} == {}", em.text))
        }
        syn::Pat::Ident(_i) => {
            // A bare ident in matches! is just a binding (always true).
            Ok(format!("({scrut}, _ := {scrut}) and True[1]")).map(|_| "True".to_string())
        }
        syn::Pat::Paren(p) => matches_pat_to_bool(w, scrut, &p.pat),
        syn::Pat::Reference(r) => matches_pat_to_bool(w, scrut, &r.pat),
        other => Err(w.err(
            other.span(),
            format!("unsupported pattern in matches!: {pat:?}"),
        ))
        .map_err(|e| w.err(other.span(), e)),
    }
}

fn is_struct_pattern(pat: &syn::Pat) -> bool {
    match pat {
        syn::Pat::Struct(_) => true,
        syn::Pat::Paren(p) => is_struct_pattern(&p.pat),
        syn::Pat::Reference(r) => is_struct_pattern(&r.pat),
        _ => false,
    }
}

/// Public entry for callers outside this module that already have the
/// inner `PatStruct`. Mirrors `struct_pat_class` but takes the inner type.
pub fn struct_pat_class_for_let(w: &PyWriter, s: &syn::PatStruct) -> Result<String, String> {
    let segs: Vec<String> = s
        .path
        .segments
        .iter()
        .map(|seg| seg.ident.to_string())
        .collect();
    match segs.as_slice() {
        [single] => Ok(single.clone()),
        [head, tail] => Ok(format!("{head}{tail}")),
        _ => Err(w.err(
            s.span(),
            format!("unsupported struct pattern path: {}", segs.join("::")),
        )),
    }
}

/// For `Foo::Bar { .. }`-style patterns, return the dataclass name `FooBar`.
fn struct_pat_class(w: &PyWriter, pat: &syn::Pat) -> Result<String, String> {
    match pat {
        syn::Pat::Struct(s) => {
            let segs: Vec<String> = s
                .path
                .segments
                .iter()
                .map(|seg| seg.ident.to_string())
                .collect();
            match segs.as_slice() {
                [single] => Ok(single.clone()),
                [head, tail] => Ok(format!("{head}{tail}")),
                _ => Err(w.err(
                    s.span(),
                    format!("unsupported struct pattern path: {}", segs.join("::")),
                )),
            }
        }
        syn::Pat::Paren(p) => struct_pat_class(w, &p.pat),
        syn::Pat::Reference(r) => struct_pat_class(w, &r.pat),
        _ => Err(w.err(pat.span(), "expected struct-style pattern")),
    }
}

fn emit_json(
    w: &mut PyWriter,
    tokens: proc_macro2::TokenStream,
    span: Span,
) -> Result<Emitted, String> {
    use proc_macro2::TokenTree;
    // Top-level: parse the entire token stream as one JSON value. The
    // grammar is: object `{...}`, array `[...]`, or a Rust expression.
    let trees: Vec<TokenTree> = tokens.into_iter().collect();
    let text = json_value(w, &trees, span)?;
    Ok(Emitted::atomic(text, Ty::Unknown))
}

fn json_value(
    w: &mut PyWriter,
    trees: &[proc_macro2::TokenTree],
    span: Span,
) -> Result<String, String> {
    use proc_macro2::{Delimiter, TokenTree};
    if trees.is_empty() {
        return Err(w.err(span, "json!(): empty value"));
    }
    // Single Group with Brace = JSON object; Bracket = JSON array.
    if trees.len() == 1
        && let TokenTree::Group(g) = &trees[0]
    {
        let inner: Vec<TokenTree> = g.stream().into_iter().collect();
        match g.delimiter() {
            Delimiter::Brace => return json_object(w, &inner, span),
            Delimiter::Bracket => return json_array(w, &inner, span),
            _ => {}
        }
    }
    // Bare ident `null` is JSON null → Python None.
    if trees.len() == 1
        && let TokenTree::Ident(i) = &trees[0]
        && *i == "null"
    {
        return Ok("None".to_string());
    }
    // Otherwise treat the whole token slice as a Rust expression.
    let stream: proc_macro2::TokenStream = trees.iter().cloned().collect();
    let expr: syn::Expr =
        syn::parse2(stream).map_err(|e| w.err(span, format!("json!() value: {e}")))?;
    Ok(emit_expr(w, &expr)?.text)
}

fn json_object(
    w: &mut PyWriter,
    trees: &[proc_macro2::TokenTree],
    span: Span,
) -> Result<String, String> {
    use proc_macro2::TokenTree;
    let mut entries: Vec<String> = Vec::new();
    let segments = split_top_level_commas(trees);
    for seg in segments {
        if seg.is_empty() {
            continue;
        }
        // Find the top-level `:` that separates key from value.
        let colon_idx = seg
            .iter()
            .position(|tt| matches!(tt, TokenTree::Punct(p) if p.as_char() == ':'))
            .ok_or_else(|| w.err(span, "json!() object entry missing `:`"))?;
        let key_trees = &seg[..colon_idx];
        let val_trees = &seg[colon_idx + 1..];
        let key_text = json_value(w, key_trees, span)?;
        let val_text = json_value(w, val_trees, span)?;
        entries.push(format!("{key_text}: {val_text}"));
    }
    Ok(format!("{{{}}}", entries.join(", ")))
}

fn json_array(
    w: &mut PyWriter,
    trees: &[proc_macro2::TokenTree],
    span: Span,
) -> Result<String, String> {
    let segments = split_top_level_commas(trees);
    let mut parts: Vec<String> = Vec::new();
    for seg in segments {
        if seg.is_empty() {
            continue;
        }
        parts.push(json_value(w, seg, span)?);
    }
    Ok(format!("[{}]", parts.join(", ")))
}

fn split_top_level_commas(trees: &[proc_macro2::TokenTree]) -> Vec<&[proc_macro2::TokenTree]> {
    use proc_macro2::TokenTree;
    let mut segments: Vec<&[proc_macro2::TokenTree]> = Vec::new();
    let mut start = 0;
    for (i, tt) in trees.iter().enumerate() {
        if let TokenTree::Punct(p) = tt
            && p.as_char() == ','
        {
            segments.push(&trees[start..i]);
            start = i + 1;
        }
    }
    segments.push(&trees[start..]);
    segments
}

fn emit_macro_expr(w: &mut PyWriter, em: &syn::ExprMacro) -> Result<Emitted, String> {
    if let Some(out) = emit_pyrust_dsl(w, em)? {
        return Ok(out);
    }
    if let Some(kind) = collection::recognize(&em.mac.path) {
        return collection::emit(w, kind, &em.mac);
    }
    // `cfg!(predicate)` evaluates at translation time to the boolean
    // literal `True` / `False`. Standard Rust dead-code elimination on
    // `if False:` then strips the disabled branch.
    if em.mac.path.is_ident("matches") {
        return emit_matches(w, em);
    }
    // `option_env!("X")` → `os.environ.get("X")`. Returns `str | None` in
    // both Rust (after `is_some`/`unwrap_or`) and Python.
    if em.mac.path.is_ident("option_env") {
        let name: syn::LitStr = syn::parse2(em.mac.tokens.clone())
            .map_err(|e| w.err(em.span(), format!("option_env!: {e}")))?;
        return Ok(Emitted::atomic(
            format!("__import__('os').environ.get(\"{}\")", name.value()),
            Ty::Unknown,
        ));
    }
    if em.mac.path.is_ident("unreachable") {
        return Ok(Emitted::atomic(
            "(_ for _ in ()).throw(AssertionError('unreachable'))".to_string(),
            Ty::Unknown,
        ));
    }
    if em.mac.path.is_ident("unimplemented") {
        return Ok(Emitted::atomic(
            "(_ for _ in ()).throw(NotImplementedError())".to_string(),
            Ty::Unknown,
        ));
    }
    if em.mac.path.is_ident("panic") {
        let msg = if em.mac.tokens.is_empty() {
            "\"panic\"".to_string()
        } else {
            super::collection::emit_format(w, em.mac.tokens.clone(), &em.mac)?.text
        };
        return Ok(Emitted::atomic(
            format!("(_ for _ in ()).throw(Exception({msg}))"),
            Ty::Unknown,
        ));
    }
    // `serde_json::json!(expr | [array] | {object})` — Python doesn't have
    // a `Value` wrapper; emit a plain dict / list / value via a token-tree
    // walker (the macro accepts a JSON-like grammar with Rust expressions
    // for values).
    {
        let segs: Vec<String> = em
            .mac
            .path
            .segments
            .iter()
            .map(|s| s.ident.to_string())
            .collect();
        let s: Vec<&str> = segs.iter().map(String::as_str).collect();
        if matches!(s.as_slice(), ["serde_json", "json"] | ["json"]) {
            return emit_json(w, em.mac.tokens.clone(), em.span());
        }
    }
    if em.mac.path.is_ident("cfg") {
        let meta: syn::Meta = syn::parse2(em.mac.tokens.clone())
            .map_err(|e| w.err(em.span(), format!("cfg!(): {e}")))?;
        let v = w.cfg().eval_meta(&meta).map_err(|e| w.err(em.span(), e))?;
        return Ok(Emitted::atomic(
            if v { "True" } else { "False" }.to_string(),
            Ty::Bool,
        ));
    }
    Err(w.err(
        em.span(),
        format!(
            "unknown macro: {} (only pyrust shim macros are supported)",
            path_to_string(&em.mac.path)
        ),
    ))
}

fn emit_block_expr(w: &mut PyWriter, b: &syn::ExprBlock) -> Result<Emitted, String> {
    let stmts = &b.block.stmts;
    // Hoistable prelude: any number of `let _foo = expr;` bindings (Rust
    // RAII guards conventionally start with `_`) followed by a single tail
    // expression. Emit each let as a Python statement at the surrounding
    // indent, then emit the tail expression as the block's value. This
    // covers the common `let path = { let _g = Scope::new(...); body };`
    // pattern used for debug instrumentation.
    if stmts.len() >= 2 {
        let (last, prelude) = stmts.split_last().unwrap();
        let all_lets = prelude.iter().all(|s| matches!(s, syn::Stmt::Local(_)));
        if all_lets && let syn::Stmt::Expr(inner, None) = last {
            for s in prelude {
                if let syn::Stmt::Local(l) = s {
                    super::stmt::emit_local_public(w, l)?;
                }
            }
            return emit_expr(w, inner);
        }
    }
    if stmts.len() != 1 {
        return Err(w.err(
            b.span(),
            "multi-statement block in expression position not supported",
        ));
    }
    let syn::Stmt::Expr(inner, None) = &stmts[0] else {
        return Err(w.err(
            stmts[0].span(),
            "block in expression position must contain a single tail expression",
        ));
    };
    emit_expr(w, inner)
}

fn emit_path(w: &mut PyWriter, p: &syn::ExprPath) -> Result<Emitted, String> {
    if p.qself.is_some() {
        return Err(w.err(p.span(), "qualified paths not supported"));
    }
    // `#[pyrust::transparent]` enum unit variant — `Foo::None` becomes
    // Python `None`. Match syntactically: if the path's penultimate
    // segment names a `#[pyrust::transparent]` type known via the
    // workspace pre-scan, the trailing segment is a unit variant we can
    // erase. ra_ap-era code consulted type info; we now rely on the
    // syntactic registry built by `scan_pyrust_attrs`.
    if p.path.segments.len() >= 2 {
        let head = &p.path.segments[p.path.segments.len() - 2].ident.to_string();
        if w.is_transparent_type(head) {
            return Ok(Emitted::atomic("None", Ty::Unknown));
        }
    }
    // `serde_json::Value::Null` / `Value::Null` → Python `None`.
    {
        let segs: Vec<String> = p
            .path
            .segments
            .iter()
            .map(|s| s.ident.to_string())
            .collect();
        let slice: Vec<&str> = segs.iter().map(String::as_str).collect();
        if matches!(
            slice.as_slice(),
            ["serde_json", "Value", "Null"] | ["Value", "Null"]
        ) {
            return Ok(Emitted::atomic("None", Ty::Unknown));
        }
    }
    if p.path.leading_colon.is_none() && p.path.segments.len() == 2 {
        let head = p.path.segments[0].ident.to_string();
        let tail = p.path.segments[1].ident.to_string();
        if head == "Option" && tail == "None" {
            return Ok(Emitted::atomic("None", Ty::Unknown));
        }
        // Class-qualified value: enum variant or class constant.
        // For sum-type enums the variant is a dataclass; emit a no-arg
        // constructor `EnumNameVariant()`. For C-style enums (or plain
        // class constants) emit `Class.Variant`.
        let class = if head == "Self" {
            w.current_class()
                .map(String::from)
                .ok_or_else(|| w.err(p.span(), "`Self::` outside of an impl block"))?
        } else {
            head
        };
        // Numeric type constants: `i32::MAX`, `f64::INFINITY`, etc.
        let int_types = matches!(
            class.as_str(),
            "i8" | "i16"
                | "i32"
                | "i64"
                | "i128"
                | "isize"
                | "u8"
                | "u16"
                | "u32"
                | "u64"
                | "u128"
                | "usize"
        );
        let float_types = matches!(class.as_str(), "f32" | "f64");
        if int_types {
            match tail.as_str() {
                "MAX" => return Ok(Emitted::atomic("9223372036854775807", Ty::Int)),
                "MIN" => return Ok(Emitted::atomic("-9223372036854775808", Ty::Int)),
                _ => {}
            }
        }
        if float_types {
            match tail.as_str() {
                "INFINITY" => {
                    return Ok(Emitted::atomic("float(\"inf\")", Ty::Unknown));
                }
                "NEG_INFINITY" => {
                    return Ok(Emitted::atomic("float(\"-inf\")", Ty::Unknown));
                }
                "NAN" => {
                    return Ok(Emitted::atomic("float(\"nan\")", Ty::Unknown));
                }
                "MAX" => {
                    return Ok(Emitted::atomic(
                        "1.7976931348623157e+308".to_owned(),
                        Ty::Unknown,
                    ));
                }
                _ => {}
            }
        }
        if w.is_sum_enum_variant(&class, &tail) {
            return Ok(Emitted::atomic(format!("{class}{tail}()"), Ty::Unknown));
        }
        return Ok(Emitted::atomic(format!("{class}.{tail}"), Ty::Unknown));
    }
    if p.path.leading_colon.is_some() || p.path.segments.len() != 1 {
        // Multi-segment path in value position (e.g. `crate::config::HARDCODE`).
        // Emit the leaf identifier — `use` statements typically expose it
        // at this name in the resulting Python module.
        let segs: Vec<String> = p
            .path
            .segments
            .iter()
            .map(|s| s.ident.to_string())
            .collect();
        if let Some(leaf) = segs.last() {
            let ty = w.lookup(leaf).unwrap_or(Ty::Unknown);
            return Ok(Emitted::atomic(leaf.clone(), ty));
        }
        return Err(w.err(
            p.span(),
            format!(
                "multi-segment path in value position: {}",
                path_to_string(&p.path)
            ),
        ));
    }
    let ident = p.path.segments[0].ident.to_string();
    let ty = w.lookup(&ident).unwrap_or(Ty::Unknown);
    Ok(Emitted::atomic(ident, ty))
}

fn emit_call(w: &mut PyWriter, c: &syn::ExprCall) -> Result<Emitted, String> {
    // `serde_json::Value::*` and `serde_json::Number::from(...)` /
    // `Number::from(...)` are JSON-wrapper constructors. Python's `json`
    // module accepts bare dict/list/str/int, so the wrapper is erased:
    // emit the inner argument and drop the constructor. Path-matched
    // syntactically — no type info needed.
    if c.args.len() == 1
        && let syn::Expr::Path(fp) = c.func.as_ref()
        && fp.qself.is_none()
    {
        let segs: Vec<String> = fp
            .path
            .segments
            .iter()
            .map(|s| s.ident.to_string())
            .collect();
        let slice: Vec<&str> = segs.iter().map(String::as_str).collect();
        let is_serde_wrapper = matches!(
            slice.as_slice(),
            ["serde_json", "Value", "String" | "Number" | "Bool"] |
["Value", "String" | "Number" | "Bool"] | ["serde_json", "Number", "from"] |
["Number", "from"]
        );
        if is_serde_wrapper {
            return emit_expr(w, c.args.first().unwrap());
        }
    }
    // `#[pyrust::transparent]` enum variant constructor — erase the
    // wrapper. `Foo::Direction(d)` becomes `d`. Detected syntactically:
    // the call's func path's penultimate segment is a transparent-type
    // name. Multi-field variants are an error.
    if let syn::Expr::Path(fp) = c.func.as_ref()
        && fp.qself.is_none()
        && fp.path.segments.len() >= 2
    {
        let head = &fp.path.segments[fp.path.segments.len() - 2]
            .ident
            .to_string();
        if w.is_transparent_type(head) {
            if c.args.len() == 1 {
                return emit_expr(w, c.args.first().unwrap());
            }
            return Err(w.err(
                c.span(),
                "transparent enum variant must have exactly one field",
            ));
        }
    }
    let path = match c.func.as_ref() {
        syn::Expr::Path(p) if p.qself.is_none() => &p.path,
        other => {
            return Err(w.err(other.span(), "only path-form calls are supported"));
        }
    };
    let mut arg_emits = Vec::with_capacity(c.args.len());
    for arg in &c.args {
        arg_emits.push(emit_expr(w, arg)?);
    }
    let joined = arg_emits
        .iter()
        .map(|e| e.text.as_str())
        .collect::<Vec<_>>()
        .join(", ");
    // Path-recognised stdlib / serde_json zero-arg constructors. These
    // are the well-known empty-collection idioms — the bot can keep
    // using bare `Vec::new()` etc. in const positions where the
    // `pyrust::vec::new!()` macro can't expand to a const expression.
    {
        let segs: Vec<String> = path.segments.iter().map(|s| s.ident.to_string()).collect();
        let slice: Vec<&str> = segs.iter().map(String::as_str).collect();
        // 1-arg numeric `T::from(x)` constructors — Python `int(x)` /
        // `float(x)`. This is the standard Rust integer-widening /
        // float-promotion idiom and is path-recognized rather than
        // requiring a DSL macro.
        if c.args.len() == 1 {
            let py = match slice.as_slice() {
                ["f32", "from"] | ["f64", "from"] => Some(("float", Ty::Float)),
                ["i8", "from"] | ["i16", "from"] | ["i32", "from"] | ["i64", "from"]
                | ["i128", "from"] | ["isize", "from"] | ["u8", "from"] | ["u16", "from"]
                | ["u32", "from"] | ["u64", "from"] | ["u128", "from"] | ["usize", "from"] => {
                    Some(("int", Ty::Int))
                }
                _ => None,
            };
            if let Some((name, ty)) = py {
                let inner = emit_expr(w, c.args.first().unwrap())?;
                return Ok(Emitted::atomic(format!("{name}({})", inner.text), ty));
            }
        }
        // Zero-arg empty constructor.
        if c.args.is_empty() {
            let py = match slice.as_slice() {
                ["Vec" | "VecDeque", "new"] => Some(("[]", Ty::List)),
                ["HashSet" | "BTreeSet", "new"] => Some(("set()", Ty::Set)),
                ["HashMap" | "BTreeMap", "new"] => Some(("{}", Ty::Dict)),
                ["serde_json", "Map", "new"] | ["Map", "new"] => Some(("{}", Ty::Dict)),
                ["String", "new"] => Some(("\"\"", Ty::Str)),
                _ => None,
            };
            if let Some((py_text, py_ty)) = py {
                return Ok(Emitted::atomic(py_text.to_string(), py_ty));
            }
        }
        // 1-arg `with_capacity(n)` — Python has no capacity hint; drop arg.
        if c.args.len() == 1
            && matches!(
                slice.as_slice(),
                ["Vec" | "VecDeque" | "HashSet" | "HashMap" | "String", "with_capacity"]
            )
        {
            let py = match slice[0] {
                "Vec" | "VecDeque" => "[]",
                "HashSet" => "set()",
                "HashMap" => "{}",
                "String" => "\"\"",
                _ => unreachable!(),
            };
            return Ok(Emitted::atomic(py.to_string(), Ty::List));
        }
    }
    // `Some(x)` / `Option::Some(x)` / `Ok(x)` / `Result::Ok(x)` collapse to
    // their inner value — these are Rust LANGUAGE-level type constructors,
    // not method-name guesses. The Python side has neither wrapper.
    if path.leading_colon.is_none() {
        let names: Vec<String> = path.segments.iter().map(|s| s.ident.to_string()).collect();
        let slice: Vec<&str> = names.iter().map(String::as_str).collect();
        if matches!(
            slice.as_slice(),
            ["Some" | "Ok"] | ["Option", "Some"] | ["Result", "Ok"]
        ) {
            if c.args.len() != 1 {
                return Err(w.err(c.span(), "Some/Ok expects exactly one argument"));
            }
            return Ok(arg_emits.into_iter().next().unwrap());
        }
    }
    if path.leading_colon.is_none() && path.segments.len() == 2 {
        let head = path.segments[0].ident.to_string();
        let tail = path.segments[1].ident.to_string();
        let class_name = if head == "Self" {
            w.current_class()
                .map(String::from)
                .ok_or_else(|| w.err(path.span(), "`Self::` outside of an impl block"))?
        } else {
            head
        };
        // `Trait::method(self, args)` — the trait class isn't emitted (its
        // default methods are folded into each concrete struct), so we
        // rewrite the call into method-call form on the first argument.
        // This is attribute-registry driven, not name-based.
        if w.cfg().trait_registry.contains_key(&class_name) && !c.args.is_empty() {
            let first = arg_emits.first().unwrap().text.clone();
            let rest: Vec<&str> = arg_emits.iter().skip(1).map(|e| e.text.as_str()).collect();
            return Ok(Emitted::atomic(
                format!("{first}.{tail}({})", rest.join(", ")),
                Ty::Unknown,
            ));
        }
        // Sum-type variant constructor: `Foo::Bar(args)` → `FooBar(args)`
        // (matching the dataclass-per-variant lowering in `emit_sum_enum`).
        // Attribute-driven via the sum-enum registry.
        if w.is_sum_enum_variant(&class_name, &tail) {
            let mut parts = Vec::with_capacity(arg_emits.len());
            for (i, em) in arg_emits.iter().enumerate() {
                parts.push(format!("_{i}={}", em.text));
            }
            return Ok(Emitted::atomic(
                format!("{class_name}{tail}({})", parts.join(", ")),
                Ty::Unknown,
            ));
        }
        // `T::new(args)` constructor convention — Rust idiom for any
        // user-defined type. Python equivalent is calling the class
        // itself (`T(args)`), since the bot's `impl T { fn new() }`
        // is the canonical constructor. This is path-recognised, not
        // method-name guessing on a receiver.
        if tail == "new" {
            return Ok(Emitted::atomic(
                format!("{class_name}({joined})"),
                Ty::Unknown,
            ));
        }
        // Generic `Type::method(args)` — pass through as Python class
        // method call. Bot is responsible for wrapping any Rust builtin
        // (String::from, i64::from, ...) in a `pyrust::*!` macro — the
        // translator does not name-match here.
        return Ok(Emitted::atomic(
            format!("{class_name}.{tail}({joined})"),
            Ty::Unknown,
        ));
    }
    if path.leading_colon.is_some() || path.segments.len() != 1 {
        // Multi-segment path call (e.g. `crate::util::directions::delta_to_dir(...)`).
        // Emit the leaf identifier — the user's `use` statements typically
        // expose it at this name.
        let segs: Vec<String> = path.segments.iter().map(|s| s.ident.to_string()).collect();
        if let Some(leaf) = segs.last() {
            let ty = w.lookup(leaf).unwrap_or(Ty::Unknown);
            return Ok(Emitted::atomic(format!("{leaf}({joined})"), ty));
        }
        return Err(w.err(
            path.span(),
            format!(
                "unknown call target: {} (only single-ident user fns and `Type::method` calls are supported; wrap Rust builtins in `pyrust::*!` macros)",
                path_to_string(path)
            ),
        ));
    }
    let name = path.segments[0].ident.to_string();
    let ty = w.lookup(&name).unwrap_or(Ty::Unknown);
    Ok(Emitted::atomic(format!("{name}({joined})"), ty))
}

fn emit_binary(w: &mut PyWriter, b: &syn::ExprBinary) -> Result<Emitted, String> {
    let l = emit_expr(w, &b.left)?;
    let r = emit_expr(w, &b.right)?;
    // Comparing with `None` uses Python identity (`is` / `is not`).
    if matches!(b.op, syn::BinOp::Eq(_) | syn::BinOp::Ne(_)) {
        let is_op = if matches!(b.op, syn::BinOp::Eq(_)) {
            "is"
        } else {
            "is not"
        };
        let other = if l.text == "None" {
            Some(&r)
        } else if r.text == "None" {
            Some(&l)
        } else {
            None
        };
        if let Some(other) = other {
            return Ok(Emitted {
                text: format!("{} {is_op} None", paren_at_least(other, Prec::Cmp)),
                ty: Ty::Bool,
                prec: Prec::Cmp,
            });
        }
    }
    // Compound assignment: `a OP= b` → `a OP= b` (same in Python).
    // Handled separately so we can reuse the same operator table.
    let assign_pair = match b.op {
        syn::BinOp::AddAssign(_) => Some("+"),
        syn::BinOp::SubAssign(_) => Some("-"),
        syn::BinOp::MulAssign(_) => Some("*"),
        syn::BinOp::DivAssign(_) => {
            let both_int = l.ty == Ty::Int && r.ty == Ty::Int;
            let any_float = l.ty == Ty::Float || r.ty == Ty::Float;
            if both_int {
                Some("//")
            } else if any_float {
                Some("/")
            } else {
                return Err(w.err(
                    b.span(),
                    format!(
                        "cannot pick /= vs //= when operand types are unknown ({:?} /= {:?}); add a type annotation",
                        l.ty, r.ty
                    ),
                ));
            }
        }
        syn::BinOp::RemAssign(_) => Some("%"),
        syn::BinOp::BitAndAssign(_) => Some("&"),
        syn::BinOp::BitOrAssign(_) => Some("|"),
        syn::BinOp::BitXorAssign(_) => Some("^"),
        syn::BinOp::ShlAssign(_) => Some("<<"),
        syn::BinOp::ShrAssign(_) => Some(">>"),
        _ => None,
    };
    if let Some(op) = assign_pair {
        return Ok(Emitted {
            text: format!("{} {op}= {}", l.text, r.text),
            ty: Ty::Unit,
            prec: Prec::Lambda,
        });
    }
    let (op_str, prec, result_ty) = match b.op {
        syn::BinOp::Add(_) => ("+", Prec::Add, promote_numeric(l.ty, r.ty)),
        syn::BinOp::Sub(_) => ("-", Prec::Add, promote_numeric(l.ty, r.ty)),
        syn::BinOp::Mul(_) => ("*", Prec::Mul, promote_numeric(l.ty, r.ty)),
        syn::BinOp::Div(_) => {
            // Rust's `/` on integers is integer division; on floats it's
            // float division. If we know either operand is a float, emit
            // Python `/`. Otherwise default to `//` — most Rust code is
            // integer-typed; explicit `as f64` is needed to opt into floats.
            let any_float = l.ty == Ty::Float || r.ty == Ty::Float;
            let (op, ty) = if any_float {
                ("/", Ty::Float)
            } else {
                ("//", Ty::Int)
            };
            (op, Prec::Mul, ty)
        }
        syn::BinOp::Rem(_) => ("%", Prec::Mul, promote_numeric(l.ty, r.ty)),
        syn::BinOp::And(_) => ("and", Prec::And, Ty::Bool),
        syn::BinOp::Or(_) => ("or", Prec::Or, Ty::Bool),
        syn::BinOp::BitAnd(_) => ("&", Prec::BitAnd, promote_numeric(l.ty, r.ty)),
        syn::BinOp::BitOr(_) => ("|", Prec::BitOr, promote_numeric(l.ty, r.ty)),
        syn::BinOp::BitXor(_) => ("^", Prec::BitXor, promote_numeric(l.ty, r.ty)),
        syn::BinOp::Shl(_) => ("<<", Prec::Shift, l.ty),
        syn::BinOp::Shr(_) => (">>", Prec::Shift, l.ty),
        syn::BinOp::Eq(_) => ("==", Prec::Cmp, Ty::Bool),
        syn::BinOp::Ne(_) => ("!=", Prec::Cmp, Ty::Bool),
        syn::BinOp::Lt(_) => ("<", Prec::Cmp, Ty::Bool),
        syn::BinOp::Le(_) => ("<=", Prec::Cmp, Ty::Bool),
        syn::BinOp::Gt(_) => (">", Prec::Cmp, Ty::Bool),
        syn::BinOp::Ge(_) => (">=", Prec::Cmp, Ty::Bool),
        other => {
            return Err(w.err(b.op.span(), format!("unsupported binary op: {other:?}")));
        }
    };
    let lt = paren_left(&l, prec);
    let rt = paren_right(&r, prec);
    Ok(Emitted {
        text: format!("{lt} {op_str} {rt}"),
        ty: result_ty,
        prec,
    })
}

fn emit_unary(w: &mut PyWriter, u: &syn::ExprUnary) -> Result<Emitted, String> {
    let inner = emit_expr(w, &u.expr)?;
    match u.op {
        syn::UnOp::Neg(_) => {
            let inner_text = paren_left(&inner, Prec::Unary);
            Ok(Emitted {
                text: format!("-{inner_text}"),
                ty: inner.ty,
                prec: Prec::Unary,
            })
        }
        syn::UnOp::Not(_) => match inner.ty {
            Ty::Int => {
                let inner_text = paren_left(&inner, Prec::Unary);
                Ok(Emitted {
                    text: format!("~{inner_text}"),
                    ty: inner.ty,
                    prec: Prec::Unary,
                })
            }
            Ty::Bool | Ty::Unknown => {
                let inner_text = paren_left(&inner, Prec::Not);
                Ok(Emitted {
                    text: format!("not {inner_text}"),
                    ty: Ty::Bool,
                    prec: Prec::Not,
                })
            }
            other => Err(w.err(u.span(), format!("cannot apply ! to {other:?}"))),
        },
        syn::UnOp::Deref(_) => Ok(inner),
        other => Err(w.err(u.op.span(), format!("unsupported unary op: {other:?}"))),
    }
}

fn some_pat_path(ts: &syn::PatTupleStruct) -> bool {
    let segs: Vec<String> = ts
        .path
        .segments
        .iter()
        .map(|s| s.ident.to_string())
        .collect();
    let s: Vec<&str> = segs.iter().map(String::as_str).collect();
    matches!(s.as_slice(), ["Some"] | ["Option", "Some"])
}

fn emit_if_expr(w: &mut PyWriter, i: &syn::ExprIf) -> Result<Emitted, String> {
    let Some((_else_tok, else_branch)) = &i.else_branch else {
        return Err(w.err(
            i.span(),
            "if without else cannot appear in expression position",
        ));
    };
    let then_inner = single_tail(&i.then_branch.stmts).ok_or_else(|| {
        w.err(
            i.then_branch.span(),
            "if-as-expression requires a single tail expression in the then branch",
        )
    })?;
    let else_inner: &syn::Expr = match else_branch.as_ref() {
        syn::Expr::Block(b) => single_tail(&b.block.stmts).ok_or_else(|| {
            w.err(
                b.span(),
                "if-as-expression requires a single tail expression in the else branch",
            )
        })?,
        other => other,
    };
    // `if let Some(p) = expr { ... } else { ... }` in value position:
    // emit as a ternary using Python's walrus operator to bind `p` in the
    // surrounding scope. Limited to single-let conditions for now.
    if let syn::Expr::Let(let_expr) = &*i.cond
        && let syn::Pat::TupleStruct(ts) = let_expr.pat.as_ref()
        && some_pat_path(ts)
        && ts.elems.len() == 1
        && let syn::Pat::Ident(pi) = ts.elems.first().unwrap()
    {
        let name = pi.ident.to_string();
        let val = emit_expr(w, &let_expr.expr)?;
        w.declare(&name, Ty::Unknown);
        let then_e = emit_expr(w, then_inner)?;
        let else_e = emit_expr(w, else_inner)?;
        let then_text = paren_in_ternary(&then_e);
        let else_text = paren_in_ternary(&else_e);
        return Ok(Emitted {
            text: format!(
                "{then_text} if (({name} := {}) is not None) else {else_text}",
                val.text
            ),
            ty: Ty::Unknown,
            prec: Prec::Lambda,
        });
    }
    let cond = emit_expr(w, &i.cond)?;
    let then_e = emit_expr(w, then_inner)?;
    let else_e = emit_expr(w, else_inner)?;
    let ty = if then_e.ty == else_e.ty {
        then_e.ty
    } else {
        Ty::Unknown
    };
    let cond_text = paren_in_ternary(&cond);
    let then_text = paren_in_ternary(&then_e);
    let else_text = paren_in_ternary(&else_e);
    Ok(Emitted {
        text: format!("{then_text} if {cond_text} else {else_text}"),
        ty,
        prec: Prec::Lambda,
    })
}

pub fn single_tail(stmts: &[syn::Stmt]) -> Option<&syn::Expr> {
    if stmts.len() == 1
        && let syn::Stmt::Expr(e, None) = &stmts[0] {
            return Some(e);
        }
    None
}

fn paren_in_ternary(e: &Emitted) -> String {
    if e.prec <= Prec::Lambda {
        format!("({})", e.text)
    } else {
        e.text.clone()
    }
}

fn paren_left(e: &Emitted, ctx: Prec) -> String {
    if e.prec < ctx {
        format!("({})", e.text)
    } else {
        e.text.clone()
    }
}

fn paren_right(e: &Emitted, ctx: Prec) -> String {
    if e.prec <= ctx && matches!(ctx, Prec::Add | Prec::Mul | Prec::Shift) {
        format!("({})", e.text)
    } else if e.prec < ctx {
        format!("({})", e.text)
    } else {
        e.text.clone()
    }
}

fn emit_lit(w: &mut PyWriter, lit: &syn::Lit, span: Span) -> Result<Emitted, String> {
    match lit {
        syn::Lit::Str(s) => Ok(Emitted::atomic(py_string_literal(&s.value()), Ty::Str)),
        syn::Lit::Int(i) => {
            if !i.suffix().is_empty() && !is_supported_int_suffix(i.suffix()) {
                return Err(w.err(span, format!("unsupported integer suffix: {}", i.suffix())));
            }
            Ok(Emitted::atomic(i.base10_digits().to_owned(), Ty::Int))
        }
        syn::Lit::Float(f) => {
            if !f.suffix().is_empty() && !matches!(f.suffix(), "f32" | "f64") {
                return Err(w.err(span, format!("unsupported float suffix: {}", f.suffix())));
            }
            Ok(Emitted::atomic(f.base10_digits().to_owned(), Ty::Float))
        }
        syn::Lit::Bool(b) => Ok(Emitted::atomic(
            if b.value { "True" } else { "False" },
            Ty::Bool,
        )),
        other => Err(w.err(span, format!("unsupported literal kind: {other:?}"))),
    }
}

fn is_supported_int_suffix(suffix: &str) -> bool {
    matches!(
        suffix,
        "i8" | "i16"
            | "i32"
            | "i64"
            | "i128"
            | "isize"
            | "u8"
            | "u16"
            | "u32"
            | "u64"
            | "u128"
            | "usize"
    )
}

pub fn path_to_string(path: &syn::Path) -> String {
    let mut s = if path.leading_colon.is_some() {
        String::from("::")
    } else {
        String::new()
    };
    let mut first = true;
    for seg in &path.segments {
        if !first {
            s.push_str("::");
        }
        s.push_str(&seg.ident.to_string());
        first = false;
    }
    s
}

fn py_string_literal(value: &str) -> String {
    let mut s = String::with_capacity(value.len() + 2);
    s.push('"');
    for c in value.chars() {
        match c {
            '\\' => s.push_str("\\\\"),
            '"' => s.push_str("\\\""),
            '\n' => s.push_str("\\n"),
            '\r' => s.push_str("\\r"),
            '\t' => s.push_str("\\t"),
            c if (c as u32) < 0x20 || c == '\x7f' => {
                s.push_str(&format!("\\x{:02x}", c as u32));
            }
            c => s.push(c),
        }
    }
    s.push('"');
    s
}

const fn expr_kind(e: &syn::Expr) -> &'static str {
    match e {
        syn::Expr::Array(_) => "array",
        syn::Expr::Assign(_) => "assignment",
        syn::Expr::Async(_) => "async",
        syn::Expr::Await(_) => "await",
        syn::Expr::Binary(_) => "binary op",
        syn::Expr::Block(_) => "block",
        syn::Expr::Break(_) => "break",
        syn::Expr::Call(_) => "call",
        syn::Expr::Cast(_) => "cast",
        syn::Expr::Closure(_) => "closure",
        syn::Expr::Const(_) => "const",
        syn::Expr::Continue(_) => "continue",
        syn::Expr::Field(_) => "field",
        syn::Expr::ForLoop(_) => "for loop",
        syn::Expr::Group(_) => "group",
        syn::Expr::If(_) => "if",
        syn::Expr::Index(_) => "index",
        syn::Expr::Infer(_) => "infer",
        syn::Expr::Let(_) => "let",
        syn::Expr::Lit(_) => "literal",
        syn::Expr::Loop(_) => "loop",
        syn::Expr::Macro(_) => "macro",
        syn::Expr::Match(_) => "match",
        syn::Expr::MethodCall(_) => "method call",
        syn::Expr::Paren(_) => "paren",
        syn::Expr::Path(_) => "path",
        syn::Expr::Range(_) => "range",
        syn::Expr::RawAddr(_) => "raw addr",
        syn::Expr::Reference(_) => "reference",
        syn::Expr::Repeat(_) => "repeat",
        syn::Expr::Return(_) => "return",
        syn::Expr::Struct(_) => "struct literal",
        syn::Expr::Try(_) => "try",
        syn::Expr::TryBlock(_) => "try block",
        syn::Expr::Tuple(_) => "tuple",
        syn::Expr::Unary(_) => "unary",
        syn::Expr::Unsafe(_) => "unsafe",
        syn::Expr::Verbatim(_) => "verbatim",
        syn::Expr::While(_) => "while",
        syn::Expr::Yield(_) => "yield",
        _ => "expression",
    }
}

// ---- pyrust DSL macro dispatch ----------------------------------------
//
// Each macro under `pyrust::<ns>::<name>` has a fixed Rust expansion (in
// the shim) and a fixed Python emission (here). The translator pattern-
// matches on the full path and parses the macro's tokens as a comma-
// separated expression list (or, for `iter::min_by`, a closure form).
//
// `pyrust::result::try_!(expr)` is special: it expands to a statement
// (`_r = ...; if _r is not None: return _r`), not a value. Currently
// emitted as a multi-line statement when the call appears in statement
// position; in expression position it would have to be hoisted.

/// Public surface for use by `emit_stmt_macro` so a statement-position
/// `pyrust::vec::push!(v, x);` reaches the same dispatch as an
/// expression-position macro.
pub fn emit_pyrust_dsl_for_stmt(
    w: &mut PyWriter,
    em: &syn::ExprMacro,
) -> Result<Option<Emitted>, String> {
    emit_pyrust_dsl(w, em)
}

/// Try the pyrust DSL pattern dispatch. Returns `Some(emitted)` if the
/// macro path matched a known DSL macro, `None` otherwise.
fn emit_pyrust_dsl(w: &mut PyWriter, em: &syn::ExprMacro) -> Result<Option<Emitted>, String> {
    let segs: Vec<String> = em
        .mac
        .path
        .segments
        .iter()
        .map(|s| s.ident.to_string())
        .collect();
    let slice: Vec<&str> = segs.iter().map(String::as_str).collect();
    // Surface forms after the `pyrust` namespace shake-out:
    //
    //   `pyrust::<name>!(...)`            — top-level free function
    //   `pyrust::<ns>::<name>!(...)`      — type-namespaced method
    //   `<ns>::<name>!(...)`              — `use pyrust::<ns>;` brought
    //                                         the type namespace in scope
    //
    // Top-level free functions always carry the `pyrust::` prefix at
    // the call site (they don't have a namespace to bring in scope).
    const TYPE_NS: &[&str] = &["vec", "set", "dict", "string"];
    let tail: Vec<&str> = if slice.first() == Some(&"pyrust") {
        slice[1..].to_vec()
    } else if slice.len() == 2 && TYPE_NS.contains(&slice[0]) {
        slice.clone()
    } else {
        return Ok(None);
    };
    let tokens = em.mac.tokens.clone();
    let display = tail.join("::");

    macro_rules! parse_args {
        () => {
            parse_macro_arg_list(tokens.clone())
                .map_err(|e| w.err(em.span(), format!("{display}!: {e}")))?
        };
    }

    let emit_args = |w: &mut PyWriter, args: &[syn::Expr]| -> Result<Vec<Emitted>, String> {
        args.iter().map(|a| emit_expr(w, a)).collect()
    };

    // Helper: emit a 1-arg "identity passthrough" (Rust expression
    // text only — Python equivalent is just the inner expression).
    let identity = |w: &mut PyWriter, n: &str| -> Result<Emitted, String> {
        let args = parse_macro_arg_list(tokens.clone())
            .map_err(|e| w.err(em.span(), format!("{display}!: {e}")))?;
        if args.len() != 1 {
            return Err(w.err(em.span(), format!("{n}!: expected 1 argument")));
        }
        emit_expr(w, &args[0])
    };

    match tail.as_slice() {
        // ============================================================
        // Top-level: Option / control flow / cast
        // ============================================================
        ["try_"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "try_!: expected 1 argument"));
            }
            let inner = emit_expr(w, &args[0])?;
            let tmp = w.fresh_tmp();
            w.line(&format!("{tmp} = {}", inner.text));
            w.line(&format!("if {tmp} is not None:"));
            w.enter_indent();
            w.line(&format!("return {tmp}"));
            w.exit_indent();
            Ok(Some(Emitted::atomic("None".to_string(), Ty::Unknown)))
        }
        ["unwrap"] => {
            // Option<T>.unwrap() → x. The Some wrapper was already
            // erased on the Rust side (Python sees the bare value).
            Ok(Some(identity(w, "unwrap")?))
        }
        ["expect"] => {
            // Option<T>.expect(msg) → x. Drops the message.
            let args = parse_args!();
            if args.len() != 2 {
                return Err(w.err(em.span(), "expect!: expected (opt, msg)"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(inner))
        }
        ["unwrap_or"] => {
            let args = parse_args!();
            if args.len() != 2 {
                return Err(w.err(em.span(), "unwrap_or!: expected (opt, default)"));
            }
            let opt = emit_expr(w, &args[0])?;
            let dflt = emit_expr(w, &args[1])?;
            Ok(Some(Emitted::atomic(
                format!("({0} if {0} is not None else {1})", opt.text, dflt.text),
                Ty::Unknown,
            )))
        }
        ["is_some"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "is_some!: expected 1 argument"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted {
                text: format!("({} is not None)", inner.text),
                ty: Ty::Bool,
                prec: Prec::Atom,
            }))
        }
        ["is_none"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "is_none!: expected 1 argument"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted {
                text: format!("({} is None)", inner.text),
                ty: Ty::Bool,
                prec: Prec::Atom,
            }))
        }
        ["is_some_and"] => {
            let parsed = syn::parse2::<ClosureArgs>(tokens.clone())
                .map_err(|e| w.err(em.span(), format!("is_some_and!: {e}")))?;
            let opt = emit_expr(w, &parsed.recv)?;
            let body = emit_expr(w, &parsed.body)?;
            let pname = parsed.param.clone();
            Ok(Some(Emitted {
                text: format!(
                    "({0} is not None and (lambda {1}: {2})({0}))",
                    opt.text, pname, body.text
                ),
                ty: Ty::Bool,
                prec: Prec::Atom,
            }))
        }
        ["int"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "int!: expected 1 argument"));
            }
            let emits = emit_args(w, &args)?;
            Ok(Some(Emitted::atomic(
                format!("int({})", emits[0].text),
                Ty::Int,
            )))
        }
        ["float"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "float!: expected 1 argument"));
            }
            let emits = emit_args(w, &args)?;
            Ok(Some(Emitted::atomic(
                format!("float({})", emits[0].text),
                Ty::Float,
            )))
        }
        ["abs"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "abs!: expected 1 argument"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("abs({})", inner.text),
                Ty::Unknown,
            )))
        }
        ["clone"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "clone!: expected 1 argument"));
            }
            let inner = emit_expr(w, &args[0])?;
            // Default to Vec-shaped clone — for HashSet/HashMap clone
            // bot author should use the type-specific macro.
            Ok(Some(Emitted::atomic(
                format!("list({})", inner.text),
                Ty::Unknown,
            )))
        }
        ["drop"] => {
            // `pyrust::drop!(x)` — invoke a `Drop` impl explicitly. In
            // Python the translator emits `x.drop()` so the user's
            // `impl Drop for T` (lowered to a `drop` method) fires.
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "drop!: expected 1 argument"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("{}.drop()", inner.text),
                Ty::Unit,
            )))
        }
        ["round"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "round!: expected 1 argument"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("round({})", inner.text),
                Ty::Float,
            )))
        }
        ["sqrt"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "sqrt!: expected 1 argument"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("math.sqrt({})", inner.text),
                Ty::Float,
            )))
        }
        ["floor"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "floor!: expected 1 argument"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("math.floor({})", inner.text),
                Ty::Float,
            )))
        }
        ["ceil"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "ceil!: expected 1 argument"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("math.ceil({})", inner.text),
                Ty::Float,
            )))
        }

        // ============================================================
        // Iterator: identity / no-op in Python (lists/dicts are iterable)
        // ============================================================
        ["iter" | "into_iter" | "copied" | "cloned" | "into"] => {
            Ok(Some(identity(w, tail[0])?))
        }
        ["collect"] => {
            // Materialize a (lazy) generator/iterator into a list. The
            // Rust expansion is `.collect()` (target type from binding).
            // Python: `list(it)` to force evaluation so subsequent
            // mutations like `.sort()` work.
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "collect!: expected 1 argument"));
            }
            let it = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("list({})", it.text),
                Ty::List,
            )))
        }
        ["enumerate"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "enumerate!: expected 1 argument"));
            }
            let it = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("enumerate({})", it.text),
                Ty::Unknown,
            )))
        }
        ["zip"] => {
            let args = parse_args!();
            if args.len() != 2 {
                return Err(w.err(em.span(), "zip!: expected (a, b)"));
            }
            let a = emit_expr(w, &args[0])?;
            let b = emit_expr(w, &args[1])?;
            Ok(Some(Emitted::atomic(
                format!("zip({}, {})", a.text, b.text),
                Ty::Unknown,
            )))
        }
        ["take"] => {
            let args = parse_args!();
            if args.len() != 2 {
                return Err(w.err(em.span(), "take!: expected (it, n)"));
            }
            let it = emit_expr(w, &args[0])?;
            let n = emit_expr(w, &args[1])?;
            Ok(Some(Emitted::atomic(
                format!("itertools.islice({}, {})", it.text, n.text),
                Ty::Unknown,
            )))
        }
        ["skip"] => {
            let args = parse_args!();
            if args.len() != 2 {
                return Err(w.err(em.span(), "skip!: expected (it, n)"));
            }
            let it = emit_expr(w, &args[0])?;
            let n = emit_expr(w, &args[1])?;
            Ok(Some(Emitted::atomic(
                format!("itertools.islice({}, {}, None)", it.text, n.text),
                Ty::Unknown,
            )))
        }
        ["rev"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "rev!: expected 1 argument"));
            }
            let it = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("reversed({})", it.text),
                Ty::Unknown,
            )))
        }
        ["chain"] => {
            let args = parse_args!();
            if args.len() != 2 {
                return Err(w.err(em.span(), "chain!: expected (a, b)"));
            }
            let a = emit_expr(w, &args[0])?;
            let b = emit_expr(w, &args[1])?;
            Ok(Some(Emitted::atomic(
                format!("itertools.chain({}, {})", a.text, b.text),
                Ty::Unknown,
            )))
        }
        ["map" | "filter" | "filter_map"] => {
            let parsed = syn::parse2::<ClosureArgs>(tokens.clone())
                .map_err(|e| w.err(em.span(), format!("{display}!: {e}")))?;
            let it = emit_expr(w, &parsed.recv)?;
            let body = emit_expr(w, &parsed.body)?;
            let pname = parsed.param.clone();
            let text = match tail[0] {
                "map" => format!("({} for {} in {})", body.text, pname, it.text),
                "filter" => format!("({1} for {1} in {2} if {0})", body.text, pname, it.text),
                "filter_map" => format!(
                    "(__v for {1} in {2} if (__v := {0}) is not None)",
                    body.text, pname, it.text
                ),
                _ => unreachable!(),
            };
            Ok(Some(Emitted::atomic(text, Ty::Unknown)))
        }
        ["find"] => {
            let parsed = syn::parse2::<ClosureArgs>(tokens.clone())
                .map_err(|e| w.err(em.span(), format!("find!: {e}")))?;
            let it = emit_expr(w, &parsed.recv)?;
            let body = emit_expr(w, &parsed.body)?;
            let pname = parsed.param.clone();
            Ok(Some(Emitted::atomic(
                format!(
                    "next(({1} for {1} in {2} if {0}), None)",
                    body.text, pname, it.text
                ),
                Ty::Unknown,
            )))
        }
        ["position"] => {
            let parsed = syn::parse2::<ClosureArgs>(tokens.clone())
                .map_err(|e| w.err(em.span(), format!("position!: {e}")))?;
            let it = emit_expr(w, &parsed.recv)?;
            let body = emit_expr(w, &parsed.body)?;
            let pname = parsed.param.clone();
            Ok(Some(Emitted::atomic(
                format!(
                    "next((__i for __i, {1} in enumerate({2}) if {0}), None)",
                    body.text, pname, it.text
                ),
                Ty::Unknown,
            )))
        }
        ["any" | "all"] => {
            let parsed = syn::parse2::<ClosureArgs>(tokens.clone())
                .map_err(|e| w.err(em.span(), format!("{display}!: {e}")))?;
            let it = emit_expr(w, &parsed.recv)?;
            let body = emit_expr(w, &parsed.body)?;
            let pname = parsed.param.clone();
            let py_fn = tail[0];
            Ok(Some(Emitted::atomic(
                format!("{0}({1} for {2} in {3})", py_fn, body.text, pname, it.text),
                Ty::Bool,
            )))
        }
        ["count"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "count!: expected 1 argument"));
            }
            let it = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("sum(1 for _ in {})", it.text),
                Ty::Int,
            )))
        }
        ["next"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "next!: expected 1 argument"));
            }
            let it = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("next(iter({}), None)", it.text),
                Ty::Unknown,
            )))
        }
        ["rng_choices"] => {
            let args = parse_args!();
            if args.len() != 4 {
                return Err(w.err(em.span(), "rng_choices!: expected (rng, pop, weights, k)"));
            }
            let rng = emit_expr(w, &args[0])?;
            let pop = emit_expr(w, &args[1])?;
            let weights = emit_expr(w, &args[2])?;
            let k = emit_expr(w, &args[3])?;
            Ok(Some(Emitted::atomic(
                format!(
                    "{}.choices({}, {}, k={})",
                    rng.text, pop.text, weights.text, k.text
                ),
                Ty::List,
            )))
        }
        ["sum"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "sum!: expected 1 argument"));
            }
            let it = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(format!("sum({})", it.text), Ty::Int)))
        }
        ["min" | "max"] => {
            let args = parse_args!();
            let py_fn = tail[0];
            if args.len() == 1 {
                let it = emit_expr(w, &args[0])?;
                Ok(Some(Emitted::atomic(
                    format!("({0}({1}) if {1} else None)", py_fn, it.text),
                    Ty::Unknown,
                )))
            } else if args.len() == 2 {
                let a = emit_expr(w, &args[0])?;
                let b = emit_expr(w, &args[1])?;
                Ok(Some(Emitted::atomic(
                    format!("{0}({1}, {2})", py_fn, a.text, b.text),
                    Ty::Unknown,
                )))
            } else {
                Err(w.err(em.span(), "min/max!: expected 1 or 2 arguments"))
            }
        }
        ["min_by" | "max_by"] => {
            let parsed = syn::parse2::<ClosureArgs>(tokens.clone())
                .map_err(|e| w.err(em.span(), format!("{display}!: {e}")))?;
            let it = emit_expr(w, &parsed.recv)?;
            let key = emit_expr(w, &parsed.body)?;
            let pname = parsed.param.clone();
            let py_fn = if tail[0] == "min_by" { "min" } else { "max" };
            Ok(Some(Emitted::atomic(
                format!(
                    "({0}({1}, key=lambda {2}: {3}) if {1} else None)",
                    py_fn, it.text, pname, key.text
                ),
                Ty::Unknown,
            )))
        }
        ["sort"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "sort!: expected (vec)"));
            }
            let v = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("{}.sort()", v.text),
                Ty::Unit,
            )))
        }
        ["sort_by_key"] => {
            let parsed = syn::parse2::<ClosureArgs>(tokens.clone())
                .map_err(|e| w.err(em.span(), format!("sort_by_key!: {e}")))?;
            let v = emit_expr(w, &parsed.recv)?;
            let key = emit_expr(w, &parsed.body)?;
            let pname = parsed.param.clone();
            Ok(Some(Emitted::atomic(
                format!("{}.sort(key=lambda {}: {})", v.text, pname, key.text),
                Ty::Unit,
            )))
        }
        ["sorted"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "sorted!: expected 1 argument"));
            }
            let it = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("sorted({})", it.text),
                Ty::Unknown,
            )))
        }
        ["sorted_by_key"] => {
            let parsed = syn::parse2::<ClosureArgs>(tokens.clone())
                .map_err(|e| w.err(em.span(), format!("sorted_by_key!: {e}")))?;
            let it = emit_expr(w, &parsed.recv)?;
            let key = emit_expr(w, &parsed.body)?;
            let pname = parsed.param.clone();
            Ok(Some(Emitted::atomic(
                format!("sorted({}, key=lambda {}: {})", it.text, pname, key.text),
                Ty::Unknown,
            )))
        }
        ["print"] => {
            let args = parse_args!();
            let emits = emit_args(w, &args)?;
            let joined = emits
                .iter()
                .map(|e| e.text.as_str())
                .collect::<Vec<_>>()
                .join(", ");
            Ok(Some(Emitted::atomic(
                format!("print({joined})"),
                Ty::Unit,
            )))
        }
        ["len"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "len!: expected 1 argument"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("len({})", inner.text),
                Ty::Int,
            )))
        }
        ["to_string"] => {
            // Python: usually `str(x)`, but if x is already a string
            // literal or known str, just pass through. Default to str(x)
            // for safety.
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "to_string!: expected 1 argument"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("str({})", inner.text),
                Ty::Str,
            )))
        }

        // ============================================================
        // vec::*
        // ============================================================
        ["vec", "new"] => Ok(Some(Emitted::atomic("[]".to_string(), Ty::List))),
        ["vec", "push" | "push_back"] => {
            let args = parse_args!();
            if args.len() != 2 {
                return Err(w.err(em.span(), "vec::push(_back)!: expected (vec, item)"));
            }
            let emits = emit_args(w, &args)?;
            Ok(Some(Emitted::atomic(
                format!("{}.append({})", emits[0].text, emits[1].text),
                Ty::Unit,
            )))
        }
        ["vec", "push_front"] => {
            let args = parse_args!();
            if args.len() != 2 {
                return Err(w.err(em.span(), "vec::push_front!: expected (vec, item)"));
            }
            let emits = emit_args(w, &args)?;
            Ok(Some(Emitted::atomic(
                format!("{}.insert(0, {})", emits[0].text, emits[1].text),
                Ty::Unit,
            )))
        }
        ["vec", "pop_front"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "vec::pop_front!: expected (vec)"));
            }
            let emits = emit_args(w, &args)?;
            Ok(Some(Emitted::atomic(
                format!("({0}.pop(0) if {0} else None)", emits[0].text),
                Ty::Unknown,
            )))
        }
        ["vec", "pop_back"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "vec::pop_back!: expected (vec)"));
            }
            let emits = emit_args(w, &args)?;
            Ok(Some(Emitted::atomic(
                format!("({0}.pop() if {0} else None)", emits[0].text),
                Ty::Unknown,
            )))
        }
        ["vec", "swap_remove"] => {
            let args = parse_args!();
            if args.len() != 2 {
                return Err(w.err(em.span(), "vec::swap_remove!: expected (vec, idx)"));
            }
            let emits = emit_args(w, &args)?;
            // O(1) swap with last then pop. Order not preserved.
            // Emit as a tuple-assignment trick to keep it a single
            // expression-shaped statement.
            Ok(Some(Emitted::atomic(
                format!(
                    "({0}.__setitem__({1}, {0}[-1]) or {0}.pop())",
                    emits[0].text, emits[1].text
                ),
                Ty::Unknown,
            )))
        }
        ["vec", "pop"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "vec::pop!: expected (vec)"));
            }
            let emits = emit_args(w, &args)?;
            Ok(Some(Emitted::atomic(
                format!("({0}.pop() if {0} else None)", emits[0].text),
                Ty::Unknown,
            )))
        }
        ["vec", "clear"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "vec::clear!: expected (vec)"));
            }
            let emits = emit_args(w, &args)?;
            Ok(Some(Emitted::atomic(
                format!("{}.clear()", emits[0].text),
                Ty::Unit,
            )))
        }
        ["vec", "len"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "vec::len!: expected (vec)"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("len({})", inner.text),
                Ty::Int,
            )))
        }
        ["vec", "is_empty"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "vec::is_empty!: expected (vec)"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted {
                text: format!("(not {})", inner.text),
                ty: Ty::Bool,
                prec: Prec::Not,
            }))
        }
        ["vec", "contains"] => {
            let args = parse_args!();
            if args.len() != 2 {
                return Err(w.err(em.span(), "vec::contains!: expected (vec, item)"));
            }
            let emits = emit_args(w, &args)?;
            Ok(Some(Emitted {
                text: format!("({} in {})", emits[1].text, emits[0].text),
                ty: Ty::Bool,
                prec: Prec::Atom,
            }))
        }
        ["vec", "extend"] => {
            let args = parse_args!();
            if args.len() != 2 {
                return Err(w.err(em.span(), "vec::extend!: expected (vec, other)"));
            }
            let emits = emit_args(w, &args)?;
            Ok(Some(Emitted::atomic(
                format!("{}.extend({})", emits[0].text, emits[1].text),
                Ty::Unit,
            )))
        }

        // ============================================================
        // set::*
        // ============================================================
        ["set", "new"] => Ok(Some(Emitted::atomic("set()".to_string(), Ty::Set))),
        ["set", "clone"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "set::clone!: expected (set)"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("set({})", inner.text),
                Ty::Set,
            )))
        }
        ["set", "add"] => {
            let args = parse_args!();
            if args.len() != 2 {
                return Err(w.err(em.span(), "set::add!: expected (set, item)"));
            }
            let emits = emit_args(w, &args)?;
            Ok(Some(Emitted::atomic(
                format!("{}.add({})", emits[0].text, emits[1].text),
                Ty::Bool,
            )))
        }
        ["set" | "dict", "contains"] => {
            let args = parse_args!();
            if args.len() != 2 {
                return Err(w.err(em.span(), "contains!: expected (collection, item)"));
            }
            let emits = emit_args(w, &args)?;
            Ok(Some(Emitted {
                text: format!("({} in {})", emits[1].text, emits[0].text),
                ty: Ty::Bool,
                prec: Prec::Atom,
            }))
        }
        ["set", "remove"] => {
            let args = parse_args!();
            if args.len() != 2 {
                return Err(w.err(em.span(), "set::remove!: expected (set, item)"));
            }
            let emits = emit_args(w, &args)?;
            Ok(Some(Emitted::atomic(
                format!("{}.discard({})", emits[0].text, emits[1].text),
                Ty::Unit,
            )))
        }
        ["set", "len"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "set::len!: expected (set)"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("len({})", inner.text),
                Ty::Int,
            )))
        }
        ["set", "is_empty"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "set::is_empty!: expected (set)"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted {
                text: format!("(not {})", inner.text),
                ty: Ty::Bool,
                prec: Prec::Not,
            }))
        }
        ["set", "clear"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "set::clear!: expected (set)"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("{}.clear()", inner.text),
                Ty::Unit,
            )))
        }
        ["set", "difference"] => {
            let args = parse_args!();
            if args.len() != 2 {
                return Err(w.err(em.span(), "set::difference!: expected (a, b)"));
            }
            let emits = emit_args(w, &args)?;
            Ok(Some(Emitted::atomic(
                format!("({} - {})", emits[0].text, emits[1].text),
                Ty::Unknown,
            )))
        }

        // ============================================================
        // dict::*
        // ============================================================
        ["dict", "new"] => Ok(Some(Emitted::atomic("{}".to_string(), Ty::Dict))),
        ["dict", "insert"] => {
            let args = parse_args!();
            if args.len() != 3 {
                return Err(w.err(em.span(), "dict::insert!: expected (dict, key, value)"));
            }
            let emits = emit_args(w, &args)?;
            Ok(Some(Emitted::atomic(
                format!("{}[{}] = {}", emits[0].text, emits[1].text, emits[2].text),
                Ty::Unit,
            )))
        }
        ["dict", "get"] => {
            let args = parse_args!();
            let emits = emit_args(w, &args)?;
            let text = match emits.len() {
                2 => format!("{}.get({})", emits[0].text, emits[1].text),
                3 => format!(
                    "{}.get({}, {})",
                    emits[0].text, emits[1].text, emits[2].text
                ),
                _ => return Err(w.err(em.span(), "dict::get!: expected 2 or 3 arguments")),
            };
            Ok(Some(Emitted::atomic(text, Ty::Unknown)))
        }
        ["dict", "remove"] => {
            let args = parse_args!();
            if args.len() != 2 {
                return Err(w.err(em.span(), "dict::remove!: expected (dict, key)"));
            }
            let emits = emit_args(w, &args)?;
            Ok(Some(Emitted::atomic(
                format!("{}.pop({}, None)", emits[0].text, emits[1].text),
                Ty::Unknown,
            )))
        }
        ["dict", "len"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "dict::len!: expected (dict)"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("len({})", inner.text),
                Ty::Int,
            )))
        }
        ["dict", "is_empty"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "dict::is_empty!: expected (dict)"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted {
                text: format!("(not {})", inner.text),
                ty: Ty::Bool,
                prec: Prec::Not,
            }))
        }
        ["dict", "clear"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "dict::clear!: expected (dict)"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("{}.clear()", inner.text),
                Ty::Unit,
            )))
        }
        ["dict", "items"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "dict::items!: expected (dict)"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("{}.items()", inner.text),
                Ty::Unknown,
            )))
        }
        ["dict", "keys"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "dict::keys!: expected (dict)"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("{}.keys()", inner.text),
                Ty::Unknown,
            )))
        }
        ["dict", "values"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "dict::values!: expected (dict)"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("{}.values()", inner.text),
                Ty::Unknown,
            )))
        }

        // ============================================================
        // string::*
        // ============================================================
        ["string", "new"] => Ok(Some(Emitted::atomic("\"\"".to_string(), Ty::Str))),
        ["string", "clear"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "string::clear!: expected (s)"));
            }
            let emits = emit_args(w, &args)?;
            Ok(Some(Emitted::atomic(
                format!("{} = \"\"", emits[0].text),
                Ty::Unit,
            )))
        }
        ["string", "len"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "string::len!: expected (s)"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted::atomic(
                format!("len({})", inner.text),
                Ty::Int,
            )))
        }
        ["string", "is_empty"] => {
            let args = parse_args!();
            if args.len() != 1 {
                return Err(w.err(em.span(), "string::is_empty!: expected (s)"));
            }
            let inner = emit_expr(w, &args[0])?;
            Ok(Some(Emitted {
                text: format!("({} == \"\")", inner.text),
                ty: Ty::Bool,
                prec: Prec::Cmp,
            }))
        }

        _ => Ok(None),
    }
}

/// Parse a macro's body as a comma-separated `Vec<syn::Expr>`. Used by
/// the DSL dispatch to extract argument expressions.
fn parse_macro_arg_list(tokens: proc_macro2::TokenStream) -> Result<Vec<syn::Expr>, String> {
    use syn::parse::Parser;
    let parser = syn::punctuated::Punctuated::<syn::Expr, syn::Token![,]>::parse_terminated;
    let parsed = parser
        .parse2(tokens)
        .map_err(|e| format!("parse args: {e}"))?;
    Ok(parsed.into_iter().collect())
}

/// `pyrust::macro!(recv, |x| body)` — argument shape with one
/// receiver expression and a one-parameter closure. The closure is
/// parsed as a full `syn::ExprClosure` so `|_| body`, `|&x| body`,
/// `|(a, b)| body`, and explicit type annotations all work.
struct ClosureArgs {
    recv: syn::Expr,
    param: String,
    body: syn::Expr,
}

impl syn::parse::Parse for ClosureArgs {
    fn parse(input: syn::parse::ParseStream) -> syn::Result<Self> {
        let recv: syn::Expr = input.parse()?;
        let _: syn::Token![,] = input.parse()?;
        let closure: syn::ExprClosure = input.parse()?;
        if closure.inputs.len() != 1 {
            return Err(input.error("expected single-parameter closure"));
        }
        let param = format_closure_param(closure.inputs.first().unwrap());
        let body = (*closure.body).clone();
        Ok(Self { recv, param, body })
    }
}

/// Render a closure parameter pattern as Python lambda parameter
/// text. For tuple destructure `(a, b)`, emits a fresh name and the
/// caller handles the body substitution; here we just emit `_t<n>`
/// for tuple patterns and leave body as-is — caller's responsibility
/// to convert tuple-uses to t.0/t.1 (the v55 source already does).
fn format_closure_param(p: &syn::Pat) -> String {
    match p {
        syn::Pat::Ident(pi) => pi.ident.to_string(),
        syn::Pat::Wild(_) => "_".to_string(),
        syn::Pat::Type(pt) => format_closure_param(&pt.pat),
        syn::Pat::Reference(r) => format_closure_param(&r.pat),
        syn::Pat::Paren(p) => format_closure_param(&p.pat),
        // Tuple-destructure patterns: render as a fresh name. The
        // body is expected to use field accesses like `t.0`/`t.1`.
        _ => "_t".to_string(),
    }
}
