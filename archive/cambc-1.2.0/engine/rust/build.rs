use std::fs;
use std::path::PathBuf;
use std::process::Command;

fn main() {
    println!("cargo:rerun-if-env-changed=PYO3_PYTHON");
    println!("cargo:rerun-if-env-changed=PYTHON_SYS_EXECUTABLE");
    println!("cargo:rerun-if-env-changed=PYO3_BUILD_EXTENSION_MODULE");

    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = manifest_dir
        .parent()
        .and_then(|p| p.parent())
        .expect("repo root");
    let proto_path = repo_root.join("proto").join("cambc.proto");
    println!("cargo:rerun-if-changed={}", proto_path.display());
    let out_dir = PathBuf::from(std::env::var("OUT_DIR").expect("OUT_DIR missing"));
    let expected = out_dir.join("battlecode.rs");
    if expected.exists() {
        let _ = fs::remove_file(&expected);
    }
    let mut config = prost_build::Config::new();
    config.out_dir(&out_dir);
    config
        .compile_protos(&[proto_path], &[repo_root.join("proto")])
        .expect("failed to compile cambc.proto");
    if !expected.exists() {
        let mut generated = None;
        if let Ok(entries) = fs::read_dir(&out_dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.extension().and_then(|e| e.to_str()) == Some("rs") {
                    generated = Some(path);
                    break;
                }
            }
        }
        if let Some(path) = generated {
            fs::copy(&path, &expected)
                .unwrap_or_else(|_| panic!("failed to copy {} to battlecode.rs", path.display()));
        } else {
            panic!(
                "prost-build did not generate battlecode.rs in {}",
                out_dir.display()
            );
        }
    }

    // --- Compute CPython struct offsets for the direct-write watchdog ---
    // We compile a tiny C program against the Python 3.12 headers to get
    // offsetof(PyThreadState, async_exc) and offsetof(PyInterpreterState, ceval.eval_breaker).
    // These are written to $OUT_DIR/cpython_offsets.rs as constants.
    {
        let offsets_path = out_dir.join("cpython_offsets.rs");
        let mut probed = false;

        let py_cfg = Command::new(
            std::env::var("PYO3_PYTHON").unwrap_or_else(|_| "python3".into()),
        )
        .args([
            "-c",
            "import sysconfig; p = sysconfig.get_paths(); \
             print(p['include'])",
        ])
        .output();
        if let Ok(ref out) = py_cfg {
            if out.status.success() {
                let include_dir = String::from_utf8_lossy(&out.stdout).trim().to_string();
                let c_src = format!(
                    r#"
#define Py_BUILD_CORE
#include <Python.h>
#include <stdio.h>
#include <stddef.h>
#include <internal/pycore_interp.h>
#include <internal/pycore_ceval_state.h>
int main() {{
    printf("pub const ASYNC_EXC_OFFSET: usize = %zu;\n",
        offsetof(PyThreadState, async_exc));
    printf("pub const THREAD_ID_OFFSET: usize = %zu;\n",
        offsetof(PyThreadState, thread_id));
    printf("pub const EVAL_BREAKER_OFFSET: usize = %zu;\n",
        (size_t)offsetof(PyInterpreterState, ceval)
        + (size_t)offsetof(struct _ceval_state, eval_breaker));
    printf("pub const INTERP_OFFSET: usize = %zu;\n",
        offsetof(PyThreadState, interp));
    return 0;
}}
"#
                );
                let c_path = out_dir.join("cpython_offsets.c");
                let bin_path = out_dir.join("cpython_offsets_probe");
                fs::write(&c_path, &c_src).expect("write cpython_offsets.c");
                let cc = std::env::var("CC").unwrap_or_else(|_| "cc".into());
                let compile = Command::new(&cc)
                    .args([
                        "-DPy_BUILD_CORE",
                        &format!("-I{include_dir}"),
                        &format!("-I{include_dir}/internal"),
                        c_path.to_str().unwrap(),
                        "-o",
                        bin_path.to_str().unwrap(),
                    ])
                    .output();
                if let Ok(ref cout) = compile {
                    if cout.status.success() {
                        let run = Command::new(&bin_path).output();
                        if let Ok(ref rout) = run {
                            if rout.status.success() {
                                let rs_code = String::from_utf8_lossy(&rout.stdout);
                                fs::write(&offsets_path, rs_code.as_ref())
                                    .expect("write cpython_offsets.rs");
                                eprintln!("cpython offsets:\n{rs_code}");
                                probed = true;
                            }
                        }
                    } else {
                        let stderr = String::from_utf8_lossy(&cout.stderr);
                        eprintln!("Warning: cpython offset probe compile failed: {stderr}");
                    }
                }
            }
        }

        // Write dummy offsets if probe failed — the values are only used when
        // the "tle" feature is enabled, which should only happen in environments
        // where the probe succeeds (the runner Docker image).
        if !probed && !offsets_path.exists() {
            fs::write(
                &offsets_path,
                "pub const ASYNC_EXC_OFFSET: usize = 0;\n\
                 pub const THREAD_ID_OFFSET: usize = 0;\n\
                 pub const EVAL_BREAKER_OFFSET: usize = 0;\n\
                 pub const INTERP_OFFSET: usize = 0;\n",
            )
            .expect("write dummy cpython_offsets.rs");
            eprintln!("Warning: cpython offset probe failed, wrote dummy offsets");
        }
    }

    // Only emit python link flags for the standalone binary (titan_runner).
    // Extension modules (cdylib for the CLI) must not link libpython — PyO3's
    // extension-module feature handles this. Maturin sets this env var.
    if std::env::var("PYO3_BUILD_EXTENSION_MODULE").is_ok() {
        return;
    }

    let output = Command::new("python3-config")
        .args(["--embed", "--ldflags"])
        .output();

    let output = match output {
        Ok(out) if out.status.success() => out,
        _ => return,
    };

    let flags = String::from_utf8_lossy(&output.stdout);
    for token in flags.split_whitespace() {
        if let Some(path) = token.strip_prefix("-L") {
            println!("cargo:rustc-link-search=native={}", path);
        } else if let Some(lib) = token.strip_prefix("-l") {
            println!("cargo:rustc-link-lib={}", lib);
        }
    }
}
