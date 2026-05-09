use std::fmt::Write;

pub fn render(label_a: &str, a: &str, label_b: &str, b: &str) -> String {
    let mut out = String::new();
    let _ = writeln!(out, "--- {label_a}");
    let _ = writeln!(out, "+++ {label_b}");
    let lines_a: Vec<&str> = a.split_inclusive('\n').collect();
    let lines_b: Vec<&str> = b.split_inclusive('\n').collect();
    let common = lines_a.len().min(lines_b.len());
    let mut i = 0;
    while i < common && lines_a[i] == lines_b[i] {
        i += 1;
    }
    for k in i..lines_a.len() {
        out.push('-');
        push_line_visible(&mut out, lines_a[k]);
    }
    for k in i..lines_b.len() {
        out.push('+');
        push_line_visible(&mut out, lines_b[k]);
    }
    out
}

fn push_line_visible(out: &mut String, line: &str) {
    if let Some(stripped) = line.strip_suffix('\n') {
        out.push_str(stripped);
        out.push('\n');
    } else {
        out.push_str(line);
        out.push_str("\\ No newline at end of file\n");
    }
}
