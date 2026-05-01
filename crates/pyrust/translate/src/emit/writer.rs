use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};

use proc_macro2::Span;

use super::types::{Scope, Ty};
use crate::cfg::CfgEnv;
use crate::tyctx::{FileTyTable, TyKind};

pub struct PyWriter {
    source_path: PathBuf,
    buf: String,
    indent: usize,
    pub scope: Scope,
    current_class: Vec<String>,
    /// Field names of the struct we're currently emitting a class body for.
    /// Used by folded trait default methods (where `ra_ap` type info isn't
    /// available for the body's spans because they live in another file)
    /// to recognise `self.<name>` as a field access vs method call.
    current_class_fields: Vec<String>,
    cfg: CfgEnv,
    /// Names of sum-type enums declared in this file (any variant has
    /// fields). Used by `emit_path` and `pat_to_python` to decide whether
    /// `EnumName::Variant` should map to `EnumName.Variant` (C-style) or
    /// to the dataclass `EnumNameVariant()` constructor.
    sum_enums: HashSet<String>,
    /// Identifiers referenced from runtime (non-type) positions in this file.
    /// Populated by `set_runtime_idents` during the pre-scan; consulted by
    /// `emit_use` to decide whether an import line should be emitted under
    /// `if TYPE_CHECKING:` (annotations only) or unconditionally (runtime).
    runtime_idents: HashSet<String>,
    module_refs: HashSet<String>,
    /// Names of module-level `static mut` (and `static`) bindings declared
    /// in this file. Functions that assign to one of these need a Python
    /// `global X` declaration prepended.
    statics: HashSet<String>,
    type_checking_imported: bool,
    /// ra_ap-resolved type kinds for every expression in this file, keyed
    /// by byte range. Empty when the source isn't part of a loaded cargo
    /// workspace (single-file `pyrust-translate input.rs` invocations).
    types: FileTyTable,
    /// Counter for unique walrus-binding names so emit sites that use
    /// `(__tN := expr)` don't collide when nested.
    tmp_counter: std::cell::Cell<u32>,
    /// Identifiers we've auto-imported because a folded trait default
    /// body referenced them as free functions in another module.
    folded_imports: HashSet<String>,
    /// Per-class-frame override for `Self` resolution. Pushed alongside
    /// `current_class`. `None` means default (Self = current class
    /// name); `Some(enum_name)` means we're inside a sum-type variant
    /// class but want `Self::Variant` paths to resolve through the
    /// enum (whose dataclass for Variant is `EnumNameVariant`).
    self_overrides: Vec<Option<String>>,
    /// File-level `#[pyrust::inline]` consts: name → Python literal.
    /// Single-segment ident references resolve to the literal directly,
    /// and the `const` declaration itself is suppressed.
    inline_consts: HashMap<String, String>,
    /// Stack of inline functions currently being expanded. Used to
    /// guard against recursive inline expansion (`fn a(...) { b(...) }`
    /// where `b` calls `a`).
    inlining_stack: Vec<String>,
}

impl PyWriter {
    pub fn new(source_path: &Path, cfg: CfgEnv, types: &FileTyTable) -> Self {
        Self {
            source_path: source_path.to_path_buf(),
            buf: String::new(),
            indent: 0,
            scope: Scope::new(),
            current_class: Vec::new(),
            current_class_fields: Vec::new(),
            cfg,
            sum_enums: HashSet::new(),
            runtime_idents: HashSet::new(),
            module_refs: HashSet::new(),
            statics: HashSet::new(),
            type_checking_imported: false,
            types: types.clone(),
            tmp_counter: std::cell::Cell::new(0),
            folded_imports: HashSet::new(),
            self_overrides: Vec::new(),
            inline_consts: HashMap::new(),
            inlining_stack: Vec::new(),
        }
    }

    /// True iff we're already expanding `name`'s body. Used to short-
    /// circuit recursive inline calls so we don't expand forever.
    pub fn is_inlining(&self, name: &str) -> bool {
        self.inlining_stack.iter().any(|n| n == name)
    }

    pub fn push_inlining(&mut self, name: &str) {
        self.inlining_stack.push(name.to_string());
    }

    pub fn pop_inlining(&mut self) {
        self.inlining_stack.pop();
    }

    /// Register an `#[pyrust::inline]`-marked const. Use sites resolve
    /// to `lit` and the declaration is suppressed.
    pub fn note_inline_const(&mut self, name: String, lit: String) {
        self.inline_consts.insert(name, lit);
    }

    /// Look up an inline-const by name. Returns the Python literal text
    /// to substitute, or None if the name is not inlined.
    pub fn inline_const_lit(&self, name: &str) -> Option<&str> {
        self.inline_consts.get(name).map(String::as_str)
    }

    /// Allocate a fresh `__tN` identifier for one-shot walrus bindings.
    pub fn fresh_tmp(&self) -> String {
        let n = self.tmp_counter.get();
        self.tmp_counter.set(n + 1);
        format!("__t{n}")
    }

    /// Look up the ra_ap-resolved type kind of the expression at `span`.
    /// Returns `None` if no type info is loaded (single-file mode) or the
    /// span doesn't match a known expression node (e.g. translator-emitted
    /// helpers, comments, etc.).
    pub fn ty_at(&self, span: Span) -> Option<&TyKind> {
        let r = span.byte_range();
        self.types.kind_for(r)
    }

    /// True when `name` is a Rust trait or `#[pyrust::transparent]` ADT —
    /// either way, no Python class is emitted, so any `use` of the name
    /// must be dropped.
    pub fn is_transparent_type(&self, name: &str) -> bool {
        self.types.is_transparent_name(name)
            || self.cfg.trait_registry.contains_key(name)
            || self.cfg.transparent_def_names.contains(name)
    }

    /// True when `name` carries `#[pyrust::exception]` and so should be
    /// emitted as a Python `Exception` subclass.
    pub fn is_exception_type(&self, name: &str) -> bool {
        self.types.is_exception_name(name) || self.cfg.exception_def_names.contains(name)
    }

    /// True when `name` carries `#[pyrust::context_manager]`. The struct
    /// emitter adds `__enter__`/`__exit__` methods, and `let _g = T::CTOR(..)`
    /// becomes `with T(..) as _g:` followed by an indented body.
    pub fn is_context_manager_type(&self, name: &str) -> bool {
        self.cfg.context_manager_def_names.contains(name)
    }

    /// True if a folded-trait import for `ident` has already been emitted
    /// in this file.
    pub fn has_emitted_folded_import(&self, ident: &str) -> bool {
        self.folded_imports.contains(ident)
    }

    /// Emit a `from <module> import <ident>` line for a free function
    /// pulled in by a folded trait default body. Idempotent. Writes at the
    /// file's top-level by snapping indent to zero around the line — the
    /// fold call site is inside a class body.
    pub fn emit_folded_import(&mut self, module: &str, ident: &str) {
        if !self.folded_imports.insert(ident.to_owned()) {
            return;
        }
        let saved = self.indent;
        self.indent = 0;
        if module.is_empty() {
            self.line(&format!("import {ident}"));
        } else {
            self.line(&format!("from {module} import {ident}"));
        }
        self.indent = saved;
    }

    pub fn note_static(&mut self, name: &str) {
        self.statics.insert(name.to_owned());
    }

    pub const fn statics(&self) -> &HashSet<String> {
        &self.statics
    }

    pub const fn has_emitted_type_checking_import(&self) -> bool {
        self.type_checking_imported
    }

    pub const fn mark_type_checking_imported(&mut self) {
        self.type_checking_imported = true;
    }

    /// True for the crate root file (`lib.rs` / `main.rs`) — the entry point
    /// loaded as `__main__` by the Python sandbox, where relative imports
    /// fail because there's no parent package.
    pub fn is_root_module(&self) -> bool {
        self.source_path
            .file_stem()
            .and_then(|s| s.to_str())
            .is_some_and(|s| s == "lib" || s == "main")
    }

    pub fn note_sum_enum(&mut self, name: &str) {
        self.sum_enums.insert(name.to_owned());
    }

    pub fn is_sum_enum(&self, name: &str) -> bool {
        if self.sum_enums.contains(name) {
            return true;
        }
        // Also check the project-wide registry so cross-module references
        // to a sum type (e.g. `Policy::Group(...)` when `Policy` lives in
        // another file) lower the same way as in the defining file.
        self.cfg
            .sum_enum_registry
            .values()
            .any(|m| m.contains_key(name))
    }

    /// True when `variant` is one of the variant names of sum-type enum
    /// `enum_name`. Distinguishes a constructor-call path (`Marker::Symmetry`)
    /// from a method call on the enum (`Marker::decode`).
    pub fn is_sum_enum_variant(&self, enum_name: &str, variant: &str) -> bool {
        for enums in self.cfg.sum_enum_registry.values() {
            if let Some(variants) = enums.get(enum_name)
                && variants.iter().any(|v| v == variant)
            {
                return true;
            }
        }
        false
    }

    pub fn set_runtime_idents(&mut self, idents: HashSet<String>) {
        self.runtime_idents = idents;
    }

    pub fn is_runtime_ident(&self, name: &str) -> bool {
        self.runtime_idents.contains(name)
    }

    pub fn set_module_refs(&mut self, refs: HashSet<String>) {
        self.module_refs = refs;
    }

    pub fn is_module_referenced(&self, name: &str) -> bool {
        self.module_refs.contains(name)
    }

    pub const fn cfg(&self) -> &CfgEnv {
        &self.cfg
    }

    pub fn enter_class(&mut self, name: String) {
        self.current_class.push(name);
        self.self_overrides.push(None);
    }

    /// Same as `enter_class` but overrides the Self-resolution: while the
    /// returned class is the current "container" (so methods are emitted
    /// inside it), `Self::X` paths resolve as if Self were `self_type`.
    /// Used when emitting a sum-type variant class: methods are folded
    /// into the variant dataclass (current_class = "MarkerSymmetry"),
    /// but `Self::Variant` in the source still means `Marker::Variant`.
    pub fn enter_class_with_self(&mut self, name: String, self_type: String) {
        self.current_class.push(name);
        self.self_overrides.push(Some(self_type));
    }

    pub fn exit_class(&mut self) {
        self.current_class.pop();
        self.self_overrides.pop();
        self.current_class_fields.clear();
    }

    pub fn current_class(&self) -> Option<&str> {
        self.current_class.last().map(String::as_str)
    }

    /// Resolution target for `Self::X` paths. Defaults to the current
    /// class name; an active `enter_class_with_self` overrides it.
    pub fn self_type(&self) -> Option<&str> {
        match self.self_overrides.last() {
            Some(Some(s)) => Some(s.as_str()),
            _ => self.current_class.last().map(String::as_str),
        }
    }

    pub fn set_current_class_fields(&mut self, fields: Vec<String>) {
        self.current_class_fields = fields;
    }

    pub fn current_class_has_field(&self, name: &str) -> bool {
        self.current_class_fields.iter().any(|f| f == name)
    }

    pub fn line(&mut self, line: &str) {
        if !line.is_empty() {
            for _ in 0..self.indent {
                self.buf.push_str("    ");
            }
            self.buf.push_str(line);
        }
        self.buf.push('\n');
    }

    pub fn blank_line(&mut self) {
        self.buf.push('\n');
    }

    pub const fn enter_indent(&mut self) {
        self.indent += 1;
    }

    pub const fn exit_indent(&mut self) {
        self.indent = self.indent.checked_sub(1).expect("dedent below zero");
    }

    pub fn enter_block(&mut self) {
        self.scope.push();
    }

    pub fn exit_block(&mut self) {
        self.scope.pop();
    }

    pub fn declare(&mut self, name: &str, ty: Ty) {
        self.scope.declare(name, ty);
    }

    pub fn lookup(&self, name: &str) -> Option<Ty> {
        self.scope.lookup(name)
    }

    pub fn is_outer_binding(&self, name: &str) -> bool {
        self.scope.is_in_outer_frame(name)
    }

    pub fn is_current_binding(&self, name: &str) -> bool {
        self.scope.is_in_current_frame(name)
    }

    pub fn finish(self) -> String {
        let mut s = self.buf;
        if !s.ends_with('\n') {
            s.push('\n');
        }
        s
    }

    pub fn err(&self, span: Span, msg: impl Into<String>) -> String {
        let start = span.start();
        format!(
            "{}:{}:{}: {}",
            self.source_path.display(),
            start.line,
            start.column + 1,
            msg.into()
        )
    }
}
