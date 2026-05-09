use std::fs;
use std::path::Path;

use cambc_libre_engine::common::{Direction, Pos};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Kind {
    Conveyor,
    Splitter,
    ArmouredConveyor,
    Bridge,
    Harvester,
    Foundry,
    Road,
    Barrier,
}

#[derive(Debug, Clone)]
pub struct Placement {
    pub pos: Pos,
    pub kind: Kind,
    pub direction: Option<Direction>,
    pub bridge_target: Option<Pos>,
    pub line: usize,
}

#[derive(Debug)]
pub struct ParseError {
    pub line: usize,
    pub message: String,
}

impl std::fmt::Display for ParseError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "line {}: {}", self.line, self.message)
    }
}

impl std::error::Error for ParseError {}

pub fn load(path: &Path) -> Result<Vec<Placement>, Box<dyn std::error::Error>> {
    let text = fs::read_to_string(path)?;
    parse(&text).map_err(Into::into)
}

pub fn parse(text: &str) -> Result<Vec<Placement>, ParseError> {
    let mut out = Vec::new();
    for (i, raw) in text.lines().enumerate() {
        let line_no = i + 1;
        let line = raw.split('#').next().unwrap_or("").trim();
        if line.is_empty() {
            continue;
        }
        if line.starts_with("map:") {
            continue;
        }
        out.push(parse_line(line_no, line)?);
    }
    Ok(out)
}

fn parse_line(line_no: usize, line: &str) -> Result<Placement, ParseError> {
    let mut tokens = line.split_whitespace();
    let x = next_i32(line_no, &mut tokens, "x")?;
    let y = next_i32(line_no, &mut tokens, "y")?;
    let kind_token = tokens
        .next()
        .ok_or_else(|| err(line_no, "missing entity"))?;
    let kind = parse_kind(line_no, kind_token)?;

    let mut direction = None;
    let mut bridge_target = None;
    for tok in tokens {
        if let Some(rest) = tok.strip_prefix("dir=") {
            direction = Some(parse_direction(line_no, rest)?);
        } else if let Some(rest) = tok.strip_prefix("bridge=") {
            bridge_target = Some(parse_pos(line_no, rest)?);
        } else {
            return Err(err(line_no, format!("unknown token {tok:?}")));
        }
    }

    match kind {
        Kind::Conveyor | Kind::Splitter | Kind::ArmouredConveyor => {
            if direction.is_none() {
                return Err(err(line_no, format!("{kind:?} requires dir=...")));
            }
        }
        Kind::Bridge => {
            if bridge_target.is_none() {
                return Err(err(line_no, "bridge requires bridge=x,y"));
            }
        }
        _ => {}
    }

    Ok(Placement {
        pos: Pos { x, y },
        kind,
        direction,
        bridge_target,
        line: line_no,
    })
}

fn next_i32<'a>(
    line_no: usize,
    it: &mut impl Iterator<Item = &'a str>,
    label: &str,
) -> Result<i32, ParseError> {
    let tok = it
        .next()
        .ok_or_else(|| err(line_no, format!("missing {label}")))?;
    tok.parse::<i32>()
        .map_err(|_| err(line_no, format!("bad {label}: {tok:?}")))
}

fn parse_pos(line_no: usize, s: &str) -> Result<Pos, ParseError> {
    let (a, b) = s
        .split_once(',')
        .ok_or_else(|| err(line_no, format!("expected x,y, got {s:?}")))?;
    let x = a
        .parse::<i32>()
        .map_err(|_| err(line_no, format!("bad x in {s:?}")))?;
    let y = b
        .parse::<i32>()
        .map_err(|_| err(line_no, format!("bad y in {s:?}")))?;
    Ok(Pos { x, y })
}

fn parse_kind(line_no: usize, s: &str) -> Result<Kind, ParseError> {
    Ok(match s {
        "CONVEYOR" => Kind::Conveyor,
        "SPLITTER" => Kind::Splitter,
        "ARMOURED_CONVEYOR" => Kind::ArmouredConveyor,
        "BRIDGE" => Kind::Bridge,
        "HARVESTER" => Kind::Harvester,
        "FOUNDRY" => Kind::Foundry,
        "ROAD" => Kind::Road,
        "BARRIER" => Kind::Barrier,
        other => return Err(err(line_no, format!("unknown entity {other:?}"))),
    })
}

fn parse_direction(line_no: usize, s: &str) -> Result<Direction, ParseError> {
    Ok(match s {
        "NORTH" => Direction::North,
        "NORTHEAST" => Direction::Northeast,
        "EAST" => Direction::East,
        "SOUTHEAST" => Direction::Southeast,
        "SOUTH" => Direction::South,
        "SOUTHWEST" => Direction::Southwest,
        "WEST" => Direction::West,
        "NORTHWEST" => Direction::Northwest,
        other => return Err(err(line_no, format!("unknown direction {other:?}"))),
    })
}

fn err(line_no: usize, message: impl Into<String>) -> ParseError {
    ParseError {
        line: line_no,
        message: message.into(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_pong() {
        let path = Path::new("../../maps/blueprints/pong.bp");
        let placements = load(path).expect("parse pong.bp");
        assert!(!placements.is_empty());
        let foundries = placements
            .iter()
            .filter(|p| p.kind == Kind::Foundry)
            .count();
        let harvesters = placements
            .iter()
            .filter(|p| p.kind == Kind::Harvester)
            .count();
        let bridges = placements.iter().filter(|p| p.kind == Kind::Bridge).count();
        assert!(foundries > 0, "no foundries parsed");
        assert!(harvesters > 0, "no harvesters parsed");
        assert!(bridges > 0, "no bridges parsed");
    }

    #[test]
    fn rejects_bridge_without_target() {
        let r = parse("0 0 BRIDGE\n");
        assert!(r.is_err());
    }

    #[test]
    fn rejects_conveyor_without_dir() {
        let r = parse("0 0 CONVEYOR\n");
        assert!(r.is_err());
    }
}
