//! ra_ap-backed type information for the translator.
//!
//! Two layers:
//!
//! - [`TyCtx`] owns the loaded cargo workspace (`RootDatabase` + `Vfs` +
//!   sysroot crate). One per `pyrust-translate --dir` invocation.
//! - [`FileTyTable`] holds the span-keyed type kind for every expression in
//!   one source file. Built once when `emit_file` starts; queried by
//!   `emit/expr.rs` etc. to decide method dispatch.
//!
//! The split exists to side-step the lifetime cascade. `Semantics<'db, _>`
//! borrows the database, so threading it through every emit fn would force
//! a `'db` lifetime onto `PyWriter` and everything beneath. Doing the type
//! walk eagerly into a span-keyed table means `PyWriter` just owns a
//! `FileTyTable` (no lifetimes) and call sites do byte-range lookups.
//!
//! Span lookups use `proc_macro2::Span::byte_range()`, which matches the
//! byte offsets ra_ap reports from `TextRange`.

use std::collections::HashMap;
use std::ops::Range;
use std::path::Path;

use ra_ap_hir::{DisplayTarget, HasSource, HirDisplay, Semantics, Type};
use ra_ap_ide_db::RootDatabase;
use ra_ap_load_cargo::{LoadCargoConfig, ProcMacroServerChoice, load_workspace_at};
use ra_ap_paths::AbsPathBuf;
use ra_ap_project_model::{CargoConfig, RustLibSource};
use ra_ap_syntax::ast::{self, AstNode, HasAttrs};
use ra_ap_vfs::{Vfs, VfsPath};

/// Kind of a Rust expression's resolved type. Coarse enough that a
/// translator only needs to ask: is this an `Option`? a `Vec`? an iterator?
/// — without storing the full type tree.
#[derive(Clone, Debug)]
pub enum TyKind {
    /// Any signed/unsigned integer (`i32`, `u64`, `usize`, …).
    Int,
    /// `f32` / `f64`.
    Float,
    Bool,
    Str,
    /// Tuple — including `()` (unit).
    Tuple,
    Vec,
    VecDeque,
    HashMap,
    BTreeMap,
    HashSet,
    BTreeSet,
    Option,
    /// `Result<T, E>`. Carries the err type's terminal name (e.g.
    /// `"TaskRejected"`) when known, so a `match Result { ... Err(...) => }`
    /// translation knows what to write in `except <Type> as e:`.
    Result(Option<String>),
    Iterator,
    /// Any other concrete struct/enum.
    Adt(AdtInfo),
    /// A function pointer / fn item.
    Fn,
    /// Closure.
    Closure,
    /// A type the translator doesn't classify.
    Other,
}

/// Coarse view of a struct/enum: name, canonical path (`serde_json::Value`),
/// fields, and per-variant fields (for sum-type enums).
#[derive(Clone, Debug)]
pub struct AdtInfo {
    pub name: String,
    /// Fully-qualified path including the crate, e.g. `serde_json::Value`.
    /// `None` when ra_ap couldn't compute it (rare).
    pub canonical_path: Option<String>,
    /// Direct field names on the struct itself; empty for enums.
    pub field_names: Vec<String>,
    /// For sum-type enums: each variant's field names. The translator
    /// uses this to decide that `enum.method_name()` is a field access
    /// when every variant has a field by that name (e.g. `Building::team`).
    pub variant_fields: Vec<Vec<String>>,
    /// True if the source has a `#[pyrust::transparent]` attribute on the
    /// type definition. The translator erases such enums in Python:
    /// unit variants → `None`, 1-field variants → the field value.
    pub is_transparent: bool,
    /// True if the source has a `#[pyrust::exception]` attribute. The
    /// emitted Python class subclasses `Exception` so `raise X` works.
    pub is_exception: bool,
}

impl AdtInfo {
    /// True if every variant of a sum-type enum has a field by `name`.
    /// Used by the translator to lower `enum.field()` accessors to attribute
    /// access — Python's variant dataclasses each carry the field directly.
    pub fn all_variants_have_field(&self, name: &str) -> bool {
        !self.variant_fields.is_empty()
            && self
                .variant_fields
                .iter()
                .all(|fs| fs.iter().any(|f| f == name))
    }
}

impl AdtInfo {
    pub fn matches_path(&self, expected: &str) -> bool {
        self.canonical_path.as_deref() == Some(expected)
    }

    /// True if this ADT lives in `expected_crate` and its terminal name is
    /// `expected_name`. Tolerates intermediate module paths (e.g.
    /// `serde_json::value::Value` matches `("serde_json", "Value")`).
    pub fn matches_crate_type(&self, expected_crate: &str, expected_name: &str) -> bool {
        if self.name != expected_name {
            return false;
        }
        match self.canonical_path.as_deref() {
            Some(p) => {
                p.starts_with(&format!("{expected_crate}::"))
                    && p.ends_with(&format!("::{expected_name}"))
            }
            None => false,
        }
    }
}

impl TyKind {
    pub fn is_iterator_like(&self) -> bool {
        matches!(self, TyKind::Iterator | TyKind::Vec | TyKind::VecDeque)
    }

    pub fn adt_name(&self) -> Option<&str> {
        match self {
            TyKind::Adt(a) => Some(a.name.as_str()),
            _ => None,
        }
    }

    pub fn adt(&self) -> Option<&AdtInfo> {
        match self {
            TyKind::Adt(a) => Some(a),
            _ => None,
        }
    }
}

/// Workspace-level type context. Built once, shared across all translation
/// passes for a given `--dir` invocation.
pub struct TyCtx {
    db: RootDatabase,
    vfs: Vfs,
    /// Names of `#[pyrust::transparent]` traits and ADTs found anywhere in
    /// the loaded workspace. Translator drops imports of these names — the
    /// Python target has no class to import.
    transparent_def_names: std::collections::HashSet<String>,
    /// Names of `#[pyrust::exception]` ADTs in the loaded workspace. The
    /// emitted Python class subclasses `Exception` so `raise X` works.
    exception_def_names: std::collections::HashSet<String>,
}

impl TyCtx {
    /// Load a cargo workspace via ra_ap. `manifest_path` is a `Cargo.toml`
    /// (an enclosing crate's manifest is fine).
    pub fn load(manifest_path: &Path) -> Result<Self, String> {
        let manifest = manifest_path
            .canonicalize()
            .map_err(|e| format!("canonicalize {}: {e}", manifest_path.display()))?;
        let abs = AbsPathBuf::assert_utf8(manifest);
        let (db, vfs, _proc_macro) = load_workspace_at(
            abs.as_ref(),
            &CargoConfig {
                sysroot: Some(RustLibSource::Discover),
                ..CargoConfig::default()
            },
            &LoadCargoConfig {
                load_out_dirs_from_check: false,
                with_proc_macro_server: ProcMacroServerChoice::None,
                prefill_caches: false,
                num_worker_threads: 0,
                proc_macro_processes: 0,
            },
            &|_msg| {},
        )
        .map_err(|e| format!("load workspace: {e}"))?;
        let (transparent_def_names, exception_def_names) = collect_pyrust_attr_defs(&db);
        Ok(TyCtx {
            db,
            vfs,
            transparent_def_names,
            exception_def_names,
        })
    }

    pub fn is_transparent_def(&self, name: &str) -> bool {
        self.transparent_def_names.contains(name)
    }

    pub fn exception_def_names(&self) -> &std::collections::HashSet<String> {
        &self.exception_def_names
    }

    /// Build the per-file span-keyed type table. Returns `None` if the file
    /// isn't part of the loaded workspace (e.g. a transient input).
    pub fn build_file_table(&self, source_path: &Path) -> Option<FileTyTable> {
        let canon = source_path.canonicalize().ok()?;
        let vfs_path: VfsPath = AbsPathBuf::assert_utf8(canon).into();
        let (file_id, _excluded) = self.vfs.file_id(&vfs_path)?;
        let sema = Semantics::new(&self.db);
        let parse = sema.parse_guess_edition(file_id);
        let display_target = DisplayTarget::from_crate(&self.db, sema.first_crate(file_id)?.into());
        let mut table = HashMap::new();

        ra_ap_hir::attach_db(&self.db, || {
            for node in parse.syntax().descendants() {
                let Some(expr) = ast::Expr::cast(node) else {
                    continue;
                };
                let Some(ty_info) = sema.type_of_expr(&expr) else {
                    continue;
                };
                let kind = classify(&self.db, display_target, &ty_info.original);
                let range = expr.syntax().text_range();
                let start: usize = range.start().into();
                let end: usize = range.end().into();
                table.insert((start, end), kind);
            }
        });

        Some(FileTyTable {
            table,
            transparent_names: self.transparent_def_names.clone(),
            exception_names: self.exception_def_names.clone(),
        })
    }
}

/// Span-keyed type-kind lookup for one file.
#[derive(Clone, Default)]
pub struct FileTyTable {
    table: HashMap<(usize, usize), TyKind>,
    /// Names of `#[pyrust::transparent]` enums seen anywhere in the table
    /// (any expression's type that resolved to a transparent ADT). The
    /// import emitter uses this to drop `from <crate> import X` lines —
    /// transparent enums have no Python class, only their inner values.
    transparent_names: std::collections::HashSet<String>,
    /// Names of `#[pyrust::exception]` types in the workspace. The struct
    /// emitter inserts `Exception` as a base class for these.
    exception_names: std::collections::HashSet<String>,
}

impl FileTyTable {
    pub fn empty() -> Self {
        FileTyTable::default()
    }

    /// Look up the kind of the expression that spans the given byte range.
    pub fn kind_for(&self, range: Range<usize>) -> Option<&TyKind> {
        self.table.get(&(range.start, range.end))
    }

    /// True if `name` is a `#[pyrust::transparent]` enum referenced from
    /// any expression in this file. Used to drop the import line — the
    /// Python runtime has no class to import.
    pub fn is_transparent_name(&self, name: &str) -> bool {
        self.transparent_names.contains(name)
    }

    /// True if `name` carries `#[pyrust::exception]` somewhere in the
    /// workspace. The class emitter uses this to add `Exception` to the
    /// type's base list so `raise X` works in Python.
    pub fn is_exception_name(&self, name: &str) -> bool {
        self.exception_names.contains(name)
    }
}

/// Convert one `ra_ap_hir::Type` to the coarse [`TyKind`]. Strips outer
/// references — `&Vec<T>` is just `Vec` for the translator's purposes.
fn classify(db: &RootDatabase, display: DisplayTarget, ty: &Type<'_>) -> TyKind {
    let ty = ty.strip_references();
    if ty.is_unit() {
        return TyKind::Tuple;
    }
    if ty.is_bool() {
        return TyKind::Bool;
    }
    if ty.is_str() {
        return TyKind::Str;
    }
    // Numeric scalars don't have a single predicate; check via the
    // displayed name.
    let display_name = ty.display(db, display).to_string();
    match display_name.as_str() {
        "i8" | "i16" | "i32" | "i64" | "i128" | "isize" | "u8" | "u16" | "u32" | "u64" | "u128"
        | "usize" => return TyKind::Int,
        "f32" | "f64" => return TyKind::Float,
        _ => {}
    }
    if let Some(adt) = ty.as_adt() {
        let name = adt.name(db).as_str().to_owned();
        return match name.as_str() {
            "Vec" => TyKind::Vec,
            "VecDeque" => TyKind::VecDeque,
            "HashMap" => TyKind::HashMap,
            "BTreeMap" => TyKind::BTreeMap,
            "HashSet" => TyKind::HashSet,
            "BTreeSet" => TyKind::BTreeSet,
            "Option" => TyKind::Option,
            "Result" => {
                // Pull the second generic argument (the error type) and
                // record its terminal name. Used to emit
                // `except <ErrName> as e:` for `match Result { Err(e) => }`.
                let err_name = ty
                    .type_arguments()
                    .nth(1)
                    .and_then(|t| t.as_adt().map(|a| a.name(db).as_str().to_owned()));
                TyKind::Result(err_name)
            }
            _ => TyKind::Adt(adt_info(db, adt)),
        };
    }
    if ty.is_closure() {
        return TyKind::Closure;
    }
    if ty.is_fn() {
        return TyKind::Fn;
    }
    // Tuples
    if display_name.starts_with('(') {
        return TyKind::Tuple;
    }
    TyKind::Other
}

fn adt_info(db: &RootDatabase, adt: ra_ap_hir::Adt) -> AdtInfo {
    let name = adt.name(db).as_str().to_owned();
    // `ModuleDef::canonical_path` walks ancestors via `Module::name`, which
    // returns None for the crate root — so the crate name doesn't appear.
    // Prepend it explicitly via the Adt's owning crate.
    let in_crate_path =
        ra_ap_hir::ModuleDef::from(adt).canonical_path(db, ra_ap_ide::Edition::Edition2024);
    let krate = adt.module(db).krate(db);
    let crate_name = krate
        .display_name(db)
        .map(|d| d.canonical_name().as_str().to_owned());
    let canonical_path = match (crate_name, in_crate_path) {
        (Some(c), Some(p)) => Some(format!("{c}::{p}")),
        (Some(c), None) => Some(c),
        (None, p) => p,
    };
    let mut field_names = Vec::new();
    if let ra_ap_hir::Adt::Struct(s) = adt {
        for field in s.fields(db) {
            field_names.push(field.name(db).as_str().to_owned());
        }
    }
    // For enums, record each variant's fields. Caller uses this to decide
    // that calls like `Building::team` (which all variants carry as a
    // field) are field accesses.
    let mut variant_fields = Vec::new();
    if let ra_ap_hir::Adt::Enum(e) = adt {
        for variant in e.variants(db) {
            let fields: Vec<String> = variant
                .fields(db)
                .iter()
                .map(|f| f.name(db).as_str().to_owned())
                .collect();
            variant_fields.push(fields);
        }
    }
    let is_transparent = has_pyrust_attr(db, adt, "pyrust::transparent");
    let is_exception = has_pyrust_attr(db, adt, "pyrust::exception");
    AdtInfo {
        name,
        canonical_path,
        field_names,
        variant_fields,
        is_transparent,
        is_exception,
    }
}

/// Walk every crate's defined traits and ADTs, collecting the names of
/// those marked `#[pyrust::transparent]` and `#[pyrust::exception]`. Run
/// once at workspace load.
fn collect_pyrust_attr_defs(
    db: &RootDatabase,
) -> (
    std::collections::HashSet<String>,
    std::collections::HashSet<String>,
) {
    use ra_ap_hir::{Crate, ModuleDef};
    let mut transparent = std::collections::HashSet::new();
    let mut exception = std::collections::HashSet::new();
    let crates: Vec<Crate> = Crate::all(db);
    ra_ap_hir::attach_db(db, || {
        for krate in crates {
            for module in krate.modules(db) {
                for def in module.declarations(db) {
                    let (name, attrs): (String, Vec<ast::Attr>) = match def {
                        ModuleDef::Adt(adt) => {
                            let Some(src) = adt.source(db) else { continue };
                            let attrs: Vec<ast::Attr> = match &src.value {
                                ast::Adt::Struct(s) => s.attrs().collect(),
                                ast::Adt::Enum(e) => e.attrs().collect(),
                                ast::Adt::Union(u) => u.attrs().collect(),
                            };
                            (adt.name(db).as_str().to_owned(), attrs)
                        }
                        ModuleDef::Trait(t) => {
                            let Some(src) = t.source(db) else { continue };
                            (t.name(db).as_str().to_owned(), src.value.attrs().collect())
                        }
                        _ => continue,
                    };
                    if attrs_match_path(attrs.iter().cloned(), "pyrust::transparent") {
                        transparent.insert(name.clone());
                    }
                    if attrs_match_path(attrs.iter().cloned(), "pyrust::exception") {
                        exception.insert(name);
                    }
                }
            }
        }
    });
    (transparent, exception)
}

fn attrs_match_path(attrs: impl Iterator<Item = ast::Attr>, expected: &str) -> bool {
    for attr in attrs {
        let Some(path) = attr.path() else { continue };
        let txt = path.syntax().text().to_string();
        let normalized: String = txt.split_whitespace().collect();
        if normalized == expected {
            return true;
        }
    }
    false
}

fn attrs_match_pyrust_transparent(attrs: impl Iterator<Item = ast::Attr>) -> bool {
    attrs_match_path(attrs, "pyrust::transparent")
}

/// Check whether the adt's source carries the named pyrust attribute
/// (e.g. `pyrust::transparent`, `pyrust::exception`). Walks the syntax
/// tree directly since ra_ap's `AttrFlags` only recognises hardcoded
/// well-known attributes.
fn has_pyrust_attr(db: &RootDatabase, adt: ra_ap_hir::Adt, expected: &str) -> bool {
    let Some(src) = adt.source(db) else {
        return false;
    };
    let node: &ast::Adt = &src.value;
    let attrs: Box<dyn Iterator<Item = ast::Attr>> = match node {
        ast::Adt::Struct(s) => Box::new(s.attrs()),
        ast::Adt::Enum(e) => Box::new(e.attrs()),
        ast::Adt::Union(u) => Box::new(u.attrs()),
    };
    attrs_match_path(attrs, expected)
}
