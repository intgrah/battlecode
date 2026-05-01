use syn::spanned::Spanned;

use super::expr;
use super::types::Ty;
use super::writer::PyWriter;

/// Whether the pattern matches the literal Python value `None`.
pub fn is_none_pattern(pat: &syn::Pat) -> bool {
    match pat {
        syn::Pat::Ident(i) => i.ident == "None",
        syn::Pat::Path(p) => {
            if p.qself.is_some() {
                return false;
            }
            let segs: Vec<String> = p
                .path
                .segments
                .iter()
                .map(|s| s.ident.to_string())
                .collect();
            let slice: Vec<&str> = segs.iter().map(String::as_str).collect();
            matches!(slice.as_slice(), ["None"] | ["Option", "None"])
        }
        syn::Pat::Paren(p) => is_none_pattern(&p.pat),
        _ => false,
    }
}

/// Walk a pattern and declare any ident bindings it introduces in the current
/// scope frame so that the arm body can reference them.
pub fn declare_pat_bindings(w: &mut PyWriter, pat: &syn::Pat) {
    match pat {
        syn::Pat::Ident(i) => {
            if i.ident != "None" {
                w.declare(&i.ident.to_string(), Ty::Unknown);
            }
        }
        syn::Pat::Tuple(t) => {
            for elem in &t.elems {
                declare_pat_bindings(w, elem);
            }
        }
        syn::Pat::TupleStruct(ts) => {
            for elem in &ts.elems {
                declare_pat_bindings(w, elem);
            }
        }
        syn::Pat::Struct(s) => {
            for fp in &s.fields {
                declare_pat_bindings(w, &fp.pat);
            }
        }
        syn::Pat::Or(o) => {
            if let Some(first) = o.cases.first() {
                declare_pat_bindings(w, first);
            }
        }
        syn::Pat::Paren(p) => declare_pat_bindings(w, &p.pat),
        syn::Pat::Reference(r) => declare_pat_bindings(w, &r.pat),
        _ => {}
    }
}

/// Convert a Rust pattern to its Python `match`/`case` form.
pub fn pat_to_python(w: &mut PyWriter, pat: &syn::Pat) -> Result<String, String> {
    match pat {
        syn::Pat::Wild(_) => Ok("_".to_owned()),
        syn::Pat::Ident(i) => {
            if i.subpat.is_some() {
                return Err(w.err(i.span(), "subpatterns in match arms not supported"));
            }
            if i.by_ref.is_some() {
                return Err(w.err(i.span(), "ref bindings in match arms not supported"));
            }
            // `None` (capitalised) is conventionally the Option::None constant.
            if i.ident == "None" {
                Ok("None".to_owned())
            } else {
                Ok(i.ident.to_string())
            }
        }
        syn::Pat::Lit(lit) => {
            // A literal pattern wraps an ExprLit; emit it as the literal.
            let em = expr::emit_expr(w, &syn::Expr::Lit(lit.clone()))?;
            Ok(em.text)
        }
        syn::Pat::Path(p) => {
            // `None` / `Option::None` / `MyEnum::Variant`.
            if p.qself.is_none() {
                let segs: Vec<String> = p
                    .path
                    .segments
                    .iter()
                    .map(|s| s.ident.to_string())
                    .collect();
                let slice: Vec<&str> = segs.iter().map(String::as_str).collect();
                return match slice.as_slice() {
                    ["None"] | ["Option", "None"] => Ok("None".to_owned()),
                    [single] => Ok((*single).to_owned()),
                    [class, variant] => {
                        // Sum-type enum variant: dataclass `ClassVariant()`.
                        // C-style enum: literal `Class.Variant`.
                        if w.is_sum_enum(class) {
                            Ok(format!("{class}{variant}()"))
                        } else {
                            Ok(format!("{class}.{variant}"))
                        }
                    }
                    _ => Err(w.err(
                        p.span(),
                        format!("unsupported path pattern: {}", slice.join("::")),
                    )),
                };
            }
            Err(w.err(p.span(), "qualified path pattern not supported"))
        }
        syn::Pat::TupleStruct(ts) => {
            if ts.qself.is_some() {
                return Err(w.err(ts.span(), "qualified pattern not supported"));
            }
            let segs: Vec<String> = ts
                .path
                .segments
                .iter()
                .map(|s| s.ident.to_string())
                .collect();
            let slice: Vec<&str> = segs.iter().map(String::as_str).collect();
            // `Some(p)` collapses to the inner pattern.
            if matches!(slice.as_slice(), ["Some"] | ["Option", "Some"]) {
                if ts.elems.len() != 1 {
                    return Err(w.err(ts.span(), "Some pattern expects exactly one binding"));
                }
                return pat_to_python(w, ts.elems.first().unwrap());
            }
            // Sum-type enum tuple variant: `Foo::Bar(a, b)` → dataclass
            // `FooBar(_0=a, _1=b)` matching `emit_sum_enum`'s convention.
            // Bare 1-segment paths (`SomeStruct(a)`) likewise become
            // `SomeStruct(_0=a)`.
            let class = match slice.as_slice() {
                [single] => (*single).to_owned(),
                [head, tail] => format!("{head}{tail}"),
                _ => {
                    return Err(w.err(
                        ts.span(),
                        format!(
                            "unsupported tuple-struct pattern path: {}",
                            slice.join("::")
                        ),
                    ));
                }
            };
            let mut parts = Vec::with_capacity(ts.elems.len());
            for (i, elem) in ts.elems.iter().enumerate() {
                let inner = pat_to_python(w, elem)?;
                parts.push(format!("_{i}={inner}"));
            }
            Ok(format!("{class}({})", parts.join(", ")))
        }
        syn::Pat::Tuple(t) => {
            let mut parts = Vec::with_capacity(t.elems.len());
            for elem in &t.elems {
                parts.push(pat_to_python(w, elem)?);
            }
            Ok(format!("({})", parts.join(", ")))
        }
        syn::Pat::Struct(s) => {
            // `Foo::Bar { x, y, .. }` — sum-type enum with named fields.
            // Emit as `FooBar(x=x, y=y)` matching the dataclass-per-variant
            // convention. Bare struct patterns `Foo { ... }` map to `Foo(...)`.
            if s.qself.is_some() {
                return Err(w.err(s.span(), "qualified struct pattern not supported"));
            }
            let segs: Vec<String> = s
                .path
                .segments
                .iter()
                .map(|seg| seg.ident.to_string())
                .collect();
            let class = match segs.as_slice() {
                [single] => single.clone(),
                [head, tail] => format!("{head}{tail}"),
                _ => {
                    return Err(w.err(
                        s.span(),
                        format!("unsupported struct pattern path: {}", segs.join("::")),
                    ));
                }
            };
            let mut parts = Vec::with_capacity(s.fields.len());
            for fp in &s.fields {
                let field = match &fp.member {
                    syn::Member::Named(n) => n.to_string(),
                    syn::Member::Unnamed(_) => {
                        return Err(
                            w.err(fp.span(), "unnamed field in struct pattern not supported")
                        );
                    }
                };
                let inner = pat_to_python(w, &fp.pat)?;
                parts.push(format!("{field}={inner}"));
            }
            // The `..` rest pattern is silent — Python's class pattern is
            // already by-keyword, unspecified fields don't need to appear.
            Ok(format!("{class}({})", parts.join(", ")))
        }
        syn::Pat::Or(o) => {
            let mut parts = Vec::with_capacity(o.cases.len());
            for case in &o.cases {
                parts.push(pat_to_python(w, case)?);
            }
            Ok(parts.join(" | "))
        }
        syn::Pat::Paren(p) => pat_to_python(w, &p.pat),
        syn::Pat::Reference(r) => pat_to_python(w, &r.pat),
        other => Err(w.err(
            other.span(),
            format!("unsupported pattern in match arm: {}", pat_kind(other)),
        )),
    }
}

fn pat_kind(pat: &syn::Pat) -> &'static str {
    match pat {
        syn::Pat::Const(_) => "const",
        syn::Pat::Ident(_) => "ident",
        syn::Pat::Lit(_) => "literal",
        syn::Pat::Macro(_) => "macro",
        syn::Pat::Or(_) => "or",
        syn::Pat::Paren(_) => "paren",
        syn::Pat::Path(_) => "path",
        syn::Pat::Range(_) => "range",
        syn::Pat::Reference(_) => "reference",
        syn::Pat::Rest(_) => "rest",
        syn::Pat::Slice(_) => "slice",
        syn::Pat::Struct(_) => "struct",
        syn::Pat::Tuple(_) => "tuple",
        syn::Pat::TupleStruct(_) => "tuple-struct",
        syn::Pat::Type(_) => "type-ascribed",
        syn::Pat::Verbatim(_) => "verbatim",
        syn::Pat::Wild(_) => "wildcard",
        _ => "pattern",
    }
}
