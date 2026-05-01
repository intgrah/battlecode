use crate::builder::Builder;
use crate::builder::role::Role;

const _OPENING_ROLES: [Role; 4] = [
    Role::Parasitic,
    Role::PermEcon,
    Role::EconReactive,
    Role::Econ,
];

/// `ECON_REACTIVE` auto-flips to DEFENSE once `self.round` exceeds this.
/// Picks up an early-game economic-map snapshot before pivoting.
const _ECON_REACTIVE_FLIP_ROUND: i32 = 25;

const _INITIAL_WEIGHTS_VERY_EARLY: [(Role, u32); 4] = [
    (Role::Defense, 3),
    (Role::Push, 0),
    (Role::Parasitic, 3),
    (Role::Econ, 4),
];
const _INITIAL_WEIGHTS_EARLY: [(Role, u32); 4] = [
    (Role::Defense, 5),
    (Role::Push, 1),
    (Role::Parasitic, 1),
    (Role::Econ, 3),
];
const _INITIAL_WEIGHTS_LATE: [(Role, u32); 4] = [
    (Role::Defense, 3),
    (Role::Push, 2),
    (Role::Parasitic, 2),
    (Role::Econ, 3),
];

const _TRANSITION_ECON: [(Role, u32); 4] = [
    (Role::Push, 30),
    (Role::Parasitic, 30),
    (Role::Defense, 5),
    (Role::Econ, 35),
];
const _TRANSITION_DEFENSE: [(Role, u32); 4] = [
    (Role::Push, 5),
    (Role::Parasitic, 5),
    (Role::Defense, 80),
    (Role::Econ, 10),
];
const _TRANSITION_PUSH: [(Role, u32); 3] = [(Role::Push, 60), (Role::Defense, 0), (Role::Econ, 40)];
const _TRANSITION_PARASITIC: [(Role, u32); 3] =
    [(Role::Parasitic, 60), (Role::Defense, 0), (Role::Econ, 40)];
const _TRANSITION_PERM_ECON: [(Role, u32); 1] = [(Role::PermEcon, 1)];
const _TRANSITION_PERM_DEFENSE: [(Role, u32); 1] = [(Role::PermDefense, 1)];

const fn _transition_for(role: Role) -> &'static [(Role, u32)] {
    match role {
        Role::Econ => &_TRANSITION_ECON,
        Role::Defense => &_TRANSITION_DEFENSE,
        Role::Push => &_TRANSITION_PUSH,
        Role::Parasitic => &_TRANSITION_PARASITIC,
        Role::PermEcon => &_TRANSITION_PERM_ECON,
        Role::PermDefense => &_TRANSITION_PERM_DEFENSE,
        // EconReactive isn't a transition source: caller flips it to Defense
        // explicitly. Fall back to ECON's transition table.
        Role::EconReactive => &_TRANSITION_ECON,
    }
}

const _REASSIGN_PERIOD: i32 = 150;
const _REASSIGN_AFTER: i32 = 400;

fn weighted_choice(builder: &mut Builder, choices: &[(Role, u32)]) -> Role {
    let total: u32 = pyrust::sum!(pyrust::map!(pyrust::iter!(choices), |t| t.1));
    if total == 0 {
        return choices[0].0;
    }
    // Mirror Python's `random.choices(population, weights=..., k=1)` so
    // role transitions match across native ⇄ translated builds.
    let population: Vec<Role> = pyrust::collect!(pyrust::map!(pyrust::iter!(choices), |t| t.0));
    let weights: Vec<f64> = pyrust::collect!(pyrust::map!(
        pyrust::iter!(choices),
        |t| pyrust::float!(t.1)
    ));
    *pyrust::rng_choices!(builder.state.rng, population, weights, 1)[0]
}

/// Opening spawn slots use the hardcoded sequence indexed by the
/// builder's spawn round, since `get_unit_count()` is non-monotonic
/// — a builder dying mid-opening (or any round where the core
/// couldn't spawn) makes two later spawns share the same count and
/// pick the same opening slot. Round number always advances, so each
/// opening slot is unique. Once the opening sequence is exhausted,
/// fall back to a weighted random pick biased by game stage (early
/// defence-heavy, mid more aggressive).
fn _pick_initial_role(builder: &mut Builder) -> Role {
    let idx = builder.state.round - 1;
    if pyrust::vec::contains!((0..(pyrust::len!(_OPENING_ROLES) as i32)), &idx) {
        return _OPENING_ROLES[idx as usize];
    }
    let w: &[(Role, u32)] = if builder.state.round < 50 {
        &_INITIAL_WEIGHTS_VERY_EARLY
    } else if builder.state.round < 200 {
        &_INITIAL_WEIGHTS_EARLY
    } else {
        &_INITIAL_WEIGHTS_LATE
    };
    weighted_choice(builder, w)
}

pub fn update_role(builder: &mut Builder) {
    if pyrust::is_none!(builder.role) {
        builder.role = Some(_pick_initial_role(builder));
    }
    if builder.role == Some(Role::EconReactive) && builder.state.round > _ECON_REACTIVE_FLIP_ROUND {
        builder.role = Some(Role::Defense);
        builder.role_age = 0;
    }
    if builder.role_age > _REASSIGN_PERIOD && builder.state.round > _REASSIGN_AFTER {
        builder.role_age = 0;
        let row = _transition_for(pyrust::unwrap!(builder.role));
        let new_role = weighted_choice(builder, row);
        builder.role = Some(new_role);
        if new_role.is_offensive() {
            builder.role_age = -300;
        }
    }
    builder.role_age += 1;
}
