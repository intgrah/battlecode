use cambc_proto as proto;
use libre_engine::common::{Direction, Environment, Pos, ResourceType, Team};
use libre_engine::game_map::{Entity, PlayerState};
use libre_engine::replay_diff::GameDiff;

pub trait ToProto {
    type Output;
    fn to_proto(&self) -> Self::Output;
}

#[must_use] 
pub fn build_proto_map(environment: &[Vec<Environment>], cores: &[(Pos, Team)]) -> proto::Map {
    let height = environment.len() as i32;
    let width = environment.first().map_or(0, std::vec::Vec::len) as i32;
    let rows = environment
        .iter()
        .map(|row| proto::TileRow {
            tiles: row.iter().map(ToProto::to_proto).collect(),
        })
        .collect();
    let cores = cores
        .iter()
        .enumerate()
        .map(|(id, (pos, team))| proto::CorePosition {
            id: id as i32 + 1,
            team: team.to_proto(),
            position: Some(pos.to_proto()),
        })
        .collect();
    proto::Map {
        width,
        height,
        rows,
        cores,
    }
}

impl ToProto for [PlayerState; 2] {
    type Output = proto::Players;

    fn to_proto(&self) -> Self::Output {
        proto::Players {
            a: Some(self[0].to_proto()),
            b: Some(self[1].to_proto()),
        }
    }
}

impl ToProto for PlayerState {
    type Output = proto::Player;

    fn to_proto(&self) -> Self::Output {
        proto::Player {
            titanium: self.titanium,
            axionite: self.axionite,
            // Total resources collected (Ti + Ax). Verified against the
            // cambc 1.7.1 binary's UpdatePlayers messages.
            resources_collected: self.titanium_collected + self.axionite_collected,
            titanium_collected: self.titanium_collected,
            axionite_collected: self.axionite_collected,
        }
    }
}

impl ToProto for [GameDiff] {
    type Output = proto::Turn;

    fn to_proto(&self) -> Self::Output {
        proto::Turn {
            updates: self.iter().map(ToProto::to_proto).collect(),
        }
    }
}

impl ToProto for GameDiff {
    type Output = proto::Update;

    fn to_proto(&self) -> Self::Output {
        match self {
            Self::PlaceEntity { entity, .. } => proto::Update {
                kind: Some(proto::update::Kind::PlaceEntity(proto::PlaceEntity {
                    entity: Some(entity.to_proto()),
                })),
            },
            Self::MoveBuilderBot { id, to } => proto::Update {
                kind: Some(proto::update::Kind::MoveBuilderBot(proto::MoveBuilderBot {
                    id: *id,
                    to: Some(to.to_proto()),
                })),
            },
            Self::RemoveEntity { id } => proto::Update {
                kind: Some(proto::update::Kind::RemoveEntity(proto::RemoveEntity {
                    id: *id,
                })),
            },
            Self::DistributeResources { moves } => proto::Update {
                kind: Some(proto::update::Kind::DistributeResources(
                    proto::DistributeResources {
                        moves: moves
                            .iter()
                            .map(|(from, to, resource_id)| proto::ResourceMove {
                                from: Some(from.to_proto()),
                                to: Some(to.to_proto()),
                                resource_id: Some(*resource_id),
                            })
                            .collect(),
                    },
                )),
            },
            Self::UpdateHp { id, delta } => proto::Update {
                kind: Some(proto::update::Kind::UpdateHp(proto::UpdateHp {
                    id: *id,
                    delta: *delta,
                })),
            },
            Self::UpdatePlayers { players } => proto::Update {
                kind: Some(proto::update::Kind::UpdatePlayers(proto::UpdatePlayers {
                    players: Some(players.to_proto()),
                })),
            },
            Self::SetActionCooldown { id, value } => proto::Update {
                kind: Some(proto::update::Kind::SetActionCooldown(
                    proto::SetActionCooldown {
                        id: *id,
                        value: *value,
                    },
                )),
            },
            Self::SetMoveCooldown { id, value } => proto::Update {
                kind: Some(proto::update::Kind::SetMoveCooldown(
                    proto::SetMoveCooldown {
                        id: *id,
                        value: *value,
                    },
                )),
            },
            Self::BotOutput {
                id,
                stdout,
                exec_time_us,
                tled,
            } => proto::Update {
                kind: Some(proto::update::Kind::BotOutput(proto::BotOutput {
                    id: *id,
                    stdout: stdout.clone(),
                    exec_time_us: *exec_time_us,
                    tled: *tled,
                })),
            },
            Self::IndicatorLine {
                id,
                pos_a,
                pos_b,
                r,
                g,
                b,
            } => proto::Update {
                kind: Some(proto::update::Kind::IndicatorLine(proto::IndicatorLine {
                    id: *id,
                    pos_a: Some(pos_a.to_proto()),
                    pos_b: Some(pos_b.to_proto()),
                    r: *r,
                    g: *g,
                    b: *b,
                })),
            },
            Self::IndicatorDot { id, pos, r, g, b } => proto::Update {
                kind: Some(proto::update::Kind::IndicatorDot(proto::IndicatorDot {
                    id: *id,
                    pos: Some(pos.to_proto()),
                    r: *r,
                    g: *g,
                    b: *b,
                })),
            },
            Self::FireTurret { from, to } => proto::Update {
                kind: Some(proto::update::Kind::FireTurret(proto::FireTurret {
                    from: Some(from.to_proto()),
                    to: Some(to.to_proto()),
                })),
            },
            Self::BuilderAttack { id } => proto::Update {
                kind: Some(proto::update::Kind::BuilderAttack(proto::BuilderAttack {
                    id: *id,
                })),
            },
        }
    }
}

impl ToProto for Entity {
    type Output = proto::Entity;

    fn to_proto(&self) -> Self::Output {
        let mut proto_entity = proto::Entity {
            id: self.id,
            team: self.team.to_proto(),
            position: Some(self.position.to_proto()),
            hp: self.hp,
            max_hp: self.max_hp,
            kind: None,
        };
        proto_entity.kind = Some(match self {
            Self::BuilderBot(bot) => proto::entity::Kind::BuilderBot(proto::BuilderBot {
                action_cooldown: bot.action_cooldown,
                move_cooldown: bot.move_cooldown,
            }),
            Self::Conveyor(conveyor) => proto::entity::Kind::Conveyor(proto::Conveyor {
                direction: conveyor.direction.to_proto(),
                stored: conveyor.stored.to_proto(),
            }),
            Self::Splitter(splitter) => proto::entity::Kind::Splitter(proto::Splitter {
                direction: splitter.direction.to_proto(),
                stored: splitter.stored.to_proto(),
            }),
            Self::ArmouredConveyor(conveyor) => {
                proto::entity::Kind::ArmouredConveyor(proto::ArmouredConveyor {
                    direction: conveyor.direction.to_proto(),
                    stored: conveyor.stored.to_proto(),
                })
            }
            Self::Bridge(bridge) => proto::entity::Kind::Bridge(proto::Bridge {
                target: Some(bridge.target.to_proto()),
                stored: bridge.stored.to_proto(),
            }),
            Self::Harvester(harvester) => proto::entity::Kind::Harvester(proto::Harvester {
                cooldown: harvester.cooldown,
                resource_type: Some(harvester.resource_type).to_proto(),
            }),
            Self::Foundry(foundry) => proto::entity::Kind::Foundry(proto::Foundry {
                stored: foundry.stored.to_proto(),
            }),
            Self::Road(_) => proto::entity::Kind::Road(proto::Road {}),
            Self::Barrier(_) => proto::entity::Kind::Barrier(proto::Barrier {}),
            Self::Marker(marker) => proto::entity::Kind::Marker(proto::Marker {
                value: marker.value,
            }),
            Self::Core(core) => proto::entity::Kind::Core(proto::Core {
                action_cooldown: core.action_cooldown,
            }),
            Self::Gunner(gunner) => proto::entity::Kind::Gunner(proto::Gunner {
                direction: gunner.direction.to_proto(),
                ammo_type: gunner.ammo_type.to_proto(),
                ammo_amount: gunner.ammo_amount,
            }),
            Self::Sentinel(sentinel) => proto::entity::Kind::Sentinel(proto::Sentinel {
                direction: sentinel.direction.to_proto(),
                ammo_type: sentinel.ammo_type.to_proto(),
                ammo_amount: sentinel.ammo_amount,
            }),
            Self::Breach(breach) => proto::entity::Kind::Breach(proto::Breach {
                direction: breach.direction.to_proto(),
                ammo_type: breach.ammo_type.to_proto(),
                ammo_amount: breach.ammo_amount,
            }),
            Self::Launcher(launcher) => proto::entity::Kind::Launcher(proto::Launcher {
                ammo_type: launcher.ammo_type.to_proto(),
                ammo_amount: launcher.ammo_amount,
            }),
        });
        proto_entity
    }
}

impl ToProto for Pos {
    type Output = proto::Pos;

    fn to_proto(&self) -> Self::Output {
        proto::Pos {
            x: self.x,
            y: self.y,
        }
    }
}

impl ToProto for Team {
    type Output = i32;

    fn to_proto(&self) -> Self::Output {
        match self {
            Self::A => proto::Team::A as i32,
            Self::B => proto::Team::B as i32,
        }
    }
}

impl ToProto for Direction {
    type Output = i32;

    fn to_proto(&self) -> Self::Output {
        match self {
            Self::Centre => proto::Direction::DirCentre as i32,
            Self::North => proto::Direction::DirNorth as i32,
            Self::Northeast => proto::Direction::DirNortheast as i32,
            Self::East => proto::Direction::DirEast as i32,
            Self::Southeast => proto::Direction::DirSoutheast as i32,
            Self::South => proto::Direction::DirSouth as i32,
            Self::Southwest => proto::Direction::DirSouthwest as i32,
            Self::West => proto::Direction::DirWest as i32,
            Self::Northwest => proto::Direction::DirNorthwest as i32,
        }
    }
}

impl ToProto for Option<ResourceType> {
    type Output = i32;

    fn to_proto(&self) -> Self::Output {
        match self {
            None => proto::ResourceType::ResourceNone as i32,
            Some(ResourceType::Titanium) => proto::ResourceType::ResourceTitanium as i32,
            Some(ResourceType::RawAxionite) => proto::ResourceType::ResourceRawAxionite as i32,
            Some(ResourceType::RefinedAxionite) => {
                proto::ResourceType::ResourceRefinedAxionite as i32
            }
        }
    }
}

impl ToProto for Environment {
    type Output = i32;

    fn to_proto(&self) -> Self::Output {
        match self {
            Self::Empty => proto::Environment::EnvEmpty as i32,
            Self::Wall => proto::Environment::EnvWall as i32,
            Self::OreTitanium => proto::Environment::EnvOreTitanium as i32,
            Self::OreAxionite => proto::Environment::EnvOreAxionite as i32,
        }
    }
}
