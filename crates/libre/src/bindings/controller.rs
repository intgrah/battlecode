// NOTE: When changing the Controller API, also update the Python stub in
// engine/py/cambc.py (class Controller) so that type-checkers stay in sync.
//
// This file is a thin PyO3 adapter around `libre_engine::controller::UnitView`.
// All game logic lives there; here we only:
//   - hold the shared `Rc<RefCell<Game>>` and per-controller `has_placed_marker` cell
//   - convert `GameError` → `PyErr` (using the cached `cambc.GameError` class)
//   - convert engine return types to `PyObject` where the Python ABI demands it
//   - enforce the per-turn CPU deadline (`check_deadline`)
//   - raise `SystemExit` for `self_destruct` / `resign` so the bot exits

use pyo3::prelude::*;
use std::cell::{Cell, RefCell};
use std::rc::Rc;

use libre_engine::common::{Direction, EntityType, Pos};
use libre_engine::controller::{BuildExtra, Controller as ControllerTrait, GameError, UnitView};
use libre_engine::game::Game;

use super::py_convert::game_error;

#[pyclass(unsendable)]
pub struct Controller {
    game: Rc<RefCell<Game>>,
    unit: i32,
    has_placed_marker: Cell<bool>,
}

impl Controller {
    pub const fn new(game: Rc<RefCell<Game>>, unit: i32) -> Self {
        Self {
            game,
            unit,
            has_placed_marker: Cell::new(false),
        }
    }

    fn check_deadline(&self) -> PyResult<()> {
        let deadline = crate::runner::CPU_DEADLINE_NS.load(std::sync::atomic::Ordering::Relaxed);
        if crate::runner::thread_cpu_time_ns() >= deadline {
            Err(pyo3::exceptions::PySystemExit::new_err(()))
        } else {
            Ok(())
        }
    }

    fn with_view<R>(&self, f: impl FnOnce(&mut UnitView<'_>) -> R) -> R {
        let mut game = self.game.borrow_mut();
        let mut view = UnitView::new(&mut game, self.unit);
        view.has_placed_marker = self.has_placed_marker.get();
        let result = f(&mut view);
        self.has_placed_marker.set(view.has_placed_marker);
        result
    }
}

fn to_py_err(e: GameError) -> PyErr {
    game_error(&e.0)
}

fn map_err<T>(r: Result<T, GameError>) -> PyResult<T> {
    r.map_err(to_py_err)
}

#[pymethods]
impl Controller {
    #[pyo3(signature = (id=None))]
    fn get_team(&self, py: Python, id: Option<i32>) -> PyResult<PyObject> {
        self.check_deadline()?;
        let team = map_err(self.with_view(|v| v.get_team(id)))?;
        Ok(team.into_pyobject(py)?.unbind())
    }

    #[pyo3(signature = (id=None))]
    fn get_position(&self, py: Python, id: Option<i32>) -> PyResult<PyObject> {
        self.check_deadline()?;
        let pos = map_err(self.with_view(|v| v.get_position(id)))?;
        Ok(pos.into_pyobject(py)?.unbind())
    }

    fn get_id(&self) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_id()))
    }

    fn get_action_cooldown(&self) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_action_cooldown()))
    }

    fn get_move_cooldown(&self) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_move_cooldown()))
    }

    fn get_ammo_amount(&self) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_ammo_amount()))
    }

    fn get_ammo_type(&self, py: Python) -> PyResult<PyObject> {
        self.check_deadline()?;
        match map_err(self.with_view(|v| v.get_ammo_type()))? {
            Some(r) => Ok(r.into_pyobject(py)?.unbind()),
            None => Ok(py.None()),
        }
    }

    #[pyo3(signature = (id=None))]
    fn get_vision_radius_sq(&self, id: Option<i32>) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_vision_radius_sq(id)))
    }

    #[pyo3(signature = (id=None))]
    fn get_hp(&self, id: Option<i32>) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_hp(id)))
    }

    #[pyo3(signature = (id=None))]
    fn get_max_hp(&self, id: Option<i32>) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_max_hp(id)))
    }

    #[pyo3(signature = (id=None))]
    fn get_entity_type(&self, py: Python, id: Option<i32>) -> PyResult<PyObject> {
        self.check_deadline()?;
        let ty = map_err(self.with_view(|v| v.get_entity_type(id)))?;
        Ok(ty.into_pyobject(py)?.unbind())
    }

    #[pyo3(signature = (id=None))]
    fn get_direction(&self, py: Python, id: Option<i32>) -> PyResult<PyObject> {
        self.check_deadline()?;
        let dir = map_err(self.with_view(|v| v.get_direction(id)))?;
        Ok(dir.into_pyobject(py)?.unbind())
    }

    fn get_bridge_target(&self, py: Python, id: i32) -> PyResult<PyObject> {
        self.check_deadline()?;
        let pos = map_err(self.with_view(|v| v.get_bridge_target(id)))?;
        Ok(pos.into_pyobject(py)?.unbind())
    }

    #[pyo3(signature = (id=None))]
    fn get_stored_resource(&self, py: Python, id: Option<i32>) -> PyResult<PyObject> {
        self.check_deadline()?;
        match map_err(self.with_view(|v| v.get_stored_resource(id)))? {
            Some(r) => Ok(r.into_pyobject(py)?.unbind()),
            None => Ok(py.None()),
        }
    }

    #[pyo3(signature = (id=None))]
    fn get_stored_resource_id(&self, py: Python, id: Option<i32>) -> PyResult<PyObject> {
        self.check_deadline()?;
        match map_err(self.with_view(|v| v.get_stored_resource_id(id)))? {
            Some(rid) => Ok(rid.into_pyobject(py)?.unbind().into()),
            None => Ok(py.None()),
        }
    }

    fn get_tile_env(&self, py: Python, pos: Pos) -> PyResult<PyObject> {
        self.check_deadline()?;
        let env = map_err(self.with_view(|v| v.get_tile_env(pos)))?;
        Ok(env.into_pyobject(py)?.unbind())
    }

    fn get_tile_building_id(&self, pos: Pos) -> PyResult<Option<i32>> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_tile_building_id(pos)))
    }

    fn get_tile_builder_bot_id(&self, pos: Pos) -> PyResult<Option<i32>> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_tile_builder_bot_id(pos)))
    }

    fn is_tile_empty(&self, pos: Pos) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.is_tile_empty(pos)))
    }

    fn is_tile_passable(&self, pos: Pos) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.is_tile_passable(pos)))
    }

    fn is_in_vision(&self, pos: Pos) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.is_in_vision(pos)))
    }

    fn get_map_width(&self) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_map_width()))
    }

    fn get_map_height(&self) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_map_height()))
    }

    fn get_current_round(&self) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_current_round()))
    }

    fn get_cpu_time_elapsed(&self) -> PyResult<u64> {
        self.check_deadline()?;
        let elapsed_ns = crate::runner::thread_cpu_time_ns()
            .saturating_sub(crate::runner::CPU_START_NS.load(std::sync::atomic::Ordering::Relaxed));
        Ok(elapsed_ns / 1_000)
    }

    fn get_global_resources(&self) -> PyResult<(i32, i32)> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_global_resources()))
    }

    fn get_scale_percent(&self) -> PyResult<f64> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_scale_percent()))
    }

    fn get_unit_count(&self) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_unit_count()))
    }

    fn get_conveyor_cost(&self) -> PyResult<(i32, i32)> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_conveyor_cost()))
    }

    fn get_splitter_cost(&self) -> PyResult<(i32, i32)> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_splitter_cost()))
    }

    fn get_bridge_cost(&self) -> PyResult<(i32, i32)> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_bridge_cost()))
    }

    fn get_armoured_conveyor_cost(&self) -> PyResult<(i32, i32)> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_armoured_conveyor_cost()))
    }

    fn get_harvester_cost(&self) -> PyResult<(i32, i32)> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_harvester_cost()))
    }

    fn get_road_cost(&self) -> PyResult<(i32, i32)> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_road_cost()))
    }

    fn get_barrier_cost(&self) -> PyResult<(i32, i32)> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_barrier_cost()))
    }

    fn get_gunner_cost(&self) -> PyResult<(i32, i32)> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_gunner_cost()))
    }

    fn get_sentinel_cost(&self) -> PyResult<(i32, i32)> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_sentinel_cost()))
    }

    fn get_breach_cost(&self) -> PyResult<(i32, i32)> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_breach_cost()))
    }

    fn get_launcher_cost(&self) -> PyResult<(i32, i32)> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_launcher_cost()))
    }

    fn get_foundry_cost(&self) -> PyResult<(i32, i32)> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_foundry_cost()))
    }

    fn get_builder_bot_cost(&self) -> PyResult<(i32, i32)> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_builder_bot_cost()))
    }

    fn r#move(&self, direction: Direction) -> PyResult<()> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.move_(direction)))
    }

    fn can_move(&self, direction: Direction) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_move(direction)))
    }

    fn can_build_conveyor(&self, position: Pos, direction: Direction) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_build_conveyor(position, direction)))
    }

    fn can_build_splitter(&self, position: Pos, direction: Direction) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_build_splitter(position, direction)))
    }

    fn can_build_bridge(&self, position: Pos, target: Pos) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_build_bridge(position, target)))
    }

    fn can_build_armoured_conveyor(&self, position: Pos, direction: Direction) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_build_armoured_conveyor(position, direction)))
    }

    fn can_build_harvester(&self, position: Pos) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_build_harvester(position)))
    }

    fn can_build_road(&self, position: Pos) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_build_road(position)))
    }

    fn can_build_barrier(&self, position: Pos) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_build_barrier(position)))
    }

    fn can_build_gunner(&self, position: Pos, direction: Direction) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_build_gunner(position, direction)))
    }

    fn can_build_sentinel(&self, position: Pos, direction: Direction) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_build_sentinel(position, direction)))
    }

    fn can_build_breach(&self, position: Pos, direction: Direction) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_build_breach(position, direction)))
    }

    fn can_build_launcher(&self, position: Pos) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_build_launcher(position)))
    }

    fn can_build_foundry(&self, position: Pos) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_build_foundry(position)))
    }

    fn build_conveyor(&self, position: Pos, direction: Direction) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.build_conveyor(position, direction)))
    }

    fn build_splitter(&self, position: Pos, direction: Direction) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.build_splitter(position, direction)))
    }

    fn build_bridge(&self, position: Pos, target: Pos) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.build_bridge(position, target)))
    }

    fn build_armoured_conveyor(&self, position: Pos, direction: Direction) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.build_armoured_conveyor(position, direction)))
    }

    fn build_harvester(&self, position: Pos) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.build_harvester(position)))
    }

    fn build_road(&self, position: Pos) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.build_road(position)))
    }

    fn build_barrier(&self, position: Pos) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.build_barrier(position)))
    }

    fn build_gunner(&self, position: Pos, direction: Direction) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.build_gunner(position, direction)))
    }

    fn build_sentinel(&self, position: Pos, direction: Direction) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.build_sentinel(position, direction)))
    }

    fn build_breach(&self, position: Pos, direction: Direction) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.build_breach(position, direction)))
    }

    fn build_launcher(&self, position: Pos) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.build_launcher(position)))
    }

    fn build_foundry(&self, position: Pos) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.build_foundry(position)))
    }

    fn can_destroy(&self, building_pos: Pos) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_destroy(building_pos)))
    }

    fn destroy(&self, building_pos: Pos) -> PyResult<()> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.destroy(building_pos)))
    }

    fn heal(&self, position: Pos) -> PyResult<()> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.heal(position)))
    }

    fn can_heal(&self, position: Pos) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_heal(position)))
    }

    fn self_destruct(&self) -> PyResult<()> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.self_destruct()))?;
        Err(pyo3::exceptions::PySystemExit::new_err(()))
    }

    /// Forfeit the game with an optional message (max 500 chars). Per
    /// `docs/api/controller.md` `resign(message=None)`.
    #[pyo3(signature = (message=None))]
    fn resign(&self, message: Option<String>) -> PyResult<()> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.resign(message)))?;
        Err(pyo3::exceptions::PySystemExit::new_err(()))
    }

    fn can_place_marker(&self, position: Pos) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_place_marker(position)))
    }

    fn place_marker(&self, position: Pos, value: u32) -> PyResult<()> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.place_marker(position, value)))
    }

    fn get_marker_value(&self, id: i32) -> PyResult<u32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_marker_value(id)))
    }

    fn get_gunner_target(&self, py: Python) -> PyResult<PyObject> {
        self.check_deadline()?;
        match map_err(self.with_view(|v| v.get_gunner_target()))? {
            Some(pos) => Ok(pos.into_pyobject(py)?.unbind()),
            None => Ok(py.None()),
        }
    }

    fn can_fire(&self, target: Pos) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_fire(target)))
    }

    fn fire(&self, target: Pos) -> PyResult<()> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.fire(target)))
    }

    fn can_launch(&self, bot_pos: Pos, target: Pos) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_launch(bot_pos, target)))
    }

    fn launch(&self, bot_pos: Pos, target: Pos) -> PyResult<()> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.launch(bot_pos, target)))
    }

    fn spawn_builder(&self, position: Pos) -> PyResult<i32> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.spawn_builder(position)))
    }

    #[pyo3(signature = (dist_sq=None))]
    fn get_nearby_tiles(&self, dist_sq: Option<i32>) -> PyResult<Vec<Pos>> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_nearby_tiles(dist_sq)))
    }

    #[pyo3(signature = (dist_sq=None))]
    fn get_nearby_entities(&self, dist_sq: Option<i32>) -> PyResult<Vec<i32>> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_nearby_entities(dist_sq)))
    }

    #[pyo3(signature = (dist_sq=None))]
    fn get_nearby_buildings(&self, dist_sq: Option<i32>) -> PyResult<Vec<i32>> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_nearby_buildings(dist_sq)))
    }

    #[pyo3(signature = (dist_sq=None))]
    fn get_nearby_units(&self, dist_sq: Option<i32>) -> PyResult<Vec<i32>> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.get_nearby_units(dist_sq)))
    }

    fn can_spawn(&self, position: Pos) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_spawn(position)))
    }

    fn draw_indicator_line(&self, pos_a: Pos, pos_b: Pos, r: i32, g: i32, b: i32) -> PyResult<()> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.draw_indicator_line(pos_a, pos_b, r, g, b)))
    }

    fn draw_indicator_dot(&self, pos: Pos, r: i32, g: i32, b: i32) -> PyResult<()> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.draw_indicator_dot(pos, r, g, b)))
    }

    /// Convert refined axionite into titanium (4 Ti per Ax). Only valid
    /// on cores. Per `docs/api/controller.md` `convert(amount)`.
    fn convert(&self, amount: i32) -> PyResult<()> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.convert(amount)))
    }

    /// Whether this gunner can rotate to `direction` this turn.
    fn can_rotate(&self, direction: Direction) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_rotate(direction)))
    }

    fn rotate(&self, direction: Direction) -> PyResult<()> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.rotate(direction)))
    }

    /// Hypothetical-fire test for a turret at `position` facing `direction`.
    /// Used by bots planning where to place new turrets.
    fn can_fire_from(
        &self,
        position: Pos,
        direction: Direction,
        turret_type: EntityType,
        target: Pos,
    ) -> PyResult<bool> {
        self.check_deadline()?;
        map_err(self.with_view(|v| v.can_fire_from(position, direction, turret_type, target)))
    }

    /// Raw geometric attack pattern of THIS turret.
    fn get_attackable_tiles(&self, py: Python) -> PyResult<PyObject> {
        self.check_deadline()?;
        let tiles = map_err(self.with_view(|v| v.get_attackable_tiles()))?;
        Ok(tiles.into_pyobject(py)?.unbind())
    }

    /// Raw geometric attack pattern of a hypothetical turret.
    fn get_attackable_tiles_from(
        &self,
        py: Python,
        position: Pos,
        direction: Direction,
        turret_type: EntityType,
    ) -> PyResult<PyObject> {
        self.check_deadline()?;
        let tiles = map_err(
            self.with_view(|v| v.get_attackable_tiles_from(position, direction, turret_type)),
        )?;
        Ok(tiles.into_pyobject(py)?.unbind())
    }

    /// Generic `can_build(entity_type, position, extra)` dispatch. `extra`
    /// is a Direction for directional buildings/turrets, a target Position
    /// for bridge, and unused otherwise.
    #[pyo3(signature = (entity_type, position, extra=None))]
    fn can_build(
        &self,
        py: Python,
        entity_type: EntityType,
        position: Pos,
        extra: Option<PyObject>,
    ) -> PyResult<bool> {
        self.check_deadline()?;
        let extra = extract_build_extra(py, extra)?;
        map_err(self.with_view(|v| v.can_build(entity_type, position, extra)))
    }

    #[pyo3(signature = (entity_type, position, extra=None))]
    fn build(
        &self,
        py: Python,
        entity_type: EntityType,
        position: Pos,
        extra: Option<PyObject>,
    ) -> PyResult<i32> {
        self.check_deadline()?;
        let extra = extract_build_extra(py, extra)?;
        map_err(self.with_view(|v| v.build(entity_type, position, extra)))
    }
}

/// Extract `BuildExtra` from a Python `Direction | Position | None`.
/// Tries `Direction` first, then `Position`. The dispatch into `UnitView`
/// validates whether the extracted variant matches what the entity type
/// requires.
fn extract_build_extra(py: Python, extra: Option<PyObject>) -> PyResult<BuildExtra> {
    let Some(extra) = extra else {
        return Ok(BuildExtra::None);
    };
    if let Ok(d) = extra.extract::<Direction>(py) {
        return Ok(BuildExtra::Direction(d));
    }
    if let Ok(p) = extra.extract::<Pos>(py) {
        return Ok(BuildExtra::Position(p));
    }
    Err(game_error("extra must be a Direction, Position, or None"))
}

#[pymodule]
pub fn controller_mod(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Controller>()?;
    Ok(())
}
