use std::collections::HashMap;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Ty {
    Int,
    Float,
    Bool,
    Str,
    List,
    Dict,
    Set,
    Unit,
    Unknown,
}

#[derive(Default)]
pub struct Scope {
    frames: Vec<HashMap<String, Ty>>,
}

impl Scope {
    pub fn new() -> Self {
        Self {
            frames: vec![HashMap::new()],
        }
    }

    pub fn push(&mut self) {
        self.frames.push(HashMap::new());
    }

    pub fn pop(&mut self) {
        self.frames.pop();
    }

    pub fn declare(&mut self, name: &str, ty: Ty) {
        self.frames
            .last_mut()
            .expect("scope frame stack is empty")
            .insert(name.to_owned(), ty);
    }

    pub fn lookup(&self, name: &str) -> Option<Ty> {
        for frame in self.frames.iter().rev() {
            if let Some(ty) = frame.get(name) {
                return Some(*ty);
            }
        }
        None
    }

    pub fn is_in_current_frame(&self, name: &str) -> bool {
        self.frames
            .last()
            .is_some_and(|f| f.contains_key(name))
    }

    pub fn is_in_outer_frame(&self, name: &str) -> bool {
        if self.frames.len() < 2 {
            return false;
        }
        for frame in self.frames.iter().take(self.frames.len() - 1).rev() {
            if frame.contains_key(name) {
                return true;
            }
        }
        false
    }
}

pub fn type_from_annotation(ty: &syn::Type) -> Ty {
    match ty {
        syn::Type::Path(p) if p.qself.is_none() => {
            let segs: Vec<String> = p
                .path
                .segments
                .iter()
                .map(|s| s.ident.to_string())
                .collect();
            match segs
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>()
                .as_slice()
            {
                [
                    "i8" | "i16" | "i32" | "i64" | "i128" | "isize" | "u8" | "u16" | "u32" | "u64"
                    | "u128" | "usize",
                ] => Ty::Int,
                ["f32" | "f64"] => Ty::Float,
                ["bool"] => Ty::Bool,
                ["str" | "String"] => Ty::Str,
                ["List"] | ["pyrust", "List"] => Ty::List,
                ["Dict"] | ["pyrust", "Dict"] => Ty::Dict,
                ["Set"] | ["pyrust", "Set"] => Ty::Set,
                _ => Ty::Unknown,
            }
        }
        syn::Type::Reference(r) => type_from_annotation(&r.elem),
        syn::Type::Array(_) | syn::Type::Slice(_) => Ty::List,
        syn::Type::Tuple(t) if t.elems.is_empty() => Ty::Unit,
        _ => Ty::Unknown,
    }
}

pub const fn promote_numeric(a: Ty, b: Ty) -> Ty {
    match (a, b) {
        (Ty::Float, _) | (_, Ty::Float) => Ty::Float,
        (Ty::Int, Ty::Int) => Ty::Int,
        _ => Ty::Unknown,
    }
}

/// Convert a Rust type annotation to its Python equivalent, including generic
/// parameters (`pyrust::List<i64>` → `list[int]`).
pub fn type_to_python_str(ty: &syn::Type) -> Result<String, String> {
    match ty {
        syn::Type::Path(p) if p.qself.is_none() => path_type_to_python(&p.path),
        syn::Type::Reference(r) => type_to_python_str(&r.elem),
        // `_` placeholder: drop to a bare collection name (Python doesn't
        // need the element type for runtime annotations).
        syn::Type::Infer(_) => Ok("object".to_owned()),
        syn::Type::Array(a) => Ok(format!("list[{}]", type_to_python_str(&a.elem)?)),
        syn::Type::Slice(s) => Ok(format!("list[{}]", type_to_python_str(&s.elem)?)),
        syn::Type::Tuple(t) if t.elems.is_empty() => Ok("None".to_owned()),
        syn::Type::Tuple(t) => {
            let mut parts = Vec::with_capacity(t.elems.len());
            for elem in &t.elems {
                parts.push(type_to_python_str(elem)?);
            }
            Ok(format!("tuple[{}]", parts.join(", ")))
        }
        // `fn(A, B) -> C` → `Callable[[A, B], C]`. The Python `Callable`
        // import is left to user code (typing.Callable, conventional).
        syn::Type::BareFn(bf) => {
            let mut params = Vec::with_capacity(bf.inputs.len());
            for input in &bf.inputs {
                params.push(type_to_python_str(&input.ty)?);
            }
            let ret = match &bf.output {
                syn::ReturnType::Default => "None".to_string(),
                syn::ReturnType::Type(_, t) => type_to_python_str(t)?,
            };
            Ok(format!("Callable[[{}], {ret}]", params.join(", ")))
        }
        // `impl Trait` / `dyn Trait` in type position — emit the bare trait
        // name. Python doesn't model trait bounds.
        syn::Type::TraitObject(t) => {
            for bound in &t.bounds {
                if let syn::TypeParamBound::Trait(tb) = bound
                    && let Some(last) = tb.path.segments.last()
                {
                    return Ok(last.ident.to_string());
                }
            }
            Err("dyn Trait without a concrete bound".to_string())
        }
        syn::Type::ImplTrait(t) => {
            for bound in &t.bounds {
                if let syn::TypeParamBound::Trait(tb) = bound
                    && let Some(last) = tb.path.segments.last()
                {
                    return Ok(last.ident.to_string());
                }
            }
            Err("impl Trait without a concrete bound".to_string())
        }
        other => Err(format!("unsupported type annotation: {other:?}")),
    }
}

fn path_type_to_python(path: &syn::Path) -> Result<String, String> {
    let names: Vec<String> = path.segments.iter().map(|s| s.ident.to_string()).collect();
    let slice: Vec<&str> = names.iter().map(String::as_str).collect();
    let last_seg = path
        .segments
        .last()
        .ok_or_else(|| "empty path".to_owned())?;
    match (path.leading_colon.is_some(), slice.as_slice()) {
        (
            false,
            [
                "i8" | "i16" | "i32" | "i64" | "i128" | "isize" | "u8" | "u16" | "u32" | "u64"
                | "u128" | "usize",
            ],
        ) => Ok("int".to_owned()),
        (false, ["f32" | "f64"]) => Ok("float".to_owned()),
        (false, ["bool"]) => Ok("bool".to_owned()),
        (false, ["str" | "String"]) => Ok("str".to_owned()),
        (false,
["List" | "Vec" | "VecDeque"] | ["pyrust", "List"] |
["std", "collections", "VecDeque"]) => {
            let arg = generic_type_arg(last_seg, 0)?;
            Ok(format!("list[{}]", type_to_python_str(arg)?))
        }
        (false,
["Dict" | "HashMap" | "BTreeMap"] | ["pyrust", "Dict"] |
["std", "collections", "HashMap" | "BTreeMap"]) => {
            let k = generic_type_arg(last_seg, 0)?;
            let v = generic_type_arg(last_seg, 1)?;
            Ok(format!(
                "dict[{}, {}]",
                type_to_python_str(k)?,
                type_to_python_str(v)?
            ))
        }
        (false,
["Set" | "HashSet" | "BTreeSet"] | ["pyrust", "Set"] |
["std", "collections", "HashSet" | "BTreeSet"]) => {
            let arg = generic_type_arg(last_seg, 0)?;
            Ok(format!("set[{}]", type_to_python_str(arg)?))
        }
        (false, ["Option"]) => {
            let arg = generic_type_arg(last_seg, 0)?;
            Ok(format!("{} | None", type_to_python_str(arg)?))
        }
        (false, _) => Ok(last_seg.ident.to_string()),
        (true, _) => Err(format!(
            "absolute paths in type annotations not supported: {}",
            slice.join("::")
        )),
    }
}

fn generic_type_arg(seg: &syn::PathSegment, idx: usize) -> Result<&syn::Type, String> {
    let args = match &seg.arguments {
        syn::PathArguments::AngleBracketed(a) => a,
        syn::PathArguments::None => {
            return Err(format!("type `{}` requires generic arguments", seg.ident));
        }
        _ => {
            return Err(format!("unsupported path arguments on `{}`", seg.ident));
        }
    };
    args.args
        .iter()
        .filter_map(|a| {
            if let syn::GenericArgument::Type(t) = a {
                Some(t)
            } else {
                None
            }
        })
        .nth(idx)
        .ok_or_else(|| format!("`{}` missing generic arg #{}", seg.ident, idx))
}
