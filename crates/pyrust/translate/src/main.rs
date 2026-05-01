mod cfg;
mod emit;
mod parse;
mod tyctx;

use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use cfg::CfgEnv;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match parse(&args) {
        Ok(cmd) => match run(&cmd) {
            Ok(()) => ExitCode::SUCCESS,
            Err(e) => {
                eprintln!("pyrust-translate: {e}");
                ExitCode::from(1)
            }
        },
        Err(e) => {
            eprintln!("pyrust-translate: {e}");
            eprintln!();
            eprintln!("usage:");
            eprintln!(
                "  pyrust-translate [--cfg KEY[=VAL]]... [--release] <input.rs> [-o <output.py>]"
            );
            eprintln!("  pyrust-translate [--cfg KEY[=VAL]]... [--release] --check <input.rs>");
            eprintln!(
                "  pyrust-translate [--cfg KEY[=VAL]]... [--release] --dir <src_dir> -o <out_dir>"
            );
            eprintln!();
            eprintln!("  --release           equivalent to --cfg debug_assertions=false");
            eprintln!("  --cfg KEY           set boolean cfg flag (truthy)");
            eprintln!("  --cfg KEY=true|false explicit boolean");
            eprintln!("  --cfg KEY=value     set kv form for cfg(KEY = \"value\") matching");
            ExitCode::from(2)
        }
    }
}

#[derive(Debug)]
enum Cmd {
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

fn parse(args: &[String]) -> Result<Cmd, String> {
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

fn run(cmd: &Cmd) -> Result<(), String> {
    match cmd {
        Cmd::Translate { input, output, cfg } => translate_file(input, output.as_deref(), cfg),
        Cmd::Check { input, cfg } => check_file(input, cfg),
        Cmd::Dir { src, out, cfg } => translate_dir(src, out, cfg),
    }
}

fn translate_file(input: &Path, output: Option<&Path>, cfg: &CfgEnv) -> Result<(), String> {
    translate_file_with_types(input, output, cfg, &tyctx::FileTyTable::empty())
}

fn translate_file_with_types(
    input: &Path,
    output: Option<&Path>,
    cfg: &CfgEnv,
    types: &tyctx::FileTyTable,
) -> Result<(), String> {
    let source = read_source(input)?;
    let py = translate_source(&source, input, cfg, types)?;
    match output {
        None => {
            io::stdout()
                .write_all(py.as_bytes())
                .map_err(|e| format!("write stdout: {e}"))?;
        }
        Some(path) => {
            if let Some(parent) = path.parent() {
                if !parent.as_os_str().is_empty() {
                    fs::create_dir_all(parent)
                        .map_err(|e| format!("create {}: {e}", parent.display()))?;
                }
            }
            fs::write(path, py.as_bytes()).map_err(|e| format!("write {}: {e}", path.display()))?;
        }
    }
    Ok(())
}

fn check_file(input: &Path, cfg: &CfgEnv) -> Result<(), String> {
    let source = read_source(input)?;
    let _ = translate_source(&source, input, cfg, &tyctx::FileTyTable::empty())?;
    Ok(())
}

fn translate_dir(src: &Path, out: &Path, cfg: &CfgEnv) -> Result<(), String> {
    if !src.is_dir() {
        return Err(format!("not a directory: {}", src.display()));
    }
    fs::create_dir_all(out).map_err(|e| format!("create {}: {e}", out.display()))?;
    let entries = walk_rs(src)?;
    // Pre-scan: build the project-wide sum-enum registry so cross-module
    // `use` of a sum type can also import its variant dataclasses.
    let mut cfg = cfg.clone();
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
        // Build the convention set: scan every impl block, every method
        // whose name matches a struct field on the impl target. The
        // resulting names are emitted as field accesses by `emit_method`.
        for item in &file.items {
            if let syn::Item::Impl(im) = item
                && let Some(target) = impl_target_struct_name(&im.self_ty)
                && let Some(struct_fields) = struct_fields_in_file(&file, &target)
            {
                for ii in &im.items {
                    if let syn::ImplItem::Fn(f) = ii
                        && f.sig
                            .inputs
                            .iter()
                            .all(|inp| matches!(inp, syn::FnArg::Receiver(_)))
                    {
                        let name = f.sig.ident.to_string();
                        if struct_fields.iter().any(|f| f == &name) {
                            cfg.field_accessor_names.insert(name);
                        }
                    }
                }
            }
        }
    }
    // Load the cargo workspace once via ra_ap so we can do real type lookups
    // per expression. If the source tree isn't part of a cargo project we
    // fall back to syntactic-only translation (`tyctx = None`).
    let tyctx = match find_cargo_manifest(src) {
        Some(manifest) => match tyctx::TyCtx::load(&manifest) {
            Ok(ctx) => Some(ctx),
            Err(e) => {
                eprintln!(
                    "warning: ra_ap workspace load failed ({e}); proceeding without type info"
                );
                None
            }
        },
        None => {
            eprintln!(
                "warning: no Cargo.toml found above {}; proceeding without type info",
                src.display()
            );
            None
        }
    };
    for entry in &entries {
        let rel = entry
            .strip_prefix(src)
            .map_err(|e| format!("path strip: {e}"))?
            .to_path_buf();
        let dest = py_dest(&rel, out);
        let table = tyctx
            .as_ref()
            .and_then(|ctx| ctx.build_file_table(entry))
            .unwrap_or_else(tyctx::FileTyTable::empty);
        translate_file_with_types(entry, Some(&dest), &cfg, &table)?;
    }
    Ok(())
}

/// Walk upwards from `start` looking for the nearest `Cargo.toml`. The
/// translator wants the manifest of any crate that contains the source —
/// ra_ap's load_workspace_at handles workspace discovery from there.
fn find_cargo_manifest(start: &Path) -> Option<PathBuf> {
    let start = start.canonicalize().ok()?;
    let mut dir: &Path = if start.is_file() {
        start.parent()?
    } else {
        &start
    };
    loop {
        let candidate = dir.join("Cargo.toml");
        if candidate.is_file() {
            return Some(candidate);
        }
        dir = dir.parent()?;
    }
}

/// Convert a relative source path to the corresponding Python module path.
/// `builder/tasks/_policy.rs` → `builder.tasks._policy`. `mod.rs` collapses to
/// its parent directory. `lib.rs` at root becomes the empty path (top-level).
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

fn impl_target_struct_name(ty: &syn::Type) -> Option<String> {
    if let syn::Type::Path(p) = ty
        && let Some(last) = p.path.segments.last()
    {
        return Some(last.ident.to_string());
    }
    None
}

fn struct_fields_in_file(file: &syn::File, name: &str) -> Option<Vec<String>> {
    for item in &file.items {
        if let syn::Item::Struct(s) = item
            && s.ident == name
            && let syn::Fields::Named(named) = &s.fields
        {
            return Some(
                named
                    .named
                    .iter()
                    .filter_map(|f| f.ident.as_ref().map(|i| i.to_string()))
                    .collect(),
            );
        }
    }
    None
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

/// Map a Rust source path (relative to the crate root) to the corresponding
/// Python file under `out`. `mod.rs` becomes `__init__.py` (the Rust module-
/// declaration convention maps to Python's package marker). `lib.rs` at the
/// root is the bot's entry point and maps to `main.py`. Everything else keeps
/// its name and gets a `.py` extension.
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

fn translate_source(
    source: &str,
    path: &Path,
    cfg: &CfgEnv,
    types: &tyctx::FileTyTable,
) -> Result<String, String> {
    let file = parse::parse_file(source, path)?;
    emit::emit_file(&file, path, cfg, types)
}
