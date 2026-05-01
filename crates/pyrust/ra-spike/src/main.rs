//! Smoke test for `ra_ap_*` integration. Loads the `bots/rs/v55` crate as a
//! cargo workspace, picks one source file, walks expressions, and prints the
//! inferred type of each. We're checking three things:
//!
//! 1. The workspace loads at all.
//! 2. `Semantics::type_of_expr` answers for arbitrary expressions.
//! 3. Per-translation overhead is acceptable (printed at the end).

use std::path::PathBuf;
use std::time::Instant;

use ra_ap_hir::{DisplayTarget, HirDisplay, Semantics};
use ra_ap_ide_db::FxHashMap;
use ra_ap_load_cargo::{LoadCargoConfig, ProcMacroServerChoice, load_workspace_at};
use ra_ap_paths::AbsPathBuf;
use ra_ap_project_model::CargoConfig;
use ra_ap_syntax::ast::{self, AstNode};
use ra_ap_vfs::VfsPath;

fn adt_name<'a>(
    db: &'a ra_ap_ide_db::RootDatabase,
    ty: &ra_ap_hir::Type<'_>,
) -> Option<&'static str> {
    let adt = ty.as_adt()?;
    let name = adt.name(db).as_str().to_owned();
    Some(match name.as_str() {
        "Option" => "Option",
        "Result" => "Result",
        "Vec" => "Vec",
        "VecDeque" => "VecDeque",
        "HashMap" => "HashMap",
        "BTreeMap" => "BTreeMap",
        "HashSet" => "HashSet",
        "BTreeSet" => "BTreeSet",
        _ => return None,
    })
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let manifest = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "bots/rs/v55/Cargo.toml".to_owned());
    let manifest_path = PathBuf::from(&manifest).canonicalize()?;
    let abs_manifest = AbsPathBuf::assert_utf8(manifest_path);

    let load_start = Instant::now();
    let (db, vfs, _proc_macro) = load_workspace_at(
        abs_manifest.as_ref(),
        &CargoConfig {
            sysroot: Some(ra_ap_project_model::RustLibSource::Discover),
            ..CargoConfig::default()
        },
        &LoadCargoConfig {
            load_out_dirs_from_check: false,
            with_proc_macro_server: ProcMacroServerChoice::None,
            prefill_caches: false,
            num_worker_threads: 0,
            proc_macro_processes: 0,
        },
        &|msg| eprintln!("[ra] {msg}"),
    )?;
    let load_ms = load_start.elapsed().as_millis();
    eprintln!("workspace loaded in {load_ms} ms");

    // Pick one source file: builder/mod.rs is the heaviest — good stress test.
    let target_rel = std::env::args()
        .nth(2)
        .unwrap_or_else(|| "bots/rs/v55/src/builder/mod.rs".to_owned());
    let target_abs = PathBuf::from(&target_rel).canonicalize()?;
    let vfs_path: VfsPath = AbsPathBuf::assert_utf8(target_abs).into();
    let (file_id, _excluded) = vfs
        .file_id(&vfs_path)
        .ok_or_else(|| format!("file not in workspace VFS: {target_rel}"))?;

    let sema = Semantics::new(&db);
    let parse = sema.parse_guess_edition(file_id);
    // Display targets need an edition + sysroot crate for path qualification.
    let display_target = DisplayTarget::from_crate(&db, sema.first_crate(file_id).unwrap().into());

    // Walk every expression node and ask Semantics for its type. Count
    // hits/misses so we can see how complete the inference is. The chalk
    // next-solver requires the HirDatabase to be thread-local-attached.
    let q_start = Instant::now();
    let mut hits = 0usize;
    let mut misses = 0usize;
    let mut histogram: FxHashMap<String, usize> = FxHashMap::default();
    let mut method_recv_kinds: FxHashMap<String, usize> = FxHashMap::default();
    ra_ap_hir::attach_db(&db, || {
        for node in parse.syntax().descendants() {
            if let Some(expr) = ast::Expr::cast(node.clone()) {
                match sema.type_of_expr(&expr) {
                    Some(ty_info) => {
                        hits += 1;
                        let mut s = ty_info.original.display(&db, display_target).to_string();
                        if let Some(adt) = ty_info.original.as_adt() {
                            let in_path = ra_ap_hir::ModuleDef::from(adt)
                                .canonical_path(&db, ra_ap_ide::Edition::Edition2024);
                            let krate = adt.module(&db).krate(&db);
                            let crate_name = krate
                                .display_name(&db)
                                .map(|d| d.canonical_name().as_str().to_owned());
                            let canonical = match (crate_name, in_path) {
                                (Some(c), Some(p)) => Some(format!("{c}::{p}")),
                                (Some(c), None) => Some(c),
                                (None, p) => p,
                            };
                            if let Some(p) = canonical {
                                s = format!("{s} [{p}]");
                            }
                        }
                        *histogram.entry(s).or_insert(0) += 1;
                    }
                    None => misses += 1,
                }
            }
            // For each method-call expression, classify the receiver's type
            // family — this is the dispatch info the translator needs.
            if let Some(mc) = ast::MethodCallExpr::cast(node.clone())
                && let Some(name) = mc.name_ref()
                && let Some(recv) = mc.receiver()
                && let Some(recv_ty) = sema.type_of_expr(&recv)
            {
                let ty = recv_ty.original.strip_references();
                let kind = if ty.is_str() {
                    "str"
                } else if adt_name(&db, &ty) == Some("Option") {
                    "Option"
                } else if adt_name(&db, &ty) == Some("Result") {
                    "Result"
                } else if adt_name(&db, &ty) == Some("Vec") {
                    "Vec"
                } else if adt_name(&db, &ty) == Some("HashMap") {
                    "HashMap"
                } else if adt_name(&db, &ty) == Some("HashSet") {
                    "HashSet"
                } else if false {
                    "Iterator"
                } else {
                    "other"
                };
                let key = format!("{}.{}() :: {}", kind, name.text(), kind);
                *method_recv_kinds.entry(key).or_insert(0) += 1;
            }
        }
    });
    let q_ms = q_start.elapsed().as_millis();
    eprintln!(
        "queried {} expressions in {} ms ({} hits, {} misses)",
        hits + misses,
        q_ms,
        hits,
        misses
    );

    // Show the most common types — sanity check that inference produced
    // sensible answers.
    let mut top: Vec<_> = histogram.iter().collect();
    top.sort_by(|a, b| b.1.cmp(a.1));
    eprintln!("top inferred types:");
    for (ty, count) in top.iter().take(20) {
        eprintln!("  {count:5}  {ty}");
    }

    let mut top_methods: Vec<_> = method_recv_kinds.iter().collect();
    top_methods.sort_by(|a, b| b.1.cmp(a.1));
    eprintln!("\nmethod-call dispatch (receiver kind):");
    for (key, count) in top_methods.iter().take(30) {
        eprintln!("  {count:5}  {key}");
    }

    Ok(())
}
