use crossterm::event::{KeyCode, KeyEvent, KeyModifiers, MouseButton, MouseEvent, MouseEventKind};
use ratatui::{
    prelude::*,
    widgets::{Block, Borders, Gauge, Paragraph, Wrap},
};

use crate::kitty;
use crate::proto;
use crate::renderer;
use crate::sprites::SpriteAtlas;
use crate::state::{Entity, EntityKind, GameState};

pub struct App {
    game: GameState,
    atlas: SpriteAtlas,
    turn: usize,
    pub playing: bool,
    speed: i32,
    cursor: (i32, i32),
    selected_entity: Option<i32>,
    show_indicators: bool,
    show_network: bool,
    show_vision: bool,
    show_help: bool,
    follow_entity: bool,
    needs_redraw: bool,
    map_area: Option<Rect>,
    scrubber_area: Option<Rect>,
}

impl App {
    pub fn new(replay: proto::Replay, atlas: SpriteAtlas) -> Self {
        let game = GameState::from_replay(&replay);
        Self {
            game,
            atlas,
            turn: 0,
            playing: false,
            speed: 0,
            cursor: (0, 0),
            selected_entity: None,
            show_indicators: false,
            show_network: false,
            show_vision: false,
            show_help: false,
            follow_entity: false,
            needs_redraw: true,
            map_area: None,
            scrubber_area: None,
        }
    }

    pub const fn tick_ms(&self) -> u64 {
        500 / (1u64 << self.speed as u64)
    }

    pub const fn speed_label(&self) -> u32 {
        1 << self.speed as u32
    }

    pub fn step_forward(&mut self, n: usize) {
        let old = self.turn;
        self.turn = (self.turn + n).min(self.game.turn_count());
        if self.turn >= self.game.turn_count() {
            self.playing = false;
        }
        if self.turn != old {
            self.needs_redraw = true;
        }
    }

    fn step_backward(&mut self, n: usize) {
        let old = self.turn;
        self.turn = self.turn.saturating_sub(n);
        if self.turn != old {
            self.needs_redraw = true;
        }
    }

    pub fn handle_key(&mut self, key: KeyEvent) -> bool {
        if self.show_help {
            self.show_help = false;
            return false;
        }

        let shift = key.modifiers.contains(KeyModifiers::SHIFT);
        match key.code {
            KeyCode::Char('q') | KeyCode::Esc => {
                if self.selected_entity.is_some() {
                    self.selected_entity = None;
                    self.follow_entity = false;
                    self.needs_redraw = true;
                    return false;
                }
                return true;
            }
            KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => return true,

            KeyCode::Char(' ') => self.playing = !self.playing,
            KeyCode::Right => self.step_forward(1),
            KeyCode::Left => self.step_backward(1),
            KeyCode::Char('L') | KeyCode::Char('>') => self.step_forward(10),
            KeyCode::Char('H') | KeyCode::Char('<') => self.step_backward(10),
            KeyCode::Home | KeyCode::Char('g') => {
                self.turn = 0;
                self.needs_redraw = true;
            }
            KeyCode::End | KeyCode::Char('G') => {
                self.turn = self.game.turn_count();
                self.needs_redraw = true;
            }
            KeyCode::Char('+' | '=') => self.speed = (self.speed + 1).min(8),
            KeyCode::Char('-') if !shift => self.speed = (self.speed - 1).max(0),

            KeyCode::Char('k') | KeyCode::Up => {
                self.cursor.1 = (self.cursor.1 - 1).max(0);
                self.needs_redraw = true;
            }
            KeyCode::Char('j') | KeyCode::Down => {
                self.cursor.1 = (self.cursor.1 + 1).min(self.game.height - 1);
                self.needs_redraw = true;
            }
            KeyCode::Char('h') => {
                self.cursor.0 = (self.cursor.0 - 1).max(0);
                self.needs_redraw = true;
            }
            KeyCode::Char('l') => {
                self.cursor.0 = (self.cursor.0 + 1).min(self.game.width - 1);
                self.needs_redraw = true;
            }

            KeyCode::Enter => {
                self.select_at_cursor();
                self.needs_redraw = true;
            }
            KeyCode::Tab => {
                self.cycle_entity_at_cursor();
                self.needs_redraw = true;
            }
            KeyCode::Char('f') => self.follow_entity = !self.follow_entity,

            KeyCode::Char('i') => {
                self.show_indicators = !self.show_indicators;
                self.needs_redraw = true;
            }
            KeyCode::Char('n') => {
                self.show_network = !self.show_network;
                self.needs_redraw = true;
            }
            KeyCode::Char('v') => {
                self.show_vision = !self.show_vision;
                self.needs_redraw = true;
            }
            KeyCode::Char('?') => self.show_help = true,

            KeyCode::Char(c @ '1'..='9') => {
                let frac = f64::from(c as u8 - b'0') / 10.0;
                #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
                {
                    self.turn = (frac * self.game.turn_count() as f64) as usize;
                }
                self.needs_redraw = true;
            }

            _ => {}
        }
        false
    }

    #[allow(
        clippy::cast_possible_truncation,
        clippy::cast_sign_loss,
        clippy::cast_precision_loss
    )]
    pub fn handle_mouse(&mut self, mouse: MouseEvent) {
        let col = mouse.column;
        let row = mouse.row;

        match mouse.kind {
            MouseEventKind::Down(MouseButton::Left) | MouseEventKind::Drag(MouseButton::Left) => {
                if let Some(scrub) = self.scrubber_area {
                    if row >= scrub.y
                        && row < scrub.y + scrub.height
                        && col >= scrub.x
                        && col < scrub.x + scrub.width
                    {
                        let frac = f64::from(col - scrub.x) / f64::from(scrub.width);
                        self.turn = (frac * self.game.turn_count() as f64) as usize;
                        self.turn = self.turn.min(self.game.turn_count());
                        self.needs_redraw = true;
                        return;
                    }
                }

                if matches!(mouse.kind, MouseEventKind::Down(MouseButton::Left)) {
                    if let Some(map) = self.map_area {
                        if row >= map.y
                            && row < map.y + map.height
                            && col >= map.x
                            && col < map.x + map.width
                        {
                            let ts = self.atlas.tile_size;
                            let chars_per_tile_x = ts / 2;
                            let chars_per_tile_y = ts / 4;
                            if chars_per_tile_x > 0 && chars_per_tile_y > 0 {
                                let gx = i32::from(col - map.x) / chars_per_tile_x as i32;
                                let gy = i32::from(row - map.y) / chars_per_tile_y as i32;
                                let gx = gx.clamp(0, self.game.width - 1);
                                let gy = gy.clamp(0, self.game.height - 1);
                                self.cursor = (gx, gy);
                                self.select_at_cursor();
                                self.needs_redraw = true;
                            }
                        }
                    }
                }
            }
            _ => {}
        }
    }

    fn select_at_cursor(&mut self) {
        let state = &self.game.turns[self.turn];
        self.selected_entity = state
            .entities
            .values()
            .find(|e| e.pos == (self.cursor.0, self.cursor.1))
            .map(|e| e.id);
    }

    fn cycle_entity_at_cursor(&mut self) {
        let state = &self.game.turns[self.turn];
        let at_cursor: Vec<i32> = state
            .entities
            .values()
            .filter(|e| e.pos == (self.cursor.0, self.cursor.1))
            .map(|e| e.id)
            .collect();
        if at_cursor.is_empty() {
            self.selected_entity = None;
            return;
        }
        let next = match self.selected_entity {
            Some(current) => {
                let idx = at_cursor.iter().position(|&id| id == current).unwrap_or(0);
                at_cursor[(idx + 1) % at_cursor.len()]
            }
            None => at_cursor[0],
        };
        self.selected_entity = Some(next);
    }

    pub fn render(&mut self, frame: &mut Frame) {
        if self.show_help {
            render_help(frame);
            return;
        }

        if self.follow_entity {
            if let Some(id) = self.selected_entity {
                let state = &self.game.turns[self.turn];
                if let Some(e) = state.entities.get(&id) {
                    if self.cursor != e.pos {
                        self.cursor = e.pos;
                        self.needs_redraw = true;
                    }
                }
            }
        }

        let outer =
            Layout::vertical([Constraint::Min(10), Constraint::Length(3)]).split(frame.area());

        let main =
            Layout::horizontal([Constraint::Min(20), Constraint::Length(30)]).split(outer[0]);

        self.map_area = Some(main[0]);
        self.scrubber_area = Some(outer[1]);
        self.render_info(frame, main[1]);
        self.render_scrubber(frame, outer[1]);
    }

    pub fn render_map_if_needed(&mut self) {
        if !self.needs_redraw {
            return;
        }
        let Some(area) = self.map_area else { return };
        self.needs_redraw = false;
        let turn_state = &self.game.turns[self.turn];
        let img = renderer::render_map(
            &self.game,
            turn_state,
            &self.atlas,
            self.cursor,
            self.selected_entity,
        );
        let _ = kitty::display_image(&img, 1, area.x, area.y);
    }

    fn render_info(&self, frame: &mut Frame, area: Rect) {
        let state = &self.game.turns[self.turn];

        let chunks = Layout::vertical([
            Constraint::Length(8),
            Constraint::Min(8),
            Constraint::Min(6),
        ])
        .split(area);

        let a = &state.players[0];
        let b = &state.players[1];
        let status = format!(
            "Turn: {}/{}\n\n\
             Team A: {} Ti  {} Ax\n\
             Mined:  {} Ti  {} Ax\n\n\
             Team B: {} Ti  {} Ax\n\
             Mined:  {} Ti  {} Ax",
            self.turn,
            self.game.turn_count(),
            a.titanium,
            a.axionite,
            a.ti_collected,
            a.ax_collected,
            b.titanium,
            b.axionite,
            b.ti_collected,
            b.ax_collected,
        );
        let status_widget = Paragraph::new(status)
            .block(Block::default().borders(Borders::ALL).title(" Status "))
            .wrap(Wrap { trim: false });
        frame.render_widget(status_widget, chunks[0]);

        let inspector_text = if let Some(id) = self.selected_entity {
            if let Some(e) = state.entities.get(&id) {
                format_entity_info(e)
            } else {
                format_tile_info(&self.game, self.cursor)
            }
        } else {
            format_tile_info(&self.game, self.cursor)
        };
        let inspector = Paragraph::new(inspector_text)
            .block(Block::default().borders(Borders::ALL).title(" Inspector "))
            .wrap(Wrap { trim: false });
        frame.render_widget(inspector, chunks[1]);

        let log_text: String = if let Some(id) = self.selected_entity {
            state
                .outputs
                .iter()
                .filter(|(oid, _)| *oid == id)
                .map(|(_, s)| s.as_str())
                .collect::<Vec<_>>()
                .join("\n")
        } else {
            String::new()
        };
        let log = Paragraph::new(log_text)
            .block(Block::default().borders(Borders::ALL).title(" Log "))
            .wrap(Wrap { trim: false });
        frame.render_widget(log, chunks[2]);
    }

    fn render_scrubber(&self, frame: &mut Frame, area: Rect) {
        let total = self.game.turn_count().max(1);
        #[allow(clippy::cast_precision_loss)]
        let ratio = self.turn as f64 / total as f64;
        let label = format!(
            "T{}/{} {}x {}",
            self.turn,
            total,
            self.speed_label(),
            if self.playing { "❚❚" } else { "▶" },
        );
        let gauge = Gauge::default()
            .block(Block::default().borders(Borders::ALL))
            .gauge_style(Style::default().fg(Color::Cyan))
            .ratio(ratio.min(1.0))
            .label(label);
        frame.render_widget(gauge, area);
    }
}

fn format_entity_info(e: &Entity) -> String {
    let team = match e.team {
        proto::Team::A => "A",
        proto::Team::B => "B",
    };
    let kind_name = match &e.kind {
        EntityKind::BuilderBot { .. } => "Builder Bot",
        EntityKind::Core { .. } => "Core",
        EntityKind::CoreEdge { .. } => "Core",
        EntityKind::Conveyor { .. } => "Conveyor",
        EntityKind::ArmouredConveyor { .. } => "Armoured Conv",
        EntityKind::Splitter { .. } => "Splitter",
        EntityKind::Bridge { .. } => "Bridge",
        EntityKind::Harvester { .. } => "Harvester",
        EntityKind::Foundry { .. } => "Foundry",
        EntityKind::Road => "Road",
        EntityKind::Barrier => "Barrier",
        EntityKind::Marker { .. } => "Marker",
        EntityKind::Gunner { .. } => "Gunner",
        EntityKind::Sentinel { .. } => "Sentinel",
        EntityKind::Breach { .. } => "Breach",
        EntityKind::Launcher { .. } => "Launcher",
    };
    let mut s = format!(
        "({},{}) {}\nTeam {}\nHP: {}/{}\nID: {}",
        e.pos.0, e.pos.1, kind_name, team, e.hp, e.max_hp, e.id
    );
    match &e.kind {
        EntityKind::BuilderBot { action_cd, move_cd } => {
            s.push_str(&format!("\nAct CD: {action_cd}\nMov CD: {move_cd}"));
        }
        EntityKind::Bridge { target, stored } => {
            s.push_str(&format!(
                "\nTarget: ({},{})\nStored: {stored:?}",
                target.0, target.1
            ));
        }
        EntityKind::Conveyor { dir, stored }
        | EntityKind::ArmouredConveyor { dir, stored }
        | EntityKind::Splitter { dir, stored } => {
            s.push_str(&format!("\nDir: {dir:?}\nStored: {stored:?}"));
        }
        EntityKind::Harvester {
            cooldown,
            resource_type,
        } => {
            s.push_str(&format!("\nCD: {cooldown}\nRes: {resource_type:?}"));
        }
        EntityKind::Marker { value } => {
            s.push_str(&format!("\nValue: {value:#010x}"));
        }
        EntityKind::Gunner {
            dir,
            ammo_type,
            ammo,
        }
        | EntityKind::Sentinel {
            dir,
            ammo_type,
            ammo,
        }
        | EntityKind::Breach {
            dir,
            ammo_type,
            ammo,
        } => {
            s.push_str(&format!("\nDir: {dir:?}\nAmmo: {ammo} {ammo_type:?}"));
        }
        _ => {}
    }
    s
}

fn format_tile_info(game: &GameState, pos: (i32, i32)) -> String {
    let env = game
        .env
        .get(pos.1 as usize)
        .and_then(|r| r.get(pos.0 as usize))
        .copied()
        .unwrap_or(proto::Environment::EnvEmpty);
    let env_name = match env {
        proto::Environment::EnvEmpty => "Empty",
        proto::Environment::EnvWall => "Wall",
        proto::Environment::EnvOreTitanium => "Ore (Ti)",
        proto::Environment::EnvOreAxionite => "Ore (Ax)",
    };
    format!(
        "({},{}) {}\n\nNo entity selected\n(Enter to select)",
        pos.0, pos.1, env_name
    )
}

fn render_help(frame: &mut Frame) {
    let text = "\
Space       Play/Pause
Right       Step +1
Left        Step -1
> / L       Step +10
< / H       Step -10
g / Home    Turn 0
G / End     Last turn
+ / -       Speed up/down
1-9         Jump to 10-90%

hjkl        Move cursor
Enter       Select entity
Tab         Cycle entities
f           Follow entity
Esc/q       Deselect/Quit

Click       Select tile/entity
Drag        Scrub timeline

i           Indicators
n           Network
v           Vision
?           This help";

    let para = Paragraph::new(text)
        .block(Block::default().borders(Borders::ALL).title(" Help "))
        .wrap(Wrap { trim: false });
    frame.render_widget(para, frame.area());
}
