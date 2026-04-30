use std::path::Path;

pub fn parse_file(source: &str, path: &Path) -> Result<syn::File, String> {
    syn::parse_file(source).map_err(|e| {
        let span = e.span();
        let start = span.start();
        format!(
            "{}:{}:{}: parse error: {e}",
            path.display(),
            start.line,
            start.column + 1
        )
    })
}
