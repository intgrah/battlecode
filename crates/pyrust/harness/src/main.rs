mod diff;

use std::ffi::OsStr;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode, Stdio};

const RUNNER_PLACEHOLDER: &str = "fn main() {\n    println!(\"pyrust runner placeholder\");\n}\n";

struct Paths {
    pyrust_root: PathBuf,
    translate_bin: PathBuf,
    runner_manifest: PathBuf,
    runner_main: PathBuf,
    runner_src_dir: PathBuf,
    corpus_dir: PathBuf,
    check_dir: PathBuf,
}

impl Paths {
    fn discover() -> Result<Self, String> {
        let pyrust_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .ok_or("CARGO_MANIFEST_DIR has no parent")?
            .to_path_buf();
        let translate_bin = match std::env::var_os("PYRUST_TRANSLATE_BIN") {
            Some(p) => PathBuf::from(p),
            None => {
                let exe = std::env::current_exe().map_err(|e| format!("current_exe: {e}"))?;
                let dir = exe.parent().ok_or("current_exe has no parent")?;
                let suffix = if cfg!(windows) { ".exe" } else { "" };
                dir.join(format!("pyrust-translate{suffix}"))
            }
        };
        if !translate_bin.exists() {
            return Err(format!(
                "pyrust-translate binary not found at {}; build it first or set PYRUST_TRANSLATE_BIN",
                translate_bin.display()
            ));
        }
        let runner_manifest = pyrust_root.join("runner/Cargo.toml");
        let runner_main = pyrust_root.join("runner/src/main.rs");
        let runner_src_dir = pyrust_root.join("runner/src");
        let corpus_dir = pyrust_root.join("tests/corpus");
        let check_dir = pyrust_root.join("tests/check");
        Ok(Self {
            pyrust_root,
            translate_bin,
            runner_manifest,
            runner_main,
            runner_src_dir,
            corpus_dir,
            check_dir,
        })
    }
}

fn main() -> ExitCode {
    let paths = match Paths::discover() {
        Ok(p) => p,
        Err(e) => {
            eprintln!("pyrust-harness: {e}");
            return ExitCode::from(2);
        }
    };
    let mut report = Report::default();
    if paths.corpus_dir.exists() {
        match collect_corpus_cases(&paths.corpus_dir) {
            Ok(cases) => {
                for case in &cases {
                    let label = case_label(&paths.corpus_dir, &case.dir);
                    let r = match case.kind {
                        CaseKind::Single => run_corpus_case(&paths, &case.dir),
                        CaseKind::Multi => run_corpus_case_multi(&paths, &case.dir),
                    };
                    match r {
                        Ok(()) => report.pass(&label),
                        Err(e) => report.fail(&label, &e),
                    }
                }
            }
            Err(e) => {
                eprintln!("pyrust-harness: scanning corpus: {e}");
                return ExitCode::from(2);
            }
        }
    }
    if paths.check_dir.exists() {
        match collect_marker_dirs(&paths.check_dir, "input.rs") {
            Ok(cases) => {
                for case in &cases {
                    let label = format!("check/{}", case_label(&paths.check_dir, case));
                    match run_check_case(&paths, case) {
                        Ok(()) => report.pass(&label),
                        Err(e) => report.fail(&label, &e),
                    }
                }
            }
            Err(e) => {
                eprintln!("pyrust-harness: scanning check corpus: {e}");
                return ExitCode::from(2);
            }
        }
    }
    report.print_summary();
    if report.failed == 0 {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    }
}

#[derive(Default)]
struct Report {
    passed: usize,
    failed: usize,
}

impl Report {
    fn pass(&mut self, label: &str) {
        self.passed += 1;
        println!("PASS  {label}");
    }
    fn fail(&mut self, label: &str, msg: &str) {
        self.failed += 1;
        println!("FAIL  {label}");
        for line in msg.lines() {
            println!("        {line}");
        }
    }
    fn print_summary(&self) {
        let total = self.passed + self.failed;
        println!();
        println!(
            "summary: {} passed, {} failed, {} total",
            self.passed, self.failed, total
        );
    }
}

fn case_label(root: &Path, case_dir: &Path) -> String {
    case_dir
        .strip_prefix(root)
        .ok()
        .map(|p| p.to_string_lossy().into_owned())
        .unwrap_or_else(|| case_dir.display().to_string())
}

#[derive(Clone, Copy, Debug)]
enum CaseKind {
    Single,
    Multi,
}

struct CorpusCase {
    dir: PathBuf,
    kind: CaseKind,
}

fn collect_corpus_cases(root: &Path) -> Result<Vec<CorpusCase>, String> {
    let mut found = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let entries = fs::read_dir(&dir).map_err(|e| format!("read {}: {e}", dir.display()))?;
        let mut subdirs = Vec::new();
        let mut has_input = false;
        let mut has_src_dir = false;
        for entry in entries {
            let entry = entry.map_err(|e| format!("read entry: {e}"))?;
            let path = entry.path();
            let ft = entry.file_type().map_err(|e| format!("file_type: {e}"))?;
            if ft.is_dir() {
                if path.file_name() == Some(OsStr::new("src")) && path.join("main.rs").is_file() {
                    has_src_dir = true;
                }
                subdirs.push(path);
            } else if ft.is_file() && path.file_name() == Some(OsStr::new("input.rs")) {
                has_input = true;
            }
        }
        if has_input {
            found.push(CorpusCase {
                dir,
                kind: CaseKind::Single,
            });
        } else if has_src_dir {
            found.push(CorpusCase {
                dir,
                kind: CaseKind::Multi,
            });
        } else {
            stack.extend(subdirs);
        }
    }
    found.sort_by(|a, b| a.dir.cmp(&b.dir));
    Ok(found)
}

fn collect_marker_dirs(root: &Path, marker: &str) -> Result<Vec<PathBuf>, String> {
    let mut found = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let entries = fs::read_dir(&dir).map_err(|e| format!("read {}: {e}", dir.display()))?;
        let mut subdirs = Vec::new();
        let mut has_marker = false;
        for entry in entries {
            let entry = entry.map_err(|e| format!("read entry: {e}"))?;
            let path = entry.path();
            let ft = entry.file_type().map_err(|e| format!("file_type: {e}"))?;
            if ft.is_dir() {
                subdirs.push(path);
            } else if ft.is_file() && path.file_name() == Some(OsStr::new(marker)) {
                has_marker = true;
            }
        }
        if has_marker {
            found.push(dir);
        } else {
            stack.extend(subdirs);
        }
    }
    found.sort();
    Ok(found)
}

fn run_corpus_case(paths: &Paths, case: &Path) -> Result<(), String> {
    let input = case.join("input.rs");
    let expected_py_path = case.join("expected.py");
    let expected_out_path = case.join("expected.out");
    let expected_py = read_file(&expected_py_path)?;
    let expected_out = read_file(&expected_out_path)?;

    let translator_out = run_translator(paths, &input)?;
    if translator_out != expected_py {
        return Err(format!(
            "step 1 (translator output != expected.py):\n{}",
            diff::render("expected.py", &expected_py, "translator", &translator_out)
        ));
    }

    let rust_out = run_runner(paths, &input)?;
    if rust_out != expected_out {
        return Err(format!(
            "step 2 (Rust execution != expected.out):\n{}",
            diff::render("expected.out", &expected_out, "rust", &rust_out)
        ));
    }

    let py_expected_out = run_python(&expected_py_path)?;
    if py_expected_out != expected_out {
        return Err(format!(
            "step 3 (python3 expected.py != expected.out):\n{}",
            diff::render(
                "expected.out",
                &expected_out,
                "python(expected.py)",
                &py_expected_out
            )
        ));
    }

    let translated_path = paths.pyrust_root.join("target/.harness-translated.py");
    if let Some(parent) = translated_path.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("create {}: {e}", parent.display()))?;
    }
    fs::write(&translated_path, &translator_out)
        .map_err(|e| format!("write {}: {e}", translated_path.display()))?;
    let py_translated_out = run_python(&translated_path)?;
    if py_translated_out != expected_out {
        return Err(format!(
            "step 4 (python3 <translated> != expected.out):\n{}",
            diff::render(
                "expected.out",
                &expected_out,
                "python(translated)",
                &py_translated_out
            )
        ));
    }

    Ok(())
}

fn run_check_case(paths: &Paths, case: &Path) -> Result<(), String> {
    let input = case.join("input.rs");
    let expected_error = read_file(&case.join("expected_error.txt"))?;
    let needle = expected_error.trim();
    if needle.is_empty() {
        return Err("expected_error.txt is empty".into());
    }
    let output = Command::new(&paths.translate_bin)
        .arg("--check")
        .arg(&input)
        .output()
        .map_err(|e| format!("spawn pyrust-translate: {e}"))?;
    if output.status.success() {
        return Err("--check exited 0 but should have rejected".into());
    }
    let stderr = String::from_utf8_lossy(&output.stderr);
    if !stderr.contains(needle) {
        return Err(format!(
            "stderr does not contain expected substring {needle:?}\n--- stderr ---\n{stderr}"
        ));
    }
    Ok(())
}

fn run_translator(paths: &Paths, input: &Path) -> Result<String, String> {
    let output = Command::new(&paths.translate_bin)
        .arg(input)
        .stdin(Stdio::null())
        .output()
        .map_err(|e| format!("spawn pyrust-translate: {e}"))?;
    if !output.status.success() {
        return Err(format!(
            "pyrust-translate exited {} on {}\n--- stderr ---\n{}",
            output.status,
            input.display(),
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    String::from_utf8(output.stdout).map_err(|e| format!("translator stdout not utf-8: {e}"))
}

fn run_runner(paths: &Paths, input: &Path) -> Result<String, String> {
    let original = fs::read_to_string(&paths.runner_main).unwrap_or_default();
    let case_src = read_file(input)?;
    fs::write(&paths.runner_main, &case_src)
        .map_err(|e| format!("write {}: {e}", paths.runner_main.display()))?;
    let result = (|| -> Result<String, String> {
        let output = Command::new("cargo")
            .arg("run")
            .arg("--quiet")
            .arg("--manifest-path")
            .arg(&paths.runner_manifest)
            .stdin(Stdio::null())
            .output()
            .map_err(|e| format!("spawn cargo run (runner): {e}"))?;
        if !output.status.success() {
            return Err(format!(
                "runner cargo run exited {}\n--- stderr ---\n{}",
                output.status,
                String::from_utf8_lossy(&output.stderr)
            ));
        }
        String::from_utf8(output.stdout).map_err(|e| format!("runner stdout not utf-8: {e}"))
    })();
    let restore = if original.is_empty() {
        RUNNER_PLACEHOLDER
    } else {
        original.as_str()
    };
    let restore_err = fs::write(&paths.runner_main, restore)
        .err()
        .map(|e| format!("restore {}: {e}", paths.runner_main.display()));
    match (result, restore_err) {
        (Ok(s), None) => Ok(s),
        (Ok(_), Some(e)) => Err(e),
        (Err(e), None) => Err(e),
        (Err(e), Some(re)) => Err(format!("{e}\n(also: {re})")),
    }
}

fn run_corpus_case_multi(paths: &Paths, case: &Path) -> Result<(), String> {
    let src_dir = case.join("src");
    let expected_dir = case.join("expected");
    if !expected_dir.is_dir() {
        return Err(format!(
            "multi-file case missing `expected/` directory at {}",
            expected_dir.display()
        ));
    }
    let expected_out_path = case.join("expected.out");
    let expected_out = read_file(&expected_out_path)?;

    let translated_dir = paths.pyrust_root.join("target/.harness-translated-tree");
    if translated_dir.exists() {
        fs::remove_dir_all(&translated_dir)
            .map_err(|e| format!("clear {}: {e}", translated_dir.display()))?;
    }
    fs::create_dir_all(&translated_dir)
        .map_err(|e| format!("create {}: {e}", translated_dir.display()))?;

    let translate_status = Command::new(&paths.translate_bin)
        .arg("--dir")
        .arg(&src_dir)
        .arg("-o")
        .arg(&translated_dir)
        .stdin(Stdio::null())
        .output()
        .map_err(|e| format!("spawn pyrust-translate --dir: {e}"))?;
    if !translate_status.status.success() {
        return Err(format!(
            "pyrust-translate --dir exited {}\n--- stderr ---\n{}",
            translate_status.status,
            String::from_utf8_lossy(&translate_status.stderr)
        ));
    }

    if let Some(diff) = diff_trees(&expected_dir, &translated_dir, "py")? {
        return Err(format!("step 1 (translated tree != expected/):\n{diff}"));
    }

    let rust_out = run_runner_multi(paths, &src_dir)?;
    if rust_out != expected_out {
        return Err(format!(
            "step 2 (Rust execution != expected.out):\n{}",
            diff::render("expected.out", &expected_out, "rust", &rust_out)
        ));
    }

    let py_expected_out = run_python(&expected_dir.join("main.py"))?;
    if py_expected_out != expected_out {
        return Err(format!(
            "step 3 (python3 expected/main.py != expected.out):\n{}",
            diff::render(
                "expected.out",
                &expected_out,
                "python(expected)",
                &py_expected_out,
            )
        ));
    }

    let py_translated_out = run_python(&translated_dir.join("main.py"))?;
    if py_translated_out != expected_out {
        return Err(format!(
            "step 4 (python3 <translated>/main.py != expected.out):\n{}",
            diff::render(
                "expected.out",
                &expected_out,
                "python(translated)",
                &py_translated_out,
            )
        ));
    }

    Ok(())
}

fn run_runner_multi(paths: &Paths, src_dir: &Path) -> Result<String, String> {
    reset_runner_src(paths)?;
    populate_runner_src(paths, src_dir)?;
    let result = (|| -> Result<String, String> {
        let output = Command::new("cargo")
            .arg("run")
            .arg("--quiet")
            .arg("--manifest-path")
            .arg(&paths.runner_manifest)
            .stdin(Stdio::null())
            .output()
            .map_err(|e| format!("spawn cargo run (runner): {e}"))?;
        if !output.status.success() {
            return Err(format!(
                "runner cargo run exited {}\n--- stderr ---\n{}",
                output.status,
                String::from_utf8_lossy(&output.stderr)
            ));
        }
        String::from_utf8(output.stdout).map_err(|e| format!("runner stdout not utf-8: {e}"))
    })();
    let restore_err = reset_runner_src(paths).err();
    match (result, restore_err) {
        (Ok(s), None) => Ok(s),
        (Ok(_), Some(e)) => Err(e),
        (Err(e), None) => Err(e),
        (Err(e), Some(re)) => Err(format!("{e}\n(also: {re})")),
    }
}

fn reset_runner_src(paths: &Paths) -> Result<(), String> {
    if paths.runner_src_dir.exists() {
        fs::remove_dir_all(&paths.runner_src_dir)
            .map_err(|e| format!("clear {}: {e}", paths.runner_src_dir.display()))?;
    }
    fs::create_dir_all(&paths.runner_src_dir)
        .map_err(|e| format!("create {}: {e}", paths.runner_src_dir.display()))?;
    fs::write(&paths.runner_main, RUNNER_PLACEHOLDER)
        .map_err(|e| format!("write {}: {e}", paths.runner_main.display()))
}

fn populate_runner_src(paths: &Paths, src_dir: &Path) -> Result<(), String> {
    copy_tree(src_dir, &paths.runner_src_dir, "rs")
}

fn copy_tree(src: &Path, dst: &Path, ext: &str) -> Result<(), String> {
    let entries = fs::read_dir(src).map_err(|e| format!("read {}: {e}", src.display()))?;
    for entry in entries {
        let entry = entry.map_err(|e| format!("read entry: {e}"))?;
        let path = entry.path();
        let name = entry.file_name();
        let dest = dst.join(&name);
        let ft = entry.file_type().map_err(|e| format!("file_type: {e}"))?;
        if ft.is_dir() {
            fs::create_dir_all(&dest).map_err(|e| format!("create {}: {e}", dest.display()))?;
            copy_tree(&path, &dest, ext)?;
        } else if ft.is_file() && path.extension().is_some_and(|e| e == ext) {
            fs::copy(&path, &dest)
                .map_err(|e| format!("copy {} → {}: {e}", path.display(), dest.display()))?;
        }
    }
    Ok(())
}

fn list_files(root: &Path, ext: &str) -> Result<Vec<PathBuf>, String> {
    let mut found = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let entries = fs::read_dir(&dir).map_err(|e| format!("read {}: {e}", dir.display()))?;
        for entry in entries {
            let entry = entry.map_err(|e| format!("read entry: {e}"))?;
            let path = entry.path();
            let ft = entry.file_type().map_err(|e| format!("file_type: {e}"))?;
            if ft.is_dir() {
                stack.push(path);
            } else if ft.is_file() && path.extension().is_some_and(|e| e == ext) {
                found.push(path);
            }
        }
    }
    found.sort();
    Ok(found)
}

fn diff_trees(expected_dir: &Path, actual_dir: &Path, ext: &str) -> Result<Option<String>, String> {
    let expected_files = list_files(expected_dir, ext)?;
    let actual_files = list_files(actual_dir, ext)?;
    let expected_rel: Vec<PathBuf> = expected_files
        .iter()
        .map(|p| p.strip_prefix(expected_dir).unwrap().to_path_buf())
        .collect();
    let actual_rel: Vec<PathBuf> = actual_files
        .iter()
        .map(|p| p.strip_prefix(actual_dir).unwrap().to_path_buf())
        .collect();
    if expected_rel != actual_rel {
        let exp_set: std::collections::BTreeSet<_> = expected_rel.iter().cloned().collect();
        let act_set: std::collections::BTreeSet<_> = actual_rel.iter().cloned().collect();
        let missing: Vec<_> = exp_set.difference(&act_set).collect();
        let extra: Vec<_> = act_set.difference(&exp_set).collect();
        let mut msg = String::new();
        if !missing.is_empty() {
            msg.push_str("missing in translator output:\n");
            for p in missing {
                msg.push_str(&format!("  {}\n", p.display()));
            }
        }
        if !extra.is_empty() {
            msg.push_str("extra in translator output:\n");
            for p in extra {
                msg.push_str(&format!("  {}\n", p.display()));
            }
        }
        return Ok(Some(msg));
    }
    for rel in &expected_rel {
        let exp = read_file(&expected_dir.join(rel))?;
        let act = read_file(&actual_dir.join(rel))?;
        if exp != act {
            return Ok(Some(format!(
                "file {} differs:\n{}",
                rel.display(),
                diff::render(
                    &format!("expected/{}", rel.display()),
                    &exp,
                    &format!("translated/{}", rel.display()),
                    &act,
                )
            )));
        }
    }
    Ok(None)
}

fn run_python(path: &Path) -> Result<String, String> {
    let output = Command::new("python3")
        .arg(path)
        .stdin(Stdio::null())
        .output()
        .map_err(|e| format!("spawn python3: {e}"))?;
    if !output.status.success() {
        return Err(format!(
            "python3 {} exited {}\n--- stderr ---\n{}",
            path.display(),
            output.status,
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    String::from_utf8(output.stdout).map_err(|e| format!("python stdout not utf-8: {e}"))
}

fn read_file(path: &Path) -> Result<String, String> {
    fs::read_to_string(path).map_err(|e| format!("read {}: {e}", path.display()))
}
