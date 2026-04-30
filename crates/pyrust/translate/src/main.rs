mod cfg;
mod emit;
mod parse;

use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use cfg::CfgEnv;

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
            ExitCode::from(2)
        }
    }
}

#[derive(Debug)]
enum Cmd {
    Translate {
        input: PathBuf,
        output: Option<PathBuf>,
        cfg: CfgEnv,
    },
    Check {
        input: PathBuf,
        cfg: CfgEnv,
    },
    Dir {
        src: PathBuf,
        out: PathBuf,
        cfg: CfgEnv,
    },
}

fn parse(args: &[String]) -> Result<Cmd, String> {
    if args.is_empty() {
        return Err("missing argument".into());
    }
    // Strip leading --cfg / --release flags. They may appear in any order
    // before the subcommand or input path.
    let mut cfg = CfgEnv::debug();
    let mut i = 0usize;
    while i < args.len() {
        match args[i].as_str() {
            "--release" => {
                cfg.apply_cfg_arg("debug_assertions=false")?;
                i += 1;
            }
            "--cfg" => {
                let val = args
                    .get(i + 1)
                    .ok_or_else(|| "--cfg requires an argument".to_string())?;
                cfg.apply_cfg_arg(val)?;
                i += 2;
            }
            _ => break,
        }
    }
    let rest = &args[i..];
    if rest.is_empty() {
        return Err("missing input".into());
    }
    match rest[0].as_str() {
        "--check" => {
            let [_, input] = rest else {
                return Err("--check expects exactly one input path".into());
            };
            Ok(Cmd::Check {
                input: input.into(),
                cfg,
            })
        }
        "--dir" => {
            if rest.len() != 4 || rest[2] != "-o" {
                return Err("--dir expects: --dir <src> -o <out>".into());
            }
            Ok(Cmd::Dir {
                src: PathBuf::from(&rest[1]),
                out: PathBuf::from(&rest[3]),
                cfg,
            })
        }
        _ => {
            let input: PathBuf = rest[0].as_str().into();
            let output = match rest.get(1).map(String::as_str) {
                None => None,
                Some("-o") => match rest.get(2) {
                    Some(p) => Some(PathBuf::from(p)),
                    None => return Err("-o requires a path argument".into()),
                },
                Some(other) => return Err(format!("unexpected argument: {other}")),
            };
            if let Some(extra) = rest.get(if output.is_some() { 3 } else { 1 }) {
                return Err(format!("unexpected trailing argument: {extra}"));
            }
            Ok(Cmd::Translate { input, output, cfg })
        }
    }
}

fn run(cmd: &Cmd) -> Result<(), String> {
    match cmd {
        Cmd::Translate { input, output, cfg } => translate_file(input, output.as_deref(), cfg),
        Cmd::Check { input, cfg } => check_file(input, cfg),
        Cmd::Dir { src, out, cfg } => translate_dir(src, out, cfg),
    }
}

fn translate_file(input: &Path, output: Option<&Path>, cfg: &CfgEnv) -> Result<(), String> {
    let source = read_source(input)?;
    let py = translate_source(&source, input, cfg)?;
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

fn check_file(input: &Path, cfg: &CfgEnv) -> Result<(), String> {
    let source = read_source(input)?;
    let _ = translate_source(&source, input, cfg)?;
    Ok(())
}

fn translate_dir(src: &Path, out: &Path, cfg: &CfgEnv) -> Result<(), String> {
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
        translate_file(&entry, Some(&dest), cfg)?;
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

fn translate_source(source: &str, path: &Path, cfg: &CfgEnv) -> Result<String, String> {
    let file = parse::parse_file(source, path)?;
    emit::emit_file(&file, path, cfg)
}
