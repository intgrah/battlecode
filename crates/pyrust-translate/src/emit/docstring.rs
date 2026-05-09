use syn::Attribute;

/// Collects all `#[doc = "..."]` attribute values into a single string.
///
/// `///` doc comments are stored by syn as `#[doc = " text"]` attributes (note
/// the leading space). We strip a single leading space from each line and join
/// with newlines so the output reads like the original source.
pub fn collect(attrs: &[Attribute]) -> Option<String> {
    let lines: Vec<String> = attrs.iter().filter_map(extract).collect();
    if lines.is_empty() {
        None
    } else {
        Some(lines.join("\n"))
    }
}

fn extract(attr: &Attribute) -> Option<String> {
    if !attr.path().is_ident("doc") {
        return None;
    }
    let syn::Meta::NameValue(nv) = &attr.meta else {
        return None;
    };
    let syn::Expr::Lit(lit) = &nv.value else {
        return None;
    };
    let syn::Lit::Str(s) = &lit.lit else {
        return None;
    };
    let raw = s.value();
    let trimmed = raw.strip_prefix(' ').unwrap_or(&raw).to_owned();
    Some(trimmed)
}

/// Format a multi-line docstring as a Python triple-quoted string. The output
/// does not include the indent prefix (the writer adds that).
pub fn format(text: &str) -> Vec<String> {
    if !text.contains('\n') {
        let escaped = escape_for_triple_quote(text);
        return vec![format!("\"\"\"{escaped}\"\"\"")];
    }
    let mut out = Vec::new();
    out.push(String::from("\"\"\""));
    for line in text.split('\n') {
        out.push(escape_for_triple_quote(line));
    }
    out.push(String::from("\"\"\""));
    out
}

fn escape_for_triple_quote(line: &str) -> String {
    line.replace('\\', "\\\\").replace("\"\"\"", "\\\"\\\"\\\"")
}
