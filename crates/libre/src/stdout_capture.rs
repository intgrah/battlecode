//! Per-call capture of process stdout — Linux fd redirection.
//!
//! Mirrors the Python subinterpreter's `sys.stdout = StringIO()` trick at
//! a level Rust bots can't avoid: the bot's `println!` writes go to
//! `STDOUT_FILENO`, which we briefly point at a pipe. A drainer thread
//! reads the pipe so the bot doesn't block when it overflows the kernel
//! pipe buffer (~64 KB).
//!
//! This module is `cfg(target_os = "linux")` only — matches the rest of
//! the engine's TLE policy.

use std::io::{Read, Write};
use std::os::unix::io::FromRawFd;
use std::thread;

/// Run `f`, capturing everything it writes to `stdout` (fd 1) into the
/// returned `String`. Restores stdout on return, even if `f` panics
/// (the drainer thread joins after restore).
pub fn capture<F: FnOnce()>(f: F) -> String {
    // Flush Rust's own stdout so any *prior* buffered text goes out the
    // real stdout, not into our capture pipe.
    let _ = std::io::stdout().flush();

    let mut fds = [0i32; 2];
    // SAFETY: pipe2 with O_CLOEXEC is a syscall taking a 2-int array.
    let rc = unsafe { libc::pipe2(fds.as_mut_ptr(), libc::O_CLOEXEC) };
    if rc != 0 {
        f();
        return String::new();
    }
    let read_fd = fds[0];
    let write_fd = fds[1];

    // Save current stdout so we can restore it.
    let saved = unsafe { libc::dup(libc::STDOUT_FILENO) };
    if saved < 0 {
        unsafe {
            libc::close(read_fd);
            libc::close(write_fd);
        }
        f();
        return String::new();
    }
    // Redirect stdout to the pipe's write end, then close the duplicate
    // — STDOUT_FILENO now holds the only kernel-side ref to the write end.
    unsafe {
        libc::dup2(write_fd, libc::STDOUT_FILENO);
        libc::close(write_fd);
    }

    // Drainer thread: keep the pipe from filling up by reading until EOF.
    // EOF arrives once we restore stdout below (closes the write end).
    let drainer = thread::spawn(move || {
        let mut file = unsafe { std::fs::File::from_raw_fd(read_fd) };
        let mut buf: Vec<u8> = Vec::new();
        let _ = file.read_to_end(&mut buf);
        buf
    });

    // Run the closure inside a panic guard so we always restore stdout.
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(f));

    // Flush again — bot's println! is fully buffered when stdout isn't a
    // terminal. Without this, the buffered tail is lost on dup2.
    let _ = std::io::stdout().flush();

    // Restore stdout. dup2 closes the destination first, which closes the
    // pipe's write end and lets the drainer see EOF.
    unsafe {
        libc::dup2(saved, libc::STDOUT_FILENO);
        libc::close(saved);
    }

    let bytes = drainer.join().unwrap_or_default();

    if let Err(payload) = result {
        std::panic::resume_unwind(payload);
    }

    String::from_utf8_lossy(&bytes).into_owned()
}
