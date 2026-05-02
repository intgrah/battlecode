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
}

impl Role {
    #[must_use]
    pub const fn is_offensive(self) -> bool {
        matches!(self, Self::Push | Self::Parasitic)
    }
}

impl fmt::Display for Role {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::Econ => "econ",
            Self::Defense => "defense",
            Self::Push => "push",
            Self::PermEcon => "perm_econ",
            Self::PermDefense => "perm_defense",
            Self::Parasitic => "parasitic",
        })
    }
}
