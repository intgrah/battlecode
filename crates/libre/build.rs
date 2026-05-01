use std::fs;
use std::path::PathBuf;
use std::process::Command;

fn main() {
    println!("cargo:rerun-if-env-changed=PYO3_PYTHON");
    println!("cargo:rerun-if-env-changed=PYTHON_SYS_EXECUTABLE");

    let out_dir = PathBuf::from(std::env::var("OUT_DIR").expect("OUT_DIR missing"));

    // --- Compute CPython struct offsets for the direct-write watchdog ---
    // We compile a tiny C program against the Python 3.12 headers to get
    // offsetof(PyThreadState, async_exc) and offsetof(PyInterpreterState, ceval.eval_breaker).
    // These are written to $OUT_DIR/cpython_offsets.rs as constants.
    let offsets_path = out_dir.join("cpython_offsets.rs");
    let mut probed = false;

    let py_cfg = Command::new(std::env::var("PYO3_PYTHON").unwrap_or_else(|_| "python3".into()))
        .args([
            "-c",
            "import sysconfig; p = sysconfig.get_paths(); print(p['include'])",
        ])
        .output();
    if let Ok(ref out) = py_cfg
        && out.status.success() {
            let include_dir = String::from_utf8_lossy(&out.stdout).trim().to_string();
            let c_src = r#"
#define Py_BUILD_CORE
#include <Python.h>
#include <stdio.h>
#include <stddef.h>
#include <internal/pycore_interp.h>
#include <internal/pycore_ceval_state.h>
int main() {
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
}
"#.to_string();
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
                    if let Ok(ref rout) = run
                        && rout.status.success() {
                            let rs_code = String::from_utf8_lossy(&rout.stdout);
                            fs::write(&offsets_path, rs_code.as_ref())
                                .expect("write cpython_offsets.rs");
                            eprintln!("cpython offsets:\n{rs_code}");
                            probed = true;
                        }
                } else {
                    let stderr = String::from_utf8_lossy(&cout.stderr);
                    eprintln!("Warning: cpython offset probe compile failed: {stderr}");
                }
            }
        }

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

    // Bake the libpython directory into the binary's RPATH and the
    // Python install prefix into a CARGO env var (CAMBC_PYTHON_HOME).
    if let Ok(py) = std::env::var("PYO3_PYTHON") {
        let probe = Command::new(&py)
            .args([
                "-c",
                "import sysconfig; \
                 print(sysconfig.get_config_var('LIBDIR')); \
                 print(sysconfig.get_config_var('prefix'))",
            ])
            .output();
        if let Ok(out) = probe {
            let text = String::from_utf8_lossy(&out.stdout);
            let mut lines = text.lines();
            let libdir = lines.next().unwrap_or("").trim();
            let prefix = lines.next().unwrap_or("").trim();
            if !libdir.is_empty() && libdir != "None" {
                println!("cargo:rustc-link-arg=-Wl,-rpath,{libdir}");
            }
            if !prefix.is_empty() && prefix != "None" {
                println!("cargo:rustc-env=CAMBC_PYTHON_HOME={prefix}");
            }
        }
    }
}
