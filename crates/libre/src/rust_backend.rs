//! Native-Rust bot backend.
//!
//! A Rust bot is a `cdylib` that uses the `cambc::cambc_bot!` macro to
//! export three `extern "C"` symbols (`__cambc_create_bot`,
//! `__cambc_run_bot`, `__cambc_drop_bot`). At game start the engine
//! `dlopen`s the `.so` and resolves the three symbols. Per turn it
//! calls `run` with a raw pointer to the engine's `UnitView<'_>`.
//!
//! ABI safety: the bot and engine must be built from the SAME version
//! of `libre-engine` so that `UnitView` / `Game` layouts agree. The
//! Cargo workspace ensures this when both are part of the same build
//! tree (e.g. `bots/test_rust/<bot>/Cargo.toml` depends on
//! `crates/cambc` by relative path).
//!
//! Methods on `Controller` (the engine's trait) are monomorphised into
//! the bot's compiled copy, so no `dyn` fat-pointer is exchanged across
//! the FFI boundary — only `*mut c_void` (`UnitView`) and `*mut c_void`
//! (the boxed `Box<dyn Player>`).

use std::ffi::c_void;
use std::path::Path;

use cambc::ffi;
use libre_engine::controller::UnitView;

pub struct RustBackend {
    // Library must outlive every function pointer below; keep it boxed.
    _lib: libloading::Library,
    create: unsafe extern "C" fn() -> *mut c_void,
    run: unsafe extern "C" fn(*mut c_void, *mut c_void),
    drop_fn: unsafe extern "C" fn(*mut c_void),
}

impl RustBackend {
    pub fn load(so_path: &Path) -> Result<Self, String> {
        let lib = unsafe {
            libloading::Library::new(so_path)
                .map_err(|e| format!("dlopen {}: {e}", so_path.display()))?
        };
        // Resolve symbols and reify them into bare fn pointers; the
        // `Symbol` borrows from `lib`, so we end-of-life it before
        // packaging.
        let create_fn: unsafe extern "C" fn() -> *mut c_void = unsafe {
            *lib.get(ffi::CREATE_NAME)
                .map_err(|e| format!("missing __cambc_create_bot: {e}"))?
        };
        let run_fn: unsafe extern "C" fn(*mut c_void, *mut c_void) = unsafe {
            *lib.get(ffi::RUN_NAME)
                .map_err(|e| format!("missing __cambc_run_bot: {e}"))?
        };
        let drop_fn: unsafe extern "C" fn(*mut c_void) = unsafe {
            *lib.get(ffi::DROP_NAME)
                .map_err(|e| format!("missing __cambc_drop_bot: {e}"))?
        };
        Ok(Self {
            _lib: lib,
            create: create_fn,
            run: run_fn,
            drop_fn,
        })
    }

    #[must_use] 
    pub fn create_bot(&self) -> *mut c_void {
        unsafe { (self.create)() }
    }

    /// Run one turn for `bot` against `view`. The view borrow lives only
    /// for the duration of this call.
    pub fn run_bot(&self, bot: *mut c_void, view: &mut UnitView<'_>) {
        let view_ptr = std::ptr::from_mut::<UnitView<'_>>(view).cast::<c_void>();
        unsafe { (self.run)(bot, view_ptr) }
    }

    pub fn drop_bot(&self, bot: *mut c_void) {
        unsafe { (self.drop_fn)(bot) }
    }
}
