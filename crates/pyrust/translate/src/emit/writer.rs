use std::path::{Path, PathBuf};

use proc_macro2::Span;

use super::types::{Scope, Ty};

pub struct PyWriter {
    source_path: PathBuf,
    buf: String,
    indent: usize,
    pub scope: Scope,
    current_class: Vec<String>,
}

impl PyWriter {
    pub fn new(source_path: &Path) -> Self {
        Self {
            source_path: source_path.to_path_buf(),
            buf: String::new(),
            indent: 0,
            scope: Scope::new(),
            current_class: Vec::new(),
        }
    }

    pub fn enter_class(&mut self, name: String) {
        self.current_class.push(name);
    }

    pub fn exit_class(&mut self) {
        self.current_class.pop();
    }

    pub fn current_class(&self) -> Option<&str> {
        self.current_class.last().map(String::as_str)
    }

    pub fn line(&mut self, line: &str) {
        if !line.is_empty() {
            for _ in 0..self.indent {
                self.buf.push_str("    ");
            }
            self.buf.push_str(line);
        }
        self.buf.push('\n');
    }

    pub fn blank_line(&mut self) {
        self.buf.push('\n');
    }

    pub fn enter_indent(&mut self) {
        self.indent += 1;
    }

    pub fn exit_indent(&mut self) {
        self.indent = self.indent.checked_sub(1).expect("dedent below zero");
    }

    pub fn enter_block(&mut self) {
        self.scope.push();
    }

    pub fn exit_block(&mut self) {
        self.scope.pop();
    }

    pub fn declare(&mut self, name: &str, ty: Ty) {
        self.scope.declare(name, ty);
    }

    pub fn lookup(&self, name: &str) -> Option<Ty> {
        self.scope.lookup(name)
    }

    pub fn is_outer_binding(&self, name: &str) -> bool {
        self.scope.is_in_outer_frame(name)
    }

    pub fn is_current_binding(&self, name: &str) -> bool {
        self.scope.is_in_current_frame(name)
    }

    pub fn finish(self) -> String {
        let mut s = self.buf;
        if !s.ends_with('\n') {
            s.push('\n');
        }
        s
    }

    pub fn err(&self, span: Span, msg: impl Into<String>) -> String {
        let start = span.start();
        format!(
            "{}:{}:{}: {}",
            self.source_path.display(),
            start.line,
            start.column + 1,
            msg.into()
        )
    }
}
