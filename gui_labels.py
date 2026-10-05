# -*- coding: utf-8 -*-
"""통합 창 - '라벨' 탭: 라벨지 미리보기 + 사용한 칸 지정 (웹 도구와 같은 조작) + 바로 인쇄·엑셀"""
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox

import labels as L
import order_print as op
from gui_schedule import hint
import theme as T

NUM_W = 20          # 줄 번호 칸 폭(px)
CELL_W, CELL_H = 150, 24
GAP = 10
USED_BG, EMPTY_BG, BORDER = "#9E9E9E", "#FFFFFF", "#D0D0D0"


class LabelTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=12, style="Page.TFrame")
        self.app = app
        self.rows = None           # 라벨을 만들 원본 줄
        self.ids = None            # (예전 택배 파일) 줄이 아직 없을 때 불러올 주문번호
        self.title = ""
        self.used = {}             # {페이지: {칸번호}}
        self.page = 0
        self.drag = None           # 드래그 중 칠할 상태 (True=사용함)
        self.last_click = None     # Shift+클릭 기준 (페이지, 칸)
        self.last_drag_slot = None
        self.f_txt = tkfont.Font(family=T.FONT, size=7)
        self.f_opt = tkfont.Font(family=T.FONT, size=7, weight="bold")
        self.f_name = tkfont.Font(family=T.FONT, size=9, weight="bold")
        self.f_num = tkfont.Font(family=T.FONT, size=7)

        left = ttk.Frame(self, style="Page.TFrame"); left.grid(row=0, column=0, sticky="nw")
        right = ttk.Frame(self, style="Page.TFrame"); right.grid(row=0, column=1, sticky="nw", padx=(16, 0))

        # ---- 왼쪽: 대상·인쇄
        tf = ttk.LabelFrame(left, text=" 라벨 대상 ", padding=10); tf.grid(row=0, column=0, sticky="we")
        self.target_lb = ttk.Label(tf, text="", wraplength=280, justify="left", font=T.f(11, True))
        self.target_lb.grid(row=0, column=0, sticky="w")
        self.count_lb = ttk.Label(tf, text="", wraplength=280, justify="left"); self.count_lb.grid(row=1, column=0, sticky="w", pady=(4, 0))
        hint(tf, "택배 탭에서 택배 파일을 만들거나 미리 확인하면 그 주문으로 라벨이 준비됩니다. "
                 "예전 택배 파일을 고르면 그 주문으로 바뀝니다.", row=2, column=0, sticky="w", pady=(6, 0), wrap=280)
        lg = ttk.Frame(tf); lg.grid(row=3, column=0, sticky="w", pady=(8, 0))
        for color, text in (("#FFC0CB", "일반"), ("#FFFF00", "묶음배송"), ("#B7E4B0", "스마트스토어 묶음배송")):
            tk.Label(lg, text="  ", bg=color, relief="solid", bd=1).pack(side="left")
            ttk.Label(lg, text=f" {text}  ", style="Hint.TLabel").pack(side="left")
        self.split_new_page = tk.BooleanVar(value=True)
        self.split_cb = ttk.Checkbutton(tf, text="스마트스토어 다음은 새 장부터", variable=self.split_new_page,
                                        command=self.draw)
        self.split_hint = ttk.Label(tf, text="", style="Hint.TLabel", wraplength=280, justify="left")

        pf = ttk.LabelFrame(left, text=" 인쇄 ", padding=10); pf.grid(row=1, column=0, sticky="we", pady=(10, 0))
        self.b_print = ttk.Button(pf, text="라벨 인쇄", style="Main.TButton", command=lambda: self.output("pdf"))
        self.b_print.grid(row=0, column=0, sticky="we")
        hint(pf, "실제 크기(100%)로, 관리 탭에서 고른 라벨 프린터·트레이로 인쇄합니다.", row=1, column=0, sticky="w",
             pady=(2, 8), wrap=280)
        self.b_xlsx = ttk.Button(pf, text="라벨 엑셀 저장", command=lambda: self.output("xlsx"))
        self.b_xlsx.grid(row=2, column=0, sticky="we")
        hint(pf, "웹 도구와 같은 모양의 라벨 엑셀을 '택배발송 파일' 폴더에 저장합니다.", row=3, column=0, sticky="w",
             pady=(2, 0), wrap=280)

        kf = ttk.LabelFrame(left, text=" 사용한 칸 지정 방법 ", padding=10); kf.grid(row=2, column=0, sticky="we", pady=(10, 0))
        for i, (k, v) in enumerate((("클릭", "그 칸을 사용함 / 다시 누르면 해제"),
                                    ("드래그", "지나가는 칸을 한 번에 칠하기"),
                                    ("Shift + 클릭", "마지막으로 클릭한 칸부터 여기까지 전부 사용함"))):
            ttk.Label(kf, text=k, font=T.f(9, True), width=11).grid(row=i, column=0, sticky="nw", pady=1)
            ttk.Label(kf, text=v, wraplength=180, justify="left").grid(row=i, column=1, sticky="w", pady=1)
        hint(kf, "회색 칸은 건너뛰고 위→아래, 왼쪽 줄부터 채워집니다. 페이지마다 따로 지정할 수 있고, "
                 "지정은 이번 인쇄에만 적용됩니다.", row=3, column=0, columnspan=2, sticky="w", pady=(6, 0), wrap=280)
        ttk.Button(kf, text="모든 페이지 초기화", command=self.reset_all).grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # ---- 오른쪽: 미리보기
        nav = ttk.Frame(right, style="Page.TFrame"); nav.grid(row=0, column=0, sticky="we")
        self.nav_btns = []
        for text, cmd in (("◀◀ 맨 앞", lambda: self.go(first=True)), ("◀ 이전", lambda: self.go(-1))):
            b = ttk.Button(nav, text=text, style="Page.TButton", command=cmd); b.pack(side="left", padx=(0, 4)); self.nav_btns.append(b)
        self.page_lb = ttk.Label(nav, text="페이지 - / -", style="PageTitle.TLabel", width=14, anchor="center")
        self.page_lb.pack(side="left", padx=8)
        for text, cmd in (("다음 ▶", lambda: self.go(1)), ("맨 뒤 ▶▶", lambda: self.go(last=True))):
            b = ttk.Button(nav, text=text, style="Page.TButton", command=cmd); b.pack(side="left", padx=(0, 4)); self.nav_btns.append(b)
        width = 5 * (NUM_W + CELL_W) + 4 * GAP + 20
        self.cv = tk.Canvas(right, width=width, height=29 * CELL_H + 16, background=T.CARD,
                            highlightthickness=1, highlightbackground=T.LINE, cursor="hand2")
        self.cv.grid(row=1, column=0, pady=(8, 6))
        self.cv.bind("<Button-1>", self.press)
        self.cv.bind("<B1-Motion>", self.motion)
        self.cv.bind("<ButtonRelease-1>", self.release)
        bot = ttk.Frame(right, style="Page.TFrame"); bot.grid(row=2, column=0, sticky="we")
        self.info_lb = ttk.Label(bot, text="", style="Page.TLabel"); self.info_lb.pack(side="left")
        ttk.Button(bot, text="이 페이지 초기화", style="Page.TButton", command=self.reset_page).pack(side="right")
        from gui_courier import SplitBadge, put_on_top
        self.split_badge = SplitBadge(pf, app, wrap=280)
        put_on_top(pf, self.split_badge)
        self.buttons = [self.b_print, self.b_xlsx]
        self.draw()

    # ------------------------------------------------------------ 대상 설정 (택배 탭에서 호출)
    def set_target(self, rows=None, ids=None, title="", split_n=0):
        self.rows, self.ids, self.title, self.split_n = rows, ids, title, split_n
        self.used, self.page, self.last_click = {}, 0, None
        self.draw()

    def _break_at(self):
        if self.rows is None:
            return None
        b = L.split_break(self.rows)
        if b is None:
            self.split_cb.grid_remove(); self.split_hint.grid_remove()
            return None
        n_smart = len(L.build_sequence([r for r in self.rows if r.get("_split")]))
        self.split_cb.grid(row=4, column=0, sticky="w", pady=(8, 0))
        self.split_hint.configure(text=f"스마트스토어 쪽 라벨 {n_smart}칸이 앞쪽에 있습니다. 체크하면 나머지 라벨은 "
                                       "새 장부터 시작해서, 스마트스토어 라벨을 장 단위로 넘기기 편합니다.")
        self.split_hint.grid(row=5, column=0, sticky="w")
        return b if self.split_new_page.get() else None

    def ensure_rows(self, then):
        if self.rows is not None:
            then(); return
        if not self.ids:
            messagebox.showinfo("라벨", "먼저 택배 탭에서 택배 파일을 만들거나 미리 확인해 주세요.")
            return

        def done(rows):
            self.rows = rows
            self.draw()
            then()
        self.app.bg(lambda prog: op.rows_for_orders(self.app.cfg, op.get_access_token(self.app.cfg), self.ids, prog,
                                                    getattr(self, "split_n", 0)),
                    done, "카페24에서 주문 불러오는 중...", progress=True)

    # ------------------------------------------------------------ 그리기
    def _pages(self):
        if self.rows is None:
            return None
        return L.paginate(L.build_sequence(self.rows), self.used, self._break_at())

    def _cut(self, text, font, width):
        if font.measure(text) <= width:
            return text
        while text and font.measure(text + "…") > width:
            text = text[:-1]
        return text + "…"

    def _xy(self, slot):
        col, g = divmod(slot - 1, 29)
        x = 10 + col * (NUM_W + CELL_W + GAP) + NUM_W
        return x, 8 + g * CELL_H

    def draw(self):
        cv = self.cv
        cv.delete("all")
        if self.rows is None:
            self.target_lb.configure(text=self.title or "라벨 대상 없음")
            self.count_lb.configure(text="(인쇄할 때 카페24에서 불러옵니다)" if self.ids else
                                    "택배 탭에서 택배 파일을 만들거나 미리 확인해 주세요.")
            self.page_lb.configure(text="페이지 - / -")
            self.info_lb.configure(text="")
            for b in self.nav_btns:
                b.state(["disabled"])
            if self.ids:
                cv.create_text(cv.winfo_reqwidth() / 2, 60, text="[불러오기]를 누르면 미리보기가 나옵니다",
                               font=T.f(11), fill="#888888")
                bt = ttk.Button(cv, text="불러오기", command=lambda: self.ensure_rows(lambda: None))
                cv.create_window(cv.winfo_reqwidth() / 2, 100, window=bt)
            return
        seq = L.build_sequence(self.rows)
        pages = self._pages()
        ykeys = L.yellow_keys(self.rows)
        self.page = max(0, min(self.page, len(pages) - 1))
        items = pages[self.page]
        used = self.used.get(self.page, set())
        self.target_lb.configure(text=self.title)
        n_used = sum(len(v) for v in self.used.values())
        self.count_lb.configure(text=f"라벨 {len(seq)}칸 · {len(pages)}장" + (f" · 사용함 표시 {n_used}칸" if n_used else ""))
        self.page_lb.configure(text=f"페이지 {self.page + 1} / {len(pages)}")
        states = [self.page > 0, self.page > 0, self.page < len(pages) - 1, self.page < len(pages) - 1]
        for b, ok in zip(self.nav_btns, states):
            b.state(["!disabled"] if ok else ["disabled"])
        for col in range(5):
            gx = 10 + col * (NUM_W + CELL_W + GAP)
            for g in range(29):
                cv.create_text(gx + NUM_W - 4, 8 + g * CELL_H + CELL_H / 2, text=str(g + 1), anchor="e",
                               font=self.f_num, fill="#9A9A9A")
        for slot in range(1, 146):
            x, y = self._xy(slot)
            it = items[slot - 1]
            tag = f"s{slot}"
            if slot in used:
                cv.create_rectangle(x, y, x + CELL_W, y + CELL_H - 2, fill=USED_BG, outline=USED_BG, tags=tag)
                cv.create_text(x + CELL_W / 2, y + CELL_H / 2 - 1, text="사용함", fill="white", font=self.f_opt, tags=tag)
            elif it is None:
                cv.create_rectangle(x, y, x + CELL_W, y + CELL_H - 2, fill=EMPTY_BG, outline=BORDER, dash=(2, 2), tags=tag)
            elif it["type"] == "NAME":
                color = "#" + L.name_color(it, ykeys)[2:]
                cv.create_rectangle(x, y, x + CELL_W, y + CELL_H - 2, fill=color, outline=BORDER, tags=tag)
                cv.create_text(x + CELL_W / 2, y + CELL_H / 2 - 1, text=self._cut(it["text"], self.f_name, CELL_W - 8),
                               font=self.f_name, tags=tag)
            else:
                cv.create_rectangle(x, y, x + CELL_W, y + CELL_H - 2, fill="white", outline=BORDER, tags=tag)
                if it["line2"]:
                    cv.create_text(x + 4, y + 6, text=self._cut(it["line1"], self.f_txt, CELL_W - 8), anchor="w",
                                   font=self.f_txt, tags=tag)
                    cv.create_text(x + CELL_W / 2, y + 16, text=self._cut(it["line2"], self.f_opt, CELL_W - 8),
                                   font=self.f_opt, fill="#4F81BD", tags=tag)
                else:
                    cv.create_text(x + CELL_W / 2, y + CELL_H / 2 - 1, text=self._cut(it["line1"], self.f_txt, CELL_W - 8),
                                   font=self.f_txt, tags=tag)
        self.info_lb.configure(text=f"이 페이지에서 {len(used)}칸 사용됨으로 표시됨" if used else "이 페이지는 전체 칸 사용 가능")

    # ------------------------------------------------------------ 조작 (웹 도구와 같음)
    def _slot_at(self, x, y):
        for col in range(5):
            gx = 10 + col * (NUM_W + CELL_W + GAP) + NUM_W
            if gx <= x <= gx + CELL_W:
                g = int((y - 8) // CELL_H)
                if 0 <= g < 29:
                    return col * 29 + g + 1
        return None

    def _paint_cell(self, slot, on):
        """드래그 중엔 해당 칸만 가볍게 칠함 (전체는 손을 뗄 때 다시 그림)"""
        x, y = self._xy(slot)
        self.cv.delete(f"s{slot}")
        if on:
            self.cv.create_rectangle(x, y, x + CELL_W, y + CELL_H - 2, fill=USED_BG, outline=USED_BG, tags=f"s{slot}")
            self.cv.create_text(x + CELL_W / 2, y + CELL_H / 2 - 1, text="사용함", fill="white", font=self.f_opt,
                                tags=f"s{slot}")
        else:
            self.cv.create_rectangle(x, y, x + CELL_W, y + CELL_H - 2, fill="#EFEFEF", outline=BORDER, tags=f"s{slot}")

    def press(self, e):
        if self.rows is None:
            return
        slot = self._slot_at(e.x, e.y)
        if slot is None:
            return
        cur = self.used.setdefault(self.page, set())
        if (e.state & 0x0001) and self.last_click and self.last_click[0] == self.page:     # Shift+클릭
            lo, hi = sorted((self.last_click[1], slot))
            cur.update(range(lo, hi + 1))
            self.draw()
            return
        self.last_click = (self.page, slot)
        self.drag = slot not in cur
        (cur.add if self.drag else cur.discard)(slot)
        self.last_drag_slot = slot
        self._paint_cell(slot, self.drag)

    def motion(self, e):
        if self.drag is None:
            return
        slot = self._slot_at(e.x, e.y)
        if slot is None or slot == self.last_drag_slot:
            return
        self.last_drag_slot = slot
        cur = self.used.setdefault(self.page, set())
        (cur.add if self.drag else cur.discard)(slot)
        self._paint_cell(slot, self.drag)

    def release(self, e):
        if self.drag is not None:
            self.drag = None
            self.last_drag_slot = None
            self.draw()

    def go(self, d=0, first=False, last=False):
        pages = self._pages()
        if not pages:
            return
        self.page = 0 if first else len(pages) - 1 if last else max(0, min(len(pages) - 1, self.page + d))
        self.draw()

    def reset_page(self):
        self.used.pop(self.page, None)
        self.draw()

    def reset_all(self):
        self.used = {}
        self.draw()

    # ------------------------------------------------------------ 인쇄·저장
    def output(self, kind):
        def go():
            pages = len(self._pages())
            dialog = kind == "pdf" and (self.app.cfg or {}).get("label_print_dialog", True)
            msg = f"라벨 {pages}장을 인쇄할까요?\n뒷면 트레이에 라벨지(폼텍 LS-3145)를 넣었는지 확인해 주세요."
            if dialog:
                msg += "\n\n인쇄 창이 뜨면: 프린터 선택 → [기본 설정]에서 급지를 '뒷면 트레이'로 → 인쇄"
            if kind == "pdf" and not messagebox.askyesno("라벨 인쇄", msg):
                return

            def work():
                path, n, pg = op.make_labels(self.app.cfg, self.rows, self.used, kind,
                                             self._break_at() is not None)
                if kind == "pdf":
                    op.print_pdf(self.app.cfg, path, exact=True)
                return path, n, pg

            def done(r):
                path, n, pg = r
                if kind == "pdf":
                    self.app.flash(f"라벨 {n}칸 ({pg}장) 인쇄를 마쳤습니다.")
                else:
                    messagebox.showinfo("라벨", f"{path.name} 저장 ({n}칸, {pg}장)")
                    op.open_file(op.COURIER_DIR)
            self.app.bg(work, done, "라벨 만드는 중...")
        self.ensure_rows(go)
