# -*- coding: utf-8 -*-
"""통합 창 - '택배·라벨' 탭 (택배 발송용 파일, 확인 목록, 라벨)"""
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox

import order_print as op
from gui_schedule import hint
import theme as T

BOXES = ["묶음배송 확인", "중요 배송메세지 확인", "블랙리스트·경계대상", "추가배송 포함", "제주도 확인", "주소 '~' 변경 확인"]
BOX_HINTS = {
    "묶음배송 확인": "이름·주소가 같은 주문 (택배 파일에 노란색). 롯데택배에 올리면 자동으로 묶입니다.",
    "중요 배송메세지 확인": "'문 앞' 같은 흔한 메세지를 뺀 나머지 배송메세지입니다.",
    "블랙리스트·경계대상": "택배 파일에 빨강(블랙리스트)·파랑(경계대상)으로 표시됩니다.",
    "추가배송 포함": "구글 시트에 등록된 추가배송(재발송 등)입니다. 택배 파일을 만들면 시트에서 지워집니다.",
    "제주도 확인": "제주·서귀포 주소입니다.",
    "주소 '~' 변경 확인": "롯데택배가 '~'를 못 읽어서 '-'로 바꾼 주소입니다.",
}


class CourierTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=12, style="Page.TFrame")
        self.app = app
        self.last = None            # 마지막으로 만든(또는 미리 본) 결과
        left = ttk.Frame(self, style="Page.TFrame"); left.grid(row=0, column=0, sticky="nsw")
        right = ttk.Frame(self, style="Page.TFrame"); right.grid(row=0, column=1, sticky="nsew", padx=(16, 0))
        self.columnconfigure(1, weight=1); self.rowconfigure(0, weight=1)

        # ---- 대기 목록
        wf = ttk.LabelFrame(left, text=" 택배 파일 대기 주문 ", padding=10); wf.grid(row=0, column=0, sticky="we")
        self.wait_lb = ttk.Label(wf, text="", style="Big.TLabel"); self.wait_lb.grid(row=0, column=0, sticky="w")
        hint(wf, "이 프로그램으로 출력한 주문 중 아직 택배 파일을 만들지 않은 주문입니다 (뽑은 순서대로). "
                 "오늘 못 보내는 주문도 포함됩니다.", row=1, column=0, sticky="w", pady=(2, 6), wrap=430)
        cols = (("oid", "주문번호", 140), ("buyer", "주문자", 70), ("place", "경로", 85), ("when", "출력한 때", 100))
        self.wait = ttk.Treeview(wf, columns=[c[0] for c in cols], show="headings", height=9, selectmode="extended")
        for c, t, w in cols:
            self.wait.heading(c, text=t); self.wait.column(c, width=w, anchor="w")
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
        hint(af, "파일을 만들지 않고 묶음배송·배송메세지·블랙리스트 등을 먼저 봅니다. 추가배송은 지우지 않습니다.",
             row=1, column=0, sticky="w", pady=(2, 8), wrap=430)
        self.b_make = ttk.Button(af, text="택배 파일 만들기", style="Main.TButton", command=lambda: self.run(True))
        self.b_make.grid(row=2, column=0, sticky="w")
        hint(af, "대기 주문 전체와 구글 시트의 추가배송으로 택배 파일을 만들고 폴더를 엽니다. 추가배송은 시트에서 지워지고, "
                 "만든 주문은 대기 목록에서 빠집니다. 카페24에서 최신 정보를 불러오며 그사이 취소된 주문은 뺍니다.",
             row=3, column=0, sticky="w", pady=(2, 0), wrap=430)
        self.stat = ttk.Label(af, text="", justify="left", foreground=T.GREEN_D, wraplength=430)
        self.stat.grid(row=4, column=0, sticky="w", pady=(8, 0))
        bb = ttk.Frame(af); bb.grid(row=5, column=0, sticky="w", pady=(6, 0))
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
            box = ttk.LabelFrame(right, text=f" {name} ", padding=6)
            box.grid(row=i + 1, column=0, sticky="nsew", pady=(6, 0))
            right.rowconfigure(i + 1, weight=6 if name == "중요 배송메세지 확인" else 2 if name == "묶음배송 확인" else 1)
            box.columnconfigure(0, weight=1); box.rowconfigure(1, weight=1)
            head = ttk.Frame(box); head.grid(row=0, column=0, columnspan=2, sticky="we")
            ttk.Label(head, text=BOX_HINTS[name], style="Hint.TLabel").pack(side="left")
            ttk.Button(head, text="복사", width=6, command=lambda n=name: self.copy(n)).pack(side="right")
            t = T.text_box(tk.Text(box, height=16 if name == "중요 배송메세지 확인" else 3, wrap="none"))
            t.grid(row=1, column=0, sticky="nsew")
            sb = ttk.Scrollbar(box, orient="vertical", command=t.yview); sb.grid(row=1, column=1, sticky="ns")
            t.configure(yscrollcommand=sb.set, state="disabled")
            self.texts[name] = t
        self.buttons = [self.b_pre, self.b_make, self.b_rm, self.b_clear]
        self.refresh()

    # ------------------------------------------------------------
    def refresh(self):
        cand = op.courier_candidates()
        self.wait.delete(*self.wait.get_children())
        for o, when in cand:
            if not self.wait.exists(o["order_id"]):
                self.wait.insert("", "end", iid=o["order_id"], values=(o["order_id"], o["buyer"], o["place"], when))
        self.wait_lb.configure(text=f"대기 {len(cand)}건")
        hist = op.load_courier_history()
        self.hist.configure(values=[f"{h['time'][5:16].replace('T', ' ')} · {h['count']}건 · {Path(h['file']).name}"
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

    def _fill(self, texts):
        for name, t in self.texts.items():
            t.configure(state="normal"); t.delete("1.0", "end")
            v = texts.get(name, "")
            t.insert("1.0", v if v else "(없음)")
            t.configure(state="disabled")

    def copy(self, name):
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
        self.app.label_tab.set_target(ids=h.get("orders", []), split_n=h.get("split_orders", 0),
                                      title=f"{h['time'][5:16].replace('T', ' ')} 택배 파일의 주문 {len(h.get('orders', []))}건")

    def run(self, create):
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
            self.app.label_tab.set_target(rows=r["rows"], title=("방금 만든 택배 파일" if create else "미리 확인한 대기 주문")
                                          + f"의 주문 {len(r['orders'])}건")
            a = r["analysis"]
            self._fill(r["texts"])
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
            if r["path"]:
                op.open_file(op.COURIER_DIR)
            self.refresh()
            self.app.refresh_status()
        self.app.bg(work, done, "카페24에서 주문 불러오는 중...", progress=True)
