use proc_macro2::Span;
use syn::spanned::Spanned;

use super::collection;
use super::shim::{self, ShimCall};
use super::types::{Ty, promote_numeric};
use super::writer::PyWriter;
use crate::tyctx::TyKind;

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
    use syn::spanned::Spanned;
    // Look up the ra_ap-resolved type kind of the receiver before lowering
    // it. Method dispatch (Option::map vs Iterator::map, etc.) reads this.
    let recv_kind = w.ty_at(m.receiver.span()).cloned();
    let recv = emit_expr(w, &m.receiver)?;
    let method = m.method.to_string();
    let arg_exprs: Vec<&syn::Expr> = m.args.iter().collect();

    // Type-driven field-accessor collapse: if the receiver is an ADT and
    // its struct fields include a name matching the method, with zero
    // args, emit field access. Also fires for sum-type enums where every
    // variant carries the same-named field (e.g. `Building::team()` —
    // each variant has a `team: Team`, the impl method just match-extracts
    // it). Cuts out the trait-accessor methods (e.g. `Unit::state(&self)
    // -> &UnitState`) that Python doesn't need.
    if arg_exprs.is_empty()
        && let Some(rk) = recv_kind.as_ref()
        && let Some(adt) = rk.adt()
        && (adt.field_names.iter().any(|f| f == method.as_str())
            || adt.all_variants_have_field(method.as_str()))
    {
        return Ok(Emitted::atomic(
            format!("{}.{}", recv.text, method),
            Ty::Unknown,
        ));
    }
    // Folded trait default body fallback: ra_ap's per-file type table
    // doesn't cover spans that came from another file (where the trait
    // is defined). When the receiver is `self` and the surrounding class
    // has a same-named field, treat it like the field-accessor collapse.
    if arg_exprs.is_empty() && recv.text == "self" && w.current_class_has_field(method.as_str()) {
        return Ok(Emitted::atomic(format!("self.{}", method), Ty::Unknown));
    }
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
        ("into", _, 0) => return Ok(recv),
        ("into_iter", _, 0) => return Ok(recv),
        ("clone", _, 0) => return Ok(recv),
        ("enumerate", _, 0) => {
            return Ok(Emitted::atomic(
                format!("enumerate({})", recv.text),
                Ty::Unknown,
            ));
        }
        // Rust iterator's `.next() -> Option<T>` becomes Python
        // `next(iter(recv), None)`. The `.iter()` we already collapse, so
        // the translator must wrap manually here.
        ("next", _, 0) => {
            return Ok(Emitted::atomic(
                format!("next(iter({}), None)", recv.text),
                Ty::Unknown,
            ));
        }
        ("zip", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("zip({}, {})", recv.text, arg.text),
                Ty::Unknown,
            ));
        }
        ("rev", _, 0) => {
            return Ok(Emitted::atomic(
                format!("reversed({})", recv.text),
                Ty::Unknown,
            ));
        }
        ("chain", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("itertools.chain({}, {})", recv.text, arg.text),
                Ty::Unknown,
            ));
        }
        ("take", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("itertools.islice({}, {})", recv.text, arg.text),
                Ty::Unknown,
            ));
        }
        ("skip", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("itertools.islice({}, {}, None)", recv.text, arg.text),
                Ty::Unknown,
            ));
        }
        ("to_string", _, 0) => return Ok(recv),
        ("to_owned", _, 0) => return Ok(recv),
        ("to_vec", _, 0) => {
            return Ok(Emitted::atomic(format!("list({})", recv.text), Ty::List));
        }
        ("as_str", _, 0) => return Ok(recv),
        ("as_mut", _, 0) => return Ok(recv),
        ("as_ref", _, 0) => return Ok(recv),
        ("as_deref", _, 0) => return Ok(recv),
        ("expect", _, 1) => return Ok(recv),
        // `Option::take()` — Rust ownership transfer; in Python we just
        // read the value and let the surrounding code overwrite the field
        // on the next assignment. Loses the "leave None during body"
        // observability, but v55 never inspects the field mid-body.
        ("take", _, 0) => return Ok(recv),
        // `random.Random.choices(pop, weights, k)` — Python's stdlib makes
        // `k` keyword-only. Translate to `.choices(pop, weights, k=K)`.
        ("choices", _, 3) => {
            let pop = emit_expr(w, arg_exprs[0])?;
            let weights = emit_expr(w, arg_exprs[1])?;
            let k = emit_expr(w, arg_exprs[2])?;
            return Ok(Emitted::atomic(
                format!(
                    "{}.choices({}, {}, k={})",
                    recv.text, pop.text, weights.text, k.text
                ),
                Ty::List,
            ));
        }
        ("choices", _, 2) => {
            // `.choices(pop, k)` — uniform.
            let pop = emit_expr(w, arg_exprs[0])?;
            let k = emit_expr(w, arg_exprs[1])?;
            return Ok(Emitted::atomic(
                format!("{}.choices({}, k={})", recv.text, pop.text, k.text),
                Ty::List,
            ));
        }
        // `rng.sample(pop, k)` — k is positional in Python.
        ("shuffle", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("{}.shuffle({})", recv.text, arg.text),
                Ty::Unit,
            ));
        }
        // `t.elapsed()` where `t` came from `Instant::now()` becomes
        // `(time.monotonic() - t)`; `.as_micros()` then scales the float
        // diff into integer microseconds. We do these together because
        // the bot's only `elapsed` uses chain straight into `.as_micros()`.
        ("elapsed", _, 0) => {
            return Ok(Emitted::atomic(
                format!("(time.monotonic() - {})", recv.text),
                Ty::Unknown,
            ));
        }
        ("as_micros", _, 0) => {
            return Ok(Emitted::atomic(
                format!("int({} * 1000000)", recv.text),
                Ty::Int,
            ));
        }
        ("as_millis", _, 0) => {
            return Ok(Emitted::atomic(
                format!("int({} * 1000)", recv.text),
                Ty::Int,
            ));
        }
        ("as_secs", _, 0) => {
            return Ok(Emitted::atomic(format!("int({})", recv.text), Ty::Int));
        }
        ("as_secs_f64" | "as_secs_f32", _, 0) => return Ok(recv),
        ("copied", _, 0) => return Ok(recv),
        ("cloned", _, 0) => return Ok(recv),
        ("push", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("{}.append({})", recv.text, arg.text),
                Ty::Unit,
            ));
        }
        // `set.insert(x)` → `set.add(x)`. `map.insert(k, v)` → `map[k] = v`.
        ("insert", Ty::Set, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("{}.add({})", recv.text, arg.text),
                Ty::Unit,
            ));
        }
        ("insert", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("{}.add({})", recv.text, arg.text),
                Ty::Unit,
            ));
        }
        ("insert", _, 2) => {
            let key = emit_expr(w, arg_exprs[0])?;
            let val = emit_expr(w, arg_exprs[1])?;
            return Ok(Emitted::atomic(
                format!("{}[{}] = {}", recv.text, key.text, val.text),
                Ty::Unit,
            ));
        }
        ("remove", Ty::Set | Ty::Unknown, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("{}.discard({})", recv.text, arg.text),
                Ty::Unit,
            ));
        }
        ("contains_key", _, 1) | ("contains", Ty::Dict, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("({} in {})", arg.text, recv.text),
                Ty::Bool,
            ));
        }
        ("get", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("{}.get({})", recv.text, arg.text),
                Ty::Unknown,
            ));
        }
        ("clear", _, 0) => {
            // Python strings are immutable; `String::clear()` becomes
            // assignment to the empty string. ra_ap reports `&str` as
            // `TyKind::Str` and `String` as an Adt named "String"; both map
            // to Python `str`.
            let is_string = matches!(recv_kind, Some(crate::tyctx::TyKind::Str))
                || recv_kind
                    .as_ref()
                    .and_then(|k| k.adt())
                    .map(|a| a.name == "String")
                    .unwrap_or(false);
            if is_string {
                return Ok(Emitted::atomic(
                    format!("{} = \"\"", recv.text),
                    Ty::Unit,
                ));
            }
            return Ok(Emitted::atomic(format!("{}.clear()", recv.text), Ty::Unit));
        }
        ("pop", _, 0) => {
            // Rust `Vec::pop()` / `VecDeque::pop_back()` return `Option<T>`
            // (None on empty); Python `list.pop()` raises IndexError. Wrap
            // with a truthy check so the translation matches the Option
            // contract.
            return Ok(Emitted::atomic(
                format!("({0}.pop() if {0} else None)", recv.text),
                Ty::Unknown,
            ));
        }
        ("pop_back", _, 0) => {
            return Ok(Emitted::atomic(
                format!("({0}.pop() if {0} else None)", recv.text),
                Ty::Unknown,
            ));
        }
        ("pop_front", _, 0) => {
            return Ok(Emitted::atomic(
                format!("({0}.pop(0) if {0} else None)", recv.text),
                Ty::Unknown,
            ));
        }
        ("split_off", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("{}[{}:]", recv.text, arg.text),
                Ty::List,
            ));
        }
        ("front", _, 0) => {
            return Ok(Emitted::atomic(format!("{}[0]", recv.text), Ty::Unknown));
        }
        ("back", _, 0) => {
            return Ok(Emitted::atomic(format!("{}[-1]", recv.text), Ty::Unknown));
        }
        ("first", _, 0) => {
            return Ok(Emitted::atomic(
                format!("({0}[0] if {0} else None)", recv.text),
                Ty::Unknown,
            ));
        }
        ("last", _, 0) => {
            return Ok(Emitted::atomic(
                format!("({0}[-1] if {0} else None)", recv.text),
                Ty::Unknown,
            ));
        }
        ("push_back", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("{}.append({})", recv.text, arg.text),
                Ty::Unit,
            ));
        }
        ("push_front", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("{}.insert(0, {})", recv.text, arg.text),
                Ty::Unit,
            ));
        }
        ("extend", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("{}.extend({})", recv.text, arg.text),
                Ty::Unit,
            ));
        }
        ("remove", Ty::List, 1) | ("swap_remove", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("{}.pop({})", recv.text, arg.text),
                Ty::Unknown,
            ));
        }
        ("retain", _, 1) => {
            // `xs.retain(|x| pred)` → `xs[:] = [x for x in xs if pred]`.
            if let syn::Expr::Closure(cl) = arg_exprs[0]
                && cl.inputs.len() == 1
                && let Some(body) = closure_body_expr(cl)
                && let Some(param_text) = closure_param_text(cl.inputs.first().unwrap())
            {
                w.scope.push();
                w.scope.declare(&param_text, Ty::Unknown);
                let body_res = emit_expr(w, body);
                w.scope.pop();
                let body_em = body_res?;
                return Ok(Emitted::atomic(
                    format!(
                        "{0}[:] = [{param_text} for {param_text} in {0} if {1}]",
                        recv.text, body_em.text
                    ),
                    Ty::Unit,
                ));
            }
        }
        ("truncate", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("del {}[{}:]", recv.text, arg.text),
                Ty::Unit,
            ));
        }
        ("resize", _, 2) => {
            let n = emit_expr(w, arg_exprs[0])?;
            let v = emit_expr(w, arg_exprs[1])?;
            return Ok(Emitted::atomic(
                format!(
                    "{0}.extend([{2}] * max(0, {1} - len({0})))",
                    recv.text, n.text, v.text
                ),
                Ty::Unit,
            ));
        }
        ("reverse", _, 0) => {
            return Ok(Emitted::atomic(
                format!("{}.reverse()", recv.text),
                Ty::Unit,
            ));
        }
        ("sort", _, 0) => {
            return Ok(Emitted::atomic(format!("{}.sort()", recv.text), Ty::Unit));
        }
        ("dedup", _, 0) => {
            return Ok(Emitted::atomic(
                format!(
                    "{0}[:] = [x for i, x in enumerate({0}) if i == 0 or {0}[i-1] != x]",
                    recv.text
                ),
                Ty::Unit,
            ));
        }
        ("fill", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("{0}[:] = [{1}] * len({0})", recv.text, arg.text),
                Ty::Unit,
            ));
        }
        ("len", _, 0) => {
            return Ok(Emitted::atomic(format!("len({})", recv.text), Ty::Int));
        }
        ("is_empty", _, 0) => {
            return Ok(Emitted::atomic(
                format!("(len({}) == 0)", recv.text),
                Ty::Bool,
            ));
        }
        ("abs", _, 0) => {
            return Ok(Emitted::atomic(format!("abs({})", recv.text), Ty::Int));
        }
        ("round", _, 0) => {
            return Ok(Emitted::atomic(format!("round({})", recv.text), Ty::Int));
        }
        ("floor", _, 0) => {
            return Ok(Emitted::atomic(
                format!("math.floor({})", recv.text),
                Ty::Int,
            ));
        }
        ("ceil", _, 0) => {
            return Ok(Emitted::atomic(
                format!("math.ceil({})", recv.text),
                Ty::Int,
            ));
        }
        ("sqrt", _, 0) => {
            return Ok(Emitted::atomic(
                format!("math.sqrt({})", recv.text),
                Ty::Unknown,
            ));
        }
        ("min", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("min({}, {})", recv.text, arg.text),
                Ty::Unknown,
            ));
        }
        ("max", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("max({}, {})", recv.text, arg.text),
                Ty::Unknown,
            ));
        }
        ("clamp", _, 2) => {
            let lo = emit_expr(w, arg_exprs[0])?;
            let hi = emit_expr(w, arg_exprs[1])?;
            return Ok(Emitted::atomic(
                format!("max({}, min({}, {}))", lo.text, recv.text, hi.text),
                Ty::Unknown,
            ));
        }
        ("rem_euclid", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("(({}) % ({}))", recv.text, arg.text),
                Ty::Int,
            ));
        }
        ("div_euclid", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("(({}) // ({}))", recv.text, arg.text),
                Ty::Int,
            ));
        }
        ("pow", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("(({}) ** ({}))", recv.text, arg.text),
                Ty::Int,
            ));
        }
        ("powi" | "powf", _, 1) => {
            let arg = emit_expr(w, arg_exprs[0])?;
            return Ok(Emitted::atomic(
                format!("({} ** {})", recv.text, arg.text),
                Ty::Unknown,
            ));
        }
        ("signum", _, 0) => {
            return Ok(Emitted::atomic(
                format!("(0 if {0} == 0 else (1 if {0} > 0 else -1))", recv.text),
                Ty::Int,
            ));
        }
        ("sum", _, 0) => {
            return Ok(Emitted::atomic(format!("sum({})", recv.text), Ty::Int));
        }
        ("product", _, 0) => {
            return Ok(Emitted::atomic(
                format!("math.prod({})", recv.text),
                Ty::Int,
            ));
        }
        ("count", _, 0) => {
            return Ok(Emitted::atomic(
                format!("sum(1 for _ in {})", recv.text),
                Ty::Int,
            ));
        }
        ("collect", _, 0) => {
            // `.collect()` materialises an iterator. Default to `list(...)`,
            // but honour the turbofish: `.collect::<HashSet<_>>()` →
            // `set(...)`, `.collect::<HashMap<_, _>>()` → `dict(...)`.
            let turbofish_kind = m
                .turbofish
                .as_ref()
                .and_then(|tb| tb.args.first())
                .and_then(|arg| match arg {
                    syn::GenericArgument::Type(syn::Type::Path(tp)) => tp.path.segments.last(),
                    _ => None,
                })
                .map(|seg| seg.ident.to_string());
            let (wrap, ty) = match turbofish_kind.as_deref() {
                Some("HashSet" | "BTreeSet") => ("set", Ty::Set),
                Some("HashMap" | "BTreeMap") => ("dict", Ty::Dict),
                _ => ("list", Ty::List),
            };
            return Ok(Emitted::atomic(format!("{wrap}({})", recv.text), ty));
        }
        ("map", _, 1) => {
            if let syn::Expr::Closure(c) = arg_exprs[0] {
                // ra_ap-resolved receiver type decides the dispatch:
                //   Option::map(|x| body)  → walrus-conditional in Python
                //   Iterator::map(|p| body) → generator expression
                if matches!(recv_kind, Some(TyKind::Option)) {
                    return emit_option_map(w, &recv, c);
                }
                return emit_iter_map(w, &recv, c);
            }
        }
        ("filter_map", _, 1) => {
            // `iter.filter_map(|p| if cond { Some(x) } else { None })` →
            // `(x for p in iter if cond)`. Generator expression.
            if let syn::Expr::Closure(c) = arg_exprs[0]
                && c.inputs.len() == 1
                && let Some(body) = closure_body_expr(c)
                && let syn::Expr::If(if_expr) = body
                && let Some((_, else_branch)) = &if_expr.else_branch
                && let syn::Expr::Block(else_block) = else_branch.as_ref()
                && else_block.block.stmts.len() == 1
                && let syn::Stmt::Expr(else_inner, None) = &else_block.block.stmts[0]
                && super::pat::is_none_pattern(&else_pat_for_expr(else_inner))
                && let syn::Stmt::Expr(then_inner, None) =
                    &if_expr.then_branch.stmts[if_expr.then_branch.stmts.len() - 1]
                && let syn::Expr::Call(call) = then_inner
                && is_some_call(call)
                && call.args.len() == 1
                && let Some(param_text) = closure_param_text(&c.inputs[0])
            {
                declare_closure_pat_idents(w, &c.inputs[0]);
                let cond_em = emit_expr(w, &if_expr.cond)?;
                let some_inner_em = emit_expr(w, &call.args[0])?;
                return Ok(Emitted::atomic(
                    format!(
                        "({} for {param_text} in {} if {})",
                        some_inner_em.text, recv.text, cond_em.text
                    ),
                    Ty::Unknown,
                ));
            }
        }
        ("find_map", _, 1) => {
            // `iter.find_map(|p| if cond { Some(x) } else { None })` →
            // `next((x for p in iter if cond), None)`. Limited to that
            // exact closure shape; otherwise pass through to the catch-all.
            if let syn::Expr::Closure(c) = arg_exprs[0]
                && c.inputs.len() == 1
                && let Some(body) = closure_body_expr(c)
                && let syn::Expr::If(if_expr) = body
                && let Some((_, else_branch)) = &if_expr.else_branch
                && let syn::Expr::Block(else_block) = else_branch.as_ref()
                && else_block.block.stmts.len() == 1
                && let syn::Stmt::Expr(else_inner, None) = &else_block.block.stmts[0]
                && super::pat::is_none_pattern(&else_pat_for_expr(else_inner))
                && let syn::Stmt::Expr(then_inner, None) =
                    &if_expr.then_branch.stmts[if_expr.then_branch.stmts.len() - 1]
                && let syn::Expr::Call(call) = then_inner
                && is_some_call(call)
                && call.args.len() == 1
                && let Some(param_text) = closure_param_text(&c.inputs[0])
            {
                declare_closure_pat_idents(w, &c.inputs[0]);
                let cond_em = emit_expr(w, &if_expr.cond)?;
                let some_inner_em = emit_expr(w, &call.args[0])?;
                return Ok(Emitted::atomic(
                    format!(
                        "next(({} for {param_text} in {} if {}), None)",
                        some_inner_em.text, recv.text, cond_em.text
                    ),
                    Ty::Unknown,
                ));
            }
        }
        ("find", _, 1) => {
            // `iter.find(|p| body)` → `next((p for p in iter if body), None)`
            if let syn::Expr::Closure(c) = arg_exprs[0]
                && c.inputs.len() == 1
                && let Some(param_text) = closure_param_text(&c.inputs[0])
                && let Some(body) = closure_body_expr(c)
            {
                declare_closure_pat_idents(w, &c.inputs[0]);
                let body_em = emit_expr(w, body)?;
                return Ok(Emitted::atomic(
                    format!(
                        "next((({param_text}) for {param_text} in {} if {}), None)",
                        recv.text, body_em.text
                    ),
                    Ty::Unknown,
                ));
            }
        }
        ("position", _, 1) => {
            // `iter.position(|p| body)` → returns the index of the first
            // matching element. Python: `next((i for i, p in enumerate(iter)
            // if body), None)`.
            if let syn::Expr::Closure(c) = arg_exprs[0]
                && c.inputs.len() == 1
                && let Some(param_text) = closure_param_text(&c.inputs[0])
                && let Some(body) = closure_body_expr(c)
            {
                declare_closure_pat_idents(w, &c.inputs[0]);
                let body_em = emit_expr(w, body)?;
                return Ok(Emitted::atomic(
                    format!(
                        "next((__i for __i, {param_text} in enumerate({}) if {}), None)",
                        recv.text, body_em.text
                    ),
                    Ty::Unknown,
                ));
            }
        }
        ("min_by_key", _, 1) | ("max_by_key", _, 1) => {
            // `iter.min_by_key(|p| key)` → `min(iter, key=lambda p: key, default=None)`.
            if let syn::Expr::Closure(c) = arg_exprs[0]
                && c.inputs.len() == 1
                && let Some(param_text) = closure_param_text(&c.inputs[0])
                && let Some(body) = closure_body_expr(c)
            {
                declare_closure_pat_idents(w, &c.inputs[0]);
                let body_em = emit_expr(w, body)?;
                let func = if method == "min_by_key" { "min" } else { "max" };
                return Ok(Emitted::atomic(
                    format!(
                        "{func}({}, key=lambda {param_text}: {}, default=None)",
                        recv.text, body_em.text
                    ),
                    Ty::Unknown,
                ));
            }
        }
        ("sort_by_key", _, 1) => {
            // `vec.sort_by_key(|p| key)` → `vec.sort(key=lambda p: key)`.
            if let syn::Expr::Closure(c) = arg_exprs[0]
                && c.inputs.len() == 1
                && let Some(param_text) = closure_param_text(&c.inputs[0])
                && let Some(body) = closure_body_expr(c)
            {
                declare_closure_pat_idents(w, &c.inputs[0]);
                let body_em = emit_expr(w, body)?;
                return Ok(Emitted {
                    text: format!(
                        "{}.sort(key=lambda {param_text}: {})",
                        recv.text, body_em.text
                    ),
                    ty: Ty::Unit,
                    prec: Prec::Atom,
                });
            }
        }
        ("iter_mut", _, 0) => return Ok(recv),
        ("any", _, 1) | ("all", _, 1) => {
            // `iter.any(|p| body)` / `iter.all(|p| body)` →
            // `any(body for p in iter)` / `all(...)`. Generator handles
            // tuple-pattern params natively.
            if let syn::Expr::Closure(c) = arg_exprs[0]
                && c.inputs.len() == 1
                && let Some(param_text) = closure_param_text(&c.inputs[0])
                && let Some(body) = closure_body_expr(c)
            {
                declare_closure_pat_idents(w, &c.inputs[0]);
                let body_em = emit_expr(w, body)?;
                let func = method.as_str();
                return Ok(Emitted::atomic(
                    format!("{func}({} for {param_text} in {})", body_em.text, recv.text),
                    Ty::Bool,
                ));
            }
        }
        ("filter", _, 1) => {
            // `iter.filter(|p| body)` → `(p for p in iter if body)`. Tuple
            // patterns get unpacked natively by Python's `for x, y in ...`.
            if let syn::Expr::Closure(c) = arg_exprs[0]
                && c.inputs.len() == 1
                && let Some(param_text) = closure_param_text(&c.inputs[0])
                && let Some(body) = closure_body_expr(c)
            {
                declare_closure_pat_idents(w, &c.inputs[0]);
                let body_em = emit_expr(w, body)?;
                // Yield variable is awkward when param is a tuple; reuse
                // the iter element by repeating param tokens (works for
                // both ident and tuple patterns).
                return Ok(Emitted::atomic(
                    format!(
                        "(({param_text}) for {param_text} in {} if {})",
                        recv.text, body_em.text
                    ),
                    Ty::Unknown,
                ));
            }
        }
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
        ("is_some_and", _, 1) => {
            // `opt.is_some_and(|x| pred)` → `(x := opt) is not None and pred`.
            if let syn::Expr::Closure(cl) = arg_exprs[0]
                && cl.inputs.len() == 1
                && let Some(body) = closure_body_expr(cl)
                && let Some(param_text) = closure_param_text(cl.inputs.first().unwrap())
            {
                w.scope.push();
                w.scope.declare(&param_text, Ty::Unknown);
                let body_res = emit_expr(w, body);
                w.scope.pop();
                let body_em = body_res?;
                return Ok(Emitted::atomic(
                    format!(
                        "(({param_text} := {}) is not None and {})",
                        recv.text, body_em.text
                    ),
                    Ty::Bool,
                ));
            }
        }
        ("is_none_or", _, 1) => {
            if let syn::Expr::Closure(cl) = arg_exprs[0]
                && cl.inputs.len() == 1
                && let Some(body) = closure_body_expr(cl)
                && let Some(param_text) = closure_param_text(cl.inputs.first().unwrap())
            {
                w.scope.push();
                w.scope.declare(&param_text, Ty::Unknown);
                let body_res = emit_expr(w, body);
                w.scope.pop();
                let body_em = body_res?;
                return Ok(Emitted::atomic(
                    format!(
                        "(({param_text} := {}) is None or {})",
                        recv.text, body_em.text
                    ),
                    Ty::Bool,
                ));
            }
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
            // Walrus-bind the receiver to a fresh temp so it evaluates once.
            let default = emit_expr(w, arg_exprs[0])?;
            let default_text = paren_at_least(&default, Prec::Or);
            let tmp = w.fresh_tmp();
            return Ok(Emitted {
                text: format!(
                    "({tmp} if ({tmp} := {}) is not None else {default_text})",
                    recv.text
                ),
                ty: default.ty,
                prec: Prec::Atom,
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
///   matches!(x, EnumName::A | EnumName::B)           → `x in (EnumName.A, EnumName.B)`
///   matches!(x, EnumName::Variant { .. })            → `isinstance(x, EnumNameVariant)`
///   matches!(x, EnumName::A { .. } | EnumName::B {.}) → `isinstance(x, EnumNameA | EnumNameB)`
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
            Ok(MatchesArgs {
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
        let lam = format!(
            "(lambda {lam_args}: {})({})",
            g_em.text,
            attrs.join(", ")
        );
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
    let segs: Vec<String> = ts.path.segments.iter().map(|s| s.ident.to_string()).collect();
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
        syn::Pat::Ident(i) => {
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
        && i.to_string() == "null"
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
    // Python `None`. Only a multi-segment path can be a variant (a bare
    // ident is a variable binding, which we mustn't erase even if its
    // type is the transparent enum).
    if p.path.segments.len() >= 2
        && let Some(result_kind) = w.ty_at(p.span())
        && let Some(adt) = result_kind.adt()
        && adt.is_transparent
    {
        return Ok(Emitted::atomic("None", Ty::Unknown));
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
    // Type-driven: a 1-arg call that produces `serde_json::Value` (or
    // `serde_json::Number`) is wrapping a Python-equivalent value into a
    // tagged JSON node. Python's `json` module uses bare dict/list/str/int,
    // so emit just the argument and drop the constructor.
    if c.args.len() == 1
        && let Some(result_kind) = w.ty_at(c.span())
        && let Some(adt) = result_kind.adt()
        && (adt.matches_crate_type("serde_json", "Value")
            || adt.matches_crate_type("serde_json", "Number"))
    {
        return emit_expr(w, c.args.first().unwrap());
    }
    // `#[pyrust::transparent]` enum variant constructor — erase the
    // wrapper. `Foo::Direction(d)` becomes just `d`; multi-field variants
    // are an error because there's no obvious Python equivalent.
    if let Some(result_kind) = w.ty_at(c.span())
        && let Some(adt) = result_kind.adt()
        && adt.is_transparent
    {
        if c.args.len() == 1 {
            return emit_expr(w, c.args.first().unwrap());
        }
        return Err(w.err(
            c.span(),
            "transparent enum variant must have exactly one field",
        ));
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
                return Err(w.err(c.span(), "Some/Ok expects exactly one argument"));
            }
            return Ok(arg_emits.into_iter().next().unwrap());
        }
        // Rust's prelude `drop(x)` runs the `Drop::drop` impl. We translate
        // it to a method call so the user's `impl Drop for X` (lowered to
        // a `drop` method on the Python class) fires explicitly. This is a
        // generic Rust → Python lowering, not bot-specific.
        if matches!(
            slice.as_slice(),
            ["drop"] | ["std", "mem", "drop"] | ["mem", "drop"]
        ) && c.args.len() == 1
        {
            let arg = arg_emits.into_iter().next().unwrap();
            return Ok(Emitted::atomic(format!("{}.drop()", arg.text), Ty::Unit));
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
        if w.cfg().trait_registry.contains_key(&class_name) && !c.args.is_empty() {
            let first = arg_emits.first().unwrap().text.clone();
            let rest: Vec<&str> = arg_emits.iter().skip(1).map(|e| e.text.as_str()).collect();
            return Ok(Emitted::atomic(
                format!("{first}.{tail}({})", rest.join(", ")),
                Ty::Unknown,
            ));
        }
        // Numeric `T::from(x)` constructors map to Python's int/float.
        if tail == "from" && c.args.len() == 1 {
            let py = match class_name.as_str() {
                "f32" | "f64" => Some(("float", Ty::Float)),
                "i8" | "i16" | "i32" | "i64" | "i128" | "isize" | "u8" | "u16" | "u32" | "u64"
                | "u128" | "usize" => Some(("int", Ty::Int)),
                _ => None,
            };
            if let Some((name, ty)) = py {
                return Ok(Emitted::atomic(format!("{name}({joined})"), ty));
            }
        }
        if tail == "default" && c.args.is_empty() {
            // `T::default()` becomes `T()` — the auto-generated Python
            // class always has a no-arg constructor for the Default impl.
            return Ok(Emitted::atomic(format!("{class_name}()"), Ty::Unknown));
        }
        if tail == "new" || tail == "with_capacity" {
            // Container default / pre-sized constructors map to Python
            // literals (Python lists/dicts/sets don't take a capacity hint).
            match class_name.as_str() {
                "Vec" | "List" | "VecDeque" => {
                    return Ok(Emitted::atomic("[]".to_owned(), Ty::List));
                }
                "HashMap" | "BTreeMap" | "Dict" | "Map" => {
                    return Ok(Emitted::atomic("{}".to_owned(), Ty::Dict));
                }
                "HashSet" | "BTreeSet" | "Set" => {
                    return Ok(Emitted::atomic("set()".to_owned(), Ty::Set));
                }
                "String" => {
                    return Ok(Emitted::atomic("\"\"".to_owned(), Ty::Unknown));
                }
                _ => {}
            }
            if tail == "new" {
                // Constructor convention: `Type::new(args)` becomes `Type(args)`.
                return Ok(Emitted::atomic(
                    format!("{class_name}({joined})"),
                    Ty::Unknown,
                ));
            }
        }
        // Sum-type variant constructor: `Foo::Bar(args)` → `FooBar(args)`
        // (matching the dataclass-per-variant lowering in `emit_sum_enum`).
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
        return Ok(Emitted::atomic(
            format!("{class_name}.{tail}({joined})"),
            Ty::Unknown,
        ));
    }
    // `std::mem::take(&mut x)` — Rust takes ownership and replaces with
    // default. Python doesn't move; emit as the inner expression. The
    // surrounding code in v55 always reassigns the original location
    // afterwards, so the alias semantics are equivalent in practice.
    if !path.leading_colon.is_some() {
        let names: Vec<String> = path.segments.iter().map(|s| s.ident.to_string()).collect();
        let slice: Vec<&str> = names.iter().map(String::as_str).collect();
        if matches!(slice.as_slice(), ["std", "mem", "take"] | ["mem", "take"]) {
            if arg_emits.len() != 1 {
                return Err(w.err(c.span(), "std::mem::take expects exactly one argument"));
            }
            return Ok(arg_emits.into_iter().next().unwrap());
        }
    }
    if path.leading_colon.is_some() || path.segments.len() != 1 {
        // Multi-segment path call (e.g. `crate::util::directions::delta_to_dir(...)`).
        // Emit the leaf identifier — the user's `use` statements
        // typically expose it at this name. If not, the resulting Python
        // raises NameError, which is a clearer signal than failing here.
        let segs: Vec<String> = path.segments.iter().map(|s| s.ident.to_string()).collect();
        if let Some(leaf) = segs.last() {
            let ty = w.lookup(leaf).unwrap_or(Ty::Unknown);
            return Ok(Emitted::atomic(format!("{leaf}({joined})"), ty));
        }
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
