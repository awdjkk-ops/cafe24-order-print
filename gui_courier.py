# -*- coding: utf-8 -*-
"""통합 창 - '택배·라벨' 탭 (택배 발송용 파일, 확인 목록, 라벨)"""
import datetime as dt
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox

import order_print as op
from gui_schedule import hint
import theme as T

MSG = "중요 배송메세지 확인"
CHECK_BOXES = ("묶음배송 확인", "제주도 확인", MSG, "수제 제작 상품 확인")      # 줄 끝 [확인 완료]
EDIT_BOXES = ("묶음배송 확인", "제주도 확인", "수제 제작 상품 확인")              # 우클릭 삭제·수정 (화면·복사만)
BOXES = ["묶음배송 확인", "제주도 확인", "중요 배송메세지 확인", "수제 제작 상품 확인", op.PREV_BUNDLE, "추가배송 포함", "블랙리스트·경계대상", "주소 '~' 변경 확인"]
BOX_HINTS = {
    "묶음배송 확인": "이름·주소가 같은 주문 (택배 파일에 노란색). 우클릭: 지우기·고치기 (화면·복사만)",
    "중요 배송메세지 확인": "흔한 메세지를 뺀 배송메세지. 우클릭: 지우기·고치기, 두 번 누르면 바로 고치기 (택배 파일에만 반영)",
    "블랙리스트·경계대상": "택배 파일에 빨강(블랙리스트)·파랑(경계대상)으로 표시됩니다.",
    op.PREV_BUNDLE: "최근 7일 택배 파일에 넣었지만 카페24에서 아직 발송 처리 안 된 주문(보관 중)과 수령인 이름·주소가 같은 오늘 주문입니다. "
                    "알려 주기만 하고 택배 파일에는 영향이 없습니다. 카페24 발송 처리를 한 뒤에 보세요. [복사]는 묶음배송 확인과 같은 모양입니다.",
    "추가배송 포함": "구글 시트에 등록된 추가배송(재발송 등)입니다. 택배 파일을 만들면 시트에서 지워집니다.",
    "제주도 확인": "제주·서귀포 주소입니다. 우클릭: 지우기·고치기 (화면·복사만)",
    "수제 제작 상품 확인": "관리 탭에 등록한 수제 제작 상품 (주문번호 / 수령인 / 상품명 / 옵션 / 개수). 우클릭: 지우기·고치기 (화면·복사만)",
    "주소 '~' 변경 확인": "롯데택배가 '~'를 못 읽어서 '-'로 바꾼 주소입니다.",
}


class SplitBadge(ttk.Frame):
    """'오늘 스마트스토어 따로 작업: 켜짐/꺼짐' 표시 (택배·라벨 탭). 누르면 출력 탭으로 가서 바꿀 수 있음."""

    def __init__(self, parent, app, wrap=420):
        super().__init__(parent)
        self.app = app
        self.pill = T.Pill(self, text=" ", bg="#EFEFEC", fg=T.MUTED)
        self.pill.pack(anchor="w")
        self.pill.configure(cursor="hand2")
        self.pill.bind("<Button-1>", lambda e: app.show_tab("print"))
        self.note = ttk.Label(self, text="", style="Hint.TLabel", wraplength=wrap, justify="left")
        self.note.pack(anchor="w", pady=(3, 0))
        self.refresh()

    def refresh(self):
        on = op.split_on()
        self.pill.configure(text=f"오늘 스마트스토어 따로 작업: {'켜짐' if on else '꺼짐'}",
                            bg="#E3F6D8" if on else "#EFEFEC", fg="#2E7D32" if on else T.MUTED)
        self.note.configure(text=("스마트스토어 쪽이 맨 앞에 모입니다" if on else "평소처럼 뽑은 순서대로") + " · 바꾸려면 눌러서 출력 탭으로")


def put_on_top(card, widget, pady=(0, 8)):
    """카드 맨 위에 끼워 넣기 (기존 내용은 한 줄씩 아래로)"""
    for w in card.grid_slaves():
        w.grid_configure(row=int(w.grid_info()["row"]) + 1)
    widget.grid(row=0, column=0, columnspan=3, sticky="w", pady=pady)


class CourierTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=12, style="Page.TFrame")
        self.app = app
        self.last = None            # 마지막으로 만든(또는 미리 본) 결과
        self._auto_key = None       # 자동 미리보기를 한 대기 목록 (바뀌면 다시)
        self._gen = 0               # 늦게 끝난 자동 미리보기가 새 결과를 덮지 않게
        left = ttk.Frame(self, style="Page.TFrame"); left.grid(row=0, column=0, sticky="nsw")
        right = ttk.Frame(self, style="Page.TFrame"); right.grid(row=0, column=1, sticky="nsew", padx=(16, 0))
        self.columnconfigure(1, weight=1); self.rowconfigure(0, weight=1)

        # ---- 대기 목록
        wf = ttk.LabelFrame(left, text=" 택배 파일 대기 주문 ", padding=10); wf.grid(row=0, column=0, sticky="we")
        self.wait_lb = ttk.Label(wf, text="", style="Big.TLabel"); self.wait_lb.grid(row=0, column=0, sticky="w")
        hint(wf, "이 프로그램으로 출력한 주문 중 아직 택배 파일을 만들지 않은 주문입니다 (뽑은 순서대로). "
                 "오늘 못 보내는 주문도 포함됩니다.", row=1, column=0, sticky="w", pady=(2, 6), wrap=430)
        cols = (("no", "번호", 40), ("oid", "주문번호", 140), ("buyer", "수령인", 70), ("place", "경로", 85),
                ("when", "출력한 때", 100))
        self.wait = ttk.Treeview(wf, columns=[c[0] for c in cols], show="headings", height=9, selectmode="extended")
        for c, t, w in cols:
            self.wait.heading(c, text=t); self.wait.column(c, width=w, anchor="center" if c == "no" else "w")
        self.wait.grid(row=2, column=0, sticky="we")
        wb = ttk.Frame(wf); wb.grid(row=3, column=0, sticky="we", pady=(8, 0))
        self.b_rm = ttk.Button(wb, text="선택한 주문 대기에서 빼기", command=self.remove_selected)
        self.b_rm.pack(side="left")
        self.b_clear = ttk.Button(wb, text="대기 전체 비우기", style="Stop.TButton", command=self.clear_all)
        self.b_clear.pack(side="right")
        hint(wf, "뺀 주문은 택배 파일·라벨에 들어가지 않습니다. 주문서 출력 기록은 그대로이고, 출력 탭 주문 현황의 "
                 "[택배·라벨에 넣기]로 언제든 다시 넣을 수 있습니다. (Ctrl·Shift+클릭으로 여러 개 선택)",
             row=4, column=0, sticky="w", pady=(4, 0), wrap=430)

        # ---- 만들기
        af = ttk.LabelFrame(left, text=" 택배 발송용 파일 (롯데택배 알프스) ", padding=10)
        af.grid(row=1, column=0, sticky="we", pady=(10, 0))
        self.b_pre = ttk.Button(af, text="미리 확인", command=lambda: self.run(False))
        self.b_pre.grid(row=0, column=0, sticky="w")
        hint(af, "파일을 만들지 않고 묶음배송·배송메세지·블랙리스트 등을 먼저 봅니다. 추가배송은 지우지 않습니다. "
                 "택배·라벨 탭을 열면 대기 주문으로 자동으로 미리 확인합니다.",
             row=1, column=0, sticky="w", pady=(2, 8), wrap=430)
        self.b_make = ttk.Button(af, text="택배 파일 만들기", style="Main.TButton", command=lambda: self.run(True))
        self.b_make.grid(row=2, column=0, sticky="w")
        hint(af, "대기 주문 전체와 구글 시트의 추가배송으로 택배 파일을 만듭니다. 추가배송은 시트에서 지워지고, "
                 "만든 주문은 대기 목록에서 빠집니다. 카페24에서 최신 정보를 불러오며 그사이 취소된 주문은 뺍니다.",
             row=3, column=0, sticky="w", pady=(2, 0), wrap=430)
        self.stat = ttk.Label(af, text="", justify="left", foreground=T.GREEN_D, wraplength=430)
        self.stat.grid(row=4, column=0, sticky="w", pady=(8, 0))
        bb = ttk.Frame(af); bb.grid(row=5, column=0, sticky="w", pady=(6, 0))
        self.split_badge = SplitBadge(af, app)
        ttk.Button(bb, text="만든 파일 열기", command=self.open_file).pack(side="left")
        ttk.Button(bb, text="폴더 열기", command=lambda: op.open_file(op.COURIER_DIR)).pack(side="left", padx=6)

        # ---- 라벨은 '라벨' 탭에서
        lf = ttk.LabelFrame(left, text=" 검토용 라벨 ", padding=10); lf.grid(row=2, column=0, sticky="we", pady=(10, 0))
        hint(lf, "택배 파일을 만들거나 미리 확인하면 같은 주문으로 라벨이 준비됩니다. 라벨지 미리보기·사용한 칸 지정·"
                 "인쇄는 [라벨] 탭에서 합니다.", row=0, column=0, sticky="w", wrap=430)
        ttk.Button(lf, text="라벨 탭으로 가기 ▶", command=lambda: self.app.show_tab("label")).grid(row=1, column=0, sticky="w", pady=(6, 0))

        # ---- 오른쪽: 확인 목록
        right.columnconfigure(0, weight=1)
        top = ttk.Frame(right, style="Page.TFrame"); top.grid(row=0, column=0, sticky="we")
        self.res_title = ttk.Label(top, text="확인 목록", style="PageTitle.TLabel"); self.res_title.pack(side="left")
        ttk.Label(top, text="   예전 택배 파일:", style="PageHint.TLabel").pack(side="left")
        self.hist = ttk.Combobox(top, state="readonly", width=34); self.hist.pack(side="left", padx=4)
        self.hist.bind("<<ComboboxSelected>>", lambda e: self.show_hist())
        self.texts = {}
        for i, name in enumerate(BOXES):
            # 제목 줄: 제목 · ⓘ(마우스를 올리면 설명) ······ [복사]
            head = ttk.Frame(right, style="Page.TFrame")
            head.grid(row=2 * i + 1, column=0, sticky="we", pady=(10 if i else 4, 2))
            ttk.Label(head, text=name, style="Page.TLabel", font=T.f(11, True)).pack(side="left")
            info = tk.Canvas(head, width=17, height=17, bg=T.BG, highlightthickness=0, cursor="question_arrow")
            info.create_oval(1, 1, 16, 16, outline=T.MUTED, width=1.2)
            info.create_text(9, 9, text="?", fill=T.MUTED, font=T.f(8, True))
            info.pack(side="left", padx=(6, 0))
            Tip(info, BOX_HINTS[name])
            ttk.Button(head, text="복사", width=6, command=lambda n=name: self.copy(n)).pack(side="right")
            box = ttk.LabelFrame(right, padding=6, labelwidget=ttk.Frame(right, width=1, height=1))   # 제목 자리 없이 카드만
            box.grid(row=2 * i + 2, column=0, sticky="we")
            box.columnconfigure(0, weight=1)
            t = T.text_box(tk.Text(box, height=1, wrap="none"))
            t.grid(row=0, column=0, sticky="we")
            sb = ttk.Scrollbar(box, orient="vertical", command=t.yview)
            t.configure(yscrollcommand=lambda a, b, sb=sb: self._scroll_set(sb, a, b), state="disabled")
            sb.grid(row=0, column=1, sticky="ns"); sb.grid_remove()
            self.texts[name] = t
            t.tag_configure("done", background=T.GREEN_L)      # [확인 완료]를 누른 줄
            if name in EDIT_BOXES:
                t.tag_configure("deleted", foreground=T.DIM, overstrike=True)
                t.tag_configure("edited", background=T.HILITE)
                t.tag_configure("mark", foreground=T.GREEN_D)
                t.tag_configure("cur", background="#F1F1EE")
                t.bind("<Button-3>", lambda e, n=name: self._line_menu(n, e))
                t.bind("<Double-Button-1>", lambda e, n=name: (self._line_edit(n, self._line_at(n, e)), "break")[1])
        # 중요 배송메세지: 우클릭(삭제·수정·되돌리기), 두 번 누르면 수정
        self.msg_rows, self.msg_editable, self._editor = [], False, None
        self.box_lines = {}
        mt = self.texts[MSG]
        mt.tag_configure("deleted", foreground=T.DIM)
        mt.tag_configure("edited", background=T.HILITE)
        mt.tag_configure("mark", foreground=T.GREEN_D)
        mt.tag_configure("cur", background="#F1F1EE")
        mt.bind("<Button-3>", self._msg_menu)
        mt.bind("<Double-Button-1>", lambda e: (self._msg_edit(self._msg_at(e)), "break")[1])
        put_on_top(self.split_badge.master, self.split_badge)
        self.buttons = [self.b_pre, self.b_make, self.b_rm, self.b_clear]
        self.refresh()

    # ------------------------------------------------------------
    def refresh(self):
        self.split_badge.refresh()
        cand = op.courier_candidates()
        self.wait.delete(*self.wait.get_children())
        n = 0
        for o, when in cand:
            if not self.wait.exists(o["order_id"]):
                n += 1
                self.wait.insert("", "end", iid=o["order_id"],
                                 values=(n, o["order_id"], o.get("receiver") or o["buyer"], o["place"], when))
        self.wait_lb.configure(text=f"대기 {len(cand)}건")
        hist = op.load_courier_history()
        self.hist.configure(values=[f"{h['time'][5:16].replace('T', ' ')} · {'추가배송만 ' if h.get('extra_only') else ''}"
                                    f"{h['count']}건 · {Path(h['file']).name}"
                                    for h in hist])

    def remove_selected(self):
        ids = list(self.wait.selection())
        if not ids:
            messagebox.showinfo("대기에서 빼기", "대기 목록에서 뺄 주문을 골라 주세요. (Ctrl·Shift+클릭으로 여러 개)")
            return
        if not messagebox.askyesno("대기에서 빼기", f"선택한 {len(ids)}건을 택배 대기에서 뺄까요?\n"
                                                + "\n".join(ids[:8]) + ("\n…" if len(ids) > 8 else "")
                                                + "\n\n주문서 출력 기록은 그대로이고, 출력 탭의 [택배·라벨에 넣기]로 다시 넣을 수 있습니다."):
            return
        op.remove_from_courier_wait(ids)
        self.app.flash(f"{len(ids)}건을 택배 대기에서 뺐습니다.")
        self.refresh()
        self.auto_preview()

    def clear_all(self):
        ids = [o["order_id"] for o, _ in op.courier_candidates()]
        if not ids:
            messagebox.showinfo("대기 전체 비우기", "택배 대기가 이미 비어 있습니다.")
            return
        if not messagebox.askyesno("대기 전체 비우기", f"택배 대기 {len(ids)}건을 모두 뺄까요?\n\n"
                                                    "주문서 출력 기록은 그대로이고, 필요한 주문은 출력 탭의 [택배·라벨에 넣기]로 다시 넣을 수 있습니다."):
            return
        if not messagebox.askyesno("한 번 더 확인", f"정말 {len(ids)}건 전부 택배 대기에서 뺄까요?\n"
                                                 "오늘 보낼 송장이 있다면 택배 파일을 먼저 만드세요.", icon="warning"):
            return
        op.remove_from_courier_wait(ids)
        self.app.flash(f"택배 대기 {len(ids)}건을 모두 뺐습니다.")
        self.refresh()
        self.auto_preview()

    def _fill(self, texts):
        self._end_edit(False)
        self.msg_rows, self.msg_editable = [], False
        for name, t in self.texts.items():
            t.configure(state="normal"); t.delete("1.0", "end")
            v = texts.get(name, "")
            if name in EDIT_BOXES:
                self._render_edit_box(name, v)
            else:
                t.insert("1.0", v if v else "(없음)")
                if v and name in CHECK_BOXES:
                    self._add_checks(name)
            t.configure(state="disabled")
            self._fit(name)
        self.copy_texts = {n: texts.get(n + "|복사", "") for n in BOXES}

    MAX_LINES = 5

    def _scroll_set(self, sb, a, b):
        sb.set(a, b)
        (sb.grid_remove if float(a) <= 0 and float(b) >= 1 else sb.grid)()   # 넘칠 때만 스크롤바

    def _fit(self, name):
        """칸 높이 = 줄 수 (없으면 1줄, 최대 5줄 — 넘치면 칸 안에서 스크롤)"""
        t = self.texts[name]
        n = max(1, int(t.index("end-1c").split(".")[0]))
        if n > self.MAX_LINES:
            t.configure(height=self.MAX_LINES)          # 5줄 넘는 내용은 칸 안에서 스크롤
            return
        t.configure(height=n)

    # ---------------------------------------------------------------- 줄마다 [확인 완료] (그날만 기억)
    CHECK_FILE = op.DATA / "courier_checks.json"

    def _check_key(self, name, line):
        line = line.replace(" ✎", "").strip()
        return line.split(" / ")[0] if name == MSG else line      # 배송메세지는 고치면 글이 바뀌므로 주문번호로

    def _load_checks(self):
        d = op.read_json(self.CHECK_FILE, {})
        return d.get("done", {}) if d.get("date") == dt.date.today().isoformat() else {}

    def _save_check(self, name, key, on):
        d = self._day()
        done = d.setdefault("done", {})
        keys = set(done.get(name, []))
        (keys.add if on else keys.discard)(key)
        done[name] = sorted(keys)
        op.write_json(self.CHECK_FILE, d)

    def _add_checks(self, name):
        """줄 끝마다 [확인 완료] — 누르면 줄 전체가 초록색, 다시 누르면 취소. 다음 날이면 모두 지워짐"""
        t = self.texts[name]
        done = set(self._load_checks().get(name, []))
        state = t.cget("state")
        t.configure(state="normal")
        n = int(t.index("end-1c").split(".")[0])
        for i in range(1, n + 1):
            line = t.get(f"{i}.0", f"{i}.end")
            if not line.strip() or line.strip() == "(없음)":
                continue
            if name in EDIT_BOXES:
                orig = self.box_lines[name][i - 1] if i - 1 < len(self.box_lines.get(name, [])) else line
                if self._line_edits(name).get(orig) == "":
                    continue                                   # 지운 줄은 확인 버튼 없음
                key = orig
            else:
                key = self._check_key(name, line)
            lb = tk.Label(t, text="확인 완료", font=T.f(7, True), padx=6, pady=0, bd=0, cursor="hand2")

            def paint(on, i=i, lb=lb):
                (t.tag_add if on else t.tag_remove)("done", f"{i}.0", f"{i}.0 lineend +1c")
                lb.configure(text="✓ 확인 완료" if on else "확인 완료", bg=T.GREEN if on else "#EFEFEC",
                             fg="white" if on else T.MUTED)

            def toggle(e, i=i, key=key, paint=paint):
                on = "done" not in t.tag_names(f"{i}.0")
                paint(on)
                self._save_check(name, key, on)
            lb.bind("<Button-1>", toggle)
            t.window_create(f"{i}.end", window=lb, padx=10, align="center")
            paint(key in done)
        t.configure(state=state)

    # ---------------------------------------------------------------- 중요 배송메세지 지우기·고치기
    def _fill_messages(self, r):
        """미리 확인 결과로 배송메세지 칸을 다시 그림 (지운 줄=회색, 고친 메세지=형광펜). 파일을 만든 뒤에는 보기만"""
        self._end_edit(False)
        a = (r or {}).get("analysis")
        if not a:
            return
        self.msg_rows = list(a["messages"])
        self.msg_editable = not r.get("path")
        t = self.texts[MSG]
        t.configure(state="normal"); t.delete("1.0", "end")
        for i, row in enumerate(self.msg_rows):
            oid, orig, cur, st = op.msg_state(row)
            if i:
                t.insert("end", "\n")
            start = t.index("end-1c")
            t.insert("end", f"{oid} / ")
            shown = "(배송메세지 지움)" if st == "deleted" else str(cur).replace("\n", " ")
            t.insert("end", shown, ("edited",) if st == "edited" else ())
            if st == "edited":
                t.insert("end", " ✎", ("mark",))
            if st == "deleted":
                t.tag_add("deleted", start, "end-1c")
        if not self.msg_rows:
            t.insert("1.0", "(없음)")
        else:
            self._add_checks(MSG)
        t.configure(state="disabled")
        self._fit(MSG)

    def _msg_at(self, e):
        t = self.texts[MSG]
        i = int(t.index(f"@{e.x},{e.y}").split(".")[0]) - 1
        return i if 0 <= i < len(self.msg_rows) else None

    def _msg_menu(self, e):
        i = self._msg_at(e)
        if i is None:
            return
        if not self.msg_editable:
            self.app.flash("이미 만든 택배 파일의 메세지는 바꿀 수 없습니다. 대기 주문 미리 확인에서 바꿔 주세요.")
            return
        t = self.texts[MSG]
        t.tag_remove("cur", "1.0", "end"); t.tag_add("cur", f"{i + 1}.0", f"{i + 1}.end")
        m = tk.Menu(self, tearoff=0, font=T.f(10))
        m.add_command(label="배송 메세지 삭제", command=lambda: self._msg_set(i, ""))
        m.add_command(label="배송 메세지 수정", command=lambda: self._msg_edit(i))
        if self.msg_rows[i].get("msgState"):
            m.add_separator()
            m.add_command(label="원래 메세지로 되돌리기", command=lambda: self._msg_set(i, None))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()
            self.after(300, lambda: t.tag_remove("cur", "1.0", "end"))

    def _msg_set(self, i, new):
        """new="" 지우기, 글=고치기, None=되돌리기"""
        row = self.msg_rows[i]
        oid, orig, _, _ = op.msg_state(row)
        if new is not None and new.strip() == str(orig).replace("\n", " ").strip():
            new = None                                   # 원래와 같으면 되돌리기
        op.set_msg_edit(oid, orig, None if new is None else new.strip())
        row["origNote"] = orig
        if new is None:
            row["note"] = orig; row.pop("msgState", None)
            self.app.flash(f"{oid} 배송메세지를 원래대로 되돌렸습니다.")
        elif not new.strip():
            row["note"] = "0"; row["msgState"] = "deleted"
            self.app.flash(f"{oid} 배송메세지를 지웠습니다 (택배 파일에 '0'으로 들어갑니다).")
        else:
            row["note"] = new.strip(); row["msgState"] = "edited"
            self.app.flash(f"{oid} 배송메세지를 고쳤습니다.")
        self._fill_messages(self.last)

    def _msg_edit(self, i):
        """그 줄의 배송메세지 부분만 입력칸으로 바꾸고 글자를 블록으로 잡음. Enter·다른 곳 누르기=저장, Esc=취소"""
        if i is None:
            return
        if not self.msg_editable:
            self.app.flash("이미 만든 택배 파일의 메세지는 바꿀 수 없습니다. 대기 주문 미리 확인에서 바꿔 주세요.")
            return
        self._end_edit(True)
        t = self.texts[MSG]
        line = i + 1
        pos = t.search(" / ", f"{line}.0", f"{line}.end")
        if not pos:
            return
        start = f"{pos}+3c"
        row = self.msg_rows[i]
        _, orig, cur, st = op.msg_state(row)
        before = str(orig if st == "deleted" else cur).replace("\n", " ")

        def save(val, i=i, before=before):
            if i < len(self.msg_rows) and val.strip() != before.strip():   # 안 바꿨으면 그대로
                self._msg_set(i, val)
        self._open_editor(t, start, before, save)

    def _open_editor(self, t, start, value, on_save):
        """start 위치부터 줄 끝까지를 입력칸으로 덮고 글자를 블록으로 잡음. Enter·다른 곳 누르기=저장, Esc=취소"""
        t.see(start); t.update_idletasks()
        box, line_box = t.bbox(start), t.dlineinfo(start)
        if not box or not line_box:
            return
        x = box[0]
        y, h = line_box[1], line_box[3]                  # 줄 전체 높이에 맞춤
        ent = tk.Entry(t, font=T.f(9), relief="flat", bd=0, bg=T.CARD, fg=T.INK, highlightthickness=1,
                       highlightbackground=T.GREEN, highlightcolor=T.GREEN, selectbackground=T.HILITE,
                       selectforeground=T.INK, insertwidth=1)
        ent.insert(0, value)
        ent.place(x=x - 2, y=y, width=max(120, t.winfo_width() - x - 6), height=h, bordermode="outside")
        ent.focus_set()
        ent.select_range(0, "end"); ent.icursor("end")
        self._editor = (ent, on_save)
        ent.bind("<Return>", lambda e: (self._end_edit(True), "break")[1])
        ent.bind("<KP_Enter>", lambda e: (self._end_edit(True), "break")[1])
        ent.bind("<Escape>", lambda e: (self._end_edit(False), "break")[1])
        ent.bind("<FocusOut>", lambda e: self.after(1, lambda: self._end_edit(True)))

    def _end_edit(self, save):
        if not self._editor:
            return
        ent, on_save = self._editor
        self._editor = None
        try:
            val = ent.get()
            ent.destroy()
        except tk.TclError:
            return
        if save:
            on_save(val)

    # ---------------------------------------------------------------- 묶음배송·제주도·수제 제작: 줄 지우기·고치기 (화면·복사만)
    def _day(self):
        d = op.read_json(self.CHECK_FILE, {})
        return d if d.get("date") == dt.date.today().isoformat() else {"date": dt.date.today().isoformat()}

    def _line_edits(self, name):
        return self._day().get("edits", {}).get(name, {})

    def _set_line_edit(self, name, orig, new):
        """new="" 지우기, 글=고치기, None=되돌리기. 그날만 기억"""
        d = self._day()
        e = d.setdefault("edits", {}).setdefault(name, {})
        if new is None or new.strip() == orig.strip():
            e.pop(orig, None)
        else:
            e[orig] = new.strip()
        op.write_json(self.CHECK_FILE, d)

    def _render_edit_box(self, name, text):
        t = self.texts[name]
        lines = [l for l in str(text or "").split("\n") if l.strip()]
        self.box_lines[name] = lines
        edits = self._line_edits(name)
        t.delete("1.0", "end")
        for i, orig in enumerate(lines):
            if i:
                t.insert("end", "\n")
            e = edits.get(orig)
            if e is None:
                t.insert("end", orig)
            elif e == "":
                t.insert("end", f"(지움) {orig}", ("deleted",))
            else:
                t.insert("end", e, ("edited",)); t.insert("end", " ✎", ("mark",))
        if not lines:
            t.insert("1.0", "(없음)")
        else:
            self._add_checks(name)

    def _line_at(self, name, e):
        t = self.texts[name]
        i = int(t.index(f"@{e.x},{e.y}").split(".")[0]) - 1
        return i if 0 <= i < len(self.box_lines.get(name, [])) else None

    def _line_menu(self, name, e):
        i = self._line_at(name, e)
        if i is None:
            return
        t = self.texts[name]
        orig = self.box_lines[name][i]
        t.tag_remove("cur", "1.0", "end"); t.tag_add("cur", f"{i + 1}.0", f"{i + 1}.end")
        m = tk.Menu(self, tearoff=0, font=T.f(10))
        m.add_command(label="삭제", command=lambda: self._line_set(name, i, ""))
        m.add_command(label="수정", command=lambda: self._line_edit(name, i))
        if orig in self._line_edits(name):
            m.add_separator()
            m.add_command(label="원래대로 되돌리기", command=lambda: self._line_set(name, i, None))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()
            self.after(300, lambda: t.tag_remove("cur", "1.0", "end"))

    def _line_set(self, name, i, new):
        orig = self.box_lines[name][i]
        self._set_line_edit(name, orig, new)
        t = self.texts[name]
        t.configure(state="normal")
        self._render_edit_box(name, "\n".join(self.box_lines[name]))
        t.configure(state="disabled")
        self._fit(name)
        self.app.flash("줄을 되돌렸습니다." if new is None else "줄을 지웠습니다 (화면·복사에서만)." if not new.strip()
                       else "줄을 고쳤습니다 (화면·복사에서만).")

    def _line_edit(self, name, i):
        if i is None:
            return
        self._end_edit(True)
        orig = self.box_lines[name][i]
        cur = self._line_edits(name).get(orig) or orig

        def save(val):
            if val.strip() != cur.strip():
                self._line_set(name, i, val if val.strip() else "")
        self._open_editor(self.texts[name], f"{i + 1}.0", cur, save)

    def copy(self, name):
        alt = getattr(self, "copy_texts", {}).get(name) or ""   # 따로 정한 복사 양식 (수제 제작: 상품명 전체, 이전 주문 묶음: 묶음배송 모양)
        if name in EDIT_BOXES and self.box_lines.get(name):
            ed = self._line_edits(name)
            full = alt.split("\n") if alt else []
            out = []
            for k, l in enumerate(self.box_lines[name]):
                if ed.get(l, None) == "":
                    continue                                  # 지운 줄은 복사에서 뺌
                out.append(ed.get(l) or (full[k] if k < len(full) else l))
            v = "\n".join(out)
        elif alt:
            v = alt
        else:
            v = self.texts[name].get("1.0", "end").strip()
        if v and v != "(없음)":
            self.clipboard_clear(); self.clipboard_append(v)
            self.app.flash(f"'{name}' 내용을 복사했습니다.")

    def open_file(self):
        if self.last and self.last.get("path"):
            op.open_file(self.last["path"])
        else:
            op.open_file(op.COURIER_DIR)

    def show_hist(self):
        i = self.hist.current()
        h = op.load_courier_history()[i]
        self._fill(h.get("texts", {}))
        self.res_title.configure(text=f"확인 목록 — {h['time'][5:16].replace('T', ' ')} 택배 파일")
        self.last = {"path": h["file"]}
        if h.get("extra_only"):              # 추가배송만 만든 파일 — 라벨은 그대로 둠
            self.res_title.configure(text=f"확인 목록 — {h['time'][5:16].replace('T', ' ')} 추가배송만 만든 택배 파일")
            return
        self.app.label_tab.set_target(ids=h.get("orders", []), split_n=h.get("split_orders", 0),
                                      title=f"{h['time'][5:16].replace('T', ' ')} 택배 파일의 주문 {len(h.get('orders', []))}건")

    def auto_preview(self, force=False):
        """대기 주문으로 확인 목록과 라벨을 조용히 미리보기 (팝업 없음, 대기 목록이 바뀌었을 때만)"""
        cand = op.courier_candidates()
        ids = [o["order_id"] for o, _ in cand]
        today = dt.date.today().isoformat()
        key = (tuple(ids), op.split_on(), today)            # 날짜가 바뀌면 다시 확인
        if not ids or self.app.busy or (key == self._auto_key and not force):
            if not ids and key != self._auto_key:
                self._auto_key = key
                # 대기 주문이 없으면 오늘 마지막으로 만든 택배 파일의 확인 목록을 그대로 보여 줌 (다음 날이면 비움)
                h = next((h for h in op.load_courier_history() if str(h.get("time", "")).startswith(today) and not h.get("extra_only")), None)
                if h:
                    self._fill(h.get("texts", {}))
                    self.last = {"path": h["file"]}
                    self.res_title.configure(text=f"확인 목록 — {h['time'][5:16].replace('T', ' ')} 만든 택배 파일")
                else:
                    self.res_title.configure(text="확인 목록 — 대기 주문 없음")
                    self._fill({})
                self.app.label_tab.waiting_preview(None)
            return
        self._auto_key = key
        self._gen += 1
        gen = self._gen
        self.res_title.configure(text="확인 목록 — 대기 주문 불러오는 중...")

        def work():
            return op.make_courier(self.app.cfg, op.get_access_token(self.app.cfg), ids, False)

        def done(r):
            if gen != self._gen:
                return                      # 그사이 택배 파일을 만들거나 다시 미리 봄
            self.last = r
            self._fill(r["texts"])
            self._fill_messages(r)
            a = r["analysis"]
            self.res_title.configure(text=f"확인 목록 — 대기 주문 {len(r['orders'])}건 자동 미리 확인 (파일 안 만듦)")
            self.stat.configure(text=f"대기 주문 {len(r['orders'])}건 · 묶음배송 {len(a['bundle'])}묶음 · "
                                     f"블랙리스트·경계대상 {len(a['blacklist'])}건"
                                     + (f" · 추가배송 {len(a['extra'])}건" if a["extra"] else "")
                                     + ("\n" + "\n".join(r["warnings"]) if r["warnings"] else ""))
            self.app.label_tab.waiting_preview(r)

        def failed(e):
            if gen == self._gen:
                self._auto_key = None
                self.res_title.configure(text="확인 목록 — 자동 미리 확인 실패 ([미리 확인]을 눌러 다시)")
                op.log.warning(f"[자동 미리 확인] 실패: {e}")

        def safe():
            try:
                return ("ok", work())
            except Exception as e:
                return ("err", e)
        self.app.bg(safe, lambda res: done(res[1]) if res[0] == "ok" else failed(res[1]), busy=False)

    def run(self, create):
        self._gen += 1                      # 진행 중인 자동 미리보기 결과는 버림
        cand = op.courier_candidates()
        if not cand:
            messagebox.showinfo("택배 파일", "택배 파일을 만들 대기 주문이 없습니다.\n(주문서를 먼저 출력해 주세요)")
            return
        ids = [o["order_id"] for o, _ in cand]
        if create and not messagebox.askyesno(
                "택배 파일 만들기", f"대기 주문 {len(ids)}건으로 택배 파일을 만듭니다.\n\n"
                                  "· 구글 시트의 추가배송은 파일에 들어가고 시트에서 지워집니다.\n"
                                  "· 만든 주문은 대기 목록에서 빠집니다.\n\n계속할까요?"):
            return

        def work(prog):
            token = op.get_access_token(self.app.cfg)
            if create:
                with op.run_lock():
                    return op.make_courier(self.app.cfg, token, ids, True, prog)
            return op.make_courier(self.app.cfg, token, ids, False, prog)

        def done(r):
            self.last = r
            self._auto_key = None if create else (tuple(ids), op.split_on(), dt.date.today().isoformat())
            if create:
                self.app.label_tab.set_target(rows=r["rows"], title=f"방금 만든 택배 파일의 주문 {len(r['orders'])}건")
            else:
                self.app.label_tab.waiting_preview(r)
            a = r["analysis"]
            self._fill(r["texts"])
            self._fill_messages(r)
            self.res_title.configure(text="확인 목록 — " + ("방금 만든 택배 파일" if create else "미리 확인 (파일 안 만듦)"))
            n_orders = len(r["orders"])
            sp = r.get("split_orders", 0)
            info = (f"주문 {n_orders}건 → 택배 {len(a['rows'])}건"
                    + (f" (추가배송 {len(a['extra'])}건 포함)" if a["extra"] else "")
                    + (f"\n스마트스토어 따로 작업: 스마트스토어 쪽 {sp}건이 맨 앞 (엑셀 2~{sp + 1}번째 줄)" if sp else "")
                    + f"\n묶음배송 {len(a['bundle'])}묶음 · 블랙리스트·경계대상 {len(a['blacklist'])}건"
                    + (f"\n인쇄 후 취소되어 뺀 주문 {len(r['excluded'])}건: {', '.join(r['excluded'][:5])}" if r["excluded"] else ""))
            if r["path"]:
                info = f"{Path(r['path']).name} 저장\n" + info
            self.stat.configure(text=info)
            for w in r["warnings"]:
                messagebox.showwarning("확인 필요", w)
            if a["blacklist"]:
                messagebox.showwarning("블랙리스트·경계대상 발견", r["texts"]["블랙리스트·경계대상"])
            if r["popup"]:
                messagebox.showinfo("확인해 주세요", r["popup"])
            if r["path"]:                                   # 폴더는 열지 않음 (필요하면 [만든 파일 열기]·[폴더 열기])
                self.app.flash(f"택배 파일을 만들었습니다: {Path(r['path']).name}")
            self.refresh()
            self.app.refresh_status()
        self.app.bg(work, done, "카페24에서 주문 불러오는 중...", progress=True)


class Tip:
    """마우스를 올리면 설명 상자를 띄움"""

    def __init__(self, widget, text, wrap=360):
        self.w, self.text, self.wrap, self.top = widget, text, wrap, None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _=None):
        if self.top:
            return
        x = self.w.winfo_rootx() + self.w.winfo_width() + 6
        y = self.w.winfo_rooty() - 4
        self.top = tk.Toplevel(self.w)
        self.top.wm_overrideredirect(True)
        self.top.attributes("-topmost", True)
        tk.Label(self.top, text=self.text, justify="left", wraplength=self.wrap, font=T.f(9), bg="#FFFFFF", fg=T.INK,
                 relief="solid", bd=1, padx=8, pady=6).pack()
        self.top.geometry(f"+{x}+{y}")

    def hide(self, _=None):
        if self.top:
            self.top.destroy()
            self.top = None

