/// `list![1, 2, 3]` builds a [`crate::List`]. Translates to a Python list literal.
#[macro_export]
macro_rules! list {
    () => { $crate::List::new() };
    [$($e:expr),+ $(,)?] => {{
        let mut __l = $crate::List::new();
        $(__l.append($e);)+
        __l
    }};
}

/// `dict! { k => v, ... }` builds a [`crate::Dict`]. Translates to a Python dict literal.
#[macro_export]
macro_rules! dict {
    () => { $crate::Dict::new() };
    {$($k:expr => $v:expr),+ $(,)?} => {{
        let mut __m = $crate::Dict::new();
        $(__m.insert($k, $v);)+
        __m
    }};
}

/// `set! { 1, 2, 3 }` builds a [`crate::Set`]. Translates to a Python set literal.
#[macro_export]
macro_rules! set {
    () => { $crate::Set::new() };
    {$($e:expr),+ $(,)?} => {{
        let mut __s = $crate::Set::new();
        $(__s.add($e);)+
        __s
    }};
}

/// Python-style `range`. Translates to `range(stop)`, `range(start, stop)`,
/// or `range(start, stop, step)` depending on arity.
#[macro_export]
macro_rules! range {
    ($stop:expr) => {
        (0i64)..($stop as i64)
    };
    ($start:expr, $stop:expr) => {
        ($start as i64)..($stop as i64)
    };
    ($start:expr, $stop:expr, $step:expr) => {
        ((($start as i64)..($stop as i64)).step_by($step as usize))
    };
}

/// `comprehension!(EXPR; for X in IT)` builds a [`crate::List`].
/// Optionally followed by `; if COND` for filtering.
/// Translates to `[EXPR for X in IT]` (Python list comprehension).
#[macro_export]
macro_rules! comprehension {
    ($expr:expr; for $pat:pat in $iter:expr) => {{
        let mut __l = $crate::List::new();
        for $pat in $iter {
            __l.append($expr);
        }
        __l
    }};
    ($expr:expr; for $pat:pat in $iter:expr; if $cond:expr) => {{
        let mut __l = $crate::List::new();
        for $pat in $iter {
            if $cond {
                __l.append($expr);
            }
        }
        __l
    }};
}

/// `dict_comprehension!(K => V; for X in IT)` builds a [`crate::Dict`].
/// Translates to `{K: V for X in IT}`.
#[macro_export]
macro_rules! dict_comprehension {
    ($k:expr => $v:expr; for $pat:pat in $iter:expr) => {{
        let mut __m = $crate::Dict::new();
        for $pat in $iter {
            __m.insert($k, $v);
        }
        __m
    }};
    ($k:expr => $v:expr; for $pat:pat in $iter:expr; if $cond:expr) => {{
        let mut __m = $crate::Dict::new();
        for $pat in $iter {
            if $cond {
                __m.insert($k, $v);
            }
        }
        __m
    }};
}

/// `set_comprehension!(EXPR; for X in IT)` builds a [`crate::Set`].
/// Translates to `{EXPR for X in IT}`.
#[macro_export]
macro_rules! set_comprehension {
    ($expr:expr; for $pat:pat in $iter:expr) => {{
        let mut __s = $crate::Set::new();
        for $pat in $iter {
            __s.add($expr);
        }
        __s
    }};
    ($expr:expr; for $pat:pat in $iter:expr; if $cond:expr) => {{
        let mut __s = $crate::Set::new();
        for $pat in $iter {
            if $cond {
                __s.add($expr);
            }
        }
        __s
    }};
}
