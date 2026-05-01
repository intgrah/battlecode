use proc_macro2::TokenStream;
use syn::parse::{Parse, ParseStream, Parser};
use syn::punctuated::Punctuated;
use syn::spanned::Spanned;

use super::expr::{self, Emitted};
use super::types::Ty;
use super::writer::PyWriter;

#[derive(Clone, Copy, Debug)]
pub enum CollectionMacro {
    List,
    Vec,
    Dict,
    Set,
    Range,
    ListComp,
    DictComp,
    SetComp,
    Format,
}

pub fn recognize(path: &syn::Path) -> Option<CollectionMacro> {
    if path.leading_colon.is_some() {
        return None;
    }
    let names: Vec<String> = path.segments.iter().map(|s| s.ident.to_string()).collect();
    let slice: Vec<&str> = names.iter().map(String::as_str).collect();
    match slice.as_slice() {
        ["list"] | ["pyrust", "list"] => Some(CollectionMacro::List),
        ["vec"] => Some(CollectionMacro::Vec),
        ["dict"] | ["pyrust", "dict"] => Some(CollectionMacro::Dict),
        ["set"] | ["pyrust", "set"] => Some(CollectionMacro::Set),
        ["range"] | ["pyrust", "range"] => Some(CollectionMacro::Range),
        ["comprehension"] | ["pyrust", "comprehension"] => Some(CollectionMacro::ListComp),
        ["dict_comprehension"] | ["pyrust", "dict_comprehension"] => {
            Some(CollectionMacro::DictComp)
        }
        ["set_comprehension"] | ["pyrust", "set_comprehension"] => Some(CollectionMacro::SetComp),
        ["format"] => Some(CollectionMacro::Format),
        _ => None,
    }
}

pub fn emit(w: &mut PyWriter, kind: CollectionMacro, mac: &syn::Macro) -> Result<Emitted, String> {
    let tokens = mac.tokens.clone();
    match kind {
        CollectionMacro::List => emit_list(w, tokens, mac),
        CollectionMacro::Vec => emit_vec(w, tokens, mac),
        CollectionMacro::Dict => emit_dict(w, tokens, mac),
        CollectionMacro::Set => emit_set(w, tokens, mac),
        CollectionMacro::Range => emit_range(w, tokens, mac),
        CollectionMacro::ListComp => emit_list_comp(w, tokens, mac),
        CollectionMacro::DictComp => emit_dict_comp(w, tokens, mac),
        CollectionMacro::SetComp => emit_set_comp(w, tokens, mac),
        CollectionMacro::Format => emit_format(w, tokens, mac),
    }
}

/// `vec![x, y, z]` → `[x, y, z]`. `vec![x; n]` → `[x] * n`.
fn emit_vec(w: &mut PyWriter, tokens: TokenStream, mac: &syn::Macro) -> Result<Emitted, String> {
    if let Ok(rep) = syn::parse2::<RepeatExpr>(tokens.clone()) {
        let val = expr::emit_expr(w, &rep.value)?;
        let len = expr::emit_expr(w, &rep.len)?;
        return Ok(Emitted::atomic(
            format!("[{}] * {}", val.text, len.text),
            Ty::List,
        ));
    }
    emit_list(w, tokens, mac)
}

struct RepeatExpr {
    value: syn::Expr,
    len: syn::Expr,
}

impl Parse for RepeatExpr {
    fn parse(input: ParseStream) -> syn::Result<Self> {
        let value = input.parse()?;
        let _: syn::Token![;] = input.parse()?;
        let len = input.parse()?;
        Ok(RepeatExpr { value, len })
    }
}

pub fn emit_format(
    w: &mut PyWriter,
    tokens: TokenStream,
    mac: &syn::Macro,
) -> Result<Emitted, String> {
    let exprs = parse_expr_list(tokens, mac)?;
    if exprs.is_empty() {
        return Err(w.err(mac.span(), "format!/println! requires a format string"));
    }
    let fmt_lit = match &exprs[0] {
        syn::Expr::Lit(syn::ExprLit {
            lit: syn::Lit::Str(s),
            ..
        }) => s.value(),
        other => {
            return Err(w.err(
                other.span(),
                "first argument to format!/println! must be a string literal",
            ));
        }
    };
    let arg_exprs: Vec<&syn::Expr> = exprs.iter().skip(1).collect();
    let mut arg_texts = Vec::with_capacity(arg_exprs.len());
    for a in &arg_exprs {
        arg_texts.push(expr::emit_expr(w, a)?.text);
    }
    let py_str = build_py_fstring(w, mac, &fmt_lit, &arg_texts)?;
    Ok(Emitted::atomic(py_str, Ty::Str))
}

fn build_py_fstring(
    w: &PyWriter,
    mac: &syn::Macro,
    fmt: &str,
    args: &[String],
) -> Result<String, String> {
    let mut body = String::new();
    let mut chars = fmt.chars().peekable();
    let mut next_positional = 0usize;
    let mut any_interpolation = false;
    while let Some(c) = chars.next() {
        match c {
            '{' => {
                if chars.peek() == Some(&'{') {
                    chars.next();
                    body.push_str("{{");
                    continue;
                }
                let mut spec = String::new();
                let mut closed = false;
                for nc in chars.by_ref() {
                    if nc == '}' {
                        closed = true;
                        break;
                    }
                    spec.push(nc);
                }
                if !closed {
                    return Err(w.err(mac.span(), "unclosed `{` in format string"));
                }
                // Split argument from format spec. `{x:?}` → name="x", fmt="?".
                // `{:?}` → name="", fmt="?". `{x}` → name="x", fmt=None.
                let (arg_part, fmt_part) = match spec.split_once(':') {
                    Some((n, f)) => (n.to_string(), Some(f.to_string())),
                    None => (spec, None),
                };
                let resolved_arg = if arg_part.is_empty() {
                    let idx = next_positional;
                    next_positional += 1;
                    args.get(idx).cloned().ok_or_else(|| {
                        w.err(
                            mac.span(),
                            format!(
                                "format string requires {} positional args, got {}",
                                next_positional,
                                args.len()
                            ),
                        )
                    })?
                } else if let Ok(idx) = arg_part.parse::<usize>() {
                    args.get(idx).cloned().ok_or_else(|| {
                        w.err(mac.span(), format!("positional `{{{idx}}}` out of range"))
                    })?
                } else {
                    arg_part
                };
                // `{x:?}` (Debug) → `{x!r}` (Python repr).
                // `{x:.2f}`, `{x:>5}`, etc. — Python's format mini-language is
                // a superset of Rust's for the cases we use.
                let placeholder = match fmt_part.as_deref() {
                    None => resolved_arg,
                    Some("?") => format!("{resolved_arg}!r"),
                    Some(f) => format!("{resolved_arg}:{f}"),
                };
                body.push('{');
                body.push_str(&placeholder);
                body.push('}');
                any_interpolation = true;
            }
            '}' => {
                if chars.peek() == Some(&'}') {
                    chars.next();
                    body.push_str("}}");
                } else {
                    return Err(w.err(mac.span(), "unmatched `}` in format string"));
                }
            }
            '\\' => body.push_str("\\\\"),
            '"' => body.push_str("\\\""),
            '\n' => body.push_str("\\n"),
            '\r' => body.push_str("\\r"),
            '\t' => body.push_str("\\t"),
            c => body.push(c),
        }
    }
    let prefix = if any_interpolation { "f" } else { "" };
    Ok(format!("{prefix}\"{body}\""))
}

fn emit_range(w: &mut PyWriter, tokens: TokenStream, mac: &syn::Macro) -> Result<Emitted, String> {
    let exprs = parse_expr_list(tokens, mac)?;
    if exprs.is_empty() || exprs.len() > 3 {
        return Err(w.err(
            mac.span(),
            format!("range! expects 1, 2, or 3 args; got {}", exprs.len()),
        ));
    }
    let mut parts = Vec::with_capacity(exprs.len());
    for e in &exprs {
        parts.push(expr::emit_expr(w, e)?.text);
    }
    Ok(Emitted::atomic(
        format!("range({})", parts.join(", ")),
        Ty::Unknown,
    ))
}

fn emit_list(w: &mut PyWriter, tokens: TokenStream, mac: &syn::Macro) -> Result<Emitted, String> {
    let exprs = parse_expr_list(tokens, mac)?;
    let mut parts = Vec::with_capacity(exprs.len());
    for e in &exprs {
        parts.push(expr::emit_expr(w, e)?.text);
    }
    Ok(Emitted::atomic(format!("[{}]", parts.join(", ")), Ty::List))
}

fn emit_set(w: &mut PyWriter, tokens: TokenStream, mac: &syn::Macro) -> Result<Emitted, String> {
    let exprs = parse_expr_list(tokens, mac)?;
    if exprs.is_empty() {
        return Ok(Emitted::atomic("set()", Ty::Set));
    }
    let mut parts = Vec::with_capacity(exprs.len());
    for e in &exprs {
        parts.push(expr::emit_expr(w, e)?.text);
    }
    Ok(Emitted::atomic(
        format!("{{{}}}", parts.join(", ")),
        Ty::Set,
    ))
}

fn emit_dict(w: &mut PyWriter, tokens: TokenStream, mac: &syn::Macro) -> Result<Emitted, String> {
    let parser = Punctuated::<DictPair, syn::Token![,]>::parse_terminated;
    let pairs = parser
        .parse2(tokens)
        .map_err(|e| w.err(mac.span(), format!("dict! parse error: {e}")))?;
    let mut parts = Vec::with_capacity(pairs.len());
    for p in &pairs {
        let k = expr::emit_expr(w, &p.key)?;
        let v = expr::emit_expr(w, &p.value)?;
        parts.push(format!("{}: {}", k.text, v.text));
    }
    Ok(Emitted::atomic(
        format!("{{{}}}", parts.join(", ")),
        Ty::Dict,
    ))
}

fn parse_expr_list(tokens: TokenStream, mac: &syn::Macro) -> Result<Vec<syn::Expr>, String> {
    let parser = Punctuated::<syn::Expr, syn::Token![,]>::parse_terminated;
    parser
        .parse2(tokens)
        .map(|p| p.into_iter().collect())
        .map_err(|e| {
            let s = mac.span();
            let start = s.start();
            format!(
                "{}:{}: macro arg parse error: {e}",
                start.line,
                start.column + 1
            )
        })
}

struct DictPair {
    key: syn::Expr,
    _arrow: syn::Token![=>],
    value: syn::Expr,
}

impl Parse for DictPair {
    fn parse(input: ParseStream) -> syn::Result<Self> {
        Ok(DictPair {
            key: input.parse()?,
            _arrow: input.parse()?,
            value: input.parse()?,
        })
    }
}

enum CompClause {
    For { pat: syn::Pat, iter: syn::Expr },
    If { cond: syn::Expr },
}

impl Parse for CompClause {
    fn parse(input: ParseStream) -> syn::Result<Self> {
        let lookahead = input.lookahead1();
        if lookahead.peek(syn::Token![for]) {
            let _: syn::Token![for] = input.parse()?;
            let pat = syn::Pat::parse_single(input)?;
            let _: syn::Token![in] = input.parse()?;
            let iter: syn::Expr = input.parse()?;
            Ok(CompClause::For { pat, iter })
        } else if lookahead.peek(syn::Token![if]) {
            let _: syn::Token![if] = input.parse()?;
            let cond: syn::Expr = input.parse()?;
            Ok(CompClause::If { cond })
        } else {
            Err(lookahead.error())
        }
    }
}

struct ListComp {
    expr: syn::Expr,
    clauses: Vec<CompClause>,
}

impl Parse for ListComp {
    fn parse(input: ParseStream) -> syn::Result<Self> {
        let expr: syn::Expr = input.parse()?;
        let _: syn::Token![;] = input.parse()?;
        let clauses = parse_clauses(input)?;
        Ok(ListComp { expr, clauses })
    }
}

struct DictComp {
    key: syn::Expr,
    value: syn::Expr,
    clauses: Vec<CompClause>,
}

impl Parse for DictComp {
    fn parse(input: ParseStream) -> syn::Result<Self> {
        let key: syn::Expr = input.parse()?;
        let _: syn::Token![=>] = input.parse()?;
        let value: syn::Expr = input.parse()?;
        let _: syn::Token![;] = input.parse()?;
        let clauses = parse_clauses(input)?;
        Ok(DictComp {
            key,
            value,
            clauses,
        })
    }
}

fn parse_clauses(input: ParseStream) -> syn::Result<Vec<CompClause>> {
    let mut clauses = Vec::new();
    loop {
        clauses.push(input.parse()?);
        if input.is_empty() {
            break;
        }
        let _: syn::Token![;] = input.parse()?;
    }
    Ok(clauses)
}

fn render_clauses(w: &mut PyWriter, clauses: &[CompClause]) -> Result<String, String> {
    let mut out = String::new();
    for clause in clauses {
        match clause {
            CompClause::For { pat, iter } => {
                let pat_text = pat_to_text(w, pat)?;
                let iter_expr = unwrap_iterable(iter);
                let iter_em = expr::emit_expr(w, iter_expr)?;
                out.push_str(&format!(" for {pat_text} in {}", iter_em.text));
            }
            CompClause::If { cond } => {
                let cond_em = expr::emit_expr(w, cond)?;
                out.push_str(&format!(" if {}", cond_em.text));
            }
        }
    }
    Ok(out)
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
            "comprehension pattern must be ident, wildcard, or tuple",
        )),
    }
}

fn emit_list_comp(
    w: &mut PyWriter,
    tokens: TokenStream,
    mac: &syn::Macro,
) -> Result<Emitted, String> {
    let lc: ListComp = syn::parse2(tokens)
        .map_err(|e| w.err(mac.span(), format!("comprehension! parse error: {e}")))?;
    let expr_em = expr::emit_expr(w, &lc.expr)?;
    let clauses_text = render_clauses(w, &lc.clauses)?;
    Ok(Emitted::atomic(
        format!("[{}{clauses_text}]", expr_em.text),
        Ty::List,
    ))
}

fn emit_dict_comp(
    w: &mut PyWriter,
    tokens: TokenStream,
    mac: &syn::Macro,
) -> Result<Emitted, String> {
    let dc: DictComp = syn::parse2(tokens)
        .map_err(|e| w.err(mac.span(), format!("dict_comprehension! parse error: {e}")))?;
    let k_em = expr::emit_expr(w, &dc.key)?;
    let v_em = expr::emit_expr(w, &dc.value)?;
    let clauses_text = render_clauses(w, &dc.clauses)?;
    Ok(Emitted::atomic(
        format!("{{{}: {}{clauses_text}}}", k_em.text, v_em.text),
        Ty::Dict,
    ))
}

fn emit_set_comp(
    w: &mut PyWriter,
    tokens: TokenStream,
    mac: &syn::Macro,
) -> Result<Emitted, String> {
    let lc: ListComp = syn::parse2(tokens)
        .map_err(|e| w.err(mac.span(), format!("set_comprehension! parse error: {e}")))?;
    let expr_em = expr::emit_expr(w, &lc.expr)?;
    let clauses_text = render_clauses(w, &lc.clauses)?;
    Ok(Emitted::atomic(
        format!("{{{}{clauses_text}}}", expr_em.text),
        Ty::Set,
    ))
}
