mod emit;
mod parse;

use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match parse(&args) {
        Ok(cmd) => match run(&cmd) {
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
            eprintln!("  pyrust-translate <input.rs> [-o <output.py>]");
            eprintln!("  pyrust-translate --check <input.rs>");
            eprintln!("  pyrust-translate --dir <src_dir> -o <out_dir>");
            ExitCode::from(2)
        }
    }
}

#[derive(Debug)]
enum Cmd {
    Translate {
        input: PathBuf,
        output: Option<PathBuf>,
    },
    Check {
        input: PathBuf,
    },
    Dir {
        src: PathBuf,
        out: PathBuf,
    },
}

fn parse(args: &[String]) -> Result<Cmd, String> {
    if args.is_empty() {
        return Err("missing argument".into());
    }
    match args[0].as_str() {
        "--check" => {
            let [_, input] = args else {
                return Err("--check expects exactly one input path".into());
            };
            Ok(Cmd::Check {
                input: input.into(),
            })
        }
        "--dir" => {
            if args.len() != 4 || args[2] != "-o" {
                return Err("--dir expects: --dir <src> -o <out>".into());
            }
            Ok(Cmd::Dir {
                src: PathBuf::from(&args[1]),
                out: PathBuf::from(&args[3]),
            })
        }
        _ => {
            let input: PathBuf = args[0].as_str().into();
            let output = match args.get(1).map(String::as_str) {
                None => None,
                Some("-o") => match args.get(2) {
                    Some(p) => Some(PathBuf::from(p)),
                    None => return Err("-o requires a path argument".into()),
                },
                Some(other) => return Err(format!("unexpected argument: {other}")),
            };
            if let Some(extra) = args.get(if output.is_some() { 3 } else { 1 }) {
                return Err(format!("unexpected trailing argument: {extra}"));
            }
            Ok(Cmd::Translate { input, output })
        }
    }
}

fn run(cmd: &Cmd) -> Result<(), String> {
    match cmd {
        Cmd::Translate { input, output } => translate_file(input, output.as_deref()),
        Cmd::Check { input } => check_file(input),
        Cmd::Dir { src, out } => translate_dir(src, out),
    }
}

fn translate_file(input: &Path, output: Option<&Path>) -> Result<(), String> {
    let source = read_source(input)?;
    let py = translate_source(&source, input)?;
    match output {
        None => {
            io::stdout()
                .write_all(py.as_bytes())
                .map_err(|e| format!("write stdout: {e}"))?;
        }
        Some(path) => {
            if let Some(parent) = path.parent() {
                if !parent.as_os_str().is_empty() {
                    fs::create_dir_all(parent)
                        .map_err(|e| format!("create {}: {e}", parent.display()))?;
                }
            }
            fs::write(path, py.as_bytes()).map_err(|e| format!("write {}: {e}", path.display()))?;
        }
    }
    Ok(())
}

fn check_file(input: &Path) -> Result<(), String> {
    let source = read_source(input)?;
    // Run the full translator and discard the output; any rejection (parse-time
    // or emit-time) bubbles up as a clear error.
    let _ = translate_source(&source, input)?;
    Ok(())
}

fn translate_dir(src: &Path, out: &Path) -> Result<(), String> {
    if !src.is_dir() {
        return Err(format!("not a directory: {}", src.display()));
    }
    fs::create_dir_all(out).map_err(|e| format!("create {}: {e}", out.display()))?;
    for entry in walk_rs(src)? {
        let rel = entry
            .strip_prefix(src)
            .map_err(|e| format!("path strip: {e}"))?
            .to_path_buf();
        let mut dest = out.join(&rel);
        dest.set_extension("py");
        translate_file(&entry, Some(&dest))?;
    }
    Ok(())
}

fn walk_rs(root: &Path) -> Result<Vec<PathBuf>, String> {
    let mut found = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        for entry in fs::read_dir(&dir).map_err(|e| format!("read {}: {e}", dir.display()))? {
            let entry = entry.map_err(|e| format!("read entry: {e}"))?;
            let path = entry.path();
            let ft = entry
                .file_type()
                .map_err(|e| format!("file_type {}: {e}", path.display()))?;
            if ft.is_dir() {
                stack.push(path);
            } else if ft.is_file() && path.extension().is_some_and(|ext| ext == "rs") {
                found.push(path);
            }
        }
    }
    found.sort();
    Ok(found)
}

fn read_source(path: &Path) -> Result<String, String> {
    fs::read_to_string(path).map_err(|e| format!("read {}: {e}", path.display()))
}

fn translate_source(source: &str, path: &Path) -> Result<String, String> {
    let file = parse::parse_file(source, path)?;
    emit::emit_file(&file, path)
}
