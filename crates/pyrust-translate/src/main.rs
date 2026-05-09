use std::process::ExitCode;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match pyrust_translate::parse_args(&args) {
        Ok(cmd) => match pyrust_translate::run(&cmd) {
            Ok(()) => ExitCode::SUCCESS,
            Err(e) => {
                eprintln!("pyrust-translate: {e}");
                ExitCode::from(1)
            }
        },
        Err(e) => {
            eprintln!("pyrust-translate: {e}");
            eprintln!();
            eprintln!("usage:");
            eprintln!(
                "  pyrust-translate [--cfg KEY[=VAL]]... [--release] <input.rs> [-o <output.py>]"
            );
            eprintln!("  pyrust-translate [--cfg KEY[=VAL]]... [--release] --check <input.rs>");
            eprintln!(
                "  pyrust-translate [--cfg KEY[=VAL]]... [--release] --dir <src_dir> -o <out_dir>"
            );
            eprintln!();
            eprintln!("  --release           equivalent to --cfg debug_assertions=false");
            eprintln!("  --cfg KEY           set boolean cfg flag (truthy)");
            eprintln!("  --cfg KEY=true|false explicit boolean");
            eprintln!("  --cfg KEY=value     set kv form for cfg(KEY = \"value\") matching");
            eprintln!();
            eprintln!("  --cfg preserve_comments  emit `///` doc-comments as Python");
            eprintln!("                           docstrings (default: stripped)");
            ExitCode::from(2)
        }
    }
}
