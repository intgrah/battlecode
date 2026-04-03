use pyo3::prelude::*;
use pyo3::types::PyDict;
use battlecode_titan::cli::Args;
use battlecode_titan::common::Team;
use std::path::PathBuf;

#[pyfunction]
#[pyo3(signature = (player_a, player_b, engine_root, map_path, replay="replay.replay26", seed=1))]
fn run_game(
    py: Python<'_>,
    player_a: &str,
    player_b: &str,
    engine_root: &str,
    map_path: &str,
    replay: &str,
    seed: u64,
) -> PyResult<Py<PyDict>> {
    let args = Args {
        player_a: player_a.to_string(),
        player_b: player_b.to_string(),
        replay: replay.to_string(),
        map: map_path.to_string(),
        turn_timeout_ms: 2,
        seed,
        sandboxed: false,
        suppress_indicators: false,
        engine_root: PathBuf::from(engine_root),
        encryption_keys: None,
    };
    let summary = battlecode_titan::runner::run(args)?;

    let dict = PyDict::new(py);
    dict.set_item("replay", replay)?;
    dict.set_item("winner", match summary.winner {
        Some(Team::A) => "A",
        Some(Team::B) => "B",
        None => "draw",
    })?;
    dict.set_item("turns", summary.turns_played)?;
    dict.set_item("win_condition", summary.win_condition)?;
    dict.set_item("a_titanium", summary.player_a_titanium)?;
    dict.set_item("a_axionite", summary.player_a_axionite)?;
    dict.set_item("a_titanium_collected", summary.player_a_titanium_collected)?;
    dict.set_item("a_axionite_collected", summary.player_a_axionite_collected)?;
    dict.set_item("b_titanium", summary.player_b_titanium)?;
    dict.set_item("b_axionite", summary.player_b_axionite)?;
    dict.set_item("b_titanium_collected", summary.player_b_titanium_collected)?;
    dict.set_item("b_axionite_collected", summary.player_b_axionite_collected)?;
    dict.set_item("a_units", summary.units_a)?;
    dict.set_item("a_buildings", summary.buildings_a)?;
    dict.set_item("b_units", summary.units_b)?;
    dict.set_item("b_buildings", summary.buildings_b)?;
    Ok(dict.unbind())
}

#[pymodule]
fn cambc_engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(run_game, m)?)?;
    Ok(())
}
