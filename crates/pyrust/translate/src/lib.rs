mod cfg;
mod emit;
mod parse;
mod tyctx;

use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};

pub use cfg::CfgEnv;

#[derive(Debug)]
pub enum Cmd {
    Translate {
        input: PathBuf,
        output: Option<PathBuf>,
        cfg: CfgEnv,
    },
    Check {
        input: PathBuf,
        cfg: CfgEnv,
    },
    Dir {
        src: PathBuf,
        out: PathBuf,
        cfg: CfgEnv,
    },
}

pub fn parse_args(args: &[String]) -> Result<Cmd, String> {
    if args.is_empty() {
        return Err("missing argument".into());
    }
    // Strip leading --cfg / --release flags. They may appear in any order
    // before the subcommand or input path.
    let mut cfg = CfgEnv::debug();
    let mut i = 0usize;
    while i < args.len() {
        match args[i].as_str() {
            "--release" => {
                cfg.apply_cfg_arg("debug_assertions=false")?;
                i += 1;
            }
            "--cfg" => {
                let val = args
                    .get(i + 1)
                    .ok_or_else(|| "--cfg requires an argument".to_string())?;
                cfg.apply_cfg_arg(val)?;
                i += 2;
            }
            _ => break,
        }
    }
    let rest = &args[i..];
    if rest.is_empty() {
        return Err("missing input".into());
    }
    match rest[0].as_str() {
        "--check" => {
            let [_, input] = rest else {
                return Err("--check expects exactly one input path".into());
            };
            Ok(Cmd::Check {
                input: input.into(),
                cfg,
            })
        }
        "--dir" => {
            if rest.len() != 4 || rest[2] != "-o" {
                return Err("--dir expects: --dir <src> -o <out>".into());
            }
            Ok(Cmd::Dir {
                src: PathBuf::from(&rest[1]),
                out: PathBuf::from(&rest[3]),
                cfg,
            })
        }
        _ => {
            let input: PathBuf = rest[0].as_str().into();
            let output = match rest.get(1).map(String::as_str) {
                None => None,
                Some("-o") => match rest.get(2) {
                    Some(p) => Some(PathBuf::from(p)),
                    None => return Err("-o requires a path argument".into()),
                },
                Some(other) => return Err(format!("unexpected argument: {other}")),
            };
            if let Some(extra) = rest.get(if output.is_some() { 3 } else { 1 }) {
                return Err(format!("unexpected trailing argument: {extra}"));
            }
            Ok(Cmd::Translate { input, output, cfg })
        }
    }
}

pub fn run(cmd: &Cmd) -> Result<(), String> {
    match cmd {
        Cmd::Translate { input, output, cfg } => translate_file(input, output.as_deref(), cfg),
        Cmd::Check { input, cfg } => check_file(input, cfg),
        Cmd::Dir { src, out, cfg } => translate_dir(src, out, cfg),
    }
}

pub fn translate_file(input: &Path, output: Option<&Path>, cfg: &CfgEnv) -> Result<(), String> {
    let source = read_source(input)?;
    let py = translate_source(&source, input, cfg)?;
    match output {
        None => {
            io::stdout()
                .write_all(py.as_bytes())
                .map_err(|e| format!("write stdout: {e}"))?;
        }
        Some(path) => {
            if let Some(parent) = path.parent()
                && !parent.as_os_str().is_empty()
            {
                fs::create_dir_all(parent)
                    .map_err(|e| format!("create {}: {e}", parent.display()))?;
            }
            fs::write(path, py.as_bytes()).map_err(|e| format!("write {}: {e}", path.display()))?;
        }
    }
    Ok(())
}

pub fn check_file(input: &Path, cfg: &CfgEnv) -> Result<(), String> {
    let source = read_source(input)?;
    let _ = translate_source(&source, input, cfg)?;
    Ok(())
}

pub fn translate_dir(src: &Path, out: &Path, cfg: &CfgEnv) -> Result<(), String> {
    if !src.is_dir() {
        return Err(format!("not a directory: {}", src.display()));
    }
    fs::create_dir_all(out).map_err(|e| format!("create {}: {e}", out.display()))?;
    let entries = walk_rs(src)?;
    let mut cfg = cfg.clone();

    // Pre-scan the bot's source tree: build the project-wide sum-enum
    // registry so cross-module `use` of a sum type can also import its
    // variant dataclasses.
    for entry in &entries {
        let rel = entry
            .strip_prefix(src)
            .map_err(|e| format!("path strip: {e}"))?
            .to_path_buf();
        let module_path = rel_to_module_path(&rel);
        let source = read_source(entry)?;
        let file = match parse::parse_file(&source, entry) {
            Ok(f) => f,
            Err(_) => continue,
        };
        let variants = collect_sum_enums(&file, &cfg);
        if !variants.is_empty() {
            cfg.sum_enum_registry.insert(module_path.clone(), variants);
        }
        for item in &file.items {
            if let syn::Item::Trait(t) = item {
                cfg.trait_registry
                    .insert(t.ident.to_string(), (t.clone(), module_path.clone()));
            }
        }
    }

    // Walk the enclosing cargo workspace's path-dep tree and collect
    // every type/trait carrying `#[pyrust::transparent]` or
    // `#[pyrust::exception]`. Pure syntactic — read .rs files, parse with
    // syn, look at attributes. Used by `emit_use` (drop transparent
    // imports) and the struct emitter (subclass `Exception`).
    let (transparent, exception, context_manager) = scan_pyrust_attrs(src);
    for n in transparent {
        cfg.transparent_def_names.insert(n);
    }
    for n in exception {
        cfg.exception_def_names.insert(n);
    }
    for n in context_manager {
        cfg.context_manager_def_names.insert(n);
    }
    cfg.inline_consts = scan_inline_consts(src);
    cfg.inline_fns = scan_inline_fns(src);

    let table = tyctx::FileTyTable::empty();
    for entry in &entries {
        let rel = entry
            .strip_prefix(src)
            .map_err(|e| format!("path strip: {e}"))?
            .to_path_buf();
        let dest = py_dest(&rel, out);
        if let Some(parent) = dest.parent() {
            fs::create_dir_all(parent).map_err(|e| format!("create {}: {e}", parent.display()))?;
        }
        let source = read_source(entry)?;
        let py = translate_source(&source, entry, &cfg)?;
        fs::write(&dest, py.as_bytes()).map_err(|e| format!("write {}: {e}", dest.display()))?;
        let _ = &table; // suppress unused warning; threading slot for future use
    }
    Ok(())
}

/// Map a Rust source path (relative to the crate root) to the
/// corresponding Python file under `out`. `mod.rs` becomes `__init__.py`
/// (the Rust module-declaration convention maps to Python's package
/// marker). `lib.rs` at the root is the bot's entry point and maps to
/// `main.py`. Everything else keeps its name and gets a `.py` extension.
fn py_dest(rel: &Path, out: &Path) -> PathBuf {
    let parent = rel.parent().unwrap_or_else(|| Path::new(""));
    let stem = rel.file_stem().and_then(|s| s.to_str()).unwrap_or("");
    let leaf = match stem {
        "mod" => "__init__.py".to_owned(),
        "lib" if parent.as_os_str().is_empty() => "main.py".to_owned(),
        _ => format!("{stem}.py"),
    };
    out.join(parent).join(leaf)
}

fn rel_to_module_path(rel: &Path) -> String {
    let mut parts: Vec<String> = rel
        .components()
        .filter_map(|c| c.as_os_str().to_str().map(String::from))
        .collect();
    if let Some(last) = parts.last_mut() {
        if let Some(stem) = Path::new(last).file_stem().and_then(|s| s.to_str()) {
            *last = stem.to_owned();
        }
        if last == "mod" || last == "lib" {
            parts.pop();
        }
    }
    parts.join(".")
}

fn collect_sum_enums(
    file: &syn::File,
    cfg: &CfgEnv,
) -> std::collections::HashMap<String, Vec<String>> {
    let mut out = std::collections::HashMap::new();
    for item in &file.items {
        let syn::Item::Enum(e) = item else { continue };
        if !cfg.item_enabled(&e.attrs).unwrap_or(true) {
            continue;
        }
        let is_sum = e
            .variants
            .iter()
            .any(|v| !matches!(v.fields, syn::Fields::Unit));
        if !is_sum {
            continue;
        }
        let name = e.ident.to_string();
        let variants: Vec<String> = e.variants.iter().map(|v| v.ident.to_string()).collect();
        out.insert(name, variants);
    }
    out
}

/// Walk upwards from `src` to the workspace root (the topmost directory
/// containing a `Cargo.toml`), then walk the whole workspace's `.rs`
/// files looking for items with `#[pyrust::transparent]` or
/// `#[pyrust::exception]` attributes. Returns `(transparent, exception)`
/// name sets. Pure syntactic — no `ra_ap`, no cargo metadata.
fn scan_pyrust_attrs(
    src: &Path,
) -> (
    std::collections::HashSet<String>,
    std::collections::HashSet<String>,
    std::collections::HashSet<String>,
) {
    let mut transparent = std::collections::HashSet::new();
    let mut exception = std::collections::HashSet::new();
    let mut context_manager = std::collections::HashSet::new();
    let workspace_root = match find_workspace_root(src) {
        Some(r) => r,
        None => src.to_path_buf(),
    };
    let mut stack = vec![workspace_root];
    while let Some(dir) = stack.pop() {
        let entries = match fs::read_dir(&dir) {
            Ok(e) => e,
            Err(_) => continue,
        };
        for entry in entries.flatten() {
            let path = entry.path();
            let Ok(ft) = entry.file_type() else { continue };
            if ft.is_dir() {
                // Skip target dirs and hidden dirs.
                let name = entry.file_name();
                let name_str = name.to_string_lossy();
                if name_str == "target" || name_str.starts_with('.') {
                    continue;
                }
                stack.push(path);
            } else if ft.is_file() && path.extension().is_some_and(|ext| ext == "rs") {
                let Ok(source) = fs::read_to_string(&path) else {
                    continue;
                };
                let Ok(file) = syn::parse_file(&source) else {
                    continue;
                };
                collect_pyrust_attrs_from_file(
                    &file,
                    &mut transparent,
                    &mut exception,
                    &mut context_manager,
                );
            }
        }
    }
    (transparent, exception, context_manager)
}

/// Walk the workspace and collect every `#[pyrust::inline]`-annotated
/// const that has a literal RHS. Returns name → Python literal text.
/// Names that conflict (same name, different literal across files) are
/// dropped from the map so we never inline ambiguously.
fn scan_inline_consts(src: &Path) -> std::collections::HashMap<String, String> {
    let mut map: std::collections::HashMap<String, String> = std::collections::HashMap::new();
    let mut conflicts: std::collections::HashSet<String> = std::collections::HashSet::new();
    let workspace_root = match find_workspace_root(src) {
        Some(r) => r,
        None => src.to_path_buf(),
    };
    let mut stack = vec![workspace_root];
    while let Some(dir) = stack.pop() {
        let entries = match fs::read_dir(&dir) {
            Ok(e) => e,
            Err(_) => continue,
        };
        for entry in entries.flatten() {
            let path = entry.path();
            let Ok(ft) = entry.file_type() else { continue };
            if ft.is_dir() {
                let name = entry.file_name();
                let name_str = name.to_string_lossy();
                if name_str == "target" || name_str.starts_with('.') {
                    continue;
                }
                stack.push(path);
            } else if ft.is_file() && path.extension().is_some_and(|ext| ext == "rs") {
                let Ok(source) = fs::read_to_string(&path) else {
                    continue;
                };
                let Ok(file) = syn::parse_file(&source) else {
                    continue;
                };
                for item in &file.items {
                    let syn::Item::Const(c) = item else { continue };
                    if !has_pyrust_inline(&c.attrs) {
                        continue;
                    }
                    let Some(lit) = literal_const_text(&c.expr) else {
                        continue;
                    };
                    let name = c.ident.to_string();
                    if conflicts.contains(&name) {
                        continue;
                    }
                    match map.get(&name) {
                        Some(prev) if *prev != lit => {
                            conflicts.insert(name.clone());
                            map.remove(&name);
                        }
                        _ => {
                            map.insert(name, lit);
                        }
                    }
                }
            }
        }
    }
    map
}

fn has_pyrust_inline(attrs: &[syn::Attribute]) -> bool {
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

fn literal_const_text(expr: &syn::Expr) -> Option<String> {
    match expr {
        syn::Expr::Lit(l) => match &l.lit {
            syn::Lit::Int(i) => Some(i.base10_digits().to_string()),
            syn::Lit::Float(f) => Some(f.base10_digits().to_string()),
            syn::Lit::Bool(b) => Some(if b.value { "True" } else { "False" }.to_string()),
            syn::Lit::Str(s) => {
                let v = s.value().replace('\\', "\\\\").replace('"', "\\\"");
                Some(format!("\"{v}\""))
            }
            _ => None,
        },
        syn::Expr::Unary(u) if matches!(u.op, syn::UnOp::Neg(_)) => {
            literal_const_text(&u.expr).map(|s| format!("-{s}"))
        }
        _ => None,
    }
}

fn find_workspace_root(start: &Path) -> Option<PathBuf> {
    let canonical = start.canonicalize().ok()?;
    let mut dir: &Path = if canonical.is_file() {
        canonical.parent()?
    } else {
        &canonical
    };
    let mut last_with_cargo: Option<PathBuf> = None;
    loop {
        if dir.join("Cargo.toml").is_file() {
            last_with_cargo = Some(dir.to_path_buf());
        }
        match dir.parent() {
            Some(p) if p != dir => dir = p,
            _ => break,
        }
    }
    last_with_cargo
}

fn collect_pyrust_attrs_from_file(
    file: &syn::File,
    transparent: &mut std::collections::HashSet<String>,
    exception: &mut std::collections::HashSet<String>,
    context_manager: &mut std::collections::HashSet<String>,
) {
    for item in &file.items {
        let (name, attrs): (String, &[syn::Attribute]) = match item {
            syn::Item::Struct(s) => (s.ident.to_string(), &s.attrs),
            syn::Item::Enum(e) => (e.ident.to_string(), &e.attrs),
            syn::Item::Trait(t) => (t.ident.to_string(), &t.attrs),
            _ => continue,
        };
        for attr in attrs {
            let path_text: String = attr
                .path()
                .segments
                .iter()
                .map(|s| s.ident.to_string())
                .collect::<Vec<_>>()
                .join("::");
            if path_text == "pyrust::transparent" {
                transparent.insert(name.clone());
            } else if path_text == "pyrust::exception" {
                exception.insert(name.clone());
            } else if path_text == "pyrust::context_manager" {
                context_manager.insert(name.clone());
            }
        }
    }
}

fn walk_rs(root: &Path) -> Result<Vec<PathBuf>, String> {
    let mut found = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        for entry in fs::read_dir(&dir).map_err(|e| format!("read {}: {e}", dir.display()))? {
            let entry = entry.map_err(|e| format!("read entry: {e}"))?;
            let path = entry.path();
            let ft = entry
                .file_type()
                .map_err(|e| format!("file_type {}: {e}", path.display()))?;
            if ft.is_dir() {
                stack.push(path);
            } else if ft.is_file() && path.extension().is_some_and(|ext| ext == "rs") {
                found.push(path);
            }
        }
    }
    found.sort();
    Ok(found)
}

fn read_source(path: &Path) -> Result<String, String> {
    fs::read_to_string(path).map_err(|e| format!("read {}: {e}", path.display()))
}

fn translate_source(source: &str, path: &Path, cfg: &CfgEnv) -> Result<String, String> {
    let file = parse::parse_file(source, path)?;
    emit::emit_file(&file, path, cfg, &tyctx::FileTyTable::empty())
}

/// Walk the workspace and collect every `#[pyrust::inline]`-annotated
/// function or `&self` method whose body is a single expression.
/// Same conflict policy as `scan_inline_consts`: a name with two
/// different bodies (or different param lists) across files is
/// dropped from the map.
fn scan_inline_fns(src: &Path) -> std::collections::HashMap<String, crate::cfg::InlineFn> {
    let mut map: std::collections::HashMap<String, crate::cfg::InlineFn> = std::collections::HashMap::new();
    let mut conflicts: std::collections::HashSet<String> = std::collections::HashSet::new();
    // Workspace-wide collection of all method/free-fn bodies by name.
    // After scanning, any inline-registered name whose body diverges
    // from any same-named method anywhere in the workspace (annotated
    // or not) is dropped: substituting the wrong body at a call site
    // whose receiver-type we can't statically determine would change
    // semantics.
    let mut all_bodies: std::collections::HashMap<String, std::collections::HashSet<String>> =
        std::collections::HashMap::new();
    let workspace_root = match find_workspace_root(src) {
        Some(r) => r,
        None => src.to_path_buf(),
    };
    let mut stack = vec![workspace_root];
    while let Some(dir) = stack.pop() {
        let entries = match fs::read_dir(&dir) {
            Ok(e) => e,
            Err(_) => continue,
        };
        for entry in entries.flatten() {
            let path = entry.path();
            let Ok(ft) = entry.file_type() else { continue };
            if ft.is_dir() {
                let name = entry.file_name();
                let name_str = name.to_string_lossy();
                if name_str == "target" || name_str.starts_with('.') {
                    continue;
                }
                stack.push(path);
            } else if ft.is_file() && path.extension().is_some_and(|ext| ext == "rs") {
                let Ok(source) = fs::read_to_string(&path) else {
                    continue;
                };
                let Ok(file) = syn::parse_file(&source) else {
                    continue;
                };
                collect_inline_fns(&file, &mut map, &mut conflicts);
                collect_all_method_bodies(&file, &mut all_bodies);
            }
        }
    }
    // Drop entries whose method name has divergent bodies workspace-wide.
    map.retain(|name, def| {
        let Some(bodies) = all_bodies.get(name) else {
            return true;
        };
        let inline_sig = format!("{:?}", def.body);
        // Safe to keep iff every workspace impl/fn with this name has
        // the same body as the inline def. (A 1-element set containing
        // the inline body itself is the common case.)
        bodies.iter().all(|b| b == &inline_sig)
    });
    map
}

/// Collect a body signature for every fn/method (annotated or not)
/// keyed by name. Used by `scan_inline_fns` to detect cross-impl
/// divergence. Single-expression bodies stringify to the inner Expr's
/// Debug repr so they line up with the inline registry's `def.body`
/// signatures; multi-statement bodies stringify to the full `Vec<Stmt>`.
fn collect_all_method_bodies(
    file: &syn::File,
    out: &mut std::collections::HashMap<String, std::collections::HashSet<String>>,
) {
    fn block_sig(block: &syn::Block) -> String {
        if block.stmts.len() == 1
            && let syn::Stmt::Expr(e, None) = &block.stmts[0]
        {
            return format!("{e:?}");
        }
        format!("{:?}", block.stmts)
    }
    for item in &file.items {
        match item {
            syn::Item::Fn(f) => {
                out.entry(f.sig.ident.to_string()).or_default().insert(block_sig(&f.block));
            }
            syn::Item::Impl(im) => {
                for ii in &im.items {
                    if let syn::ImplItem::Fn(f) = ii {
                        out.entry(f.sig.ident.to_string()).or_default().insert(block_sig(&f.block));
                    }
                }
            }
            syn::Item::Trait(t) => {
                for ii in &t.items {
                    if let syn::TraitItem::Fn(f) = ii
                        && let Some(b) = &f.default
                    {
                        out.entry(f.sig.ident.to_string()).or_default().insert(block_sig(b));
                    }
                }
            }
            _ => {}
        }
    }
}

fn collect_inline_fns(
    file: &syn::File,
    map: &mut std::collections::HashMap<String, crate::cfg::InlineFn>,
    conflicts: &mut std::collections::HashSet<String>,
) {
    fn body_signature(body: &syn::Expr) -> String {
        // Conflict detection across files: just stringify via Debug.
        // Token-equality would be tighter but requires `quote::ToTokens`,
        // which isn't in this crate's deps. Debug captures structural
        // equality including spans, which is fine — same source text
        // round-trips to the same Debug output deterministically.
        format!("{body:?}")
    }

    fn extract_single_expr(b: &syn::Block) -> Option<&syn::Expr> {
        // Body must be exactly one statement, a tail expression
        // (no semicolon).
        if b.stmts.len() != 1 {
            return None;
        }
        match &b.stmts[0] {
            syn::Stmt::Expr(e, None) => Some(e),
            _ => None,
        }
    }

    fn try_register(
        name: String,
        sig: &syn::Signature,
        body: Option<&syn::Expr>,
        map: &mut std::collections::HashMap<String, crate::cfg::InlineFn>,
        conflicts: &mut std::collections::HashSet<String>,
    ) {
        if conflicts.contains(&name) {
            return;
        }
        let Some(body) = body else {
            return;
        };
        // Reject `&mut self` methods: substitution would duplicate
        // mutation effects.
        let has_self = matches!(sig.inputs.first(), Some(syn::FnArg::Receiver(r)) if r.mutability.is_none());
        if matches!(sig.inputs.first(), Some(syn::FnArg::Receiver(r)) if r.mutability.is_some()) {
            return;
        }
        let mut params: Vec<String> = Vec::new();
        for arg in sig.inputs.iter().skip(if has_self { 1 } else { 0 }) {
            let syn::FnArg::Typed(pt) = arg else {
                return;
            };
            let syn::Pat::Ident(pi) = pt.pat.as_ref() else {
                return;
            };
            params.push(pi.ident.to_string());
        }
        let new_def = crate::cfg::InlineFn {
            params,
            has_self,
            body: body.clone(),
        };
        match map.get(&name) {
            Some(prev) => {
                if prev.params != new_def.params
                    || prev.has_self != new_def.has_self
                    || body_signature(&prev.body) != body_signature(&new_def.body)
                {
                    conflicts.insert(name.clone());
                    map.remove(&name);
                }
            }
            None => {
                map.insert(name, new_def);
            }
        }
    }

    for item in &file.items {
        match item {
            syn::Item::Fn(f) if has_pyrust_inline(&f.attrs) => {
                try_register(
                    f.sig.ident.to_string(),
                    &f.sig,
                    extract_single_expr(&f.block),
                    map,
                    conflicts,
                );
            }
            syn::Item::Impl(im) => {
                for ii in &im.items {
                    if let syn::ImplItem::Fn(f) = ii
                        && has_pyrust_inline(&f.attrs)
                    {
                        try_register(
                            f.sig.ident.to_string(),
                            &f.sig,
                            extract_single_expr(&f.block),
                            map,
                            conflicts,
                        );
                    }
                }
            }
            _ => {}
        }
    }
}
