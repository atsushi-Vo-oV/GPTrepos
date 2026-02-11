use std::collections::{BTreeMap, BTreeSet, HashMap};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Player {
    Black,
    White,
}

impl Player {
    pub fn opposite(self) -> Self {
        match self {
            Self::Black => Self::White,
            Self::White => Self::Black,
        }
    }
    pub fn forward_sign(self) -> i32 {
        match self {
            Self::Black => -1,
            Self::White => 1,
        }
    }
    pub fn label(self) -> &'static str {
        match self {
            Self::Black => "先手",
            Self::White => "後手",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum PieceType {
    Pawn,
    Lance,
    Knight,
    Silver,
    Gold,
    Rook,
    Bishop,
    King,
}

impl PieceType {
    pub fn all() -> BTreeSet<Self> {
        [
            Self::Pawn,
            Self::Lance,
            Self::Knight,
            Self::Silver,
            Self::Gold,
            Self::Rook,
            Self::Bishop,
            Self::King,
        ]
        .into_iter()
        .collect()
    }
    pub fn short(self) -> &'static str {
        match self {
            Self::Pawn => "歩",
            Self::Lance => "香",
            Self::Knight => "桂",
            Self::Silver => "銀",
            Self::Gold => "金",
            Self::Rook => "飛",
            Self::Bishop => "角",
            Self::King => "王",
        }
    }
}

#[derive(Clone, Debug)]
pub struct Piece {
    pub id: u64,
    pub owner: Player,
    pub candidates: BTreeSet<PieceType>,
    pub promoted: bool,
}

impl Piece {
    pub fn new(id: u64, owner: Player) -> Self {
        Self {
            id,
            owner,
            candidates: PieceType::all(),
            promoted: false,
        }
    }
}

pub type Board = Vec<Vec<Option<Piece>>>;

#[derive(Clone)]
pub struct Snapshot {
    pub board: Board,
    pub hands: HashMap<Player, Vec<Piece>>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HandMode {
    PerWorld,
    Global,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CheckAttackMode {
    Possible,
    Certain,
}

#[derive(Clone)]
pub struct Settings {
    pub max_worlds: usize,
    pub max_time_jump: i32,
    pub hand_mode: HandMode,
    pub check_attack_mode: CheckAttackMode,
    pub past_only: bool,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            max_worlds: 7,
            max_time_jump: 5,
            hand_mode: HandMode::PerWorld,
            check_attack_mode: CheckAttackMode::Possible,
            past_only: true,
        }
    }
}

#[derive(Clone)]
pub struct WorldLine {
    pub w: i32,
    pub history: Vec<Snapshot>,
    pub staged: Option<PlannedMove>,
    pub lost: bool,
}

#[derive(Clone, Debug)]
pub enum MoveKind {
    Move {
        from: (usize, usize),
        to: (usize, usize),
        promote: bool,
    },
    Drop {
        piece_index: usize,
        to: (usize, usize),
    },
}

#[derive(Clone, Debug)]
pub struct PlannedMove {
    pub kind: MoveKind,
    pub delta_w: i32,
    pub delta_t: i32,
}

pub struct Game {
    pub settings: Settings,
    pub worlds: BTreeMap<i32, WorldLine>,
    pub turn: Player,
    pub selected_world: i32,
    pub message: String,
    next_id: u64,
}

impl Game {
    pub fn new(settings: Settings) -> Self {
        let mut g = Self {
            settings,
            worlds: BTreeMap::new(),
            turn: Player::Black,
            selected_world: 0,
            message: String::new(),
            next_id: 1,
        };
        let snapshot = g.initial_snapshot();
        g.worlds.insert(
            0,
            WorldLine {
                w: 0,
                history: vec![snapshot],
                staged: None,
                lost: false,
            },
        );
        g
    }

    fn initial_snapshot(&mut self) -> Snapshot {
        let mut board = vec![vec![None; 9]; 9];
        for y in 0..3 {
            for x in 0..9 {
                board[y][x] = Some(Piece::new(self.alloc_id(), Player::White));
            }
        }
        for y in 6..9 {
            for x in 0..9 {
                board[y][x] = Some(Piece::new(self.alloc_id(), Player::Black));
            }
        }
        let mut hands = HashMap::new();
        hands.insert(Player::Black, Vec::new());
        hands.insert(Player::White, Vec::new());
        Snapshot { board, hands }
    }

    fn alloc_id(&mut self) -> u64 {
        let id = self.next_id;
        self.next_id += 1;
        id
    }

    pub fn present(&self, w: i32) -> Option<&Snapshot> {
        self.worlds.get(&w).and_then(|wl| wl.history.last())
    }

    fn mut_present(&mut self, w: i32) -> Option<&mut Snapshot> {
        self.worlds.get_mut(&w).and_then(|wl| wl.history.last_mut())
    }

    pub fn stage_move(&mut self, w: i32, mv: PlannedMove) {
        if let Some(wl) = self.worlds.get_mut(&w) {
            wl.staged = Some(mv);
        }
    }

    pub fn clear_staged(&mut self) {
        for wl in self.worlds.values_mut() {
            wl.staged = None;
        }
    }

    pub fn commit_turn(&mut self) {
        let world_ids: Vec<i32> = self.worlds.keys().copied().collect();
        for w in &world_ids {
            if self
                .worlds
                .get(w)
                .and_then(|wl| wl.staged.as_ref())
                .is_none()
            {
                self.message = format!("世界線 {} の手が未入力です", w);
                return;
            }
        }

        let staged: Vec<(i32, PlannedMove)> = world_ids
            .iter()
            .map(|w| (*w, self.worlds[w].staged.clone().unwrap()))
            .collect();

        let mut global_consumption: HashMap<PieceType, usize> = HashMap::new();

        for (w, pm) in staged {
            if let Err(e) = self.apply_one_world(w, pm, &mut global_consumption) {
                self.message = format!("不合法手: {}", e);
                return;
            }
        }

        if self.settings.hand_mode == HandMode::Global {
            let mut total: HashMap<PieceType, usize> = HashMap::new();
            for wl in self.worlds.values() {
                if let Some(s) = wl.history.last() {
                    for p in s.hands.get(&self.turn).into_iter().flatten() {
                        for c in &p.candidates {
                            *total.entry(*c).or_default() += 1;
                        }
                    }
                }
            }
            for (pt, used) in global_consumption {
                if used > *total.get(&pt).unwrap_or(&0) {
                    self.message = format!("global hand不足: {}", pt.short());
                    return;
                }
            }
        }

        for wl in self.worlds.values_mut() {
            wl.staged = None;
            if let Some(s) = wl.history.last_mut() {
                Self::collapse_by_count(s);
                wl.lost = Self::king_candidates(s, self.turn).is_empty()
                    || Self::king_candidates(s, self.turn.opposite()).is_empty();
            }
        }

        self.turn = self.turn.opposite();
        self.message = "同時確定しました".into();
    }

    fn apply_one_world(
        &mut self,
        w: i32,
        pm: PlannedMove,
        global_cons: &mut HashMap<PieceType, usize>,
    ) -> anyhow::Result<()> {
        let present_idx = self.worlds.get(&w).unwrap().history.len() as i32 - 1;
        if self.settings.past_only && pm.delta_t > 0 {
            anyhow::bail!("未来移動は無効");
        }
        if pm.delta_t.abs() > self.settings.max_time_jump {
            anyhow::bail!("時間逆行幅が上限超え");
        }
        let t_base = present_idx + pm.delta_t;
        if t_base < 0 {
            anyhow::bail!("履歴範囲外");
        }

        let branching = pm.delta_w != 0 || pm.delta_t < 0;

        if branching {
            let w_new = w + pm.delta_w;
            if self.worlds.len() >= self.settings.max_worlds {
                anyhow::bail!("MAX_WORLDS");
            }
            if self.worlds.contains_key(&w_new) {
                anyhow::bail!("world衝突");
            }
            let base = self
                .worlds
                .get(&w)
                .unwrap()
                .history
                .get(t_base as usize)
                .cloned()
                .ok_or_else(|| anyhow::anyhow!("t_base無効"))?;
            let mut src_now = self
                .worlds
                .get(&w)
                .unwrap()
                .history
                .last()
                .cloned()
                .unwrap();
            let mut new_snap = base;
            self.execute_move(&mut src_now, &mut new_snap, &pm, true, global_cons)?;
            self.worlds.get_mut(&w).unwrap().history.push(src_now);
            self.worlds.insert(
                w_new,
                WorldLine {
                    w: w_new,
                    history: vec![new_snap],
                    staged: None,
                    lost: false,
                },
            );
        } else {
            let mut cur = self
                .worlds
                .get(&w)
                .unwrap()
                .history
                .last()
                .cloned()
                .unwrap();
            let mut dummy = cur.clone();
            self.execute_move(&mut cur, &mut dummy, &pm, false, global_cons)?;
            self.worlds.get_mut(&w).unwrap().history.push(cur);
        }
        Ok(())
    }

    fn execute_move(
        &self,
        src_present: &mut Snapshot,
        target: &mut Snapshot,
        pm: &PlannedMove,
        branching: bool,
        global_cons: &mut HashMap<PieceType, usize>,
    ) -> anyhow::Result<()> {
        match pm.kind.clone() {
            MoveKind::Move { from, to, promote } => {
                let mut piece = src_present.board[from.1][from.0]
                    .take()
                    .ok_or_else(|| anyhow::anyhow!("移動元空"))?;
                if piece.owner != self.turn {
                    anyhow::bail!("自駒ではない");
                }
                let candidates = self.filter_candidates_for_move(
                    &piece,
                    from,
                    to,
                    pm.delta_w,
                    pm.delta_t,
                    src_present,
                    target,
                )?;
                if candidates.is_empty() {
                    anyhow::bail!("候補なし");
                }
                piece.candidates = candidates;
                piece.promoted = promote;

                if let Some(mut captured) = target.board[to.1][to.0].take() {
                    captured.candidates.remove(&PieceType::King);
                    target.hands.get_mut(&self.turn).unwrap().push(captured);
                }

                if !branching {
                    target.board[from.1][from.0] = None;
                }
                target.board[to.1][to.0] = Some(piece);
            }
            MoveKind::Drop { piece_index, to } => {
                if target.board[to.1][to.0].is_some() {
                    anyhow::bail!("打ち先占有");
                }
                let hand = src_present.hands.get_mut(&self.turn).unwrap();
                if piece_index >= hand.len() {
                    anyhow::bail!("持ち駒index不正");
                }
                let mut p = hand.remove(piece_index);
                if self.settings.hand_mode == HandMode::Global {
                    for c in &p.candidates {
                        *global_cons.entry(*c).or_default() += 1;
                    }
                }
                p.owner = self.turn;
                p.candidates = self.filter_drop_candidates(&p.candidates, to, target);
                if p.candidates.is_empty() {
                    anyhow::bail!("禁則により打てない");
                }
                target.board[to.1][to.0] = Some(p);
            }
        }
        Ok(())
    }

    fn filter_drop_candidates(
        &self,
        cands: &BTreeSet<PieceType>,
        to: (usize, usize),
        target: &Snapshot,
    ) -> BTreeSet<PieceType> {
        let mut out = BTreeSet::new();
        for c in cands {
            if *c == PieceType::Pawn {
                if self.double_pawn_file(target, to.0, self.turn) {
                    continue;
                }
                if (self.turn == Player::Black && to.1 == 0)
                    || (self.turn == Player::White && to.1 == 8)
                {
                    continue;
                }
            }
            if *c == PieceType::Lance {
                if (self.turn == Player::Black && to.1 == 0)
                    || (self.turn == Player::White && to.1 == 8)
                {
                    continue;
                }
            }
            if *c == PieceType::Knight {
                if (self.turn == Player::Black && to.1 <= 1)
                    || (self.turn == Player::White && to.1 >= 7)
                {
                    continue;
                }
            }
            out.insert(*c);
        }
        out
    }

    fn double_pawn_file(&self, s: &Snapshot, file: usize, owner: Player) -> bool {
        (0..9).any(|y| {
            s.board[y][file].as_ref().is_some_and(|p| {
                p.owner == owner
                    && p.candidates.len() == 1
                    && p.candidates.contains(&PieceType::Pawn)
            })
        })
    }

    fn filter_candidates_for_move(
        &self,
        piece: &Piece,
        from: (usize, usize),
        to: (usize, usize),
        dw: i32,
        dt: i32,
        src: &Snapshot,
        target: &Snapshot,
    ) -> anyhow::Result<BTreeSet<PieceType>> {
        if to.0 >= 9 || to.1 >= 9 {
            anyhow::bail!("盤外");
        }
        if let Some(tp) = target.board[to.1][to.0].as_ref() {
            if tp.owner == piece.owner {
                anyhow::bail!("味方占有");
            }
        }
        let dx = to.0 as i32 - from.0 as i32;
        let dy = to.1 as i32 - from.1 as i32;
        let mut out = BTreeSet::new();
        for c in &piece.candidates {
            if self.type_can_move(*c, piece.owner, dx, dy, dw, dt, from, src)? {
                out.insert(*c);
            }
        }
        Ok(out)
    }

    fn type_can_move(
        &self,
        t: PieceType,
        owner: Player,
        dx: i32,
        dy: i32,
        dw: i32,
        dt: i32,
        from: (usize, usize),
        src: &Snapshot,
    ) -> anyhow::Result<bool> {
        if self.settings.past_only && dt > 0 {
            return Ok(false);
        }
        if matches!(
            t,
            PieceType::Pawn | PieceType::Gold | PieceType::Silver | PieceType::King
        ) && dw.abs() >= 2
        {
            return Ok(false);
        }
        let f = owner.forward_sign();
        let ok = match t {
            PieceType::King => dx.abs().max(dy.abs()).max(dw.abs()).max(dt.abs()) == 1,
            PieceType::Pawn => {
                (dy == f && dx == 0 && dw == 0 && dt == 0)
                    || (dw == f && dx == 0 && dy == 0 && dt == 0)
                    || (dt == -1 && dx == 0 && dy == 0 && dw == 0)
            }
            PieceType::Gold => {
                let steps = [
                    (0, f, 0, 0),
                    (1, 0, 0, 0),
                    (-1, 0, 0, 0),
                    (0, -f, 0, 0),
                    (1, f, 0, 0),
                    (-1, f, 0, 0),
                    (0, 0, f, 0),
                    (0, 0, 0, -1),
                ];
                steps.contains(&(dx, dy, dw, dt))
            }
            PieceType::Silver => {
                let steps = [
                    (0, f, 0, 0),
                    (1, f, 0, 0),
                    (-1, f, 0, 0),
                    (1, -f, 0, 0),
                    (-1, -f, 0, 0),
                    (0, 0, f, 0),
                    (0, 0, 0, -1),
                ];
                steps.contains(&(dx, dy, dw, dt))
            }
            PieceType::Knight => {
                let ks = [
                    (1, 2 * f, 0, 0),
                    (-1, 2 * f, 0, 0),
                    (1, 0, 2 * f, 0),
                    (-1, 0, 2 * f, 0),
                    (1, 0, 0, -2),
                    (-1, 0, 0, -2),
                ];
                ks.contains(&(dx, dy, dw, dt))
            }
            PieceType::Lance => {
                self.is_linear_clear(from, dx, dy, dw, dt, src)?
                    && ((dx, dy, dw, dt) != (0, 0, 0, 0))
                    && ((dx == 0 && dw == 0 && dt == 0 && dy.signum() == f)
                        || (dx == 0 && dy == 0 && dt == 0 && dw.signum() == f))
            }
            PieceType::Rook => {
                self.is_linear_clear(from, dx, dy, dw, dt, src)?
                    && [dx == 0, dy == 0, dw == 0, dt == 0]
                        .into_iter()
                        .filter(|v| *v)
                        .count()
                        == 3
            }
            PieceType::Bishop => {
                let non_zero = [dx, dy, dw, dt]
                    .into_iter()
                    .filter(|x| *x != 0)
                    .collect::<Vec<_>>();
                non_zero.len() >= 2
                    && non_zero.iter().all(|v| v.abs() == non_zero[0].abs())
                    && self.is_linear_clear(from, dx, dy, dw, dt, src)?
            }
        };
        Ok(ok)
    }

    fn is_linear_clear(
        &self,
        from: (usize, usize),
        dx: i32,
        dy: i32,
        _dw: i32,
        _dt: i32,
        src: &Snapshot,
    ) -> anyhow::Result<bool> {
        let steps = dx.abs().max(dy.abs());
        if steps <= 1 {
            return Ok(true);
        }
        let sx = dx.signum();
        let sy = dy.signum();
        for i in 1..steps {
            let x = from.0 as i32 + sx * i;
            let y = from.1 as i32 + sy * i;
            if x < 0 || y < 0 || x >= 9 || y >= 9 {
                anyhow::bail!("経路範囲外");
            }
            if src.board[y as usize][x as usize].is_some() {
                return Ok(false);
            }
        }
        Ok(true)
    }

    pub fn king_candidates(s: &Snapshot, pl: Player) -> Vec<(usize, usize)> {
        let mut out = Vec::new();
        for y in 0..9 {
            for x in 0..9 {
                if let Some(p) = &s.board[y][x] {
                    if p.owner == pl && p.candidates.contains(&PieceType::King) {
                        out.push((x, y));
                    }
                }
            }
        }
        out
    }

    fn collapse_by_count(s: &mut Snapshot) {
        let limits: Vec<(PieceType, usize)> = vec![
            (PieceType::King, 1),
            (PieceType::Rook, 1),
            (PieceType::Bishop, 1),
            (PieceType::Gold, 2),
            (PieceType::Silver, 2),
            (PieceType::Knight, 2),
            (PieceType::Lance, 2),
            (PieceType::Pawn, 9),
        ];
        loop {
            let mut changed = false;
            for pl in [Player::Black, Player::White] {
                for (pt, lim) in &limits {
                    let mut ids = Vec::new();
                    for row in &s.board {
                        for p in row.iter().flatten() {
                            if p.owner == pl && p.candidates.contains(pt) {
                                ids.push(p.id);
                            }
                        }
                    }
                    for p in s.hands.get(&pl).into_iter().flatten() {
                        if p.candidates.contains(pt) {
                            ids.push(p.id);
                        }
                    }
                    if ids.len() == *lim {
                        for row in s.board.iter_mut() {
                            for p in row.iter_mut().flatten() {
                                if p.owner == pl && ids.contains(&p.id) {
                                    if !(p.candidates.len() == 1 && p.candidates.contains(pt)) {
                                        p.candidates.clear();
                                        p.candidates.insert(*pt);
                                        changed = true;
                                    }
                                }
                            }
                        }
                        for p in s.hands.get_mut(&pl).into_iter().flatten() {
                            if ids.contains(&p.id) {
                                if !(p.candidates.len() == 1 && p.candidates.contains(pt)) {
                                    p.candidates.clear();
                                    p.candidates.insert(*pt);
                                    changed = true;
                                }
                            }
                        }
                    }
                }
            }
            if !changed {
                break;
            }
        }
    }
}
