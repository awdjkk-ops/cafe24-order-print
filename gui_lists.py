# -*- coding: utf-8 -*-
"""통합 창 - '블랙리스트·추가배송' 탭 (웹 도구와 같은 구글 시트를 보고 등록·삭제)"""
import tkinter as tk
from tkinter import ttk, messagebox

import courier as C
import order_print as op
from gui_schedule import hint
import theme as T


def _order_to_fields(o):
    """카페24 주문 → 입력칸 값 (카페24 엑셀과 같은 형식)"""
    r = dict(zip(op.CSV_HEADERS, op.order_csv_rows(o)[0]))
    return {"name": r["수령인"], "zip": r["우편번호"], "address": r["주소"], "tel1": r["전화번호"],
            "tel2": r["핸드폰"], "phone": r["핸드폰"] or r["전화번호"], "message": r["비고"]}


class ListPanel(ttk.LabelFrame):
    """입력칸 + 목록 + 삭제 (블랙리스트·추가배송 공통)"""

    def __init__(self, master, app, title, fields, cols, list_action, add_action, del_action, desc, validate):
        super().__init__(master, text=f" {title} ", padding=10)
        self.app, self.fields_def, self.cols = app, fields, cols
        self.list_action, self.add_action, self.del_action, self.validate = list_action, add_action, del_action, validate
        self.items = []
        self.columnconfigure(0, weight=1); self.rowconfigure(5, weight=1)
        hint(self, desc, row=0, column=0, sticky="w", pady=(0, 6), wrap=520)

        # 주문번호로 채우기
        of = ttk.Frame(self); of.grid(row=1, column=0, sticky="w")
        ttk.Label(of, text="주문번호로 채우기").pack(side="left")
        self.oid = ttk.Entry(of, width=20); self.oid.pack(side="left", padx=6)
        ttk.Button(of, text="불러오기", command=self.load_order).pack(side="left")

        # 입력칸
        ff = ttk.Frame(self); ff.grid(row=2, column=0, sticky="we", pady=(6, 0))
        self.entries = {}
        for i, (key, label, kind) in enumerate(fields):
            r, c = divmod(i, 2)
            ttk.Label(ff, text=label).grid(row=r, column=c * 2, sticky="e", padx=(0 if c == 0 else 12, 4), pady=2)
            if isinstance(kind, list):
                w = ttk.Combobox(ff, values=kind, state="readonly", width=16); w.set(kind[0])
            else:
                w = ttk.Entry(ff, width=kind)
            w.grid(row=r, column=c * 2 + 1, sticky="w", pady=2)
            self.entries[key] = w
        bf = ttk.Frame(self); bf.grid(row=3, column=0, sticky="we", pady=(8, 4))
        ttk.Button(bf, text="등록", style="Accent.TButton", command=self.add).pack(side="left")
        ttk.Button(bf, text="입력칸 비우기", command=self.clear).pack(side="left", padx=6)
        sf = ttk.Frame(self); sf.grid(row=4, column=0, sticky="we", pady=(4, 6))
        ttk.Label(sf, text="찾기").pack(side="left", padx=(0, 4))
        self.filter = ttk.Entry(sf, width=16); self.filter.pack(side="left")
        self.filter.bind("<KeyRelease>", lambda e: self.show())
        ttk.Button(sf, text="선택 삭제", command=self.delete).pack(side="right")
        ttk.Button(sf, text="목록 새로 고침", command=self.load).pack(side="right", padx=6)

        # 목록
        lf = ttk.Frame(self); lf.grid(row=5, column=0, sticky="nsew")
        lf.columnconfigure(0, weight=1); lf.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(lf, columns=[c[0] for c in cols], show="headings", height=12, selectmode="extended")
        for key, label, w in cols:
            self.tree.heading(key, text=label); self.tree.column(key, width=w, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.tree.yview); sb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.tag_configure("black", foreground="#C0392B")
        self.tree.tag_configure("watch", foreground="#1F4E9C")
        self.count_lb = ttk.Label(self, text="", style="Hint.TLabel"); self.count_lb.grid(row=6, column=0, sticky="w", pady=(4, 0))

    @property
    def url(self):
        return (self.app.cfg or {}).get("sheet_api_url", "")

    def load(self):
        if not self.url:
            self.count_lb.configure(text="구글 시트 주소가 없습니다 (관리 탭에서 설정)")
            return

        def done(items):
            self.items = items
            self.show()
        self.app.bg(lambda: C.sheet_call(self.url, self.list_action).get("items", []), done, busy=False)

    def show(self):
        f = self.filter.get().strip()
        self.tree.delete(*self.tree.get_children())
        n = 0
        for it in self.items:
            vals = [str(it.get(k) or "") for k, _, _ in self.cols]
            if f and not any(f in v for v in vals):
                continue
            tag = ("black",) if it.get("level") == "블랙리스트" else ("watch",) if it.get("level") == "경계대상" else ()
            self.tree.insert("", "end", iid=str(it.get("id")), values=vals, tags=tag)
            n += 1
        self.count_lb.configure(text=f"{n}건" + (f" (전체 {len(self.items)}건 중)" if f else ""))

    def clear(self):
        for key, _, kind in self.fields_def:
            w = self.entries[key]
            if isinstance(kind, list):
                w.set(kind[0])
            else:
                w.delete(0, "end")

    def values(self):
        return {k: self.entries[k].get().strip() for k, _, _ in self.fields_def}

    def load_order(self):
        oid = self.oid.get().strip()
        if not oid:
            return

        def done(orders):
            if not orders:
                messagebox.showinfo("주문 불러오기", "주문을 찾지 못했습니다 (주문번호 또는 취소 여부를 확인해 주세요).")
                return
            vals = _order_to_fields(orders[0])
            vals["memo"] = f"{oid} "
            for key, _, kind in self.fields_def:
                if key in vals and not isinstance(kind, list):
                    self.entries[key].delete(0, "end"); self.entries[key].insert(0, vals[key])
        self.app.bg(lambda: op.fetch_orders_by_ids(self.app.cfg, op.get_access_token(self.app.cfg), [oid]),
                    done, "주문 불러오는 중...")

    def add(self):
        v = self.values()
        msg = self.validate(v)
        if msg:
            messagebox.showwarning("입력 확인", msg)
            return
        self.app.bg(lambda: C.sheet_call(self.url, self.add_action, retries=1, **v),
                    lambda _: (self.clear(), self.oid.delete(0, "end"), self.load(),
                               self.app.flash("등록했습니다.")), "구글 시트에 등록 중...")

    def delete(self):
        ids = list(self.tree.selection())
        if not ids:
            messagebox.showinfo("삭제", "목록에서 지울 항목을 먼저 골라 주세요.")
            return
        names = [self.tree.item(i, "values")[1 if self.cols[0][0] == "level" else 0] for i in ids]
        if not messagebox.askyesno("삭제", f"{len(ids)}건을 삭제할까요?\n" + "\n".join(names[:10])):
            return

        def work():
            for i in ids:
                C.sheet_call(self.url, self.del_action, retries=1, id=i)
        self.app.bg(work, lambda _: self.load(), "구글 시트에서 삭제 중...")


class ListsTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=12, style="Page.TFrame")
        self.app = app
        self.columnconfigure(0, weight=1); self.columnconfigure(1, weight=1); self.rowconfigure(0, weight=1)

        def v_black(v):
            if not (v["name"] or v["address"] or v["phone"]):
                return "이름·주소·휴대폰 중 하나 이상 입력해 주세요."
        self.black = ListPanel(
            self, app, "블랙리스트 · 경계대상",
            [("name", "이름", 18), ("phone", "휴대폰", 18), ("address", "주소", 18), ("level", "등급", ["블랙리스트", "경계대상"]),
             ("reason", "사유", 18)],
            [("level", "등급", 75), ("name", "이름", 70), ("address", "주소", 170), ("phone", "휴대폰", 110), ("reason", "사유", 120)],
            "list", "add", "delete",
            "택배 파일을 만들 때 '이름+주소'가 같거나 휴대폰이 같으면 표시됩니다 (블랙리스트=빨강, 경계대상=파랑). "
            "웹 도구와 같은 구글 시트라 어느 쪽에서 등록해도 똑같이 보입니다.", v_black)
        self.black.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        def v_extra(v):
            if not (v["name"] and v["address"]):
                return "이름과 주소는 꼭 입력해 주세요."
        self.extra = ListPanel(
            self, app, "추가배송 (재발송 등)",
            [("name", "이름", 18), ("zip", "우편번호", 18), ("address", "주소", 18), ("tel1", "전화번호1", 18),
             ("tel2", "전화번호2(휴대폰)", 18), ("message", "배송메세지", 18), ("memo", "메모(상품명 칸)", 18)],
            [("name", "이름", 70), ("address", "주소", 190), ("tel2", "휴대폰", 110), ("memo", "메모", 120)],
            "listExtra", "addExtra", "deleteExtra",
            "주문 파일에 없는 배송(재발송·교환 등)을 등록하면 다음 택배 파일에 함께 들어가고, 파일을 만든 뒤 자동으로 지워집니다. "
            "메모는 택배 파일의 상품명 칸에 들어갑니다.", v_extra)
        self.extra.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

    def refresh(self):
        self.black.load()
        self.extra.load()
