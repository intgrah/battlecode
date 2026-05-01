use std::fs;
use std::io;
use std::path::Path;

use prost::Message;

use libre_engine::common::Team;
use libre_engine::replay_diff::ReplayRecorder;

use crate::conversions::{ToProto, build_proto_map};

/// Build the protobuf `Replay` corresponding to `recorder`'s recorded
/// turns plus an optional declared winner.
pub fn build_replay(recorder: &ReplayRecorder, winner: Option<Team>) -> cambc_proto::Replay {
    let map = build_proto_map(recorder.environment(), recorder.cores());
    let turns = recorder
        .turns()
        .iter()
        .map(|turn| turn.as_slice().to_proto())
        .collect();
    cambc_proto::Replay {
        map: Some(map),
        turns,
        winner: winner.map(|team| team.to_proto()),
    }
}

/// Serialize and write the recorder's replay to `path`. Creates parent
/// directories if needed.
pub fn write_replay(recorder: &ReplayRecorder, path: &str, winner: Option<Team>) -> io::Result<()> {
    let replay = build_replay(recorder, winner);
    let mut buf = Vec::new();
    replay
        .encode(&mut buf)
        .map_err(|err| io::Error::other(err.to_string()))?;
    if let Some(parent) = Path::new(path).parent()
        && !parent.as_os_str().is_empty() {
            fs::create_dir_all(parent)?;
        }
    fs::write(path, buf)
}
