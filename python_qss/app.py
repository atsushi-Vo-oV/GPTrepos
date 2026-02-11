from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import List, Tuple

import pygame

try:
    from .engine import Game, MovePlan, Player
except ImportError:
    from engine import Game, MovePlan, Player


WHITE = (245, 245, 245)
BLACK = (20, 20, 20)
GRAY = (170, 170, 170)
BLUE = (80, 120, 220)
GREEN = (70, 150, 80)
RED = (180, 70, 70)
BOARD_LIGHT = (236, 220, 180)
BOARD_DARK = (224, 205, 160)


@dataclass
class InputBox:
    label: str
    rect: pygame.Rect
    text: str
    active: bool = False

    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        pygame.draw.rect(screen, BLUE if self.active else GRAY, self.rect, 2)
        screen.blit(font.render(self.label, True, BLACK), (self.rect.x, self.rect.y - 18))
        screen.blit(font.render(self.text, True, BLACK), (self.rect.x + 6, self.rect.y + 6))

    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_TAB):
                self.active = False
            elif len(event.unicode) == 1 and event.unicode.isprintable():
                self.text += event.unicode


class Button:
    def __init__(self, label: str, rect: pygame.Rect, color: Tuple[int, int, int]) -> None:
        self.label = label
        self.rect = rect
        self.color = color

    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        pygame.draw.rect(screen, self.color, self.rect, border_radius=6)
        pygame.draw.rect(screen, BLACK, self.rect, 2, border_radius=6)
        txt = font.render(self.label, True, WHITE)
        screen.blit(txt, (self.rect.centerx - txt.get_width() // 2, self.rect.centery - txt.get_height() // 2))

    def clicked(self, event: pygame.event.Event) -> bool:
        return event.type == pygame.MOUSEBUTTONDOWN and self.rect.collidepoint(event.pos)


class PygameQssApp:
    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((1360, 860))
        pygame.display.set_caption("Quantum Spacetime Shogi (pygame)")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Noto Sans CJK JP", 22)
        self.small = pygame.font.SysFont("Noto Sans CJK JP", 17)

        self.game = Game()
        self.mode = "move"
        self.promote = False
        self.selected_world = 0

        self.input_boxes = self._build_input_boxes()
        self.btn_stage = Button("この世界線の手を登録", pygame.Rect(920, 740, 230, 42), BLUE)
        self.btn_commit = Button("同時確定", pygame.Rect(1160, 740, 160, 42), GREEN)
        self.btn_clear = Button("全入力クリア", pygame.Rect(1160, 690, 160, 42), RED)
        self.btn_mode = Button("mode: move", pygame.Rect(920, 690, 120, 42), GRAY)
        self.btn_promote = Button("成り: OFF", pygame.Rect(1050, 690, 100, 42), GRAY)

    def _build_input_boxes(self) -> List[InputBox]:
        names = [
            ("from_x", "0"),
            ("from_y", "0"),
            ("to_x", "0"),
            ("to_y", "0"),
            ("hand_idx", "0"),
            ("Δw", "0"),
            ("Δt", "0"),
        ]
        boxes: List[InputBox] = []
        x, y = 920, 620
        for i, (label, default) in enumerate(names):
            boxes.append(InputBox(label, pygame.Rect(x + i * 62, y, 56, 36), default))
        return boxes

    def _ibox(self, label: str) -> str:
        for b in self.input_boxes:
            if b.label == label:
                return b.text.strip()
        return "0"

    def _to_int(self, label: str, default: int = 0) -> int:
        try:
            return int(self._ibox(label))
        except ValueError:
            return default

    def run(self) -> None:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit(0)

                for box in self.input_boxes:
                    box.handle(event)

                if self.btn_mode.clicked(event):
                    self.mode = "drop" if self.mode == "move" else "move"
                    self.btn_mode.label = f"mode: {self.mode}"

                if self.btn_promote.clicked(event):
                    self.promote = not self.promote
                    self.btn_promote.label = f"成り: {'ON' if self.promote else 'OFF'}"

                if self.btn_stage.clicked(event):
                    self._stage_current_world()

                if self.btn_commit.clicked(event):
                    self.game.commit_turn()

                if self.btn_clear.clicked(event):
                    self.game.clear_staged()

                if event.type == pygame.MOUSEBUTTONDOWN:
                    self._pick_world(event.pos)

            self.draw()
            self.clock.tick(30)

    def _pick_world(self, pos: Tuple[int, int]) -> None:
        x, y = pos
        if not (20 <= x <= 260):
            return
        base_y = 90
        row_h = 34
        idx = (y - base_y) // row_h
        worlds = sorted(self.game.worlds.keys())
        if 0 <= idx < len(worlds):
            self.selected_world = worlds[idx]
            self.game.selected_world = self.selected_world

    def _stage_current_world(self) -> None:
        plan = MovePlan(
            mode=self.mode,
            from_xy=(self._to_int("from_x"), self._to_int("from_y")),
            to_xy=(self._to_int("to_x"), self._to_int("to_y")),
            hand_index=self._to_int("hand_idx"),
            promote=self.promote,
            delta_w=self._to_int("Δw"),
            delta_t=self._to_int("Δt"),
        )
        self.game.stage(self.selected_world, plan)

    def draw(self) -> None:
        self.screen.fill(WHITE)

        self._draw_header()
        self._draw_worlds()
        self._draw_board()
        self._draw_controls()
        self._draw_hands()

        pygame.display.flip()

    def _draw_header(self) -> None:
        turn = "先手" if self.game.turn == Player.BLACK else "後手"
        title = f"量子時空将棋 (pygame)  | 手番: {turn}"
        self.screen.blit(self.font.render(title, True, BLACK), (20, 16))
        self.screen.blit(self.small.render(self.game.message, True, RED), (20, 46))

    def _draw_worlds(self) -> None:
        pygame.draw.rect(self.screen, (235, 235, 250), pygame.Rect(20, 80, 260, 760), border_radius=8)
        self.screen.blit(self.font.render("世界線一覧", True, BLACK), (30, 88))
        y = 120
        for w in sorted(self.game.worlds.keys()):
            wl = self.game.worlds[w]
            snap = wl.history[-1]
            kings = len(self.game.king_candidates(snap, self.game.turn))
            staged = " [入力済]" if wl.staged else ""
            line = f"w={w} t={len(wl.history)-1} king?={kings==1}{staged}"
            r = pygame.Rect(30, y - 2, 240, 30)
            if w == self.selected_world:
                pygame.draw.rect(self.screen, (196, 214, 255), r, border_radius=6)
            self.screen.blit(self.small.render(line, True, BLACK), (34, y + 4))
            y += 34

    def _draw_board(self) -> None:
        snap = self.game.present(self.selected_world)
        ox, oy = 320, 90
        cell = 62
        self.screen.blit(self.font.render(f"盤面 w={self.selected_world}", True, BLACK), (ox, 88 - 28))

        for y in range(9):
            for x in range(9):
                r = pygame.Rect(ox + x * cell, oy + y * cell, cell, cell)
                pygame.draw.rect(self.screen, BOARD_LIGHT if (x + y) % 2 == 0 else BOARD_DARK, r)
                pygame.draw.rect(self.screen, BLACK, r, 1)
                p = snap.board[y][x]
                if p is None:
                    continue
                owner = "▲" if p.owner == Player.BLACK else "△"
                label = next(iter(p.candidates)) if len(p.candidates) == 1 else f"{len(p.candidates)}候補"
                txt = self.small.render(f"{owner}{label}", True, BLACK)
                self.screen.blit(txt, (r.x + 4, r.y + 20))

    def _draw_controls(self) -> None:
        pygame.draw.rect(self.screen, (240, 250, 240), pygame.Rect(900, 560, 440, 280), border_radius=8)
        self.screen.blit(self.font.render("手入力", True, BLACK), (910, 568))
        for box in self.input_boxes:
            box.draw(self.screen, self.small)

        self.btn_mode.draw(self.screen, self.small)
        self.btn_promote.draw(self.screen, self.small)
        self.btn_stage.draw(self.screen, self.small)
        self.btn_clear.draw(self.screen, self.small)
        self.btn_commit.draw(self.screen, self.small)

    def _draw_hands(self) -> None:
        snap = self.game.present(self.selected_world)
        hand = snap.hands[self.game.turn]
        x, y = 320, 670
        pygame.draw.rect(self.screen, (245, 238, 230), pygame.Rect(x, y, 560, 170), border_radius=8)
        self.screen.blit(self.font.render(f"現在手番の持ち駒: {len(hand)}", True, BLACK), (x + 10, y + 8))
        row = 0
        for i, p in enumerate(hand[:8]):
            cands = ",".join(sorted(p.candidates))
            self.screen.blit(self.small.render(f"[{i}] {cands}", True, BLACK), (x + 10, y + 40 + row * 20))
            row += 1


def main() -> None:
    PygameQssApp().run()


if __name__ == "__main__":
    main()
