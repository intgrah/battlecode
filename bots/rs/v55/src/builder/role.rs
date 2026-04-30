//! Translation of `bots/intgrah/v54.7.9/builder/role.py`.

use core::fmt;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Role {
    Econ = 0,
    Defense = 1,
    Push = 2,
    PermEcon = 3,
    PermDefense = 4,
    Parasitic = 5,
    /// ECON that auto-flips to DEFENSE at round > 25. Used for the
    /// third opening builder so it gathers map intel as ECON early, then
    /// pivots to DEFENSE with a real picture of the economic terrain.
    EconReactive = 6,
}

impl Role {
    #[must_use]
    pub const fn is_offensive(self) -> bool {
        matches!(self, Role::Push | Role::Parasitic)
    }
}

impl fmt::Display for Role {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Role::Econ => "econ",
            Role::Defense => "defense",
            Role::Push => "push",
            Role::PermEcon => "perm_econ",
            Role::PermDefense => "perm_defense",
            Role::Parasitic => "parasitic",
            Role::EconReactive => "econ_reactive",
        })
    }
}
