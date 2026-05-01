pub mod builtins;
pub mod collections;
pub mod dsl;
pub mod macros;
pub mod prelude;
pub mod random;

// pyrust DSL surface. The translator path-matches `pyrust::*!` macros
// and emits the corresponding Python. ANYTHING NOT WRAPPED IN A
// `pyrust::*!` MACRO PASSES THROUGH TO PYTHON LITERALLY — bare
// `.iter()`, `.contains()`, `.push()`, `.unwrap()`, etc. on Rust
// builtins will not translate. Use the macros.
//
// Namespacing: free functions / language-level builtins at the top
// level (`pyrust::sum!`, `pyrust::abs!`, `pyrust::int!`, `pyrust::iter!`,
// `pyrust::print!`, `pyrust::len!`, `pyrust::try_!`, ...). Type methods
// under their owning type module (`pyrust::vec::push!`, `pyrust::set::add!`,
// `pyrust::dict::items!`, `pyrust::string::clear!`).

// ---- Top-level: control flow / Option / cast / iter / sort ----
pub use crate::__pyrust_abs as abs;
pub use crate::__pyrust_all as all;
pub use crate::__pyrust_any as any;
pub use crate::__pyrust_as_mut as as_mut;
pub use crate::__pyrust_as_ref as as_ref;
pub use crate::__pyrust_cast_float as float;
pub use crate::__pyrust_cast_int as int;
pub use crate::__pyrust_ceil as ceil;
pub use crate::__pyrust_chain as chain;
pub use crate::__pyrust_clone as clone;
pub use crate::__pyrust_cloned as cloned;
pub use crate::__pyrust_collect as collect;
pub use crate::__pyrust_copied as copied;
pub use crate::__pyrust_count as count;
pub use crate::__pyrust_drop as drop;
pub use crate::__pyrust_enumerate as enumerate;
pub use crate::__pyrust_expect as expect;
pub use crate::__pyrust_filter as filter;
pub use crate::__pyrust_filter_map as filter_map;
pub use crate::__pyrust_find as find;
pub use crate::__pyrust_find_map as find_map;
pub use crate::__pyrust_floor as floor;
pub use crate::__pyrust_into as into;
pub use crate::__pyrust_into_iter as into_iter;
pub use crate::__pyrust_is_none as is_none;
pub use crate::__pyrust_is_none_or as is_none_or;
pub use crate::__pyrust_is_some as is_some;
pub use crate::__pyrust_is_some_and as is_some_and;
pub use crate::__pyrust_iter as iter;
pub use crate::__pyrust_iter_max as max;
pub use crate::__pyrust_iter_max_by as max_by;
pub use crate::__pyrust_iter_min as min;
pub use crate::__pyrust_iter_min_by as min_by;
pub use crate::__pyrust_iter_sum as sum;
pub use crate::__pyrust_len as len;
pub use crate::__pyrust_map as map;
pub use crate::__pyrust_mul_add as mul_add;
pub use crate::__pyrust_next as next;
pub use crate::__pyrust_opt_map as opt_map;
pub use crate::__pyrust_opt_take as opt_take;
pub use crate::__pyrust_position as position;
pub use crate::__pyrust_powf as powf;
pub use crate::__pyrust_powi as powi;
pub use crate::__pyrust_print as print;
pub use crate::__pyrust_rem_euclid as rem_euclid;
pub use crate::__pyrust_rev as rev;
pub use crate::__pyrust_rng_choices as rng_choices;
pub use crate::__pyrust_round as round;
pub use crate::__pyrust_signum as signum;
pub use crate::__pyrust_skip as skip;
pub use crate::__pyrust_sort as sort;
pub use crate::__pyrust_sort_by_key as sort_by_key;
pub use crate::__pyrust_sorted as sorted;
pub use crate::__pyrust_sorted_by_key as sorted_by_key;
pub use crate::__pyrust_sqrt as sqrt;
pub use crate::__pyrust_take as take;
pub use crate::__pyrust_to_string as to_string;
pub use crate::__pyrust_to_vec as to_vec;
pub use crate::__pyrust_try as try_;
pub use crate::__pyrust_unwrap as unwrap;
pub use crate::__pyrust_unwrap_or as unwrap_or;
pub use crate::__pyrust_zip as zip;

pub mod vec {
    pub use crate::{
        __pyrust_vec_clear as clear, __pyrust_vec_contains as contains,
        __pyrust_vec_dedup as dedup, __pyrust_vec_extend as extend, __pyrust_vec_fill as fill,
        __pyrust_vec_first as first, __pyrust_vec_is_empty as is_empty, __pyrust_vec_last as last,
        __pyrust_vec_len as len, __pyrust_vec_new as new, __pyrust_vec_pop as pop,
        __pyrust_vec_pop_back as pop_back, __pyrust_vec_pop_front as pop_front,
        __pyrust_vec_push as push, __pyrust_vec_push_back as push_back,
        __pyrust_vec_push_front as push_front, __pyrust_vec_retain as retain,
        __pyrust_vec_reverse as reverse, __pyrust_vec_swap_remove as swap_remove,
        __pyrust_vec_take as take, __pyrust_vec_truncate as truncate,
    };
}
pub mod set {
    pub use crate::{
        __pyrust_set_add as add, __pyrust_set_clear as clear, __pyrust_set_clone as clone,
        __pyrust_set_collect as collect, __pyrust_set_contains as contains,
        __pyrust_set_difference as difference, __pyrust_set_is_empty as is_empty,
        __pyrust_set_len as len, __pyrust_set_new as new, __pyrust_set_remove as remove,
    };
}
pub mod dict {
    pub use crate::{
        __pyrust_dict_clear as clear, __pyrust_dict_collect as collect,
        __pyrust_dict_contains as contains, __pyrust_dict_get as get,
        __pyrust_dict_insert as insert, __pyrust_dict_is_empty as is_empty,
        __pyrust_dict_items as items, __pyrust_dict_keys as keys, __pyrust_dict_len as len,
        __pyrust_dict_new as new, __pyrust_dict_remove as remove, __pyrust_dict_values as values,
    };
}
pub mod string {
    pub use crate::{
        __pyrust_string_clear as clear, __pyrust_string_is_empty as is_empty,
        __pyrust_string_len as len, __pyrust_string_new as new,
    };
}
pub mod time {
    pub use crate::__pyrust_time_now_ns as now_ns;
}
pub mod serde {
    pub use crate::__pyrust_serde_array_mut as array_mut;
}

pub use builtins::{
    PyAbs, PyLen, PyMin, PySorted, PyStr, PySum, abs as abs_fn, all as all_fn, any as any_fn,
    enumerate as enumerate_fn, len as len_fn, max as max_fn, min as min_fn,
    reversed as reversed_fn, sorted as sorted_fn, sum as sum_fn, zip as zip_fn,
};
pub use collections::{Dict, List, Set};
pub use prelude::PyDisplay;

/// Inert attribute consumed by `pyrust-translate`. See
/// `pyrust_macros::context_manager` for behaviour.
pub use pyrust_macros::context_manager;
/// Inert attribute consumed by `pyrust-translate`. Marks the type as a
/// Python `Exception` subclass.
pub use pyrust_macros::exception;
/// Inert attribute consumed by `pyrust-translate`. See
/// `pyrust_macros::inline` for behaviour.
pub use pyrust_macros::inline;
/// Inert attribute consumed by `pyrust-translate`. See
/// `pyrust_macros::transparent` for behaviour.
pub use pyrust_macros::transparent;
