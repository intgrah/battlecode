//! Per-turn patrol bookkeeping. Refresh `last_seen[i]` for tiles in
//! our own vision plus (transitively) the vision disc of one trusted
//! friendly builder — chosen as the farthest visible friend, since its
//! vision disc is maximally disjoint from ours and so contributes the
//! most fresh information per offset enumerated.

use serde_json::{Map, Value};

use crate::builder::Builder;
use crate::util::constants::MAX_WIDTH;
use crate::util::debug::debug as log;
use crate::util::visualiser::auto_wrap_position;

pub fn update_patrol(builder: &mut Builder) {
    let rnd = builder.state.round;

    let mut own_count: i32 = 0;
    let nearby = pyrust::clone!(builder.state.nearby_tiles);
    for pos in &nearby {
        builder.last_seen[(pos.y as usize) * MAX_WIDTH + (pos.x as usize)] = rnd;
        own_count += 1;
    }

    if builder.state.friendly_bots.is_empty() {
        let mut args = Map::new();
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("n"),
            Value::Number(own_count.into())
        );
        log(
            "patrol: refreshed {n} own-vision tiles, no friends in vision",
            args,
        );
        return;
    }

    let my_pos = builder.state.my_pos;
    let mx = my_pos.x;
    let my = my_pos.y;
    // Maximise distance, breaking ties by (y, x) lex. Encoded as a tuple
    // to be MINIMISED: (-d, y, x). Deterministic across runs regardless
    // of HashSet iteration order.
    let mut best_key: (i32, i32, i32) = (1, 1 << 30, 1 << 30);
    let mut best_pos = None;
    let friends: Vec<_> =
        pyrust::collect!(pyrust::copied!(pyrust::iter!(builder.state.friendly_bots)));
    for f in &friends {
        let d = (f.x - mx) * (f.x - mx) + (f.y - my) * (f.y - my);
        let key = (-d, f.y, f.x);
        if key < best_key {
            best_key = key;
            best_pos = Some(*f);
        }
    }
    let best_d = -best_key.0;
    let Some(best) = best_pos else {
        let mut args = Map::new();
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("n"),
            Value::Number(own_count.into())
        );
        log(
            "patrol: refreshed {n} own-vision tiles, no farthest friend selected",
            args,
        );
        return;
    };

    let fx = best.x;
    let fy = best.y;
    let w = builder.state.width;
    let h = builder.state.height;
    let base = fy * (MAX_WIDTH as i32) + fx;
    let mut transitive_count: i32 = 0;
    let offsets: Vec<(i32, i32, i32)> = pyrust::clone!(builder._vision_offsets);
    if pyrust::vec::contains!((4..(w - 4)), &fx) && pyrust::vec::contains!((4..(h - 4)), &fy) {
        for (_, _, off) in &offsets {
            builder.last_seen[(base + off) as usize] = rnd;
            transitive_count += 1;
        }
    } else {
        for (dx, dy, off) in &offsets {
            let nx = fx + dx;
            let ny = fy + dy;
            if pyrust::vec::contains!((0..w), &nx) && pyrust::vec::contains!((0..h), &ny) {
                builder.last_seen[(base + off) as usize] = rnd;
                transitive_count += 1;
            }
        }
    }
    let nf = pyrust::len!(friends) as i64;
    let mut args = Map::new();
    pyrust::dict::insert!(
        args,
        pyrust::to_string!("own"),
        Value::Number(own_count.into())
    );
    pyrust::dict::insert!(
        args,
        pyrust::to_string!("trans"),
        Value::Number(transitive_count.into())
    );
    pyrust::dict::insert!(args, pyrust::to_string!("friend"), auto_wrap_position(best));
    pyrust::dict::insert!(args, pyrust::to_string!("d"), Value::Number(best_d.into()));
    pyrust::dict::insert!(args, pyrust::to_string!("nf"), Value::Number(nf.into()));
    log(
        "patrol: refreshed own={own} + transitive={trans} via farthest friend \
         {friend} (d²={d}, total friends={nf})",
        args,
    );
}
