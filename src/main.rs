mod engine;

use eframe::egui;
use engine::{CheckAttackMode, Game, HandMode, MoveKind, PieceType, PlannedMove, Player, Settings};

#[derive(Default, Clone)]
struct MoveInput {
    mode_drop: bool,
    from_x: usize,
    from_y: usize,
    to_x: usize,
    to_y: usize,
    promote: bool,
    hand_idx: usize,
    delta_w: i32,
    delta_t: i32,
}

struct App {
    game: Game,
    inputs: std::collections::BTreeMap<i32, MoveInput>,
}

impl Default for App {
    fn default() -> Self {
        Self {
            game: Game::new(Settings::default()),
            inputs: std::collections::BTreeMap::new(),
        }
    }
}

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        egui::TopBottomPanel::top("top").show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.heading("量子時空将棋 プロトタイプ");
                ui.separator();
                ui.label(format!("手番: {}", self.game.turn.label()));
                ui.label(&self.game.message);
            });
            ui.horizontal(|ui| {
                ui.label("MAX_WORLDS");
                ui.add(
                    egui::DragValue::new(&mut self.game.settings.max_worlds).clamp_range(1..=20),
                );
                ui.label("MAX_TIME_JUMP");
                ui.add(
                    egui::DragValue::new(&mut self.game.settings.max_time_jump).clamp_range(1..=20),
                );
                egui::ComboBox::from_label("HAND_MODE")
                    .selected_text(match self.game.settings.hand_mode {
                        HandMode::PerWorld => "per_world",
                        HandMode::Global => "global",
                    })
                    .show_ui(ui, |ui| {
                        ui.selectable_value(
                            &mut self.game.settings.hand_mode,
                            HandMode::PerWorld,
                            "per_world",
                        );
                        ui.selectable_value(
                            &mut self.game.settings.hand_mode,
                            HandMode::Global,
                            "global",
                        );
                    });
                egui::ComboBox::from_label("CHECK_ATTACK_MODE")
                    .selected_text(match self.game.settings.check_attack_mode {
                        CheckAttackMode::Possible => "possible",
                        CheckAttackMode::Certain => "certain",
                    })
                    .show_ui(ui, |ui| {
                        ui.selectable_value(
                            &mut self.game.settings.check_attack_mode,
                            CheckAttackMode::Possible,
                            "possible",
                        );
                        ui.selectable_value(
                            &mut self.game.settings.check_attack_mode,
                            CheckAttackMode::Certain,
                            "certain",
                        );
                    });
                ui.checkbox(&mut self.game.settings.past_only, "past_only");
            });
        });

        egui::SidePanel::left("worlds").show(ctx, |ui| {
            ui.heading("世界線一覧");
            for (w, wl) in &self.game.worlds {
                let snap = wl.history.last().unwrap();
                let my_king = engine::Game::king_candidates(snap, self.game.turn).len();
                let text = format!(
                    "w={w} t={} king?={}{}",
                    wl.history.len() - 1,
                    my_king == 1,
                    if wl.staged.is_some() {
                        " [入力済]"
                    } else {
                        ""
                    }
                );
                if ui
                    .selectable_label(*w == self.game.selected_world, text)
                    .clicked()
                {
                    self.game.selected_world = *w;
                }
            }
            if ui.button("全入力クリア").clicked() {
                self.game.clear_staged();
            }
            if ui.button("同時確定").clicked() {
                self.game.commit_turn();
            }
        });

        egui::CentralPanel::default().show(ctx, |ui| {
            if let Some(wl) = self.game.worlds.get(&self.game.selected_world) {
                let snap = wl.history.last().unwrap();
                ui.heading(format!("盤面 w={}", self.game.selected_world));
                egui::Grid::new("board").spacing([4.0, 4.0]).show(ui, |ui| {
                    for y in 0..9 {
                        for x in 0..9 {
                            let txt = if let Some(p) = &snap.board[y][x] {
                                let owner = if p.owner == Player::Black {
                                    "▲"
                                } else {
                                    "△"
                                };
                                let body = if p.candidates.len() == 1 {
                                    p.candidates.iter().next().unwrap().short().to_string()
                                } else {
                                    format!("{}候補", p.candidates.len())
                                };
                                format!("{}{}", owner, body)
                            } else {
                                "・".to_string()
                            };
                            ui.label(txt);
                        }
                        ui.end_row();
                    }
                });

                ui.separator();
                ui.label("手入力（この世界線）");
                let input = self.inputs.entry(self.game.selected_world).or_default();
                ui.checkbox(&mut input.mode_drop, "打つ");
                ui.horizontal(|ui| {
                    if input.mode_drop {
                        ui.label("hand_idx");
                        ui.add(egui::DragValue::new(&mut input.hand_idx).clamp_range(0..=99));
                    } else {
                        ui.label("from x,y");
                        ui.add(egui::DragValue::new(&mut input.from_x).clamp_range(0..=8));
                        ui.add(egui::DragValue::new(&mut input.from_y).clamp_range(0..=8));
                        ui.checkbox(&mut input.promote, "成り");
                    }
                    ui.label("to x,y");
                    ui.add(egui::DragValue::new(&mut input.to_x).clamp_range(0..=8));
                    ui.add(egui::DragValue::new(&mut input.to_y).clamp_range(0..=8));
                });
                ui.horizontal(|ui| {
                    ui.label("Δw");
                    ui.add(egui::DragValue::new(&mut input.delta_w).clamp_range(-20..=20));
                    ui.label("Δt");
                    ui.add(egui::DragValue::new(&mut input.delta_t).clamp_range(-20..=20));
                });

                if ui.button("この世界線の手を登録").clicked() {
                    let kind = if input.mode_drop {
                        MoveKind::Drop {
                            piece_index: input.hand_idx,
                            to: (input.to_x, input.to_y),
                        }
                    } else {
                        MoveKind::Move {
                            from: (input.from_x, input.from_y),
                            to: (input.to_x, input.to_y),
                            promote: input.promote,
                        }
                    };
                    self.game.stage_move(
                        self.game.selected_world,
                        PlannedMove {
                            kind,
                            delta_w: input.delta_w,
                            delta_t: input.delta_t,
                        },
                    );
                }

                ui.separator();
                let hand = snap.hands.get(&self.game.turn).unwrap();
                ui.label(format!("現在手番の持ち駒数: {}", hand.len()));
                for (i, p) in hand.iter().enumerate() {
                    let cands = p
                        .candidates
                        .iter()
                        .map(|c| c.short())
                        .collect::<Vec<_>>()
                        .join(",");
                    ui.label(format!("[{i}] {cands}"));
                }

                if self.game.settings.hand_mode == HandMode::Global {
                    ui.separator();
                    let mut cnt: std::collections::BTreeMap<PieceType, usize> =
                        std::collections::BTreeMap::new();
                    for wl in self.game.worlds.values() {
                        let s = wl.history.last().unwrap();
                        for p in s.hands.get(&self.game.turn).into_iter().flatten() {
                            for c in &p.candidates {
                                *cnt.entry(*c).or_default() += 1;
                            }
                        }
                    }
                    ui.label("global在庫（候補合算）");
                    for (k, v) in cnt {
                        ui.label(format!("{}: {}", k.short(), v));
                    }
                }
            }
        });
    }
}

fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions::default();
    eframe::run_native(
        "Quantum Spacetime Shogi",
        options,
        Box::new(|_cc| Box::new(App::default())),
    )
}
