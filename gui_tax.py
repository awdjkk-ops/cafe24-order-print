# -*- coding: utf-8 -*-
"""통합 창 - '세금계산서 발행' 탭
위: 요청 목록(발행 대기) — 같은 사업자의 같은 달 주문은 한 장으로 자동 합침
아래: 발행 완료 내역 (항상 보임)
건별 발급: [건별 발급 도우미]에서 칸마다 [복사] → 홈택스에 붙여넣기
일괄 발급: [일괄발급 엑셀 만들기] → 홈택스 '전자세금계산서 일괄 작성'에 올리기"""
import datetime as dt
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import order_print as op
import tax as X
import theme as T
from gui_schedule import hint


def _center(win, app, dy=3):
    win.update_idletasks()
    x = app.winfo_rootx() + (app.winfo_width() - win.winfo_width()) // 2
    y = app.winfo_rooty() + (app.winfo_height() - win.winfo_height()) // dy
    win.geometry(f"+{max(0, x)}+{max(0, y)}")


def _dialog(app, title):
    w = tk.Toplevel(app)
    w.title(title)
    w.configure(background=T.CARD)
    w.transient(app.winfo_toplevel())
    return w


def _date_txt(d):
    return d.isoformat() if isinstance(d, dt.date) else str(d or "")


# ====================================================================== 탭
class TaxTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=12, style="Page.TFrame")
        self.app = app
        self.d = X.load()
        self.groups = []          # 대기 묶음 (화면에 보이는 순서)
        self.invoices = []        # 발행 완료 (화면에 보이는 순서)
        self.helper = None
        self.columnconfigure(0, weight=1)

        # ---- 머리
        head = ttk.Frame(self, style="Page.TFrame"); head.grid(row=0, column=0, sticky="we")
        ttk.Label(head, text="세금계산서 발행", style="PageTitle.TLabel").pack(side="left")
        for txt, cmd in (("전체 내역 엑셀로 저장", self.export_all), ("기존 엑셀 가져오기", self.import_excel),
                         ("우리 회사 정보", self.edit_supplier), ("사업자 목록", self.open_biz_list)):
            ttk.Button(head, text=txt, style="Page.TButton", command=cmd).pack(side="right", padx=(6, 0))
        self.alert_fr = ttk.Frame(self, style="Page.TFrame"); self.alert_fr.grid(row=1, column=0, sticky="we")
        hint(self, "고객이 세금계산서를 요청하면 [요청 추가]로 넣어 두고, 매달 10일 전에 한꺼번에 발행합니다. "
                   "같은 사업자의 같은 달 주문은 자동으로 한 장(한 줄)으로 합쳐지고 총발행금액이 계산됩니다. "
                   "합친 내용은 이 프로그램 안에서만 보이고 홈택스에는 들어가지 않습니다.",
             page=True, row=2, column=0, sticky="w", pady=(6, 8), wrap=1100)

        # ---- 요청 목록
        wf = ttk.LabelFrame(self, text=" 요청 목록 (발행 대기) ", padding=12)
        wf.grid(row=3, column=0, sticky="nsew")
        wf.columnconfigure(0, weight=1)
        bar = ttk.Frame(wf); bar.grid(row=0, column=0, sticky="we")
        ttk.Button(bar, text="+ 요청 추가", style="Accent.TButton", command=self.add_request).pack(side="left")
        ttk.Button(bar, text="수정", command=self.edit_request).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="작성일자", command=self.change_date).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="삭제", command=self.delete_request).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="발행완료", style="Accent.TButton", command=self.mark_done).pack(side="right")
        ttk.Button(bar, text="일괄발급 엑셀 만들기", style="Ghost.TButton", command=self.make_excel).pack(side="right", padx=6)
        ttk.Button(bar, text="건별 발급 도우미", style="Ghost.TButton", command=self.open_helper).pack(side="right")
        cols = (("customer", "고객명", 110), ("company", "상호", 150), ("oid", "주문번호", 150), ("amount", "금액", 90),
                ("memo", "메모", 140), ("total", "총발행금액", 100), ("wdate", "작성일자", 95), ("state", "상태", 220))
        self.wtree = self._tree(wf, cols, 1, height=9)
        self.wtree.bind("<Double-1>", lambda e: self.edit_request())
        self.wcount = ttk.Label(wf, text="", style="Hint.TLabel"); self.wcount.grid(row=2, column=0, sticky="w", pady=(6, 0))
        hint(wf, "· 굵은 줄 하나가 계산서 한 장입니다. 주문이 여러 건이면 아래에 주문별 줄이 붙고 '○건 합침'으로 표시됩니다.\n"
                 "· 작성일자: 기본은 그 묶음의 마지막 주문일. [작성일자]에서 첫 주문일이나 직접 고른 날짜로 바꿀 수 있습니다.\n"
                 "· 건별 발급 도우미: 고른 계산서를 홈택스 화면 순서대로 칸마다 [복사]해서 붙여넣습니다.\n"
                 "· 일괄발급 엑셀 만들기: 고른 계산서(안 고르면 전체)를 홈택스 일괄 작성 양식으로 저장합니다. "
                 "발급이 끝나면 [발행완료]를 눌러 아래로 옮깁니다. (줄을 고를 때 Ctrl·Shift+클릭으로 여러 개)",
             row=3, column=0, sticky="w", pady=(4, 0), wrap=1100)
        menu = tk.Menu(self, tearoff=0, font=T.f(10))
        menu.add_command(label="수정", command=self.edit_request)
        menu.add_command(label="작성일자 바꾸기", command=self.change_date)
        menu.add_command(label="이 주문만 따로 발행 / 다시 합치기", command=self.toggle_split)
        menu.add_separator()
        menu.add_command(label="건별 발급 도우미", command=self.open_helper)
        menu.add_command(label="발행완료", command=self.mark_done)
        menu.add_separator()
        menu.add_command(label="삭제", command=self.delete_request)
        self._popup(self.wtree, menu)

        # ---- 발행 완료
        df = ttk.LabelFrame(self, text=" 발행 완료 내역 ", padding=12)
        df.grid(row=4, column=0, sticky="nsew", pady=(14, 0))
        df.columnconfigure(0, weight=1)
        sb = ttk.Frame(df); sb.grid(row=0, column=0, sticky="we")
        ttk.Label(sb, text="찾기").pack(side="left")
        self.find = ttk.Entry(sb, width=22); self.find.pack(side="left", padx=6)
        self.find.bind("<KeyRelease>", lambda e: self.show_done())
        ttk.Label(sb, text="기간").pack(side="left", padx=(10, 0))
        self.period = ttk.Combobox(sb, state="readonly", width=12); self.period.pack(side="left", padx=6)
        self.period.bind("<<ComboboxSelected>>", lambda e: self.show_done())
        ttk.Button(sb, text="대기로 되돌리기", command=self.undo_done).pack(side="right")
        ttk.Button(sb, text="내용 보기", command=self.view_done).pack(side="right", padx=6)
        cols = (("customer", "고객명", 110), ("company", "상호", 150), ("oid", "주문번호", 150), ("amount", "금액", 90),
                ("memo", "메모", 140), ("total", "총발행금액", 100), ("wdate", "작성일자", 95), ("how", "발행", 220))
        self.dtree = self._tree(df, cols, 1, height=10)
        self.dtree.bind("<Double-1>", lambda e: self.view_done())
        self.dcount = ttk.Label(df, text="", style="Hint.TLabel"); self.dcount.grid(row=2, column=0, sticky="w", pady=(6, 0))
        hint(df, "고객명·상호·주문번호·사업자번호 일부로 찾을 수 있습니다. 실수로 완료 처리했으면 [대기로 되돌리기]. "
                 "'사업자 정보 없음'은 예전 엑셀에 사업자 정보가 비어 있던 내역입니다.",
             row=3, column=0, sticky="w", pady=(4, 0), wrap=1100)
        dmenu = tk.Menu(self, tearoff=0, font=T.f(10))
        dmenu.add_command(label="내용 보기", command=self.view_done)
        dmenu.add_command(label="대기로 되돌리기", command=self.undo_done)
        self._popup(self.dtree, dmenu)
        self.refresh()

    # ---------------------------------------------------------------- 공통
    def _tree(self, parent, cols, row, height):
        fr = ttk.Frame(parent); fr.grid(row=row, column=0, sticky="nsew", pady=(8, 0))
        fr.columnconfigure(0, weight=1)
        tv = ttk.Treeview(fr, columns=[c[0] for c in cols], show="tree headings", height=height, selectmode="extended")
        tv.column("#0", width=22, minwidth=22, stretch=False)
        for c, txt, w in cols:
            tv.heading(c, text=txt)
            tv.column(c, width=w, anchor="e" if c in ("amount", "total") else "w", stretch=c in ("memo", "state", "how"))
        tv.tag_configure("group", font=T.f(10, True))
        tv.tag_configure("sub", foreground=T.MUTED)
        tv.tag_configure("bad", foreground=T.ORANGE)
        tv.tag_configure("dim", foreground=T.DIM)
        tv.grid(row=0, column=0, sticky="nsew")
        s = ttk.Scrollbar(fr, orient="vertical", command=tv.yview); s.grid(row=0, column=1, sticky="ns")
        tv.configure(yscrollcommand=s.set)
        return tv

    def _popup(self, tv, menu):
        def pop(e):
            row = tv.identify_row(e.y)
            if row and row not in tv.selection():
                tv.selection_set(row)
            if tv.selection():
                menu.tk_popup(e.x_root, e.y_root)
        tv.bind("<Button-3>", pop)

    def save(self):
        X.save(self.d)
        self.refresh()

    def refresh(self):
        self.show_waiting()
        self.show_done()
        self.show_alert()
        if self.helper and self.helper.winfo_exists():
            self.helper.reload()

    def show_alert(self):
        for w in self.alert_fr.winfo_children():
            w.destroy()
        n, due, late = X.deadline_info(self.d)
        if n:
            msg = (f"[마감 확인] 지난달까지의 요청 {n}장이 아직 발행 대기입니다 — "
                   + (f"이번 달 마감일({due.month}/{due.day})이 지났어요. 확인해 주세요" if late
                      else f"{due.month}월 {due.day}일까지 발행하세요"))
            T.alert(self.alert_fr, msg).pack(fill="x", pady=(8, 0))

    # ---------------------------------------------------------------- 대기 목록
    def show_waiting(self):
        sel = set(self.wtree.selection())
        self.wtree.delete(*self.wtree.get_children())
        self.groups = X.waiting_groups(self.d)
        for g in self.groups:
            n = len(g["lines"])
            first = g["lines"][0]
            if g["problems"]:
                state = "⚠ " + " · ".join(g["problems"])
            elif g["excel_at"]:
                state = f"엑셀 만듦 {g['excel_at'][5:10].replace('-', '/')} · 발급 후 [발행완료]"
            else:
                state = "발행 준비됨"
            if g["cards"]:
                state += f" · 카드결제 {g['cards']}건"
            if any(l.get("split") for l in g["lines"]):
                state += " · 따로 발행"
            iid = "g:" + g["key"]
            vals = (g["customer"], g["company"] or "(상호 없음)", first.get("oid") if n == 1 else f"주문 {n}건 합침",
                    X.won(first.get("amount")) if n == 1 else "", first.get("memo", "") if n == 1 else "",
                    X.won(g["total"]), _date_txt(g["date"]), state)
            self.wtree.insert("", "end", iid=iid, open=True, values=vals,
                              tags=("group", "bad") if g["problems"] else ("group",))
            if n > 1:
                for l in g["lines"]:
                    self.wtree.insert(iid, "end", iid="l:" + l["id"], tags=("sub",),
                                      values=("", "", l.get("oid"), X.won(l.get("amount")), l.get("memo", ""), "",
                                              str(l.get("date") or "")[5:].replace("-", "/") + " 주문", l.get("pay", "")))
        keep = [i for i in sel if self.wtree.exists(i)]
        if keep:
            self.wtree.selection_set(keep)
        total = sum(g["total"] for g in self.groups)
        self.wcount.configure(text=f"계산서 {len(self.groups)}장 · 주문 {sum(len(g['lines']) for g in self.groups)}건 · "
                                   f"합계 {X.won(total)}원" if self.groups else "발행 대기 중인 요청이 없습니다.")

    def selected_groups(self, allow_all=False):
        keys = []
        for iid in self.wtree.selection():
            if iid.startswith("l:"):
                iid = self.wtree.parent(iid)
            if iid not in keys:
                keys.append(iid)
        keys = [k[2:] for k in keys]
        gs = [g for g in self.groups if g["key"] in keys]
        if not gs and allow_all:
            return None
        return gs

    def selected_line(self):
        sel = self.wtree.selection()
        if len(sel) == 1 and sel[0].startswith("l:"):
            return X.line_by_id(self.d, sel[0][2:])
        gs = self.selected_groups()
        if len(gs) == 1 and len(gs[0]["lines"]) == 1:
            return gs[0]["lines"][0]
        return None

    def add_request(self):
        RequestDialog(self, None)

    def edit_request(self):
        gs = self.selected_groups()
        if len(gs) != 1:
            messagebox.showinfo("수정", "요청 목록에서 고칠 계산서(굵은 줄) 하나를 골라 주세요.")
            return
        RequestDialog(self, gs[0])

    def delete_request(self):
        sel = self.wtree.selection()
        if not sel:
            messagebox.showinfo("삭제", "요청 목록에서 지울 줄을 골라 주세요.")
            return
        ids = set()
        for iid in sel:
            if iid.startswith("l:"):
                ids.add(iid[2:])
            else:
                g = next((g for g in self.groups if "g:" + g["key"] == iid), None)
                ids.update(l["id"] for l in (g or {"lines": []})["lines"])
        lines = [l for l in self.d["lines"] if l["id"] in ids]
        txt = "\n".join(f"· {l.get('customer') or l.get('company')}  {l.get('oid') or '(주문번호 없음)'}  {X.won(l.get('amount'))}원"
                        for l in lines[:12]) + ("\n…" if len(lines) > 12 else "")
        if not messagebox.askyesno("삭제", f"요청 {len(lines)}건을 지울까요?\n\n{txt}\n\n사업자 정보는 그대로 남습니다."):
            return
        self.d["lines"] = [l for l in self.d["lines"] if l["id"] not in ids]
        op.log.info(f"[세금계산서] 요청 {len(lines)}건 삭제")
        self.save()

    def change_date(self):
        gs = self.selected_groups()
        if len(gs) != 1:
            messagebox.showinfo("작성일자", "요청 목록에서 계산서(굵은 줄) 하나를 골라 주세요.")
            return
        DateDialog(self, gs[0])

    def toggle_split(self):
        line = self.selected_line()
        gs = self.selected_groups()
        if not line and len(gs) == 1 and any(l.get("split") for l in gs[0]["lines"]):
            line = next(l for l in gs[0]["lines"] if l.get("split"))
        if not line:
            messagebox.showinfo("따로 발행", "합쳐진 계산서 아래의 주문 줄 하나를 골라 주세요.")
            return
        line["split"] = not line.get("split")
        self.save()
        self.app.flash("이 주문은 따로 한 장으로 발행합니다." if line["split"] else "같은 달 주문과 다시 합쳤습니다.")

    def open_helper(self):
        gs = self.selected_groups(allow_all=True)
        if gs is None:
            gs = list(self.groups)
        if not gs:
            messagebox.showinfo("건별 발급 도우미", "발행 대기 중인 요청이 없습니다.")
            return
        if self.helper and self.helper.winfo_exists():
            self.helper.destroy()
        self.helper = HelperWindow(self, [g["key"] for g in gs])

    def make_excel(self):
        gs = self.selected_groups(allow_all=True)
        if gs is None:
            gs = list(self.groups)
            if not gs:
                messagebox.showinfo("일괄발급 엑셀", "발행 대기 중인 요청이 없습니다.")
                return
            if not messagebox.askyesno("일괄발급 엑셀", f"고른 줄이 없어서 발행 대기 전체 {len(gs)}장으로 만듭니다. 계속할까요?"):
                return
        bad = [g for g in gs if g["problems"]]
        ok = [g for g in gs if not g["problems"]]
        if bad:
            txt = "\n".join(f"· {g['company'] or g['customer']}: {' · '.join(g['problems'])}" for g in bad[:10])
            if not ok:
                messagebox.showwarning("일괄발급 엑셀", f"고른 계산서에 고쳐야 할 내용이 있어 만들 수 없습니다.\n\n{txt}")
                return
            if not messagebox.askyesno("일괄발급 엑셀", f"다음 {len(bad)}장은 고쳐야 할 내용이 있어 빼고 만듭니다.\n\n{txt}\n\n"
                                                    f"나머지 {len(ok)}장으로 만들까요?"):
                return
        cards = sum(g["cards"] for g in ok)
        msg = (f"계산서 {len(ok)}장 · 합계 {X.won(sum(g['total'] for g in ok))}원을 홈택스 일괄발급 엑셀로 만듭니다.\n"
               f"(공급가액·세액은 홈택스 [계산] 버튼과 같은 방식으로 나눕니다)")
        if cards:
            msg += f"\n\n※ 카드결제 주문이 {cards}건 있습니다. 카드 매출전표가 이미 증빙이라 보통은 따로 발행하지 않아요."
        if not messagebox.askyesno("일괄발급 엑셀", msg + "\n\n계속할까요?"):
            return
        paths = X.make_hometax_excel(self.d, ok)
        X.mark_excel_made(self.d, ok)
        op.log.info(f"[세금계산서] 일괄발급 엑셀 {len(ok)}장 → {', '.join(p.name for p in paths)}")
        self.save()
        messagebox.showinfo("일괄발급 엑셀 완료",
                            f"{', '.join(p.name for p in paths)}\n\n파일을 만들었습니다. 이제 홈택스에서:\n"
                            "1. 계산서·영수증·카드 → 일괄/공동매입분 발급 → 전자(세금)계산서 일괄발급\n"
                            "2. 작업 구분 '파일등록(엑셀)' → [파일 선택]에서 이 파일 → [엑셀파일 변환하기]\n"
                            "3. 아래 목록에 나온 내용(상호·금액)을 확인하고 [일괄발급] → 인증서 서명\n"
                            "4. 발급이 끝나면 이 프로그램에서 그 계산서들을 골라 [발행완료]\n\n"
                            "(발급은 한 번에 50장까지입니다. 폴더를 엽니다)")
        op.open_file(X.OUT_DIR)

    def mark_done(self, keys=None):
        gs = [g for g in self.groups if g["key"] in keys] if keys else self.selected_groups()
        if not gs:
            messagebox.showinfo("발행완료", "홈택스에서 발급을 마친 계산서(굵은 줄)를 골라 주세요. (Ctrl·Shift+클릭으로 여러 개)")
            return False
        bad = [g for g in gs if "사업자 정보 없음" in g["problems"]]
        txt = "\n".join(f"· {g['company'] or g['customer']}  {_date_txt(g['date'])}  {X.won(g['total'])}원"
                        for g in gs[:12]) + ("\n…" if len(gs) > 12 else "")
        warn = f"\n\n※ {len(bad)}장은 사업자 정보가 없습니다." if bad else ""
        if not messagebox.askyesno("발행완료", f"홈택스에서 발급을 마친 계산서 {len(gs)}장을 '발행 완료'로 옮길까요?\n\n{txt}{warn}"):
            return False
        for g in gs:
            X.mark_done(self.d, g, "일괄발급" if g["excel_at"] else "건별발급")
        op.log.info(f"[세금계산서] 발행완료 {len(gs)}장")
        self.save()
        self.app.flash(f"계산서 {len(gs)}장을 발행 완료로 옮겼습니다.")
        return True

    # ---------------------------------------------------------------- 완료 목록
    def show_done(self):
        invs = X.done_invoices(self.d)
        months = sorted({str(i.get("date") or "")[:7] for i in invs if i.get("date")}, reverse=True)
        years = sorted({m[:4] for m in months}, reverse=True)
        values = ["전체"] + [f"{y}년" for y in years] + months
        cur = self.period.get() or "전체"
        self.period.configure(values=values)
        self.period.set(cur if cur in values else "전체")
        per = self.period.get()
        f = self.find.get().strip().lower()
        fd = X.digits(f)
        sel = set(self.dtree.selection())
        self.dtree.delete(*self.dtree.get_children())
        self.invoices = []
        for inv in invs:
            dtxt = str(inv.get("date") or "")
            if per != "전체" and not (dtxt.startswith(per[:4]) if per.endswith("년") else dtxt.startswith(per)):
                continue
            b = inv.get("biz") or {}
            if f:
                hay = " ".join([inv.get("customer", ""), inv.get("company", ""), b.get("name", ""), b.get("ceo", ""),
                                " ".join(l.get("oid", "") for l in inv["lines"])]).lower()
                if f not in hay and not (len(fd) >= 3 and fd in X.digits(b.get("bizno"))):
                    continue
            self.invoices.append(inv)
            n = len(inv["lines"])
            first = inv["lines"][0] if inv["lines"] else {}
            how = inv.get("how", "")
            if inv.get("issued_at"):
                how += f" · {inv['issued_at'][:10]}"
            if not b:
                how += " · 사업자 정보 없음"
            iid = "i:" + inv["id"]
            self.dtree.insert("", "end", iid=iid, open=False, tags=("group",),
                              values=(inv.get("customer", ""), inv.get("company") or b.get("name", ""),
                                      first.get("oid", "") if n == 1 else f"주문 {n}건 합침",
                                      X.won(first.get("amount")) if n == 1 else "", first.get("memo", "") if n == 1 else "",
                                      X.won(inv.get("total")), dtxt, how))
            if n > 1:
                for l in inv["lines"]:
                    self.dtree.insert(iid, "end", iid="dl:" + l["id"], tags=("sub",),
                                      values=("", "", l.get("oid"), X.won(l.get("amount")), l.get("memo", ""), "",
                                              str(l.get("date") or ""), ""))
        keep = [i for i in sel if self.dtree.exists(i)]
        if keep:
            self.dtree.selection_set(keep)
        self.dcount.configure(text=f"{len(self.invoices)}장 · 합계 {X.won(sum(int(i.get('total') or 0) for i in self.invoices))}원"
                                   + (f" (전체 {len(invs)}장 중)" if len(self.invoices) != len(invs) else ""))

    def _selected_invoices(self):
        ids = []
        for iid in self.dtree.selection():
            if iid.startswith("dl:"):
                iid = self.dtree.parent(iid)
            if iid[2:] not in ids:
                ids.append(iid[2:])
        return [i for i in self.invoices if i["id"] in ids]

    def undo_done(self):
        invs = self._selected_invoices()
        if not invs:
            messagebox.showinfo("대기로 되돌리기", "발행 완료 내역에서 되돌릴 계산서를 골라 주세요.")
            return
        txt = "\n".join(f"· {i.get('company') or i.get('customer')}  {i.get('date')}  {X.won(i.get('total'))}원" for i in invs[:10])
        if not messagebox.askyesno("대기로 되돌리기", f"계산서 {len(invs)}장을 다시 '발행 대기'로 옮길까요?\n\n{txt}\n\n"
                                                 "홈택스에서 이미 발급한 계산서는 그대로 있습니다 (이 프로그램의 표시만 바뀝니다)."):
            return
        for i in invs:
            X.undo_done(self.d, i["id"])
        self.save()

    def view_done(self):
        invs = self._selected_invoices()
        if len(invs) != 1:
            messagebox.showinfo("내용 보기", "발행 완료 내역에서 계산서 하나를 골라 주세요.")
            return
        InvoiceView(self, invs[0])

    # ---------------------------------------------------------------- 사업자·설정·가져오기
    def open_biz_list(self):
        BizListDialog(self)

    def edit_supplier(self):
        def done(info):
            self.d["supplier"] = info
            self.save()
            self.app.flash("우리 회사 정보를 저장했습니다.")
        BizDialog(self, dict(self.d["supplier"]), done, title="우리 회사 정보 (공급자)",
                  note="홈택스 일괄발급 엑셀의 공급자 칸에 들어갑니다. 홈택스에 등록된 정보와 같아야 합니다.")

    def import_excel(self):
        path = filedialog.askopenfilename(title="기존 세금계산서 엑셀 고르기",
                                          filetypes=[("엑셀 파일", "*.xlsx *.xlsm"), ("모든 파일", "*.*")])
        if not path:
            return
        again = any(i.get("imported") for i in self.d["invoices"])
        if again and not messagebox.askyesno("기존 엑셀 가져오기",
                                             "이미 기존 엑셀을 가져온 적이 있습니다. 그때 가져온 발행 내역은 지우고 "
                                             "이 파일로 다시 가져옵니다. (이 프로그램에서 직접 넣은 요청·발행 내역과 사업자 목록은 그대로)\n\n계속할까요?"):
            return
        try:
            st = X.import_excel(self.d, path)
        except Exception as e:
            op.log.exception("세금계산서 엑셀 가져오기 실패")
            messagebox.showerror("기존 엑셀 가져오기", f"가져오지 못했습니다.\n\n{e}")
            self.d = X.load()
            return
        self.save()
        op.log.info(f"[세금계산서] 기존 엑셀 가져오기: {st}")
        messagebox.showinfo("기존 엑셀 가져오기",
                            f"가져왔습니다.\n\n"
                            f"· 사업자 목록: 지금 {st['biz_total']}곳 (정보 7칸이 모두 있는 사업자만)\n"
                            f"· 발행 내역: 계산서 {st['groups']}장 · 주문 {st['lines']}줄\n"
                            f"   └ 사업자 정보가 없던 {st['no_biz'] + st['linked']}장 중 {st['linked']}장은 "
                            f"상호·고객명이 같은 사업자에 연결\n"
                            f"· 정보가 일부만 있어 사업자 목록에서 뺀 곳: {st['partial']}곳\n\n"
                            "모두 '발행 완료 내역'에 들어갔습니다.")

    def export_all(self):
        p = X.export_all(self.d)
        messagebox.showinfo("전체 내역 엑셀", f"{p.name}\n\n사업자 목록과 발행 내역(대기 포함)을 저장했습니다. 폴더를 엽니다.")
        op.open_file(X.OUT_DIR)


# ====================================================================== 요청 추가·수정
class RequestDialog(tk.Toplevel):
    def __init__(self, tab, group):
        super().__init__(tab.app)
        self.tab, self.app, self.d, self.group = tab, tab.app, tab.d, group
        self.title("세금계산서 요청 수정" if group else "세금계산서 요청 추가")
        self.configure(background=T.CARD)
        self.transient(tab.app)
        self.biz_id = group["lines"][0].get("biz_id", "") if group else ""
        self.rows = [dict(l) for l in group["lines"]] if group else []
        self.edit_idx = None
        f = ttk.Frame(self, padding=18); f.pack(fill="both", expand=True)
        f.columnconfigure(0, weight=1)

        # ① 사업자
        ttk.Label(f, text="① 사업자 고르기", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        sf = ttk.Frame(f); sf.grid(row=1, column=0, sticky="we", pady=(6, 0))
        ttk.Label(sf, text="찾기").pack(side="left")
        self.q = ttk.Entry(sf, width=26); self.q.pack(side="left", padx=6)
        self.q.bind("<KeyRelease>", lambda e: self.search())
        self.q.bind("<Down>", lambda e: (self.res.focus_set(), self.res.selection_set(0)) if self.res.size() else None)
        ttk.Button(sf, text="새 사업자 등록", command=self.new_biz).pack(side="left", padx=(6, 0))
        self.edit_biz_btn = ttk.Button(sf, text="사업자 정보 수정", command=self.edit_biz); self.edit_biz_btn.pack(side="left", padx=6)
        self.res = tk.Listbox(f, height=5, activestyle="none", font=T.f(10), relief="flat", highlightthickness=1,
                              highlightbackground=T.LINE_STRONG, selectbackground=T.GREEN_L, selectforeground=T.INK,
                              exportselection=False)
        self.res.grid(row=2, column=0, sticky="we", pady=(6, 0))
        self.res.bind("<<ListboxSelect>>", lambda e: self.pick_biz())
        self.res.bind("<Return>", lambda e: self.pick_biz())
        self.res_items = []
        self.biz_lb = tk.Label(f, text="", bg=T.GREEN_L, fg=T.INK, font=T.f(10, True), anchor="w", justify="left",
                               padx=10, pady=6)
        self.biz_lb.grid(row=3, column=0, sticky="we", pady=(6, 0))
        hint(f, "고객명·상호·성명·사업자번호 일부를 입력하면 등록된 사업자가 나옵니다. 처음 오는 사업자는 [새 사업자 등록].",
             row=4, column=0, sticky="w", pady=(2, 0), wrap=640)

        # ② 고객명
        cf = ttk.Frame(f); cf.grid(row=5, column=0, sticky="we", pady=(12, 0))
        ttk.Label(cf, text="② 고객명", style="Title.TLabel").pack(side="left")
        self.customer = ttk.Entry(cf, width=20); self.customer.pack(side="left", padx=8)
        ttk.Label(cf, text="(주문자 이름 — 주문을 불러오면 자동으로 채워집니다)", style="Hint.TLabel").pack(side="left")

        # ③ 주문
        ttk.Label(f, text="③ 주문", style="Title.TLabel").grid(row=6, column=0, sticky="w", pady=(12, 0))
        of = ttk.Frame(f); of.grid(row=7, column=0, sticky="we", pady=(6, 0))
        ttk.Label(of, text="주문번호").pack(side="left")
        self.oid = ttk.Entry(of, width=20); self.oid.pack(side="left", padx=6)
        self.oid.bind("<Return>", lambda e: self.load_order())
        self.load_btn = ttk.Button(of, text="카페24에서 불러오기", style="Ghost.TButton", command=self.load_order)
        self.load_btn.pack(side="left")
        self.load_lb = ttk.Label(of, text="", style="Hint.TLabel"); self.load_lb.pack(side="left", padx=8)
        cols = (("oid", "주문번호", 150), ("date", "주문일", 90), ("amount", "금액", 90), ("memo", "메모", 150), ("pay", "결제", 110))
        tf = ttk.Frame(f); tf.grid(row=8, column=0, sticky="we", pady=(6, 0))
        tf.columnconfigure(0, weight=1)
        self.tv = ttk.Treeview(tf, columns=[c[0] for c in cols], show="headings", height=5, selectmode="browse")
        for c, t, w in cols:
            self.tv.heading(c, text=t); self.tv.column(c, width=w, anchor="e" if c == "amount" else "w")
        self.tv.grid(row=0, column=0, sticky="we")
        self.tv.bind("<<TreeviewSelect>>", lambda e: self.pick_row())
        # 줄 편집칸
        ef = ttk.Frame(f); ef.grid(row=9, column=0, sticky="we", pady=(6, 0))
        self.ed = {}
        for i, (k, t, w) in enumerate((("oid", "주문번호", 18), ("date", "주문일", 11), ("amount", "금액", 10), ("memo", "메모", 18))):
            ttk.Label(ef, text=t).grid(row=0, column=i * 2, sticky="e", padx=(0 if i == 0 else 8, 4))
            e = ttk.Entry(ef, width=w); e.grid(row=0, column=i * 2 + 1, sticky="w")
            self.ed[k] = e
        bf2 = ttk.Frame(f); bf2.grid(row=10, column=0, sticky="we", pady=(6, 0))
        self.apply_btn = ttk.Button(bf2, text="줄 추가", command=self.apply_row); self.apply_btn.pack(side="left")
        ttk.Button(bf2, text="새 줄로", command=self.clear_row).pack(side="left", padx=6)
        self.ship_btn = ttk.Button(bf2, text="배송비 빼기", command=self.minus_shipping); self.ship_btn.pack(side="left")
        ttk.Button(bf2, text="선택한 줄 빼기", command=self.remove_row).pack(side="left", padx=6)
        self.sum_lb = tk.Label(bf2, text="", bg=T.CARD, fg=T.INK, font=T.f(11, True)); self.sum_lb.pack(side="right")
        hint(f, "주문번호를 넣고 [카페24에서 불러오기]를 누르면 주문일·실결제금액이 들어갑니다. 금액·메모는 아래 칸에서 고친 뒤 "
                "[줄 고치기]. 환불·할인 등은 금액을 직접 고치거나 마이너스 금액 줄을 추가하세요. "
                "주문번호 없이 금액만 넣어도 됩니다 (주문일은 2026-10-13처럼).",
             row=11, column=0, sticky="w", pady=(4, 0), wrap=640)
        self.info_lb = tk.Label(f, text="", bg=T.CARD, fg=T.ORANGE, font=T.f(9, True), anchor="w", justify="left", wraplength=640)
        self.info_lb.grid(row=12, column=0, sticky="we", pady=(8, 0))
        bf = ttk.Frame(f); bf.grid(row=13, column=0, sticky="we", pady=(14, 0))
        ttk.Button(bf, text="저장", style="Accent.TButton", command=self.ok).pack(side="right")
        ttk.Button(bf, text="취소", command=self.destroy).pack(side="right", padx=6)
        self.last_ship = 0

        if group:
            self.customer.insert(0, group["lines"][0].get("customer", ""))
        self.search()
        self.show_biz()
        self.show_rows()
        _center(self, self.app, 6)
        self.grab_set()
        (self.oid if group else self.q).focus_set()

    # ---- 사업자
    def search(self):
        self.res.delete(0, "end")
        t = self.q.get().strip()
        self.res_items = X.search_biz(self.d, t)[:30] if t else []
        for b in self.res_items:
            self.res.insert("end", f"  {b.get('name', '')}  ·  {b.get('ceo', '')}  ·  {X.bizno_fmt(b.get('bizno'))}"
                                   + (f"  ·  고객명 {', '.join(b.get('customers', [])[:3])}" if b.get("customers") else ""))
        if t and not self.res_items:
            self.res.insert("end", "  찾는 사업자가 없습니다 → [새 사업자 등록]")

    def pick_biz(self):
        sel = self.res.curselection()
        if not sel or sel[0] >= len(self.res_items):
            return
        self.biz_id = self.res_items[sel[0]]["id"]
        self.show_biz()

    def show_biz(self):
        b = self.d["biz"].get(self.biz_id)
        if not b:
            self.biz_lb.configure(text="선택한 사업자 없음", bg="#F4F4F2", fg=T.MUTED)
            self.edit_biz_btn.state(["disabled"])
            return
        miss = X.biz_missing(b)
        self.biz_lb.configure(text=f"선택: {b.get('name')}  ·  {b.get('ceo')}  ·  {X.bizno_fmt(b.get('bizno'))}  ·  {b.get('email')}"
                                   + (f"\n⚠ 비어 있는 칸: {', '.join(miss)} — [사업자 정보 수정]에서 채워 주세요" if miss else ""),
                              bg=T.GREEN_L if not miss else "#FFF1E6", fg=T.INK)
        self.edit_biz_btn.state(["!disabled"])

    def new_biz(self):
        t = self.q.get().strip()
        init = {"bizno": X.digits(t)} if len(X.digits(t)) == 10 else {"name": t}
        cust = self.customer.get().strip()
        init["customers"] = [cust] if cust else []

        def done(info):
            ex = X.find_biz_by_no(self.d, info["bizno"])
            if ex and not messagebox.askyesno("새 사업자 등록", f"사업자번호 {X.bizno_fmt(info['bizno'])}는 이미 "
                                                            f"'{ex.get('name')}'(으)로 등록돼 있습니다. 새로 입력한 내용으로 바꿀까요?",
                                              parent=self):
                self.biz_id = ex["id"]
            else:
                self.biz_id = X.save_biz(self.d, info, ex["id"] if ex else None)
                X.save(self.d)
            self.show_biz()
        BizDialog(self, init, done)

    def edit_biz(self):
        b = self.d["biz"].get(self.biz_id)
        if not b:
            return

        def done(info):
            X.save_biz(self.d, info, self.biz_id)
            X.save(self.d)
            self.show_biz()
            self.tab.refresh()
        BizDialog(self, dict(b), done)

    # ---- 주문 줄
    def show_rows(self):
        self.tv.delete(*self.tv.get_children())
        for i, r in enumerate(self.rows):
            self.tv.insert("", "end", iid=str(i), values=(r.get("oid", ""), r.get("date", ""), X.won(r.get("amount")),
                                                          r.get("memo", ""), r.get("pay", "")))
        total = sum(int(r.get("amount") or 0) for r in self.rows)
        sup, tax = X.split_vat(total)
        self.sum_lb.configure(text=f"총발행금액 {X.won(total)}원  (공급가액 {X.won(sup)} + 세액 {X.won(tax)})" if self.rows else "")
        self.clear_row()
        self.check_info()

    def check_info(self):
        msgs = []
        months = {str(r.get("date") or "")[:7] for r in self.rows if r.get("date")}
        if len(months) > 1:
            msgs.append(f"주문 달이 서로 다릅니다 ({', '.join(sorted(months))}) — 달마다 따로 한 장씩 발행됩니다.")
        cards = [r for r in self.rows if "카드" in str(r.get("pay") or "")]
        if cards:
            msgs.append(f"카드결제 주문 {len(cards)}건 — 카드 매출전표가 이미 증빙이라 보통은 세금계산서를 따로 발행하지 않아요.")
        self.info_lb.configure(text="\n".join("⚠ " + m for m in msgs))

    def pick_row(self):
        sel = self.tv.selection()
        if not sel:
            return
        self.edit_idx = int(sel[0])
        r = self.rows[self.edit_idx]
        for k, e in self.ed.items():
            e.delete(0, "end")
            e.insert(0, X.won(r.get(k)) if k == "amount" else str(r.get(k) or ""))
        self.apply_btn.configure(text="줄 고치기")

    def clear_row(self):
        self.edit_idx = None
        for e in self.ed.values():
            e.delete(0, "end")
        self.apply_btn.configure(text="줄 추가")
        if self.tv.selection():
            self.tv.selection_remove(self.tv.selection())

    def _dup_text(self, oid, skip_id=None):
        hits = [l for l in X.lines_with_oid(self.d, oid) if l["id"] != skip_id]
        if not hits:
            return ""
        l = hits[0]
        if l["status"] == "done":
            inv = next((i for i in self.d["invoices"] if i["id"] == l.get("inv")), {})
            return f"이 주문은 이미 발행 완료 내역에 있습니다 (작성일자 {inv.get('date', '?')}, {inv.get('company') or l.get('customer')})."
        return f"이 주문은 이미 발행 대기 목록에 있습니다 ({l.get('company') or l.get('customer')})."

    def apply_row(self):
        v = {k: e.get().strip() for k, e in self.ed.items()}
        try:
            amount = X.to_int(v["amount"])
        except ValueError:
            messagebox.showwarning("금액", "금액은 숫자로 입력해 주세요. (예: 57150, 환불은 -7500)", parent=self)
            return
        day = X.parse_date(v["date"]) or X.oid_date(v["oid"])
        if not day:
            messagebox.showwarning("주문일", "주문일을 2026-10-13처럼 입력해 주세요.", parent=self)
            return
        if amount == 0:
            messagebox.showwarning("금액", "금액을 입력해 주세요.", parent=self)
            return
        row = {"oid": v["oid"], "date": day.isoformat(), "amount": amount, "memo": v["memo"]}
        if self.edit_idx is None:
            if v["oid"]:
                if any(r.get("oid") == v["oid"] for r in self.rows):
                    messagebox.showinfo("줄 추가", "이미 목록에 있는 주문번호입니다.", parent=self)
                    return
                dup = self._dup_text(v["oid"])
                if dup and not messagebox.askyesno("같은 주문", dup + "\n\n그래도 넣을까요?", parent=self):
                    return
            self.rows.append(row)
        else:
            self.rows[self.edit_idx].update(row)
        self.show_rows()

    def remove_row(self):
        sel = self.tv.selection()
        if not sel:
            messagebox.showinfo("줄 빼기", "위 목록에서 뺄 줄을 골라 주세요.", parent=self)
            return
        del self.rows[int(sel[0])]
        self.show_rows()

    def minus_shipping(self):
        if self.edit_idx is None:
            messagebox.showinfo("배송비 빼기", "위 목록에서 배송비를 뺄 주문 줄을 먼저 골라 주세요.", parent=self)
            return
        r = self.rows[self.edit_idx]
        ship = int(r.get("shipping") or 0)
        if not ship:
            messagebox.showinfo("배송비 빼기", "이 주문은 카페24에 배송비가 없습니다 (또는 직접 넣은 줄). 금액 칸을 직접 고쳐 주세요.",
                                parent=self)
            return
        if "배송비제외" in str(r.get("memo") or ""):
            messagebox.showinfo("배송비 빼기", "이미 배송비를 뺀 줄입니다.", parent=self)
            return
        r["amount"] = int(r.get("amount") or 0) - ship
        r["memo"] = (str(r.get("memo") or "") + " 배송비제외").strip()
        idx = self.edit_idx
        self.show_rows()
        self.tv.selection_set(str(idx))

    def load_order(self):
        oid = self.oid.get().strip()
        if not oid:
            return
        if any(r.get("oid") == oid for r in self.rows):
            self.load_lb.configure(text="이미 목록에 있는 주문입니다.")
            return
        if not self.app.cfg:
            messagebox.showwarning("불러오기", "카페24 설정(config.json)을 읽지 못해 불러올 수 없습니다. 아래 칸에 직접 넣어 주세요.", parent=self)
            return
        self.load_lb.configure(text="카페24에서 불러오는 중...")
        self.load_btn.state(["disabled"])

        def work():
            try:
                return ("ok", X.fetch_order(self.app.cfg, oid))
            except Exception as e:
                op.log.warning(f"[세금계산서] 주문 불러오기 실패 {oid}: {e}")
                return ("err", e)

        def done(res):
            if not self.winfo_exists():
                return
            self.load_btn.state(["!disabled"])
            kind, info = res
            if kind == "err":
                self.load_lb.configure(text="")
                messagebox.showwarning("불러오기", f"주문을 불러오지 못했습니다.\n\n{info}\n\n아래 칸에 직접 넣어도 됩니다.", parent=self)
                return
            if not info:
                self.load_lb.configure(text="")
                messagebox.showinfo("불러오기", "카페24에서 이 주문번호를 찾지 못했습니다. 번호를 확인해 주세요.", parent=self)
                return
            if info["canceled"] and not messagebox.askyesno("취소된 주문", "카페24에서 취소된 주문입니다. 그래도 넣을까요?", parent=self):
                self.load_lb.configure(text="")
                return
            dup = self._dup_text(oid)
            if dup and not messagebox.askyesno("같은 주문", dup + "\n\n그래도 넣을까요?", parent=self):
                self.load_lb.configure(text="")
                return
            self.rows.append({"oid": info["oid"], "date": info["date"], "amount": info["amount"], "memo": "",
                              "pay": info["pay"], "shipping": info["shipping"]})
            if not self.customer.get().strip():
                self.customer.insert(0, info["customer"])
            if not self.biz_id and info["customer"]:
                hits = [b for b in self.d["biz"].values() if info["customer"] in b.get("customers", [])
                        or info["customer"] == b.get("ceo")]
                if len(hits) == 1:
                    self.biz_id = hits[0]["id"]
                    self.show_biz()
            self.oid.delete(0, "end")
            self.load_lb.configure(text=f"불러옴: {info['customer']} · {info['date']} · {X.won(info['amount'])}원"
                                        + (f" (배송비 {X.won(info['shipping'])} 포함)" if info["shipping"] else ""))
            self.show_rows()
        self.app.bg(work, done, busy=False)

    # ---- 저장
    def ok(self):
        if not self.rows:
            messagebox.showwarning("저장", "주문을 하나 이상 넣어 주세요.", parent=self)
            return
        if not self.biz_id and not messagebox.askyesno(
                "사업자 없음", "사업자를 고르지 않았습니다. 사업자 없이 저장하고 나중에 고를까요?", parent=self):
            return
        if self.edit_idx is None and any(e.get().strip() for e in self.ed.values()):
            if messagebox.askyesno("저장", "아래 칸에 넣다 만 내용이 있습니다. 줄로 추가할까요?", parent=self):
                n = len(self.rows)
                self.apply_row()
                if len(self.rows) == n:
                    return
        customer = self.customer.get().strip()
        b = self.d["biz"].get(self.biz_id) or {}
        if b and customer and customer not in b.setdefault("customers", []):
            b["customers"].append(customer)
        keep = {r.get("id") for r in self.rows if r.get("id")}
        if self.group:
            old = {l["id"] for l in self.group["lines"]}
            self.d["lines"] = [l for l in self.d["lines"] if l["id"] not in old or l["id"] in keep]
            self.d["groups"].pop(self.group["key"], None)
        mine = []
        for r in self.rows:
            fields = {"customer": customer, "company": b.get("name", ""), "biz_id": self.biz_id, "oid": r.get("oid", ""),
                      "date": r.get("date", ""), "amount": int(r.get("amount") or 0), "memo": r.get("memo", ""),
                      "pay": r.get("pay", ""), "shipping": r.get("shipping", 0)}
            line = X.line_by_id(self.d, r["id"]) if r.get("id") else None
            if line:
                line.update(fields)
            else:
                line = X.add_line(self.d, **fields)
            mine.append(line["id"])
        # 같은 사업자의 같은 달 요청이 이미 있었으면 한 장으로 합쳐짐 → 알려 줌
        merged = [g for g in X.waiting_groups(self.d)
                  if any(l["id"] in mine for l in g["lines"]) and any(l["id"] not in mine for l in g["lines"])]
        op.log.info(f"[세금계산서] 요청 {'수정' if self.group else '추가'}: 주문 {len(self.rows)}건")
        self.destroy()
        self.tab.save()
        if merged:
            self.app.flash(f"같은 사업자의 같은 달 요청과 합쳐서 한 장으로 발행됩니다 ({merged[0]['company']}).")
        else:
            self.app.flash("요청을 저장했습니다.")


# ====================================================================== 사업자 정보 입력
class BizDialog(tk.Toplevel):
    """사업자번호 → 상호 → 성명 → 주소 → 업태 → 종목 → 이메일 (Tab 키로 이동)"""

    def __init__(self, parent, info, on_ok, title="사업자 정보", note=None):
        super().__init__(parent)
        self.title(title)
        self.configure(background=T.CARD)
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.on_ok = on_ok
        self.info = info
        f = ttk.Frame(self, padding=18); f.pack(fill="both")
        ttk.Label(f, text=title, style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        if note:
            hint(f, note, row=1, column=0, columnspan=2, sticky="w", pady=(2, 6), wrap=440)
        self.e = {}
        widths = {"addr": 52, "email": 32}
        for i, (k, label) in enumerate(X.BIZ_FIELDS):
            ttk.Label(f, text=label).grid(row=i + 2, column=0, sticky="e", padx=(0, 8), pady=3)
            e = ttk.Entry(f, width=widths.get(k, 30))
            e.grid(row=i + 2, column=1, sticky="w", pady=3)
            v = info.get(k) or ""
            e.insert(0, X.bizno_fmt(v) if k == "bizno" and v else v)
            self.e[k] = e
        self.e["bizno"].bind("<FocusOut>", lambda e: self.check_no())
        self.no_lb = ttk.Label(f, text="", style="Hint.TLabel")
        self.no_lb.grid(row=len(X.BIZ_FIELDS) + 2, column=1, sticky="w")
        n = len(X.BIZ_FIELDS) + 3
        if "customers" in info or title == "사업자 정보":
            ttk.Label(f, text="고객명").grid(row=n, column=0, sticky="e", padx=(0, 8), pady=3)
            self.cust = ttk.Entry(f, width=40); self.cust.grid(row=n, column=1, sticky="w", pady=3)
            self.cust.insert(0, ", ".join(info.get("customers", [])))
            ttk.Label(f, text="메모").grid(row=n + 1, column=0, sticky="e", padx=(0, 8), pady=3)
            self.memo = ttk.Entry(f, width=40); self.memo.grid(row=n + 1, column=1, sticky="w", pady=3)
            self.memo.insert(0, info.get("memo", ""))
            hint(f, "고객명: 이 사업자로 주문하는 카페24 주문자 이름 (여러 명이면 쉼표로). 찾기와 주문 불러오기에 쓰입니다.",
                 row=n + 2, column=1, sticky="w", wrap=400)
        else:
            self.cust = self.memo = None
        bf = ttk.Frame(f); bf.grid(row=n + 3, column=0, columnspan=2, sticky="we", pady=(14, 0))
        ttk.Button(bf, text="저장", style="Accent.TButton", command=self.ok).pack(side="right")
        ttk.Button(bf, text="취소", command=self.destroy).pack(side="right", padx=6)
        self.bind("<Escape>", lambda e: self.destroy())
        self.check_no()
        _center(self, parent.winfo_toplevel(), 4)
        self.grab_set()
        first_empty = next((self.e[k] for k, _ in X.BIZ_FIELDS if not self.e[k].get()), self.e["bizno"])
        first_empty.focus_set()

    def check_no(self):
        v = self.e["bizno"].get()
        if not X.digits(v):
            self.no_lb.configure(text="사업자번호는 숫자 10자리 (- 는 있어도 없어도 됩니다)", foreground=T.MUTED)
        elif X.bizno_ok(v):
            self.no_lb.configure(text="✓ 올바른 사업자번호 형식입니다", foreground=T.GREEN_D)
            self.e["bizno"].delete(0, "end"); self.e["bizno"].insert(0, X.bizno_fmt(v))
        else:
            self.no_lb.configure(text="⚠ 사업자번호가 맞지 않습니다. 다시 확인해 주세요", foreground=T.ORANGE)

    def ok(self):
        info = {k: self.e[k].get().strip() for k, _ in X.BIZ_FIELDS}
        info["bizno"] = X.digits(info["bizno"])
        if not info["bizno"] or not info["name"]:
            messagebox.showwarning("저장", "사업자번호와 상호는 꼭 넣어 주세요.", parent=self)
            return
        if not X.bizno_ok(info["bizno"]) and not messagebox.askyesno(
                "사업자번호 확인", f"{X.bizno_fmt(info['bizno'])}는 올바른 사업자번호 형식이 아닙니다.\n"
                               "잘못 적었을 수 있어요. 그래도 저장할까요?", parent=self):
            return
        if info["email"] and "@" not in info["email"]:
            messagebox.showwarning("이메일", "이메일 형식을 확인해 주세요 (예: abc@naver.com).", parent=self)
            return
        miss = [n for k, n in X.BIZ_FIELDS if not info[k]]
        if miss and not messagebox.askyesno("빈 칸", f"비어 있는 칸: {', '.join(miss)}\n\n발행하려면 모두 필요합니다. "
                                                  "일단 이대로 저장할까요?", parent=self):
            return
        if self.cust is not None:
            info["customers"] = [c.strip() for c in self.cust.get().split(",") if c.strip()]
            info["memo"] = self.memo.get().strip()
        self.destroy()
        self.on_ok(info)


# ====================================================================== 사업자 목록
class BizListDialog(tk.Toplevel):
    def __init__(self, tab):
        super().__init__(tab.app)
        self.tab, self.d = tab, tab.d
        self.title("사업자 목록")
        self.configure(background=T.CARD)
        self.transient(tab.app)
        f = ttk.Frame(self, padding=18); f.pack(fill="both", expand=True)
        f.columnconfigure(0, weight=1); f.rowconfigure(2, weight=1)
        top = ttk.Frame(f); top.grid(row=0, column=0, sticky="we")
        ttk.Label(top, text="찾기").pack(side="left")
        self.q = ttk.Entry(top, width=24); self.q.pack(side="left", padx=6)
        self.q.bind("<KeyRelease>", lambda e: self.show())
        ttk.Button(top, text="삭제", command=self.delete).pack(side="right")
        ttk.Button(top, text="수정", command=self.edit).pack(side="right", padx=6)
        ttk.Button(top, text="새로 등록", style="Accent.TButton", command=self.add).pack(side="right")
        hint(f, "세금계산서를 받는 사업자 목록입니다. 한 번 등록하면 요청 추가에서 바로 찾아 쓸 수 있습니다. 두 번 누르면 수정.",
             row=1, column=0, sticky="w", pady=(4, 6), wrap=820)
        cols = (("name", "상호", 150), ("ceo", "성명", 80), ("bizno", "사업자번호", 110), ("email", "이메일", 180),
                ("cust", "고객명", 120), ("n", "요청", 50), ("state", "상태", 110))
        self.tv = ttk.Treeview(f, columns=[c[0] for c in cols], show="headings", height=16, selectmode="browse")
        for c, t, w in cols:
            self.tv.heading(c, text=t); self.tv.column(c, width=w, anchor="center" if c == "n" else "w")
        self.tv.tag_configure("bad", foreground=T.ORANGE)
        self.tv.grid(row=2, column=0, sticky="nsew")
        s = ttk.Scrollbar(f, orient="vertical", command=self.tv.yview); s.grid(row=2, column=1, sticky="ns")
        self.tv.configure(yscrollcommand=s.set)
        self.tv.bind("<Double-1>", lambda e: self.edit())
        self.cnt = ttk.Label(f, text="", style="Hint.TLabel"); self.cnt.grid(row=3, column=0, sticky="w", pady=(6, 0))
        ttk.Button(f, text="닫기", command=self.destroy).grid(row=4, column=0, columnspan=2, sticky="e", pady=(10, 0))
        self.show()
        _center(self, tab.app, 6)
        self.q.focus_set()

    def show(self):
        self.tv.delete(*self.tv.get_children())
        res = sorted(X.search_biz(self.d, self.q.get()), key=lambda b: b.get("name", ""))
        for b in res:
            miss = X.biz_missing(b)
            state = ("빈 칸: " + ", ".join(miss)) if miss else ("번호 확인 필요" if not X.bizno_ok(b.get("bizno")) else "정상")
            self.tv.insert("", "end", iid=b["id"], tags=("bad",) if state != "정상" else (),
                           values=(b.get("name", ""), b.get("ceo", ""), X.bizno_fmt(b.get("bizno")), b.get("email", ""),
                                   ", ".join(b.get("customers", [])), X.biz_usage(self.d, b["id"]), state))
        self.cnt.configure(text=f"{len(res)}곳" + (f" (전체 {len(self.d['biz'])}곳 중)" if len(res) != len(self.d["biz"]) else ""))

    def add(self):
        def done(info):
            ex = X.find_biz_by_no(self.d, info["bizno"])
            if ex and not messagebox.askyesno("새로 등록", f"이미 '{ex.get('name')}'(으)로 등록된 번호입니다. 새 내용으로 바꿀까요?",
                                              parent=self):
                return
            X.save_biz(self.d, info, ex["id"] if ex else None)
            X.save(self.d); self.show(); self.tab.refresh()
        BizDialog(self, {"customers": []}, done)

    def edit(self):
        sel = self.tv.selection()
        if not sel:
            return
        b = self.d["biz"][sel[0]]

        def done(info):
            ex = X.find_biz_by_no(self.d, info["bizno"])
            if ex and ex["id"] != b["id"]:
                messagebox.showwarning("수정", f"이 사업자번호는 이미 '{ex.get('name')}'에 쓰이고 있습니다.", parent=self)
                return
            X.save_biz(self.d, info, b["id"])
            X.save(self.d); self.show(); self.tab.refresh()
        BizDialog(self, dict(b), done)

    def delete(self):
        sel = self.tv.selection()
        if not sel:
            return
        b = self.d["biz"][sel[0]]
        n = X.biz_usage(self.d, b["id"])
        if n:
            messagebox.showinfo("삭제", f"'{b.get('name')}'는 요청·발행 내역 {n}건에 쓰이고 있어 지울 수 없습니다.\n"
                                      "정보가 바뀌었으면 [수정]을 쓰세요.", parent=self)
            return
        if not messagebox.askyesno("삭제", f"'{b.get('name')}' 사업자 정보를 지울까요?", parent=self):
            return
        del self.d["biz"][b["id"]]
        X.save(self.d); self.show()


# ====================================================================== 작성일자
class DateDialog(tk.Toplevel):
    def __init__(self, tab, g):
        super().__init__(tab.app)
        self.tab, self.g = tab, g
        self.title("작성일자")
        self.configure(background=T.CARD)
        self.transient(tab.app)
        self.resizable(False, False)
        dates = sorted(l["date"] for l in g["lines"] if l.get("date"))
        f = ttk.Frame(self, padding=18); f.pack(fill="both")
        ttk.Label(f, text=f"{g['company'] or g['customer']} — 작성일자", style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        hint(f, f"주문 {len(g['lines'])}건: " + ", ".join(d[5:].replace("-", "/") for d in dates),
             row=1, column=0, columnspan=2, sticky="w", pady=(2, 8))
        self.mode = tk.StringVar(value=g["mode"] if g["mode"] in ("last", "first", "custom") else "last")
        ttk.Radiobutton(f, text=f"마지막 주문일 ({dates[-1] if dates else '-'})", value="last", variable=self.mode).grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Radiobutton(f, text=f"첫 주문일 ({dates[0] if dates else '-'})", value="first", variable=self.mode).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Radiobutton(f, text="날짜 직접 고르기", value="custom", variable=self.mode).grid(row=4, column=0, sticky="w")
        self.day = ttk.Entry(f, width=12); self.day.grid(row=4, column=1, sticky="w", padx=6)
        self.day.insert(0, _date_txt(g["date"]))
        self.day.bind("<FocusIn>", lambda e: self.mode.set("custom"))
        hint(f, "홈택스 품목 줄의 '월'은 작성일자의 달로 정해지므로, 같은 달 안의 날짜로 고르세요.\n"
                "주문을 한 장씩 따로 발행하려면 목록에서 주문 줄을 오른쪽 클릭 → '이 주문만 따로 발행'.",
             row=5, column=0, columnspan=2, sticky="w", pady=(8, 0), wrap=400)
        bf = ttk.Frame(f); bf.grid(row=6, column=0, columnspan=2, sticky="we", pady=(14, 0))
        ttk.Button(bf, text="저장", style="Accent.TButton", command=self.ok).pack(side="right")
        ttk.Button(bf, text="취소", command=self.destroy).pack(side="right", padx=6)
        _center(self, tab.app)
        self.grab_set()

    def ok(self):
        m = self.mode.get()
        day = X.parse_date(self.day.get()) if m == "custom" else None
        if m == "custom" and not day:
            messagebox.showwarning("작성일자", "날짜를 2026-10-13처럼 입력해 주세요.", parent=self)
            return
        if day and day.strftime("%Y-%m") != self.g["month"] and not messagebox.askyesno(
                "작성일자", f"주문 달({self.g['month']})과 다른 달입니다. 그래도 이 날짜로 할까요?", parent=self):
            return
        X.set_group_date(self.tab.d, self.g["key"], m, day)
        self.destroy()
        self.tab.save()


# ====================================================================== 건별 발급 도우미
class HelperWindow(tk.Toplevel):
    """홈택스 '전자세금계산서 건별 발급' 화면 순서대로 칸마다 [복사]"""

    def __init__(self, tab, keys):
        super().__init__(tab.app)
        self.tab, self.keys, self.i = tab, keys, 0
        self.title("건별 발급 도우미")
        self.configure(background=T.CARD)
        self.top = tk.BooleanVar(value=True)
        self.attributes("-topmost", True)
        self.outer = ttk.Frame(self, padding=16); self.outer.pack(fill="both", expand=True)
        self.body = None
        self.reload()
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        self.geometry(f"+{max(0, sw - self.winfo_reqwidth() - 30)}+40")

    def group(self):
        gs = {g["key"]: g for g in self.tab.groups}
        self.keys = [k for k in self.keys if k in gs]
        if not self.keys:
            return None
        self.i = min(self.i, len(self.keys) - 1)
        return gs[self.keys[self.i]]

    def copy(self, label, value):
        self.clipboard_clear()
        self.clipboard_append(str(value))
        self.status.configure(text=f"복사함: {label}  →  홈택스 칸에 Ctrl+V")

    def reload(self):
        if self.body:
            self.body.destroy()
        self.body = b = ttk.Frame(self.outer); b.pack(fill="both", expand=True)
        b.columnconfigure(1, weight=1)
        g = self.group()
        if not g:
            ttk.Label(b, text="남은 계산서가 없습니다. 창을 닫아 주세요.", style="Title.TLabel").grid(row=0, column=0, sticky="w")
            ttk.Button(b, text="닫기", command=self.destroy).grid(row=1, column=0, sticky="w", pady=(10, 0))
            return
        biz = g["biz"] or {}
        n = len(g["lines"])
        head = ttk.Frame(b); head.grid(row=0, column=0, columnspan=3, sticky="we")
        ttk.Label(head, text=f"{self.i + 1} / {len(self.keys)}   {g['company'] or g['customer']}",
                  style="Big.TLabel").pack(side="left")
        if n > 1:
            T.Pill(head, text=f"주문 {n}건 합침", bg="#FFF1E6", fg=T.ORANGE).pack(side="left", padx=8)
        ttk.Checkbutton(head, text="항상 위", variable=self.top,
                        command=lambda: self.attributes("-topmost", self.top.get())).pack(side="right")
        r = 1
        if g["problems"]:
            T.RoundBox(b, text="⚠ " + " · ".join(g["problems"]) + " — 요청 목록에서 고친 뒤 발행하세요",
                       fill="#FFF1E6", fg=T.ORANGE, under=T.CARD).grid(row=r, column=0, columnspan=3, sticky="we", pady=(8, 0))
            r += 1

        def section(title):
            nonlocal r
            ttk.Label(b, text=title, style="Title.TLabel").grid(row=r, column=0, columnspan=3, sticky="w", pady=(12, 2))
            r += 1

        def field(label, value, copy_value=None, big=False):
            nonlocal r
            ttk.Label(b, text=label, foreground=T.MUTED).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=1)
            tk.Label(b, text=str(value) if value not in (None, "") else "(비어 있음)", bg=T.CARD,
                     fg=T.INK if value not in (None, "") else T.ORANGE, font=T.f(12 if big else 10, big),
                     anchor="w", justify="left", wraplength=360).grid(row=r, column=1, sticky="w", pady=1)
            btn = ttk.Button(b, text="복사", width=5,
                             command=lambda: self.copy(label, value if copy_value is None else copy_value))
            btn.grid(row=r, column=2, sticky="e", pady=1)
            if value in (None, ""):
                btn.state(["disabled"])
            r += 1

        email = str(biz.get("email") or "")
        eid, _, edom = email.partition("@")
        section("① 공급받는자  (등록번호 입력 후 [확인])")
        field("등록번호", X.bizno_fmt(biz.get("bizno")), X.digits(biz.get("bizno")))
        field("상호", biz.get("name"))
        field("성명", biz.get("ceo"))
        field("사업장", biz.get("addr"))
        field("업태", biz.get("uptae"))
        field("종목", biz.get("jongmok"))
        field("이메일 앞", eid)
        field("이메일 뒤", edom)
        section("② 작성일자")
        field("작성일자", _date_txt(g["date"]))
        section("③ 품목 첫 줄  (월은 자동)")
        field("일", f"{g['date'].day:02d}" if g["date"] else "")
        field("품목", X.ITEM_NAME)
        field("규격", X.ITEM_SPEC)
        field("수량", "1")
        section("④ 합계 [계산] 버튼 → 아래 금액 붙여넣고 Enter → [확인]")
        field("합계금액", f"{X.won(g['total'])}원", str(g["total"]), big=True)
        ttk.Label(b, text=f"홈택스에 나와야 할 값:  공급가액 {X.won(g['supply'])}  ·  세액 {X.won(g['tax'])}  ·  합계 {X.won(g['total'])}",
                  foreground=T.GREEN_D, font=T.f(10, True)).grid(row=r, column=0, columnspan=3, sticky="w", pady=(4, 0))
        r += 1
        ttk.Label(b, text="⑤ '이 금액을 (영수) 함' 선택 → [발급하기] 또는 여러 장이면 [발급보류]",
                  style="Title.TLabel").grid(row=r, column=0, columnspan=3, sticky="w", pady=(12, 0))
        r += 1
        if n > 1:
            txt = "\n".join(f"{l.get('oid') or '(번호 없음)'}  {str(l.get('date') or '')[5:].replace('-', '/')}  "
                            f"{X.won(l.get('amount'))}원  {l.get('memo', '')}" for l in g["lines"])
            tk.Label(b, text="합친 주문 (홈택스에는 안 들어감)\n" + txt, bg="#F7F7F5", fg=T.MUTED, font=T.f(9),
                     justify="left", anchor="w", padx=8, pady=6).grid(row=r, column=0, columnspan=3, sticky="we", pady=(10, 0))
            r += 1
        self.status = ttk.Label(b, text="", foreground=T.GREEN_D, font=T.f(10, True))
        self.status.grid(row=r, column=0, columnspan=3, sticky="w", pady=(10, 0))
        r += 1
        bf = ttk.Frame(b); bf.grid(row=r, column=0, columnspan=3, sticky="we", pady=(10, 0))
        prev = ttk.Button(bf, text="◀ 이전", command=lambda: self.move(-1)); prev.pack(side="left")
        nxt = ttk.Button(bf, text="다음 ▶", command=lambda: self.move(1)); nxt.pack(side="left", padx=6)
        if self.i == 0:
            prev.state(["disabled"])
        if self.i >= len(self.keys) - 1:
            nxt.state(["disabled"])
        done = ttk.Button(bf, text="이 계산서 발행완료", style="Accent.TButton", command=self.done); done.pack(side="right")
        if g["problems"]:
            done.state(["disabled"])

    def move(self, step):
        self.i = max(0, min(len(self.keys) - 1, self.i + step))
        self.reload()

    def done(self):
        g = self.group()
        if not g:
            return
        self.attributes("-topmost", False)
        ok = self.tab.mark_done(keys=[g["key"]])
        if self.winfo_exists():
            self.attributes("-topmost", self.top.get())
            if ok:
                self.reload()


# ====================================================================== 발행 완료 내용 보기
class InvoiceView(tk.Toplevel):
    def __init__(self, tab, inv):
        super().__init__(tab.app)
        self.title("발행 내용")
        self.configure(background=T.CARD)
        self.transient(tab.app)
        b = inv.get("biz") or {}
        f = ttk.Frame(self, padding=18); f.pack(fill="both")
        ttk.Label(f, text=f"{inv.get('company') or b.get('name') or inv.get('customer')}", style="Big.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        rows = [("작성일자", inv.get("date")), ("고객명", inv.get("customer")),
                ("사업자번호", X.bizno_fmt(b.get("bizno")) if b else "사업자 정보 없음"),
                ("상호", b.get("name")), ("성명", b.get("ceo")), ("주소", b.get("addr")),
                ("업태 / 종목", f"{b.get('uptae', '')} / {b.get('jongmok', '')}" if b else ""), ("이메일", b.get("email")),
                ("합계", f"{X.won(inv.get('total'))}원  (공급가액 {X.won(inv.get('supply'))} + 세액 {X.won(inv.get('tax'))})"),
                ("발행", f"{inv.get('how', '')} {str(inv.get('issued_at') or '')[:16].replace('T', ' ')}")]
        for i, (k, v) in enumerate(rows, 1):
            ttk.Label(f, text=k, foreground=T.MUTED).grid(row=i, column=0, sticky="w", padx=(0, 12), pady=1)
            ttk.Label(f, text=v or "", wraplength=420).grid(row=i, column=1, sticky="w", pady=1)
        txt = "\n".join(f"{l.get('oid') or '(번호 없음)'}  {l.get('date', '')}  {X.won(l.get('amount'))}원  {l.get('memo', '')}"
                        for l in inv["lines"])
        tk.Label(f, text="주문\n" + txt, bg="#F7F7F5", fg=T.INK, font=T.f(9), justify="left", anchor="w",
                 padx=8, pady=6).grid(row=len(rows) + 1, column=0, columnspan=2, sticky="we", pady=(10, 0))
        ttk.Button(f, text="닫기", command=self.destroy).grid(row=len(rows) + 2, column=1, sticky="e", pady=(12, 0))
        _center(self, tab.app)
