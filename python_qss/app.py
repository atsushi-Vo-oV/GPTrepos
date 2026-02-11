from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from engine import Game, MovePlan, Player


class QssApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Quantum Spacetime Shogi (Python)")
        self.geometry("1200x760")
        self.game = Game()
        self.inputs = {}

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=8, pady=6)
        self.turn_var = tk.StringVar()
        self.msg_var = tk.StringVar()
        ttk.Label(top, textvariable=self.turn_var).pack(side=tk.LEFT)
        ttk.Label(top, text=" | ").pack(side=tk.LEFT)
        ttk.Label(top, textvariable=self.msg_var).pack(side=tk.LEFT)

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        left = ttk.Frame(body)
        left.pack(side=tk.LEFT, fill=tk.Y)

        ttk.Label(left, text="世界線一覧").pack(anchor=tk.W)
        self.world_list = tk.Listbox(left, width=28, height=20)
        self.world_list.pack(fill=tk.Y, expand=False)
        self.world_list.bind("<<ListboxSelect>>", self.on_select_world)

        ttk.Button(left, text="全入力クリア", command=self.on_clear).pack(fill=tk.X, pady=4)
        ttk.Button(left, text="同時確定", command=self.on_commit).pack(fill=tk.X)

        center = ttk.Frame(body)
        center.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8)

        self.board_text = tk.Text(center, width=70, height=22, font=("Consolas", 12))
        self.board_text.pack(fill=tk.X)

        form = ttk.LabelFrame(center, text="手入力")
        form.pack(fill=tk.X, pady=8)

        self.mode_var = tk.StringVar(value="move")
        ttk.Radiobutton(form, text="移動", variable=self.mode_var, value="move").grid(row=0, column=0)
        ttk.Radiobutton(form, text="打ち", variable=self.mode_var, value="drop").grid(row=0, column=1)

        self.from_x = tk.IntVar(value=0)
        self.from_y = tk.IntVar(value=0)
        self.to_x = tk.IntVar(value=0)
        self.to_y = tk.IntVar(value=0)
        self.hand_idx = tk.IntVar(value=0)
        self.promote = tk.BooleanVar(value=False)
        self.dw = tk.IntVar(value=0)
        self.dt = tk.IntVar(value=0)

        ttk.Label(form, text="from x,y").grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(form, textvariable=self.from_x, width=4).grid(row=1, column=1)
        ttk.Entry(form, textvariable=self.from_y, width=4).grid(row=1, column=2)
        ttk.Label(form, text="to x,y").grid(row=1, column=3, sticky=tk.W)
        ttk.Entry(form, textvariable=self.to_x, width=4).grid(row=1, column=4)
        ttk.Entry(form, textvariable=self.to_y, width=4).grid(row=1, column=5)

        ttk.Label(form, text="hand_idx").grid(row=2, column=0, sticky=tk.W)
        ttk.Entry(form, textvariable=self.hand_idx, width=6).grid(row=2, column=1)
        ttk.Checkbutton(form, text="成り", variable=self.promote).grid(row=2, column=2)
        ttk.Label(form, text="Δw").grid(row=2, column=3)
        ttk.Entry(form, textvariable=self.dw, width=5).grid(row=2, column=4)
        ttk.Label(form, text="Δt").grid(row=2, column=5)
        ttk.Entry(form, textvariable=self.dt, width=5).grid(row=2, column=6)

        ttk.Button(form, text="この世界線の手を登録", command=self.on_stage).grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=6)

        self.hand_text = tk.Text(center, width=70, height=8, font=("Consolas", 11))
        self.hand_text.pack(fill=tk.X)

    def _selected_world(self) -> int:
        try:
            sel = self.world_list.curselection()[0]
            entry = self.world_list.get(sel)
            return int(entry.split()[0].replace("w=", ""))
        except Exception:
            return self.game.selected_world

    def on_select_world(self, _event=None) -> None:
        self.game.selected_world = self._selected_world()
        self.refresh()

    def on_clear(self) -> None:
        self.game.clear_staged()
        self.refresh()

    def on_commit(self) -> None:
        self.game.commit_turn()
        self.refresh()

    def on_stage(self) -> None:
        w = self._selected_world()
        plan = MovePlan(
            mode=self.mode_var.get(),
            from_xy=(self.from_x.get(), self.from_y.get()),
            to_xy=(self.to_x.get(), self.to_y.get()),
            hand_index=self.hand_idx.get(),
            promote=self.promote.get(),
            delta_w=self.dw.get(),
            delta_t=self.dt.get(),
        )
        self.game.stage(w, plan)
        self.refresh()

    def refresh(self) -> None:
        self.turn_var.set(f"手番: {'先手' if self.game.turn == Player.BLACK else '後手'}")
        self.msg_var.set(self.game.message)

        self.world_list.delete(0, tk.END)
        for w in sorted(self.game.worlds.keys()):
            wl = self.game.worlds[w]
            snap = wl.history[-1]
            kings = len(self.game.king_candidates(snap, self.game.turn))
            staged = "[入力済]" if wl.staged else ""
            self.world_list.insert(tk.END, f"w={w} t={len(wl.history)-1} king?={kings==1} {staged}")

        if self.game.selected_world not in self.game.worlds:
            self.game.selected_world = sorted(self.game.worlds.keys())[0]

        snap = self.game.present(self.game.selected_world)
        self.board_text.delete("1.0", tk.END)
        self.board_text.insert(tk.END, f"盤面 w={self.game.selected_world}\n")
        for y in range(9):
            row = []
            for x in range(9):
                p = snap.board[y][x]
                if p is None:
                    row.append(" ・ ")
                else:
                    owner = "▲" if p.owner == Player.BLACK else "△"
                    body = next(iter(p.candidates)) if len(p.candidates) == 1 else f"{len(p.candidates)}候補"
                    row.append(f"{owner}{body:>3}")
            self.board_text.insert(tk.END, " ".join(row) + "\n")

        hand = snap.hands[self.game.turn]
        self.hand_text.delete("1.0", tk.END)
        self.hand_text.insert(tk.END, f"現在手番の持ち駒: {len(hand)}\n")
        for i, p in enumerate(hand):
            self.hand_text.insert(tk.END, f"[{i}] {','.join(sorted(p.candidates))}\n")


def main() -> None:
    app = QssApp()
    app.mainloop()


if __name__ == "__main__":
    main()
