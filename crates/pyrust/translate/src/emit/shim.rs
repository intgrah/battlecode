use syn::Path;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ShimCall {
    Print,
    Len,
    Min,
    Max,
    Sum,
    Abs,
    Sorted,
    Reversed,
    Any,
    All,
    Enumerate,
    Zip,
    RandomChoice,
    RandomRandint,
    RandomSeed,
}

impl ShimCall {
    pub fn python_name(self) -> &'static str {
        match self {
            ShimCall::Print => "print",
            ShimCall::Len => "len",
            ShimCall::Min => "min",
            ShimCall::Max => "max",
            ShimCall::Sum => "sum",
            ShimCall::Abs => "abs",
            ShimCall::Sorted => "sorted",
            ShimCall::Reversed => "reversed",
            ShimCall::Any => "any",
            ShimCall::All => "all",
            ShimCall::Enumerate => "enumerate",
            ShimCall::Zip => "zip",
            ShimCall::RandomChoice => "random.choice",
            ShimCall::RandomRandint => "random.randint",
            ShimCall::RandomSeed => "random.seed",
        }
    }
}

pub fn recognize(path: &Path) -> Option<ShimCall> {
    if path.leading_colon.is_some() {
        return None;
    }
    let names: Vec<String> = path.segments.iter().map(|s| s.ident.to_string()).collect();
    let slice: Vec<&str> = names.iter().map(String::as_str).collect();
    // Strip the optional leading `pyrust::` so callers can write either
    // `print(...)` or `pyrust::print(...)`. Submodule paths like
    // `pyrust::random::choice` are also accepted.
    let key: &[&str] = match slice.as_slice() {
        ["pyrust", ..] => &slice[1..],
        other => other,
    };
    match key {
        ["print"] => Some(ShimCall::Print),
        ["len"] => Some(ShimCall::Len),
        ["min"] => Some(ShimCall::Min),
        ["max"] => Some(ShimCall::Max),
        ["sum"] => Some(ShimCall::Sum),
        ["abs"] => Some(ShimCall::Abs),
        ["sorted"] => Some(ShimCall::Sorted),
        ["reversed"] => Some(ShimCall::Reversed),
        ["any"] => Some(ShimCall::Any),
        ["all"] => Some(ShimCall::All),
        ["enumerate"] => Some(ShimCall::Enumerate),
        ["zip"] => Some(ShimCall::Zip),
        ["random", "choice"] => Some(ShimCall::RandomChoice),
        ["random", "randint"] => Some(ShimCall::RandomRandint),
        ["random", "seed"] => Some(ShimCall::RandomSeed),
        _ => None,
    }
}
