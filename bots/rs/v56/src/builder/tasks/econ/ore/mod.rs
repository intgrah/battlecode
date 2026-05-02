//! Ore-claim tasks: claim → pave inward ring (in INFRASTRUCTURE) →
//! build harvester. Three fine-grained phases instead of one monolithic
//! `build_at_ore`. The pave step lives in INFRASTRUCTURE because it's
//! shared across Ti / Ax / offensive ore claims and across already-built
//! harvesters.

pub mod build_harvester;
pub mod claim_ore;
