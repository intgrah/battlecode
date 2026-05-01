//! Translation of `bots/intgrah/v54.7.9/builder/tasks/defense/stalk_enemy.py`.
//!
//! Stalk a visible enemy builder when this bot is the closest friendly
//! to it. Pure follow — no firing. Cheap structural pressure: an enemy bot
//! shadowed by ours can't safely commit to a build action without taking
//! fire from our turret network, and any reposition the enemy makes is
//! mirrored.

use cambc::{Controller, Position};
use serde_json::Map;

use crate::builder::Builder;
use crate::builder::helpers::make_move;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::debug::debug as log;
use crate::util::visualiser::auto_wrap_position;

pub fn stalk_enemy(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if self_.enemy_bots.is_empty() {
        return Err(TaskRejected::new("no enemy builder in vision"));
    }

    let my_pos = self_.my_pos;
    let mut target: Option<Position> = None;
    let mut best_key: (i32, i32, i32) = (1 << 30, 0, 0);
    for &e in &self_.enemy_bots {
        let my_d = (e.x - my_pos.x) * (e.x - my_pos.x) + (e.y - my_pos.y) * (e.y - my_pos.y);
        let mut closer_friend = false;
        for &f in &self_.friendly_bots {
            let fd = (e.x - f.x) * (e.x - f.x) + (e.y - f.y) * (e.y - f.y);
            if fd < my_d {
                closer_friend = true;
                break;
            }
        }
        if closer_friend {
            continue;
        }
        let key = (my_d, e.y, e.x);
        if key < best_key {
            best_key = key;
            target = Some(e);
        }
    }
    let target_d = best_key.0;

    let Some(target) = target else {
        return Err(TaskRejected::new(
            "another friendly builder is closer to every visible enemy",
        ));
    };

    let mut args = Map::new();
    args.insert("target".to_string(), auto_wrap_position(target));
    args.insert("d".to_string(), serde_json::Value::Number(target_d.into()));
    log("stalk_enemy: following {target} (d²={d})", args);
    make_move(self_, ct, target);
    Ok(())
}
