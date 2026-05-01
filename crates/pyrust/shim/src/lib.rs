pub mod builtins;
pub mod collections;
pub mod dsl;
pub mod macros;
pub mod prelude;
pub mod random;

// DSL macro namespaces. Each namespace is a re-export of the
// underlying `macro_rules!` definitions so callers write
// `pyrust::iter::sum!(xs)` (path-qualified, stable since Rust 1.32).
// The translator pattern-matches on the macro's full path.
pub mod result {
    pub use crate::__pyrust_try as try_;
}
pub mod iter {
    pub use crate::{
        __pyrust_iter_max as max, __pyrust_iter_max_by as max_by,
        __pyrust_iter_min as min, __pyrust_iter_min_by as min_by,
        __pyrust_iter_sum as sum,
    };
}
pub mod vec {
    pub use crate::{
        __pyrust_vec_clear as clear, __pyrust_vec_pop as pop,
        __pyrust_vec_push as push,
    };
}
pub mod set {
    pub use crate::{
        __pyrust_set_add as add, __pyrust_set_contains as contains,
        __pyrust_set_remove as remove,
    };
}
pub mod dict {
    pub use crate::{
        __pyrust_dict_contains as contains, __pyrust_dict_get as get,
        __pyrust_dict_insert as insert, __pyrust_dict_remove as remove,
    };
}
pub mod string {
    pub use crate::__pyrust_string_clear as clear;
}
pub mod cast {
    pub use crate::{__pyrust_cast_float as float, __pyrust_cast_int as int};
}

pub use builtins::{
    PyAbs, PyLen, PyMin, PySorted, PyStr, PySum, abs, all, any, enumerate, len, max, min, reversed,
    sorted, sum, zip,
};
pub use collections::{Dict, List, Set};
pub use prelude::{PyDisplay, print};

/// Inert attribute consumed by `pyrust-translate`. Marks the type as a
/// Python `Exception` subclass.
pub use pyrust_macros::exception;
/// Inert attribute consumed by `pyrust-translate`. See
/// `pyrust_macros::transparent` for behaviour.
pub use pyrust_macros::transparent;
