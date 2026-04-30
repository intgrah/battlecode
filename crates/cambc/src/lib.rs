//! Bot-facing API for cambc_libre.
//!
//! Mirrors the Python `cambc` module. Native Rust bots `use cambc::*` and
//! receive `&mut Controller` — a re-export of the engine's `UnitView<'_>`.
//! pyrust-translated bots emit Python that imports the same names from
//! `cambc`, where `Controller` is the runtime PyO3 wrapper.

pub use libre_engine::common::{
    Direction, EntityType, Environment, Pos as Position, ResourceType, Team,
    game_constants as GameConstants,
};
pub use libre_engine::controller::{
    BuildExtra, Controller as ControllerApi, GameError, Result, UnitView as Controller,
};
pub use libre_engine::game_map::{
    ArmouredConveyor, Barrier, Breach, Bridge, BuilderBot, Conveyor, Core,
    Entity, Foundry, Gunner, Harvester, Launcher, Marker, PlayerState, Road,
    Sentinel, Splitter, Tile,
};

/// A Rust bot. Implementors live as `class Player` after pyrust
/// translation; the engine calls `run(c)` each turn the unit is alive.
/// Name it `Player` in your bot crate so the translated Python module
/// exposes `class Player` (matching the Python loader's contract).
pub trait Bot {
    fn run(&mut self, c: &mut Controller<'_>);
}

/// FFI symbol names exported by a Rust bot's cdylib. Defined here so the
/// engine's loader and the bot's `cambc_bot!` macro agree.
pub mod ffi {
    /// Constructs a `Box<dyn Player>` and returns it as `*mut c_void`.
    /// The pointer is opaque to the engine; pass it back into `RUN_NAME`
    /// and `DROP_NAME`.
    pub const CREATE_NAME: &[u8] = b"__cambc_create_bot";
    /// Calls `Player::run(controller)`. `view` is `*mut UnitView<'_>` cast
    /// to `*mut c_void`. Both engine and bot must have the SAME compiled
    /// `libre-engine` for the layout to match — Cargo workspace ensures
    /// this when both are built from the same source.
    pub const RUN_NAME: &[u8] = b"__cambc_run_bot";
    /// Drops the `Box<dyn Player>`. Called when the unit dies or the
    /// game ends.
    pub const DROP_NAME: &[u8] = b"__cambc_drop_bot";
}

/// Export a Rust bot as a cdylib loadable by `cambc-libre`.
///
/// Usage:
///
/// ```ignore
/// use cambc::*;
///
/// #[derive(Default)]
/// pub struct Player;
///
/// impl Bot for Player {
///     fn run(&mut self, c: &mut Controller<'_>) { /* ... */ }
/// }
///
/// cambc_bot!(Player);
/// ```
///
/// The bot crate's `Cargo.toml` must set `crate-type = ["cdylib"]`.
#[macro_export]
macro_rules! cambc_bot {
    ($ty:ty) => {
        #[unsafe(no_mangle)]
        pub extern "C" fn __cambc_create_bot() -> *mut ::std::ffi::c_void {
            let bot: ::std::boxed::Box<dyn $crate::Bot> =
                ::std::boxed::Box::new(<$ty as ::std::default::Default>::default());
            ::std::boxed::Box::into_raw(::std::boxed::Box::new(bot))
                as *mut ::std::ffi::c_void
        }

        #[unsafe(no_mangle)]
        pub extern "C" fn __cambc_run_bot(
            bot: *mut ::std::ffi::c_void,
            view: *mut ::std::ffi::c_void,
        ) {
            let bot = unsafe {
                &mut *(bot as *mut ::std::boxed::Box<dyn $crate::Bot>)
            };
            let view = unsafe { &mut *(view as *mut $crate::Controller<'_>) };
            bot.run(view);
        }

        #[unsafe(no_mangle)]
        pub extern "C" fn __cambc_drop_bot(bot: *mut ::std::ffi::c_void) {
            if !bot.is_null() {
                unsafe {
                    ::std::mem::drop(::std::boxed::Box::from_raw(
                        bot as *mut ::std::boxed::Box<dyn $crate::Bot>,
                    ));
                }
            }
        }
    };
}
