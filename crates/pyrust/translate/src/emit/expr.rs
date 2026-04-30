use proc_macro2::Span;
use syn::spanned::Spanned;

use super::collection;
use super::shim::{self, ShimCall};
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
        // level (Python ints are unbounded). Drop the cast entirely.
        syn::Expr::Cast(c) => emit_expr(w, &c.expr),
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
    if path.leading_colon.is_some() {
        return Err(w.err(path.span(), "absolute path in struct literal not supported"));
    }
    if path.segments.len() == 1 {
        let ident = path.segments[0].ident.to_string();
        if ident == "Self" {
            return w
                .current_class()
                .map(String::from)
                .ok_or_else(|| w.err(path.span(), "`Self` outside of an impl block"));
        }
        return Ok(ident);
    }
    Err(w.err(path.span(), "multi-segment struct path not supported"))
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
                format!("{recv_text}.{}", name),
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
    let idx = emit_expr(w, &i.index)?;
    let recv_text = if recv.prec < Prec::Atom {
        format!("({})", recv.text)
    } else {
        recv.text
    };
    Ok(Emitted::atomic(
        format!("{recv_text}[{}]", idx.text),
        Ty::Unknown,
    ))
}

fn emit_method_call(w: &mut PyWriter, m: &syn::ExprMethodCall) -> Result<Emitted, String> {
    let recv = emit_expr(w, &m.receiver)?;
    let method = m.method.to_string();
    let arg_exprs: Vec<&syn::Expr> = m.args.iter().collect();

    match (method.as_str(), recv.ty, arg_exprs.len()) {
        ("contains", Ty::List | Ty::Set | Ty::Unknown, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted {
                text: format!(
                    "{} in {}",
                    paren_at_least(&arg, Prec::Cmp),
                    paren_at_least(&recv, Prec::Cmp),
                ),
                ty: Ty::Bool,
                prec: Prec::Cmp,
            });
        }
        ("contains_key", Ty::Dict | Ty::Unknown, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted {
                text: format!(
                    "{} in {}",
                    paren_at_least(&arg, Prec::Cmp),
                    paren_at_least(&recv, Prec::Cmp),
                ),
                ty: Ty::Bool,
                prec: Prec::Cmp,
            });
        }
        ("iter", _, 0) => return Ok(recv),
        ("len", Ty::List | Ty::Dict | Ty::Set | Ty::Str, 0) => {
            return Ok(Emitted::atomic(format!("len({})", recv.text), Ty::Int));
        }
        ("is_none", _, 0) => {
            return Ok(Emitted {
                text: format!("{} is None", paren_at_least(&recv, Prec::Cmp)),
                ty: Ty::Bool,
                prec: Prec::Cmp,
            });
        }
        ("is_some", _, 0) => {
            return Ok(Emitted {
                text: format!("{} is not None", paren_at_least(&recv, Prec::Cmp)),
                ty: Ty::Bool,
                prec: Prec::Cmp,
            });
        }
        ("unwrap", _, 0) => return Ok(recv),
        ("ok", _, 0) => return Ok(recv),
        ("unwrap_or", _, 1) => {
            let default = emit_expr(w, arg_exprs[0])?;
            let recv_text = paren_at_least(&recv, Prec::Or);
            let default_text = paren_at_least(&default, Prec::Or);
            return Ok(Emitted {
                text: format!("{recv_text} if {recv_text} is not None else {default_text}"),
                ty: default.ty,
                prec: Prec::Lambda,
            });
        }
        ("insert", Ty::Dict, _) => {
            return Err(w.err(
                m.span(),
                ".insert on a dict returns Option<V> in Rust but None in Python; use it as a statement instead of capturing the return value",
            ));
        }
        _ => {}
    }

    let mut arg_texts = Vec::with_capacity(arg_exprs.len());
    for a in &arg_exprs {
        arg_texts.push(emit_expr(w, a)?.text);
    }
    let recv_text = if recv.prec < Prec::Atom {
        format!("({})", recv.text)
    } else {
        recv.text
    };
    let result_ty = method_return_type(&method, recv.ty);
    // Rust-keyword renames: `move_` → `move` (Python keyword in pattern
    // position only; method name is fine in Python).
    let py_method: &str = match method.as_str() {
        "move_" => "move",
        other => other,
    };
    Ok(Emitted::atomic(
        format!("{recv_text}.{py_method}({})", arg_texts.join(", ")),
        result_ty,
    ))
}

fn method_return_type(name: &str, recv_ty: Ty) -> Ty {
    match (name, recv_ty) {
        ("len", _) => Ty::Int,
        ("pop", Ty::List) => Ty::Unknown,
        ("append", Ty::List) => Ty::Unit,
        ("clear", _) => Ty::Unit,
        ("startswith" | "endswith", _) => Ty::Bool,
        ("upper" | "lower" | "strip" | "lstrip" | "rstrip" | "replace", _) => Ty::Str,
        _ => Ty::Unknown,
    }
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

fn emit_macro_expr(w: &mut PyWriter, em: &syn::ExprMacro) -> Result<Emitted, String> {
    if let Some(kind) = collection::recognize(&em.mac.path) {
        return collection::emit(w, kind, &em.mac);
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
    if p.path.leading_colon.is_none() && p.path.segments.len() == 2 {
        let head = p.path.segments[0].ident.to_string();
        let tail = p.path.segments[1].ident.to_string();
        if head == "Option" && tail == "None" {
            return Ok(Emitted::atomic("None", Ty::Unknown));
        }
        // Class-qualified value: enum variant or class constant.
        // `Direction::North` → `Direction.North`.
        let class = if head == "Self" {
            w.current_class()
                .map(String::from)
                .ok_or_else(|| w.err(p.span(), "`Self::` outside of an impl block"))?
        } else {
            head
        };
        return Ok(Emitted::atomic(format!("{class}.{tail}"), Ty::Unknown));
    }
    if p.path.leading_colon.is_some() || p.path.segments.len() != 1 {
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
    if let Some(call) = shim::recognize(path) {
        let ty = match call {
            ShimCall::Print => Ty::Unit,
            ShimCall::Len => Ty::Int,
            ShimCall::Min | ShimCall::Max | ShimCall::Sum | ShimCall::Abs => Ty::Unknown,
            ShimCall::Sorted | ShimCall::Reversed => Ty::List,
            ShimCall::Any | ShimCall::All => Ty::Bool,
            ShimCall::Enumerate | ShimCall::Zip => Ty::Unknown,
            ShimCall::RandomChoice => Ty::Unknown,
            ShimCall::RandomRandint => Ty::Int,
            ShimCall::RandomSeed => Ty::Unit,
        };
        return Ok(Emitted::atomic(
            format!("{}({joined})", call.python_name()),
            ty,
        ));
    }
    // `Some(x)` / `Option::Some(x)` and `Ok(x)` / `Result::Ok(x)` collapse to
    // their inner value — Python has neither wrapper, errors travel as exceptions.
    if path.leading_colon.is_none() {
        let names: Vec<String> = path.segments.iter().map(|s| s.ident.to_string()).collect();
        let slice: Vec<&str> = names.iter().map(String::as_str).collect();
        if matches!(
            slice.as_slice(),
            ["Some"] | ["Option", "Some"] | ["Ok"] | ["Result", "Ok"]
        ) {
            if c.args.len() != 1 {
                return Err(w.err(
                    c.span(),
                    "Some/Ok expects exactly one argument",
                ));
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
        if tail == "new" {
            // Constructor convention: `Type::new(args)` becomes `Type(args)`.
            return Ok(Emitted::atomic(
                format!("{class_name}({joined})"),
                Ty::Unknown,
            ));
        }
        return Ok(Emitted::atomic(
            format!("{class_name}.{tail}({joined})"),
            Ty::Unknown,
        ));
    }
    if path.leading_colon.is_some() || path.segments.len() != 1 {
        return Err(w.err(
            path.span(),
            format!(
                "unknown call target: {} (only single-ident user fns, pyrust shim calls, and `Type::method` are supported)",
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
            let both_int = l.ty == Ty::Int && r.ty == Ty::Int;
            let any_float = l.ty == Ty::Float || r.ty == Ty::Float;
            let (op, ty) = if both_int {
                ("//", Ty::Int)
            } else if any_float {
                ("/", Ty::Float)
            } else {
                return Err(w.err(
                    b.span(),
                    format!(
                        "cannot pick / vs // when operand types are unknown ({:?} / {:?}); add a type annotation",
                        l.ty, r.ty
                    ),
                ));
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
            Ty::Bool => {
                let inner_text = paren_left(&inner, Prec::Not);
                Ok(Emitted {
                    text: format!("not {inner_text}"),
                    ty: Ty::Bool,
                    prec: Prec::Not,
                })
            }
            Ty::Int | Ty::Unknown => {
                let inner_text = paren_left(&inner, Prec::Unary);
                Ok(Emitted {
                    text: format!("~{inner_text}"),
                    ty: inner.ty,
                    prec: Prec::Unary,
                })
            }
            other => Err(w.err(u.span(), format!("cannot apply ! to {other:?}"))),
        },
        syn::UnOp::Deref(_) => Ok(inner),
        other => Err(w.err(u.op.span(), format!("unsupported unary op: {other:?}"))),
    }
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
    if stmts.len() == 1 {
        if let syn::Stmt::Expr(e, None) = &stmts[0] {
            return Some(e);
        }
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

fn path_to_string(path: &syn::Path) -> String {
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

fn expr_kind(e: &syn::Expr) -> &'static str {
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
