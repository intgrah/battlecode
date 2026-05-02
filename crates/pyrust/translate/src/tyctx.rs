//! Stub type-context: the syn-only translator doesn't infer types via
//! `ra_ap_*`. The emit code keeps the API shape for compatibility with the
//! type-driven era, but every lookup returns `None` / `false`. Decisions
//! that previously consulted `TyKind` now fall through to syntactic
//! defaults — the bot is expected to use the pyrust DSL macros at the
//! call site so the translator never needs type info.

use std::ops::Range;
use std::path::Path;

#[derive(Clone, Debug)]
pub enum TyKind {
    Int,
    Float,
    Bool,
    Str,
    Tuple,
    Vec,
    VecDeque,
    HashMap,
    BTreeMap,
    HashSet,
    BTreeSet,
    Option,
    Result(Option<String>),
    Iterator,
    Adt(AdtInfo),
    Fn,
    Closure,
    Other,
}

#[derive(Clone, Debug)]
pub struct AdtInfo {
    pub name: String,
    pub canonical_path: Option<String>,
    pub field_names: Vec<String>,
    pub variant_fields: Vec<Vec<String>>,
    pub is_transparent: bool,
    pub is_exception: bool,
}

impl AdtInfo {
    #[allow(dead_code)]
    pub fn matches_path(&self, expected: &str) -> bool {
        self.canonical_path.as_deref() == Some(expected)
    }
    #[allow(dead_code)]
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
    #[allow(dead_code)]
    pub fn all_variants_have_field(&self, name: &str) -> bool {
        !self.variant_fields.is_empty()
            && self
                .variant_fields
                .iter()
                .all(|fs| fs.iter().any(|f| f == name))
    }
}

impl TyKind {
    #[allow(dead_code)]
    pub const fn adt(&self) -> Option<&AdtInfo> {
        match self {
            Self::Adt(a) => Some(a),
            _ => None,
        }
    }
    #[allow(dead_code)]
    pub const fn adt_name(&self) -> Option<&str> {
        match self {
            Self::Adt(a) => Some(a.name.as_str()),
            _ => None,
        }
    }
    #[allow(dead_code)]
    pub const fn is_iterator_like(&self) -> bool {
        matches!(self, Self::Iterator | Self::Vec | Self::VecDeque)
    }
}

/// No-op type table — all queries return `None`.
#[derive(Clone, Default)]
pub struct FileTyTable;

impl FileTyTable {
    pub const fn empty() -> Self {
        Self
    }
    pub const fn kind_for(&self, _r: Range<usize>) -> Option<&TyKind> {
        None
    }
    pub const fn is_transparent_name(&self, _name: &str) -> bool {
        false
    }
    pub const fn is_exception_name(&self, _name: &str) -> bool {
        false
    }
}

#[allow(dead_code)]
pub struct TyCtx;

impl TyCtx {
    #[allow(dead_code)]
    pub const fn load(_manifest_path: &Path) -> Result<Self, String> {
        Ok(Self)
    }
    #[allow(dead_code)]
    pub const fn build_file_table(&self, _source_path: &Path) -> Option<FileTyTable> {
        Some(FileTyTable)
    }
}
