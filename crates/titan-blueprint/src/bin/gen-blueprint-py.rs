use std::fs;
use std::path::PathBuf;
use std::process::ExitCode;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 2 {
        eprintln!("usage: gen-blueprint-py OUT.py");
        return ExitCode::from(2);
    }
    let out = PathBuf::from(&args[1]);
    let source = titan_blueprint::codegen::generate();
    if let Some(parent) = out.parent() {
        if !parent.as_os_str().is_empty() {
            let _ = fs::create_dir_all(parent);
        }
    }
    if let Err(e) = fs::write(&out, source) {
        eprintln!("write {}: {e}", out.display());
        return ExitCode::from(1);
    }
    println!("wrote {}", out.display());
    ExitCode::SUCCESS
}
