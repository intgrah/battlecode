//! AST-driven migration of v55 source to use the pyrust DSL macros.
//!
//! Strategy: rewrite every iterator chain as a single nested DSL macro
//! call from inside-out. So `xs.iter().map(|x| x.foo).sum::<i64>()`
//! becomes `pyrust::sum!(pyrust::map!(pyrust::iter!(xs), |x| x.foo))`.
//! The Rust macros expand to identical iterator chains (zero-cost); the
//! pyrust translator pattern-matches each macro's path and emits the
//! matching Python idiom (e.g. `sum((x.foo for x in xs))`).
//!
//! Arguments inside chain methods (notably closure bodies) are emitted
//! verbatim from the source; if they contain their own iterator chains
//! the bot author hand-fixes those — the visitor would re-enter them
//! anyway but to avoid overlapping edits we keep them as-is in this
//! pass and rely on a re-run.

use proc_macro2::Span;
use std::path::PathBuf;
use syn::spanned::Spanned;
use syn::visit::Visit;

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
    /// True when the current visit is inside the receiver chain of an
    /// already-rewriting chain root. Suppresses inner roots so a single
    /// edit covers the whole chain.
    inside_chain_recv: bool,
}

/// Method names the migrator wraps in pyrust DSL macros. Returns the
/// macro name (which may differ from the method name — e.g.
/// `min_by_key` → `min_by`). The argument count is part of the
/// signature so `T::insert(k, v)` (2-arg) and `T::insert(idx, x)`
/// (Vec::insert, also 2-arg) don't get mistakenly rewritten — only
/// methods on this whitelist do.
fn dsl_macro(method: &str, n_args: usize) -> Option<&'static str> {
    match (method, n_args) {
        // ---- Iterator-chain identities (Python no-op: emit recv) ----
        ("iter", 0) | ("into_iter", 0) | ("copied", 0) | ("cloned", 0) | ("collect", 0) => {
            Some(match method {
                "iter" => "iter",
                "into_iter" => "into_iter",
                "copied" => "copied",
                "cloned" => "cloned",
                "collect" => "collect",
                _ => unreachable!(),
            })
        }
        // ---- Iterator-chain transforms ----
        ("rev", 0) => Some("rev"),
        ("enumerate", 0) => Some("enumerate"),
        ("count", 0) => Some("count"),
        ("sum", 0) => Some("sum"),
        ("min", 0) => Some("min"),
        ("max", 0) => Some("max"),
        ("zip", 1) => Some("zip"),
        ("chain", 1) => Some("chain"),
        ("take", 1) => Some("take"),
        ("skip", 1) => Some("skip"),
        ("map", 1) => Some("map"),
        ("filter", 1) => Some("filter"),
        ("filter_map", 1) => Some("filter_map"),
        ("find", 1) => Some("find"),
        ("any", 1) => Some("any"),
        ("all", 1) => Some("all"),
        ("min_by_key", 1) => Some("min_by"),
        ("max_by_key", 1) => Some("max_by"),
        ("sort_by_key", 1) => Some("sort_by_key"),
        // ---- Conversions / utilities ----
        ("to_string", 0) => Some("to_string"),
        ("contains", 1) => Some("vec::contains"),
        ("contains_key", 1) => Some("dict::contains"),
        // ---- Mutating Vec/Set/Dict methods (single-shot) ----
        ("push", 1) => Some("vec::push"),
        ("push_back", 1) => Some("vec::push_back"),
        ("push_front", 1) => Some("vec::push_front"),
        ("pop", 0) => Some("vec::pop"),
        ("pop_front", 0) => Some("vec::pop_front"),
        ("extend", 1) => Some("vec::extend"),
        // 1-arg `.insert(x)` is HashSet::insert / BTreeSet::insert; the
        // bot's Vec::insert sites (2-arg with index) translate to dict
        // insert below — bot must hand-fix any Vec::insert site.
        ("insert", 1) => Some("set::add"),
        ("insert", 2) => Some("dict::insert"),
        // `.remove(&k)` 1-arg covers HashSet, HashMap (returns Option),
        // BTreeSet/Map. Default to set::remove.
        ("remove", 1) => Some("set::remove"),
        // ---- Option methods (single-shot, not chain) ----
        ("is_some", 0) => Some("is_some"),
        ("is_none", 0) => Some("is_none"),
        ("unwrap", 0) => Some("unwrap"),
        ("expect", 1) => Some("expect"),
        ("unwrap_or", 1) => Some("unwrap_or"),
        _ => None,
    }
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
            inside_chain_recv: false,
        }
    }

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

    fn span_text(&self, span: Span) -> String {
        self.span_to_byte_range(span)
            .map(|(s, e)| self.src[s..e].to_string())
            .unwrap_or_default()
    }

    fn add_edit(&mut self, start: usize, end: usize, replacement: String) {
        self.edits.push(Edit {
            start,
            end,
            replacement,
        });
    }

    /// Build the full nested DSL text for a chain-root method call.
    /// Recursively handles inner chain methods on the receiver.
    fn build_chain_text(&self, mc: &syn::ExprMethodCall) -> String {
        let method = mc.method.to_string();
        let macro_name = dsl_macro(&method, mc.args.len()).expect("checked at call site");
        let recv_text = self.build_recv_text(&mc.receiver);
        let arg_texts: Vec<String> = mc.args.iter().map(|a| self.span_text(a.span())).collect();
        if arg_texts.is_empty() {
            format!("pyrust::{}!({})", macro_name, recv_text)
        } else {
            format!(
                "pyrust::{}!({}, {})",
                macro_name,
                recv_text,
                arg_texts.join(", ")
            )
        }
    }

    /// Build text for an expression appearing as the receiver of a
    /// chain root. If `e` is a chain method itself, recurse to build
    /// its DSL form. If `e` is a non-chain method call, rewrite ITS
    /// receiver recursively and keep the method name + args verbatim
    /// (so chains buried under a non-chain like `.next()` still get
    /// migrated). For all other expression kinds, emit original
    /// source text.
    fn build_recv_text(&self, e: &syn::Expr) -> String {
        if let syn::Expr::MethodCall(mc) = e {
            if dsl_macro(&mc.method.to_string(), mc.args.len()).is_some() {
                return self.build_chain_text(mc);
            }
            // Non-chain method call sitting in the receiver path —
            // rewrite its own receiver but keep the method call form.
            let recv_text = self.build_recv_text(&mc.receiver);
            let method = mc.method.to_string();
            let turbofish_text = mc
                .turbofish
                .as_ref()
                .map(|t| self.span_text(t.span()))
                .unwrap_or_default();
            let arg_texts: Vec<String> =
                mc.args.iter().map(|a| self.span_text(a.span())).collect();
            return format!(
                "{}.{}{}({})",
                recv_text,
                method,
                turbofish_text,
                arg_texts.join(", ")
            );
        }
        self.span_text(e.span())
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
        let method = mc.method.to_string();
        let n_args = mc.args.len();
        let is_chain = dsl_macro(&method, n_args).is_some();

        if self.inside_chain_recv {
            // The outer chain root's `build_chain_text` has already
            // captured the receiver path (including any non-chain
            // methods like `.next()` wrapped around chains). Don't
            // emit any new edits along this path. Args are independent
            // — visit them with the flag reset.
            for arg in &mc.args {
                let saved = self.inside_chain_recv;
                self.inside_chain_recv = false;
                self.visit_expr(arg);
                self.inside_chain_recv = saved;
            }
            // Walk the receiver subtree under the same flag so any
            // chains nested in non-chain receivers along this path
            // are not promoted to roots either.
            self.visit_expr(&mc.receiver);
            return;
        }

        if is_chain {
            // CHAIN ROOT — emit a single edit covering the whole chain.
            let rep = self.build_chain_text(mc);
            if let Some((start, end)) = self.span_to_byte_range(mc.span()) {
                self.add_edit(start, end, rep);
            }
            // Walk receiver under the flag (suppress inner roots).
            self.inside_chain_recv = true;
            self.visit_expr(&mc.receiver);
            self.inside_chain_recv = false;
            // Args are independent (visit normally to find their own
            // chain roots).
            for arg in &mc.args {
                self.visit_expr(arg);
            }
            return;
        }

        // Non-chain method call at the top level. Walk children
        // normally — they may host chain roots independently.
        syn::visit::visit_expr_method_call(self, mc);
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
    let mut total_changed = 0usize;
    let mut total = 0usize;
    let dir = PathBuf::from(dir);
    walk(&dir, &mut |p| {
        total += 1;
        if migrate_file(p).unwrap_or(false) {
            total_changed += 1;
        }
    })?;
    println!("changed {total_changed}/{total} files");
    Ok(())
}
