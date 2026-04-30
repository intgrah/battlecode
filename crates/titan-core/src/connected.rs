pub const CARDINALS: [(i32, i32); 4] = [(0, -1), (1, 0), (0, 1), (-1, 0)];

#[must_use]
pub const fn cardinal_letter(d: (i32, i32)) -> Option<&'static str> {
    match d {
        (0, -1) => Some("n"),
        (1, 0) => Some("e"),
        (0, 1) => Some("s"),
        (-1, 0) => Some("w"),
        _ => None,
    }
}

#[must_use]
pub fn input_suffix(inputs: &[(i32, i32)]) -> String {
    if inputs.is_empty() {
        return "x".into();
    }
    let mut sorted: Vec<(i32, i32)> = inputs.to_vec();
    sorted.sort_by_key(|d| CARDINALS.iter().position(|c| c == d).unwrap_or(4));
    sorted
        .into_iter()
        .filter_map(cardinal_letter)
        .collect::<Vec<_>>()
        .join("")
}

#[must_use]
pub fn conveyor_sprite_name(
    base: &str,
    team: &str,
    out: (i32, i32),
    inputs: &[(i32, i32)],
) -> Option<String> {
    let out_s = cardinal_letter(out)?;
    Some(format!("{base}_{team}_{out_s}_{}", input_suffix(inputs)))
}

#[must_use]
pub fn bridge_base_sprite_name(team: &str, openings: &[(i32, i32)]) -> String {
    format!("bridge_base_{team}_{}", input_suffix(openings))
}
