from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


class Player(str, Enum):
    BLACK = "black"
    WHITE = "white"

    def opposite(self) -> "Player":
        return Player.WHITE if self == Player.BLACK else Player.BLACK

    def forward(self) -> int:
        return -1 if self == Player.BLACK else 1


PIECE_TYPES = ["歩", "香", "桂", "銀", "金", "飛", "角", "王"]
PIECE_LIMIT = {"王": 1, "飛": 1, "角": 1, "金": 2, "銀": 2, "桂": 2, "香": 2, "歩": 9}


@dataclass
class Piece:
    id: int
    owner: Player
    candidates: Set[str] = field(default_factory=lambda: set(PIECE_TYPES))
    promoted: bool = False


Board = List[List[Optional[Piece]]]


@dataclass
class Snapshot:
    board: Board
    hands: Dict[Player, List[Piece]]


@dataclass
class MovePlan:
    mode: str  # move/drop
    from_xy: Tuple[int, int] = (0, 0)
    to_xy: Tuple[int, int] = (0, 0)
    hand_index: int = 0
    promote: bool = False
    delta_w: int = 0
    delta_t: int = 0


@dataclass
class WorldLine:
    w: int
    history: List[Snapshot]
    staged: Optional[MovePlan] = None
    lost: bool = False


@dataclass
class Settings:
    max_worlds: int = 7
    max_time_jump: int = 5
    hand_mode: str = "per_world"  # per_world/global
    check_attack_mode: str = "possible"
    time_direction_policy: str = "past_only"


class Game:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()
        self.turn = Player.BLACK
        self.message = ""
        self.selected_world = 0
        self._next_id = 1
        self.worlds: Dict[int, WorldLine] = {0: WorldLine(0, [self._initial_snapshot()])}

    def _new_piece(self, owner: Player) -> Piece:
        p = Piece(self._next_id, owner)
        self._next_id += 1
        return p

    def _initial_snapshot(self) -> Snapshot:
        board = [[None for _ in range(9)] for _ in range(9)]
        for y in range(3):
            for x in range(9):
                board[y][x] = self._new_piece(Player.WHITE)
        for y in range(6, 9):
            for x in range(9):
                board[y][x] = self._new_piece(Player.BLACK)
        return Snapshot(board=board, hands={Player.BLACK: [], Player.WHITE: []})

    def present(self, w: int) -> Snapshot:
        return self.worlds[w].history[-1]

    def stage(self, w: int, plan: MovePlan) -> None:
        if w in self.worlds:
            self.worlds[w].staged = plan

    def clear_staged(self) -> None:
        for wl in self.worlds.values():
            wl.staged = None

    def commit_turn(self) -> bool:
        world_ids = sorted(self.worlds.keys())
        if any(self.worlds[w].staged is None for w in world_ids):
            self.message = "未入力の世界線があります"
            return False

        staged = [(w, self.worlds[w].staged) for w in world_ids]
        global_use: Dict[str, int] = {}
        for w, plan in staged:
            ok, err = self._apply_one_world(w, plan, global_use)
            if not ok:
                self.message = f"不合法手: {err}"
                return False

        if self.settings.hand_mode == "global":
            total: Dict[str, int] = {}
            for wl in self.worlds.values():
                for p in wl.history[-1].hands[self.turn]:
                    for c in p.candidates:
                        total[c] = total.get(c, 0) + 1
            for k, v in global_use.items():
                if v > total.get(k, 0):
                    self.message = f"global hand不足: {k}"
                    return False

        for wl in self.worlds.values():
            wl.staged = None
            self._collapse_by_count(wl.history[-1])
            wl.lost = len(self.king_candidates(wl.history[-1], Player.BLACK)) == 0 or len(
                self.king_candidates(wl.history[-1], Player.WHITE)
            ) == 0

        self.turn = self.turn.opposite()
        self.message = "同時確定しました"
        return True

    def _apply_one_world(self, w: int, plan: MovePlan, global_use: Dict[str, int]) -> Tuple[bool, str]:
        wl = self.worlds[w]
        present_t = len(wl.history) - 1

        if self.settings.time_direction_policy == "past_only" and plan.delta_t > 0:
            return False, "未来移動不可"
        if abs(plan.delta_t) > self.settings.max_time_jump:
            return False, "時間逆行幅オーバー"

        t_base = present_t + plan.delta_t
        if t_base < 0 or t_base >= len(wl.history):
            return False, "履歴範囲外"

        branching = plan.delta_w != 0 or plan.delta_t < 0
        if branching:
            w_new = w + plan.delta_w
            if len(self.worlds) >= self.settings.max_worlds:
                return False, "MAX_WORLDS"
            if w_new in self.worlds:
                return False, "world衝突"

            from_present = self._clone_snapshot(wl.history[-1])
            target = self._clone_snapshot(wl.history[t_base])
            ok, err = self._execute(from_present, target, plan, True, global_use)
            if not ok:
                return False, err
            wl.history.append(from_present)
            self.worlds[w_new] = WorldLine(w_new, [target])
            return True, ""

        cur = self._clone_snapshot(wl.history[-1])
        dummy = self._clone_snapshot(cur)
        ok, err = self._execute(cur, dummy, plan, False, global_use)
        if not ok:
            return False, err
        wl.history.append(cur)
        return True, ""

    def _clone_snapshot(self, s: Snapshot) -> Snapshot:
        board: Board = [[None for _ in range(9)] for _ in range(9)]
        for y in range(9):
            for x in range(9):
                p = s.board[y][x]
                if p is not None:
                    board[y][x] = Piece(p.id, p.owner, set(p.candidates), p.promoted)
        hands = {
            Player.BLACK: [Piece(p.id, p.owner, set(p.candidates), p.promoted) for p in s.hands[Player.BLACK]],
            Player.WHITE: [Piece(p.id, p.owner, set(p.candidates), p.promoted) for p in s.hands[Player.WHITE]],
        }
        return Snapshot(board, hands)

    def _execute(
        self,
        src_present: Snapshot,
        target: Snapshot,
        plan: MovePlan,
        branching: bool,
        global_use: Dict[str, int],
    ) -> Tuple[bool, str]:
        tx, ty = plan.to_xy
        if not (0 <= tx < 9 and 0 <= ty < 9):
            return False, "盤外"

        if plan.mode == "drop":
            if target.board[ty][tx] is not None:
                return False, "打ち先占有"
            hand = src_present.hands[self.turn]
            if plan.hand_index < 0 or plan.hand_index >= len(hand):
                return False, "持ち駒index不正"
            p = hand.pop(plan.hand_index)
            p.owner = self.turn
            p.candidates = self._filter_drop_candidates(p.candidates, tx, ty, target)
            if not p.candidates:
                return False, "禁則で打てない"
            if self.settings.hand_mode == "global":
                for c in p.candidates:
                    global_use[c] = global_use.get(c, 0) + 1
            target.board[ty][tx] = p
            return True, ""

        fx, fy = plan.from_xy
        if not (0 <= fx < 9 and 0 <= fy < 9):
            return False, "移動元盤外"
        piece = src_present.board[fy][fx]
        if piece is None:
            return False, "移動元空"
        if piece.owner != self.turn:
            return False, "自駒ではない"
        dst = target.board[ty][tx]
        if dst is not None and dst.owner == self.turn:
            return False, "味方占有"

        dx, dy = tx - fx, ty - fy
        filtered = {c for c in piece.candidates if self._type_can_move(c, piece.owner, dx, dy, plan.delta_w, plan.delta_t, fx, fy, src_present)}
        if not filtered:
            return False, "候補なし"

        src_present.board[fy][fx] = None
        moved = Piece(piece.id, piece.owner, filtered, plan.promote)
        if dst is not None:
            captured = Piece(dst.id, dst.owner, set(dst.candidates), dst.promoted)
            captured.candidates.discard("王")
            target.hands[self.turn].append(captured)
            target.board[ty][tx] = None

        if not branching:
            target.board[fy][fx] = None
        target.board[ty][tx] = moved
        return True, ""

    def _filter_drop_candidates(self, cands: Set[str], x: int, y: int, target: Snapshot) -> Set[str]:
        out = set()
        for c in cands:
            if c == "歩":
                if self._double_pawn(target, x, self.turn):
                    continue
                if (self.turn == Player.BLACK and y == 0) or (self.turn == Player.WHITE and y == 8):
                    continue
            if c == "香":
                if (self.turn == Player.BLACK and y == 0) or (self.turn == Player.WHITE and y == 8):
                    continue
            if c == "桂":
                if (self.turn == Player.BLACK and y <= 1) or (self.turn == Player.WHITE and y >= 7):
                    continue
            out.add(c)
        return out

    def _double_pawn(self, s: Snapshot, file_x: int, owner: Player) -> bool:
        for y in range(9):
            p = s.board[y][file_x]
            if p and p.owner == owner and p.candidates == {"歩"}:
                return True
        return False

    def _type_can_move(self, t: str, owner: Player, dx: int, dy: int, dw: int, dt: int, fx: int, fy: int, src: Snapshot) -> bool:
        if self.settings.time_direction_policy == "past_only" and dt > 0:
            return False
        if t in {"歩", "金", "銀", "王"} and abs(dw) >= 2:
            return False

        f = owner.forward()
        if t == "王":
            return max(abs(dx), abs(dy), abs(dw), abs(dt)) == 1
        if t == "歩":
            return (dx, dy, dw, dt) in {(0, f, 0, 0), (0, 0, f, 0), (0, 0, 0, -1)}
        if t == "金":
            return (dx, dy, dw, dt) in {(0, f, 0, 0), (1, 0, 0, 0), (-1, 0, 0, 0), (0, -f, 0, 0), (1, f, 0, 0), (-1, f, 0, 0), (0, 0, f, 0), (0, 0, 0, -1)}
        if t == "銀":
            return (dx, dy, dw, dt) in {(0, f, 0, 0), (1, f, 0, 0), (-1, f, 0, 0), (1, -f, 0, 0), (-1, -f, 0, 0), (0, 0, f, 0), (0, 0, 0, -1)}
        if t == "桂":
            return (dx, dy, dw, dt) in {(1, 2 * f, 0, 0), (-1, 2 * f, 0, 0), (1, 0, 2 * f, 0), (-1, 0, 2 * f, 0), (1, 0, 0, -2), (-1, 0, 0, -2)}
        if t == "香":
            if not self._is_linear_clear(dx, dy, fx, fy, src):
                return False
            return (dx == 0 and dw == 0 and dt == 0 and (dy > 0) == (f > 0)) or (
                dx == 0 and dy == 0 and dt == 0 and (dw > 0) == (f > 0)
            )
        if t == "飛":
            if not self._is_linear_clear(dx, dy, fx, fy, src):
                return False
            return [dx == 0, dy == 0, dw == 0, dt == 0].count(True) == 3
        if t == "角":
            nz = [abs(v) for v in (dx, dy, dw, dt) if v != 0]
            if len(nz) < 2 or not all(v == nz[0] for v in nz):
                return False
            return self._is_linear_clear(dx, dy, fx, fy, src)
        return False

    def _is_linear_clear(self, dx: int, dy: int, fx: int, fy: int, src: Snapshot) -> bool:
        steps = max(abs(dx), abs(dy))
        if steps <= 1:
            return True
        sx = 0 if dx == 0 else (1 if dx > 0 else -1)
        sy = 0 if dy == 0 else (1 if dy > 0 else -1)
        for i in range(1, steps):
            x = fx + sx * i
            y = fy + sy * i
            if not (0 <= x < 9 and 0 <= y < 9):
                return False
            if src.board[y][x] is not None:
                return False
        return True

    def king_candidates(self, s: Snapshot, owner: Player) -> List[Tuple[int, int]]:
        out = []
        for y in range(9):
            for x in range(9):
                p = s.board[y][x]
                if p and p.owner == owner and "王" in p.candidates:
                    out.append((x, y))
        return out

    def _collapse_by_count(self, s: Snapshot) -> None:
        changed = True
        while changed:
            changed = False
            for pl in [Player.BLACK, Player.WHITE]:
                for kind, lim in PIECE_LIMIT.items():
                    ids = []
                    for y in range(9):
                        for x in range(9):
                            p = s.board[y][x]
                            if p and p.owner == pl and kind in p.candidates:
                                ids.append(p.id)
                    for p in s.hands[pl]:
                        if kind in p.candidates:
                            ids.append(p.id)
                    if len(ids) == lim:
                        idset = set(ids)
                        for y in range(9):
                            for x in range(9):
                                p = s.board[y][x]
                                if p and p.owner == pl and p.id in idset and p.candidates != {kind}:
                                    p.candidates = {kind}
                                    changed = True
                        for p in s.hands[pl]:
                            if p.id in idset and p.candidates != {kind}:
                                p.candidates = {kind}
                                changed = True
