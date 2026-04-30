use std::collections::{HashMap, HashSet};
use std::fmt::{self, Write};

/// Python-compatible value formatting.
///
/// Two flavours:
///   - "str" form (`repr=false`): what Python's `str()` / top-level `print()` produces.
///     For example `str("hi")` → `hi` (no surrounding quotes).
///   - "repr" form (`repr=true`): what Python's `repr()` produces, used inside collection
///     output. For example `repr("hi")` → `'hi'` (with quotes and escaping).
///
/// For most primitive types the two forms agree.
pub trait PyDisplay {
    fn fmt_py(&self, f: &mut fmt::Formatter<'_>, repr: bool) -> fmt::Result;
}

pub fn print<T: PyDisplay + ?Sized>(value: &T) {
    struct Adapter<'a, T: PyDisplay + ?Sized>(&'a T);
    impl<T: PyDisplay + ?Sized> fmt::Display for Adapter<'_, T> {
        fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
            self.0.fmt_py(f, false)
        }
    }
    println!("{}", Adapter(value));
}

impl PyDisplay for str {
    fn fmt_py(&self, f: &mut fmt::Formatter<'_>, repr: bool) -> fmt::Result {
        if !repr {
            return f.write_str(self);
        }
        let needs_double = self.contains('\'') && !self.contains('"');
        let q = if needs_double { '"' } else { '\'' };
        f.write_char(q)?;
        for c in self.chars() {
            match c {
                '\\' => f.write_str("\\\\")?,
                '\n' => f.write_str("\\n")?,
                '\r' => f.write_str("\\r")?,
                '\t' => f.write_str("\\t")?,
                c if c == q => {
                    f.write_char('\\')?;
                    f.write_char(c)?;
                }
                c if (c as u32) < 0x20 || c == '\x7f' => {
                    write!(f, "\\x{:02x}", c as u32)?;
                }
                c => f.write_char(c)?,
            }
        }
        f.write_char(q)
    }
}

impl PyDisplay for String {
    fn fmt_py(&self, f: &mut fmt::Formatter<'_>, repr: bool) -> fmt::Result {
        self.as_str().fmt_py(f, repr)
    }
}

macro_rules! impl_py_display_int {
    ($($t:ty),*) => { $(
        impl PyDisplay for $t {
            fn fmt_py(&self, f: &mut fmt::Formatter<'_>, _repr: bool) -> fmt::Result {
                fmt::Display::fmt(self, f)
            }
        }
    )* };
}
impl_py_display_int!(
    i8, i16, i32, i64, i128, isize, u8, u16, u32, u64, u128, usize
);

impl PyDisplay for bool {
    fn fmt_py(&self, f: &mut fmt::Formatter<'_>, _repr: bool) -> fmt::Result {
        f.write_str(if *self { "True" } else { "False" })
    }
}

impl PyDisplay for f64 {
    fn fmt_py(&self, f: &mut fmt::Formatter<'_>, _repr: bool) -> fmt::Result {
        if self.is_nan() {
            return f.write_str("nan");
        }
        if self.is_infinite() {
            return f.write_str(if *self > 0.0 { "inf" } else { "-inf" });
        }
        if *self == self.trunc() && self.abs() < 1e16 {
            return write!(f, "{self:.1}");
        }
        write!(f, "{self}")
    }
}

impl PyDisplay for f32 {
    fn fmt_py(&self, f: &mut fmt::Formatter<'_>, repr: bool) -> fmt::Result {
        f64::from(*self).fmt_py(f, repr)
    }
}

impl<T: PyDisplay + ?Sized> PyDisplay for &T {
    fn fmt_py(&self, f: &mut fmt::Formatter<'_>, repr: bool) -> fmt::Result {
        (**self).fmt_py(f, repr)
    }
}

impl<T: PyDisplay> PyDisplay for Vec<T> {
    fn fmt_py(&self, f: &mut fmt::Formatter<'_>, _repr: bool) -> fmt::Result {
        f.write_char('[')?;
        for (i, x) in self.iter().enumerate() {
            if i > 0 {
                f.write_str(", ")?;
            }
            x.fmt_py(f, true)?;
        }
        f.write_char(']')
    }
}

impl<T: PyDisplay, const N: usize> PyDisplay for [T; N] {
    fn fmt_py(&self, f: &mut fmt::Formatter<'_>, _repr: bool) -> fmt::Result {
        f.write_char('[')?;
        for (i, x) in self.iter().enumerate() {
            if i > 0 {
                f.write_str(", ")?;
            }
            x.fmt_py(f, true)?;
        }
        f.write_char(']')
    }
}

impl<T: PyDisplay> PyDisplay for [T] {
    fn fmt_py(&self, f: &mut fmt::Formatter<'_>, _repr: bool) -> fmt::Result {
        f.write_char('[')?;
        for (i, x) in self.iter().enumerate() {
            if i > 0 {
                f.write_str(", ")?;
            }
            x.fmt_py(f, true)?;
        }
        f.write_char(']')
    }
}

/// HashMap iteration order is not Python-compatible; we render but the order
/// is not guaranteed to match Python. Phase 3 corpus does not print dicts.
impl<K: PyDisplay, V: PyDisplay> PyDisplay for HashMap<K, V> {
    fn fmt_py(&self, f: &mut fmt::Formatter<'_>, _repr: bool) -> fmt::Result {
        f.write_char('{')?;
        for (i, (k, v)) in self.iter().enumerate() {
            if i > 0 {
                f.write_str(", ")?;
            }
            k.fmt_py(f, true)?;
            f.write_str(": ")?;
            v.fmt_py(f, true)?;
        }
        f.write_char('}')
    }
}

/// HashSet iteration order is non-deterministic; do not print directly in the
/// corpus until a deterministic order type is introduced.
impl<T: PyDisplay> PyDisplay for HashSet<T> {
    fn fmt_py(&self, f: &mut fmt::Formatter<'_>, _repr: bool) -> fmt::Result {
        if self.is_empty() {
            return f.write_str("set()");
        }
        f.write_char('{')?;
        for (i, x) in self.iter().enumerate() {
            if i > 0 {
                f.write_str(", ")?;
            }
            x.fmt_py(f, true)?;
        }
        f.write_char('}')
    }
}

impl PyDisplay for () {
    fn fmt_py(&self, f: &mut fmt::Formatter<'_>, _repr: bool) -> fmt::Result {
        f.write_str("()")
    }
}

impl<A: PyDisplay> PyDisplay for (A,) {
    fn fmt_py(&self, f: &mut fmt::Formatter<'_>, _repr: bool) -> fmt::Result {
        f.write_char('(')?;
        self.0.fmt_py(f, true)?;
        f.write_str(",)")
    }
}

macro_rules! impl_py_display_tuple {
    ($($idx:tt: $name:ident),+) => {
        impl<$($name: PyDisplay),+> PyDisplay for ($($name,)+) {
            fn fmt_py(&self, f: &mut fmt::Formatter<'_>, _repr: bool) -> fmt::Result {
                f.write_char('(')?;
                let mut __first = true;
                $(
                    if !__first { f.write_str(", ")?; }
                    self.$idx.fmt_py(f, true)?;
                    __first = false;
                )+
                f.write_char(')')
            }
        }
    };
}
impl_py_display_tuple!(0: A, 1: B);
impl_py_display_tuple!(0: A, 1: B, 2: C);
impl_py_display_tuple!(0: A, 1: B, 2: C, 3: D);
impl_py_display_tuple!(0: A, 1: B, 2: C, 3: D, 4: E);
impl_py_display_tuple!(0: A, 1: B, 2: C, 3: D, 4: E, 5: F);
impl_py_display_tuple!(0: A, 1: B, 2: C, 3: D, 4: E, 5: F, 6: G);
impl_py_display_tuple!(0: A, 1: B, 2: C, 3: D, 4: E, 5: F, 6: G, 7: H);
