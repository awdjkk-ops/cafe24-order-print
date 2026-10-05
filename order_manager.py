# -*- coding: utf-8 -*-
"""주문서 출력 관리 - 통합 창 (출력 / 자동 출력 설정 / 관리)"""
import datetime as dt
import queue
import threading
import tkinter as tk
from collections import Counter
from pathlib import Path
from tkinter import ttk, messagebox

import order_print as op
import print_schedule as sch
from gui_admin import AdminTab
from gui_courier import CourierTab
from gui_lists import ListsTab
from gui_labels import LabelTab
from gui_scroll import scrolled
import theme as T
import updater
from gui_schedule import ScheduleTab, hint



class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("주문서 출력 관리")
        self.minsize(760, 520)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{min(1260, sw - 40)}x{min(960, sh - 80)}+10+10")
        self.q = queue.Queue()
        self.busy = False
        self.cfg = None
        T.apply(self)
        try:
            self.cfg = op.load_config()
        except Exception as e:
            messagebox.showerror("설정 확인", f"config.json을 확인해 주세요.\n\n{e}")

        # ---- 머리글 (엔비즈워크 스타일)
        top = tk.Frame(self, bg=T.CARD, highlightbackground=T.LINE, highlightthickness=1)
        top.pack(fill="x")
        tk.Label(top, text="주문서 출력 관리", bg=T.CARD, fg=T.INK, font=T.f(17, True)).pack(side="left", padx=(22, 8), pady=10)
        tk.Label(top, text=f"v{updater.local_info().get('version', '?')}", bg=T.CARD, fg=T.MUTED,
                 font=T.f(9)).pack(side="left", pady=(16, 10))
        self.update_pill = T.Pill(top, text=" ", bg="#E8F0FE", fg="#1A56C4")
        self.update_pill.configure(cursor="hand2")
        self.update_pill.bind("<Button-1>", lambda e: self.do_update())
        self.pending_update = None
        self.update_state = "checking"
        self.auto_pill = T.pill(top, "자동 출력 확인 중")
        self.auto_pill.pack(side="right", padx=(8, 22))
        self.result_pill = T.pill(top, "")
        self.result_pill.pack(side="right", padx=(8, 0))
        td = dt.date.today()
        tk.Label(top, text=f"{td.year}년 {td.month}월 {td.day}일({'월화수목금토일'[td.weekday()]})",
                 bg=T.CARD, fg=T.MUTED, font=T.f(10)).pack(side="right", padx=8)

        # ---- 메뉴 버튼 (바깥 탭 대신)
        self.nav = tk.Frame(self, bg=T.BG); self.nav.pack(fill="x", padx=18, pady=(12, 2))
        self.nav_btns = {}

        # 작업 중 표시 띠 (모든 탭 공통, 작업 중일 때만 보임)
        self.band = tk.Canvas(self, height=42, background=T.BG, highlightthickness=0, bd=0)
        self.band_fill, self.band_line = T.GREEN_L, "#BFE3D2"
        self.band_dot = tk.Label(self.band, text="●", bg=T.GREEN_L, fg=T.GREEN, font=T.f(11, True))
        self.prog_lb = tk.Label(self.band, text="", bg=T.GREEN_L, fg=T.GREEN_D, font=T.f(10, True), anchor="w")
        self.pbar = ttk.Progressbar(self.band, length=320)
        self._w_dot = self.band.create_window(16, 21, window=self.band_dot, anchor="w")
        self._w_lb = self.band.create_window(36, 21, window=self.prog_lb, anchor="w")
        self._w_bar = self.band.create_window(0, 21, window=self.pbar, anchor="e", state="hidden")
        self.band.bind("<Configure>", lambda e: self._band_draw())
        self._busy_msg = ""
        self._flash_job = None

        nb = ttk.Notebook(self, style="Main.TNotebook")
        nb.pack(fill="both", expand=True, padx=6, pady=(4, 6))
        self.nb = nb
        self.pages = {}

        def add(key, text, build):
            area, tab = scrolled(nb, build)
            nb.add(area, text=text)
            self.pages[key] = area
            b = T.Pill(self.nav, text=text, bg=T.CARD, fg=T.INK, outline=T.LINE, under=T.BG, padx=16, pady=8)
            b.configure(cursor="hand2")
            b.pack(side="left", padx=(0, 8))
            b.bind("<Button-1>", lambda e, k=key: self.show_tab(k))
            self.nav_btns[key] = b
            return tab
        self.print_tab = add("print", "출력", lambda p: ttk.Frame(p, padding=12, style="Page.TFrame"))
        self.courier_tab = add("courier", "택배", lambda p: CourierTab(p, self))
        self.label_tab = add("label", "라벨", lambda p: LabelTab(p, self))
        self.lists_tab = add("lists", "블랙리스트·추가배송", lambda p: ListsTab(p, self))
        self.sched_tab = add("sched", "자동 출력 설정", lambda p: ScheduleTab(p, on_saved=self.refresh_status))
        self.admin_tab = add("admin", "관리", lambda p: AdminTab(p, self))

        def on_tab(e):
            self._paint_nav()
            self.refresh_status(); self.admin_tab.refresh(); self.courier_tab.refresh()
            if nb.select() == str(self.pages["lists"]):
                self.lists_tab.refresh()
            if nb.select() == str(self.pages["courier"]) and self.cfg:
                self.bg(lambda: op.prefetch_sheet(self.cfg), lambda _: None, busy=False)   # 블랙리스트·추가배송 미리 받기
        nb.bind("<<NotebookTabChanged>>", on_tab)
        self._build_print_tab()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self._poll)
        try:
            op.cleanup()
        except Exception as e:
            op.log.warning(f"정리 중 오류: {e}")
        self.refresh_all()
        self.after(1500, self.check_update)          # 켜자마자 새 버전 확인

    # ================================================================ 업데이트
    def check_update(self, manual=False):
        def done(res):
            ok, upd = res
            self.update_state = "ok" if ok else "fail"
            if not ok:
                self.admin_tab.refresh_update()
                if manual:
                    messagebox.showwarning("업데이트 확인", f"새 버전을 확인하지 못했습니다.\n\n{upd}")
                return
            self.pending_update = upd
            if upd:
                self.update_pill.configure(text=f"새 버전 v{upd['version']} 있음 · 업데이트")
                self.update_pill.pack(side="left", padx=(14, 0), pady=12)
                if not manual and not getattr(self, "_update_popup_shown", False):
                    self._update_popup_shown = True            # 켤 때 한 번만
                    UpdateDialog(self, upd, lambda: self.do_update(confirm=False))
            else:
                self.update_pill.pack_forget()
            if manual:
                if upd:
                    self.do_update()
                else:
                    messagebox.showinfo("업데이트 확인", f"최신 버전입니다 (v{updater.local_info().get('version')}).")
            self.admin_tab.refresh_update()

        def work():
            try:
                return True, updater.check(self.cfg)
            except Exception as e:
                op.log.warning(f"업데이트 확인 실패: {e}")
                return False, e
        self.bg(work, done, busy=False)

    def do_update(self, confirm=True):
        upd = self.pending_update
        if not upd:
            return
        if self.busy or op.another_running():
            messagebox.showinfo("업데이트", "출력이나 다른 작업이 진행 중입니다. 끝난 뒤 다시 눌러 주세요.")
            return
        notes = upd.get("notes") or "(바뀐 내용 설명 없음)"
        if confirm and not messagebox.askyesno("업데이트", f"새 버전 v{upd['version']}으로 업데이트할까요?\n"
                                            f"(지금 v{updater.local_info().get('version')})\n\n바뀐 내용:\n{notes}\n\n"
                                            "설정·인증·출력 기록은 그대로 유지되고, 문제가 있으면 관리 탭에서 이전 버전으로 되돌릴 수 있습니다.\n"
                                            "업데이트가 끝나면 창을 다시 엽니다."):
            return

        def work(prog):
            with op.run_lock():
                return updater.apply(self.cfg, upd, prog)

        def done(ver):
            op.log.info(f"[업데이트] v{ver} 설치 완료")
            messagebox.showinfo("업데이트 완료", f"v{ver}으로 업데이트했습니다. 창을 다시 엽니다.")
            updater.restart_manager()
            self.destroy()
        self.bg(work, done, "새 버전 받는 중...", progress=True)

    def show_tab(self, key):
        self.nb.select(self.pages[key])
        self._paint_nav()

    def _paint_nav(self):
        cur = self.nb.select()
        for key, b in self.nav_btns.items():
            on = str(self.pages[key]) == cur
            b.configure(bg=T.INK if on else T.CARD, fg="white" if on else T.INK,
                        highlightbackground=T.INK if on else T.LINE)

    # ================================================================ 백그라운드 작업
    def bg(self, work, done=None, msg=None, busy=True, progress=False):
        """오래 걸리는 일은 따로 실행하고, 끝나면 done(결과)을 화면 쪽에서 호출"""
        if busy:
            if self.busy:
                messagebox.showinfo("잠시만요", "다른 작업이 진행 중입니다. 끝난 뒤 다시 눌러 주세요.")
                return
            self._set_busy(True, msg or "처리 중...")

        def prog(d, t):
            self.q.put(("progress", (d, t)))

        def runner():
            try:
                res = work(prog) if progress else work()
                self.q.put(("done", (done, res, busy)))
            except Exception as e:
                op.log.exception("작업 오류")
                self.q.put(("error", (e, busy)))
        threading.Thread(target=runner, daemon=True).start()

    def _poll(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "progress":
                    d, t = data
                    self.pbar.stop()
                    self.pbar.configure(mode="determinate", maximum=t, value=d)
                    base = self._busy_msg.rstrip(".") or "처리 중"
                    self.prog_lb.configure(text=f"{base}  {d} / {t}건   ·   끝날 때까지 창을 닫지 마세요")
                elif kind == "done":
                    done, res, busy = data
                    if busy:
                        self._set_busy(False)
                    if done:
                        done(res)
                elif kind == "error":
                    e, busy = data
                    if busy:
                        self._set_busy(False)
                    self._show_error(e)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _show_error(self, e):
        if isinstance(e, op.AuthError):
            messagebox.showerror("카페24 인증 필요", f"카페24 인증이 만료되었거나 없습니다.\n관리 탭에서 다시 인증해 주세요.\n\n상세: {e}")
        elif isinstance(e, op.Busy):
            messagebox.showinfo("잠시만요", str(e))
        elif isinstance(e, op.OrderCheckError):
            messagebox.showerror("인쇄 전 검사에서 멈춤", str(e))
        elif isinstance(e, updater.UpdateError):
            messagebox.showerror("업데이트 실패", f"{e}\n\n아무 파일도 바꾸지 않았습니다. 지금 버전을 그대로 쓰시면 됩니다.")
        else:
            messagebox.showerror("오류", f"작업 중 오류가 발생했습니다.\n\n{e}\n\n계속되면 관리 탭 → '실행 기록 보기' 내용을 Claude에게 보여주세요.")
        self.refresh_status()

    def _set_busy(self, on, msg=""):
        self.busy = on
        for b in (self.action_buttons + getattr(getattr(self, "courier_tab", None), "buttons", [])
                  + getattr(getattr(self, "label_tab", None), "buttons", [])):
            b.state(["disabled"] if on else ["!disabled"])
        if on:
            self._busy_msg = msg
            self._band_show(msg, T.GREEN_L, T.GREEN_D, progress=True)
            self.pbar.configure(mode="indeterminate"); self.pbar.start(12)
            self._blink()
        else:
            self.pbar.stop(); self.pbar.configure(mode="determinate", value=0)
            self._band_hide()

    def _band_draw(self):
        w = max(self.band.winfo_width(), 100)
        self.band.delete("frame")
        T._round_poly(self.band, 1, 1, w - 2, 40, T.RADIUS, fill=self.band_fill, outline=self.band_line, tags="frame")
        self.band.tag_lower("frame")
        self.band.coords(self._w_bar, w - 16, 21)

    def _band_show(self, text, bg, fg, progress=False):
        if self._flash_job:
            self.after_cancel(self._flash_job); self._flash_job = None
        self.band_fill, self.band_line = bg, ("#BFE3D2" if bg == T.GREEN_L else T.LINE)
        for w in (self.band_dot, self.prog_lb):
            w.configure(bg=bg)
        self.prog_lb.configure(text=text, fg=fg); self.band_dot.configure(fg=T.GREEN if progress else fg)
        self.band.itemconfigure(self._w_bar, state="normal" if progress else "hidden")
        if not self.band.winfo_ismapped():
            self.band.pack(fill="x", padx=18, pady=(8, 0), before=self.nb)
        self._band_draw()

    def _band_hide(self):
        self.band.pack_forget()

    def _blink(self):
        """작업 중 점이 깜빡여서 멈추지 않았다는 걸 보여줌"""
        if not self.busy:
            return
        cur = self.band_dot.cget("fg")
        self.band_dot.configure(fg=T.GREEN_L if cur == T.GREEN else T.GREEN)
        self.after(500, self._blink)

    def flash(self, text):
        """짧은 알림 (복사했습니다 등) — 3초 뒤 사라짐. 작업 중이면 표시하지 않음"""
        if self.busy:
            return
        self._band_show(text, T.CARD, T.INK)
        self._flash_job = self.after(3000, self._band_hide)

    def on_close(self):
        if self.busy and not messagebox.askyesno("작업 중", "출력 작업이 진행 중입니다. 지금 닫으면 인쇄가 중단될 수 있어요.\n그래도 닫을까요?"):
            return
        if self.sched_tab.dirty and not messagebox.askyesno("저장 안 됨", "자동 출력 설정에 저장하지 않은 변경이 있습니다.\n저장하지 않고 닫을까요?"):
            return
        self.destroy()

    # ================================================================ 출력 탭
    def _build_print_tab(self):
        t = self.print_tab
        left = ttk.Frame(t, style="Page.TFrame"); left.grid(row=0, column=0, sticky="nw")
        right = ttk.Frame(t, style="Page.TFrame"); right.grid(row=0, column=1, sticky="nsew", padx=(16, 0))
        t.columnconfigure(1, weight=1); t.rowconfigure(0, weight=1)

        # 알림 띠 (문제가 있을 때만)
        self.alert_fr = ttk.Frame(left, style="Page.TFrame"); self.alert_fr.grid(row=0, column=0, sticky="we")
        self._alerts = {}
        # 쇼핑몰별 새 주문 타일
        nf = ttk.Frame(left, style="Page.TFrame"); nf.grid(row=1, column=0, sticky="we", pady=(4, 6))
        head = ttk.Frame(nf, style="Page.TFrame"); head.pack(fill="x")
        self.new_title = ttk.Label(head, text="지금 새 주문  확인 중...", style="PageTitle.TLabel")
        self.new_title.pack(side="left")
        b = ttk.Button(head, text="새로 고침", style="Page.TButton", command=self.refresh_all); b.pack(side="right")
        self.tiles_fr = ttk.Frame(nf, style="Page.TFrame"); self.tiles_fr.pack(fill="x", pady=(8, 0))

        # 출력하기
        af = ttk.LabelFrame(left, text=" 출력하기 ", padding=12); af.grid(row=2, column=0, sticky="we", pady=(8, 0))
        brow = ttk.Frame(af); brow.grid(row=0, column=0, sticky="w")
        b1 = ttk.Button(brow, text="지금 출력", style="Main.TButton", command=self.print_now); b1.pack(side="left")
        b2 = ttk.Button(brow, text="미리보기", command=self.preview, padding=(22, 10)); b2.pack(side="left", padx=10)
        hint(af, "지금 출력: 마지막 출력 이후 새로 들어온 주문을 바로 인쇄합니다. 인쇄 전에 한 번 확인하고, 출력한 주문은 "
                 "기록되어 다시 나오지 않습니다.\n미리보기: 인쇄하지 않고 주문서를 화면으로만 봅니다.",
             row=1, column=0, sticky="w", pady=(8, 0), wrap=430)
        sp = tk.Frame(af, bg="#F1FAEC", highlightbackground="#B7E4B0", highlightthickness=1)
        sp.grid(row=2, column=0, sticky="we", pady=(10, 0))
        self.split_var = tk.BooleanVar(value=op.split_on())
        ttk.Checkbutton(sp, text="오늘 스마트스토어 따로 작업", variable=self.split_var, style="Split.TCheckbutton",
                        command=self.toggle_split).grid(row=0, column=0, sticky="w", padx=8, pady=(6, 0))
        self.split_lb = tk.Label(sp, text="", bg="#F1FAEC", fg=T.MUTED, font=T.f(9), justify="left", wraplength=410, anchor="w")
        self.split_lb.grid(row=1, column=0, sticky="w", padx=10)
        b13 = ttk.Button(sp, text="전체 인쇄 · 스마트스토어 나눠서", command=lambda: self.print_now(split=True))
        b13.grid(row=2, column=0, sticky="w", padx=8, pady=(4, 8))
        self._split_text()

        # 출력주문 엑셀
        xf = ttk.LabelFrame(left, text=" 출력주문 엑셀 (택배 발송용 원본) ", padding=10)
        xf.grid(row=4, column=0, sticky="we", pady=(8, 0))
        ttk.Label(xf, text="날짜").grid(row=0, column=0, sticky="w")
        self.xdate = ttk.Entry(xf, width=12); self.xdate.grid(row=0, column=1, sticky="w", padx=6)
        self.xdate.insert(0, dt.date.today().isoformat())
        b11 = ttk.Button(xf, text="이 날 뽑은 주문 엑셀 만들기", style="Ghost.TButton", command=self.export_csv)
        b11.grid(row=0, column=2, sticky="w")
        hint(xf, "그날 이 프로그램으로 인쇄한 주문(오전·오후·수동 모두)을 뽑은 순서대로 카페24 '엑셀 바로 다운로드'와 "
                 "같은 형식의 CSV 1개로 만듭니다. 카페24에서 최신 정보를 불러오며, 그사이 취소된 주문은 뺍니다. "
                 "만든 뒤 폴더가 열리면 웹 도구에 끌어다 놓으세요.", row=1, column=0, columnspan=3, sticky="w", pady=(4, 0), wrap=420)

        # 어디까지 뽑았나
        lf = ttk.LabelFrame(left, text=" 어디까지 뽑았나 ", padding=12); lf.grid(row=3, column=0, sticky="we", pady=(8, 0))
        self.last_lb = ttk.Label(lf, text="", justify="left", wraplength=420, font=T.f(11, True)); self.last_lb.grid(row=0, column=0, sticky="w")
        hint(lf, "오른쪽 주문 현황의 초록 줄 위치입니다. 다음 출력은 선 아래 주문부터 나옵니다. "
                 "카페24에서 직접 뽑은 날은 주문 현황에서 선을 맞춰 주세요.",
             row=1, column=0, sticky="w", pady=(4, 0), wrap=420)

        # 오른쪽: 주문 현황 / 출력 기록 / 주문 찾기
        right.columnconfigure(0, weight=1); right.rowconfigure(0, weight=1)
        sub = ttk.Notebook(right); sub.grid(row=0, column=0, sticky="nsew")
        self.sub = sub
        bf = ttk.Frame(sub, padding=10); hf = ttk.Frame(sub, padding=10); of = ttk.Frame(sub, padding=10)
        sub.add(bf, text=" 주문 현황 · 어디까지 뽑았나 "); sub.add(hf, text=" 출력 기록 "); sub.add(of, text=" 주문 찾기 ")

        # --- 주문 현황
        bf.columnconfigure(0, weight=1); bf.rowconfigure(2, weight=1)
        top = ttk.Frame(bf); top.grid(row=0, column=0, sticky="we")
        self.bsearch = ttk.Entry(top, width=24); self.bsearch.pack(side="left")
        self.bsearch.bind("<Return>", lambda e: self.board_find())
        bs = ttk.Button(top, text="목록에서 찾기", command=self.board_find); bs.pack(side="left", padx=4)
        br = ttk.Button(top, text="목록 새로 고침", command=self.load_board); br.pack(side="right")
        hint(bf, "카페24의 상품준비중·배송준비중 주문 전체를 결제시각 순으로 보여줍니다. 초록 줄이 '여기까지 뽑음' 위치입니다. "
                 "주문번호나 이름을 입력해 [목록에서 찾기]를 누르면 그 주문으로 이동합니다.",
             row=1, column=0, sticky="w", pady=(4, 6), wrap=640)
        cols = (("pay", "결제시각", 100), ("oid", "주문번호", 140), ("buyer", "주문자", 70), ("place", "경로", 85),
                ("items", "상품", 40), ("st", "상태", 200))
        self.board = ttk.Treeview(bf, columns=[c[0] for c in cols], show="headings", height=14, selectmode="extended")
        for c, txt, w in cols:
            self.board.heading(c, text=txt); self.board.column(c, width=w, anchor="center" if c == "items" else "w")
        self.board.tag_configure("done", foreground=T.DIM)
        self.board.tag_configure("todo", foreground=T.INK)
        self.board.tag_configure("late", foreground=T.INK)
        self.board.tag_configure("line", background=T.GREEN, foreground="white", font=T.f(10, True))
        self.board.grid(row=2, column=0, sticky="nsew")
        sb = ttk.Scrollbar(bf, orient="vertical", command=self.board.yview); sb.grid(row=2, column=1, sticky="ns")
        self.board.configure(yscrollcommand=sb.set)
        self.board_rows = []
        btns = ttk.Frame(bf); btns.grid(row=3, column=0, sticky="we", pady=(8, 0))
        b7 = ttk.Button(btns, text="선택한 주문까지 뽑은 것으로", command=self.set_line); b7.grid(row=0, column=0, sticky="w")
        b8 = ttk.Button(btns, text="이 고객부터 출력", command=self.print_from); b8.grid(row=0, column=1, sticky="w", padx=6)
        b9 = ttk.Button(btns, text="선택한 주문만 출력", command=self.print_selected); b9.grid(row=0, column=2, sticky="w")
        b12 = ttk.Button(btns, text="안 뽑은 상태로", command=self.revert_selected); b12.grid(row=0, column=3, sticky="w", padx=(6, 0))
        b14 = ttk.Button(btns, text="택배·라벨에 넣기", style="Ghost.TButton", command=self.add_courier_selected)
        b14.grid(row=1, column=0, sticky="w", pady=(6, 0))
        b10 = ttk.Button(btns, text="되돌리기", command=self.undo_line); b10.grid(row=0, column=4, sticky="e", padx=(12, 0))
        # 오른쪽 클릭 메뉴
        self.board_menu = tk.Menu(self, tearoff=0, font=T.f(10))
        self.board_menu.add_command(label="선택한 주문까지 뽑은 것으로", command=self.set_line)
        self.board_menu.add_command(label="이 고객부터 출력", command=self.print_from)
        self.board_menu.add_command(label="선택한 주문만 출력", command=self.print_selected)
        self.board_menu.add_separator()
        self.board_menu.add_command(label="안 뽑은 상태로 되돌리기", command=self.revert_selected)
        self.board_menu.add_command(label="택배·라벨에 넣기", command=self.add_courier_selected)

        def popup(e):
            row = self.board.identify_row(e.y)
            if row and row != "__line__" and row not in self.board.selection():
                self.board.selection_set(row)
            if self.board.selection() and not self.busy:
                self.board_menu.tk_popup(e.x_root, e.y_root)
        self.board.bind("<Button-3>", popup)
        hint(bf, "· 선택한 주문까지 뽑은 것으로: 고른 주문과 그 위는 '뽑음', 아래는 '다음에 출력'이 됩니다. 인쇄는 안 합니다. "
                 "카페24에서 직접 뽑은 뒤 위치를 맞출 때 씁니다(위·아래 어느 쪽으로든 옮길 수 있음).\n"
                 "· 이 고객부터 출력: 고른 주문 앞까지는 '뽑음'으로 두고, 고른 주문부터 끝까지 인쇄합니다.\n"
                 "· 선택한 주문만 출력: 고른 주문들만 인쇄합니다 (Ctrl·Shift+클릭으로 여러 개).\n"
                 "· 안 뽑은 상태로: 이미 뽑은(회색) 주문을 다음 출력에 다시 나오게 합니다. 택배 파일에 다시 넣을지는 확인 창에서 고릅니다.\n"
                 "· 되돌리기: 바로 전의 선 옮기기·안 뽑은 상태로 되돌리기를 취소합니다. (주문 위에서 오른쪽 클릭하면 메뉴가 나와요)\n"
                 "· 선택한 주문까지 뽑은 것으로: 표시만 하고 택배 파일·라벨·출력주문 엑셀에는 들어가지 않습니다 (카페24에서 직접 뽑은 경우).\n"
                 "· 택배·라벨에 넣기: 고른 주문을 인쇄 없이 택배 대기에 넣습니다. 택배 탭에서 택배 파일을 만들면 라벨도 함께 준비됩니다.\n"
                 "· 주황색 '늦게 들어옴'은 선보다 앞 시각이지만 나중에 카페24에 들어온 마켓 주문으로, 다음 출력 때 나옵니다.",
             row=4, column=0, sticky="w", pady=(6, 0), wrap=640)

        # --- 출력 기록
        hf.columnconfigure(0, weight=1); hf.rowconfigure(0, weight=1)
        cols = (("time", "날짜·시간", 105), ("kind", "구분", 100), ("count", "건수", 50),
                ("first", "첫 주문", 200), ("last", "마지막 주문", 200))
        self.hist = ttk.Treeview(hf, columns=[c[0] for c in cols], show="headings", height=8, selectmode="browse")
        for c, txt, w in cols:
            self.hist.heading(c, text=txt); self.hist.column(c, width=w, anchor="center" if c in ("count", "kind") else "w")
        self.hist.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.hist.bind("<<TreeviewSelect>>", lambda e: self.show_batch())
        b3 = ttk.Button(hf, text="선택한 묶음 다시 뽑기", command=self.reprint_batch)
        b3.grid(row=1, column=1, sticky="e", pady=(6, 0))
        hint(hf, "최근 30일 동안의 출력과 기준 조정 기록입니다. 줄을 누르면 아래에 주문 목록이 보이고, "
                 "용지 걸림 등으로 안 나왔을 때 [선택한 묶음 다시 뽑기]로 그대로 다시 인쇄합니다.",
             row=1, column=0, sticky="w", pady=(6, 0), wrap=430)
        self.blist = ttk.Treeview(hf, columns=("oid", "place", "buyer", "rcv", "pay"), show="headings", height=8)
        for c, txt, w in (("oid", "주문번호", 150), ("place", "경로", 90), ("buyer", "주문자", 80),
                          ("rcv", "수령자", 80), ("pay", "결제시각", 125)):
            self.blist.heading(c, text=txt); self.blist.column(c, width=w, anchor="w")
        self.blist.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        hf.rowconfigure(2, weight=1)

        # --- 주문 찾기
        of.columnconfigure(0, weight=1); of.rowconfigure(2, weight=1)
        sf2 = ttk.Frame(of); sf2.grid(row=0, column=0, columnspan=2, sticky="we")
        self.search = ttk.Entry(sf2, width=28); self.search.pack(side="left")
        self.search.bind("<Return>", lambda e: self.find())
        b4 = ttk.Button(sf2, text="출력 기록에서 찾기", command=self.find); b4.pack(side="left", padx=4)
        b5 = ttk.Button(sf2, text="카페24에서 찾기", command=self.find_cafe24); b5.pack(side="left")
        hint(of, "주문번호나 주문자·수령자 이름(일부도 가능)으로 찾습니다. 이미 배송된 예전 주문은 [카페24에서 찾기]로 "
                 "최근 3개월까지 찾을 수 있습니다.", row=1, column=0, columnspan=2, sticky="w", pady=(4, 6), wrap=640)
        cols = (("oid", "주문번호", 150), ("place", "경로", 90), ("buyer", "주문자", 75), ("rcv", "수령자", 75),
                ("pay", "결제시각", 125), ("printed", "출력한 때", 115))
        self.olist = ttk.Treeview(of, columns=[c[0] for c in cols], show="headings", height=12, selectmode="extended")
        for c, txt, w in cols:
            self.olist.heading(c, text=txt); self.olist.column(c, width=w, anchor="w")
        self.olist.grid(row=2, column=0, columnspan=2, sticky="nsew")
        self.olist_title = ttk.Label(of, text="", style="Hint.TLabel"); self.olist_title.grid(row=3, column=0, sticky="w", pady=(6, 0))
        b6 = ttk.Button(of, text="선택한 주문 다시 뽑기", command=self.reprint_selected)
        b6.grid(row=3, column=1, sticky="e", pady=(6, 0))
        hint(of, "고른 주문만 카페24에서 새로 불러와 인쇄합니다(여러 개: Ctrl+클릭). 오래된 주문도 가능합니다.",
             row=4, column=0, columnspan=2, sticky="w", wrap=640)
        self.action_buttons = [b, b1, b2, b3, b4, b5, b6, b7, b8, b9, b10, bs, br, b11, b12, b13, b14]

    # ---------------------------------------------------------------- 상태
    def _set_status(self, key, level, text):
        """상태: 자동 출력 → 머리글 알약 / 문제(카페24·프린터 등) → 빨간 알림 띠"""
        if key == "자동 출력":
            self.auto_pill.configure(text=f" {text} ", bg=T.GREEN_L if level == "ok" else "#EFEFEC",
                                     fg=T.GREEN_D if level == "ok" else T.MUTED)
            return
        if key == "지금 새 주문":
            if level == "none":
                self.new_title.configure(text="지금 새 주문  확인 중...")
            if level == "bad":
                self._alerts[key] = "[지금 새 주문] " + text
            else:
                self._alerts.pop(key, None)
        elif level in ("bad", "warn"):
            self._alerts[key] = f"[{key}] {text}"
        else:
            self._alerts.pop(key, None)
        self._render_alerts()

    def _show_auto_result(self):
        """오늘 자동 출력 결과를 머리글에 (문제가 있으면 빨간 알림 띠로도)"""
        st = op.read_json(op.AUTO_STATUS_FILE, {})
        self._alerts.pop("auto", None)
        if str(st.get("started", ""))[:10] != dt.date.today().isoformat():
            self.result_pill.pack_forget()
            return
        slot, res = str(st["started"])[11:16], st.get("result")
        if not st.get("final"):
            text, on = f"{slot} 자동 출력 진행 중", True
        elif res in ("ok", "unknown"):
            text, on = f"오늘 {slot} 자동 출력 완료 · {st.get('count', 0)}건", True
        elif res == "none":
            text, on = f"오늘 {slot} 자동 출력 · 새 주문 없음", False
        elif res == "stopped":
            text, on = f"오늘 {slot} 자동 출력 중지됨", False
            self._alerts["auto"] = (f"[자동 출력 중지] {slot} 출력을 중지했습니다 · 이번 주문 {st.get('count', 0)}건은 다음 출력에 다시 나옵니다"
                                    if st.get("count") else f"[자동 출력 중지] {slot} 출력을 중지했습니다")
        else:
            text, on = f"오늘 {slot} 자동 출력 확인 필요", False
            detail = ", ".join(st.get("printer_issues") or []) or str(st.get("message", "")).splitlines()[0][:60]
            self._alerts["auto"] = f"[자동 출력] {slot} 출력에 문제가 있었습니다: {detail} — '출력 확인 용지'가 나왔는지 확인하세요"
        self.result_pill.configure(text=f" {text} ", bg=T.GREEN_L if on else "#FDEBEC" if res in ("problem", "fail")
                                   else "#FFF1E6" if res == "stopped" else "#EFEFEC",
                                   fg=T.GREEN_D if on else T.RED if res in ("problem", "fail")
                                   else T.ORANGE if res == "stopped" else T.MUTED)
        self.result_pill.pack(side="right", padx=(8, 0))
        self._render_alerts()

    def _render_alerts(self):
        for w in self.alert_fr.winfo_children():
            w.destroy()
        for msg in self._alerts.values():
            T.alert(self.alert_fr, msg).pack(fill="x", pady=(0, 6))

    def toggle_split(self):
        op.set_split_today(self.split_var.get())
        op.log.info(f"[스마트스토어 따로 작업] 오늘 {'켬' if self.split_var.get() else '끔'}")
        self._split_text()

    def _split_text(self):
        on = op.split_on()
        self.split_var.set(on)
        self.split_lb.configure(text=("켜짐: 지금 출력·자동 출력·택배 파일·라벨에서 스마트스토어 쪽(그 고객의 다른 경로 주문 포함)이 "
                                      "맨 앞에 모이고, 주문서 사이에 구분 용지가 들어갑니다." if on else
                                      "꺼짐: 평소처럼 결제시각 순서대로. 요일 기본값은 자동 출력 설정 탭에서 정합니다.")
                                 + "\n아래 버튼은 스위치와 상관없이 이번 한 번만 나눠서 인쇄합니다.")

    def print_place(self, place):
        """타일을 누르면 그 경로의 '다음에 출력' 주문만 인쇄"""
        if self.busy:
            return
        targets = [o for o, done, _ in self.board_rows if not done
                   and op.PLACE_NAMES.get(o.get("order_place_id"), "기타") == place]
        if not targets:
            return
        if not messagebox.askyesno("이 경로만 출력", f"{place} 주문 {len(targets)}건만 인쇄할까요?\n"
                                                    "나머지 주문은 다음 출력에 그대로 나옵니다."):
            return

        def work(prog):
            token = op.get_access_token(self.cfg)
            with op.run_lock():
                op.log.info(f"[경로별 출력] {place} {len(targets)}건")
                return op.print_orders(self.cfg, token, targets, "선택 출력", prog)
        self.bg(work, lambda r: self._printed(len(targets), r), f"{place} 주문서 준비 중...", progress=True)

    def _render_tiles(self, todo):
        for w in self.tiles_fr.winfo_children():
            w.destroy()
        self.new_title.configure(text=f"지금 새 주문  {len(todo)}건")
        cnt = Counter(op.PLACE_NAMES.get(o.get("order_place_id"), "기타") for o in todo)
        if not cnt:
            ttk.Label(self.tiles_fr, text="새로 출력할 주문이 없습니다.", style="PageHint.TLabel").grid(row=0, column=0, sticky="w")
            return
        for i, (name, n) in enumerate(cnt.most_common()):
            t = T.tile(self.tiles_fr, name, n, width=138)
            t.grid(row=i // 3, column=i % 3, padx=(0, 8), pady=(0, 8))
            t.configure(cursor="hand2")
            t.bind("<Button-1>", lambda e, nm=name: self.print_place(nm))
            t.bind("<Enter>", lambda e, tt=t: tt.hover(True))
            t.bind("<Leave>", lambda e, tt=t: tt.hover(False))
        ttk.Label(self.tiles_fr, text="타일을 누르면 그 경로의 주문만 인쇄합니다.", style="PageHint.TLabel").grid(
            row=(len(cnt) - 1) // 3 + 1, column=0, columnspan=3, sticky="w")

    def refresh_all(self):
        self.refresh_status()
        self.admin_tab.refresh()
        self.load_board()

    def refresh_status(self):
        st, txt = op.token_status()
        self._set_status("카페24 연결", st, txt)
        s = sch.load_settings()
        if s.get("auto_enabled"):
            now = dt.datetime.now()
            nxt = next(((d, t) for d, times, _ in sch.upcoming(s, 30) for t in times
                        if dt.datetime.combine(d, dt.time(*map(int, t.split(":")))) > now), None)
            self._set_status("자동 출력", "ok", "자동 출력 켜짐 · 다음 " +
                             (f"{nxt[0]:%m/%d}({sch.WEEKDAYS[nxt[0].weekday()]}) {nxt[1]}" if nxt else "예정 없음"))
        else:
            self._set_status("자동 출력", "warn", "자동 출력 꺼짐")
        self._show_auto_result()
        cfg = self.cfg or {}
        if not op.find_sumatra(cfg):
            self._set_status("프린터", "bad", "인쇄 프로그램(SumatraPDF)이 없습니다 → 관리 탭 참고")
        else:
            name = cfg.get("printer_name")
            self._set_status("프린터", "ok", name if name else "윈도우 기본 프린터 사용")
        self.show_history()

    @staticmethod
    def _breakdown(orders):
        cnt = Counter(op.PLACE_NAMES.get(o.get("order_place_id"), "기타") for o in orders)
        return ", ".join(f"{k} {v}" for k, v in cnt.most_common())

    # ---------------------------------------------------------------- 주문 현황
    def load_board(self):
        if not self.cfg:
            return
        self._set_status("지금 새 주문", "none", "카페24에서 확인 중...")

        def work():
            try:
                return ("ok", op.order_board(self.cfg, op.get_access_token(self.cfg)))
            except Exception as e:
                op.log.warning(f"주문 현황 확인 실패: {e}")
                return ("err", e)

        def done(r):
            if r[0] != "ok":
                self._set_status("지금 새 주문", "bad", "확인 실패 (카페24 연결 상태를 확인해 주세요)")
                return
            self.fill_board(r[1])
        self.bg(work, done, busy=False)

    def fill_board(self, rows):
        self.board_rows = rows
        sel = set(self.board.selection())
        self.board.delete(*self.board.get_children())
        last_done = max((i for i, (_, done, _) in enumerate(rows) if done), default=-1)
        if last_done == -1:
            self.board.insert("", "end", iid="__line__", tags=("line",),
                              values=("", "▲ 아직 뽑은 주문 없음", "", "", "", ""))
        reverted = op.load_reverted()
        for i, (o, done, late) in enumerate(rows):
            br = op.order_brief(o)
            st = ("✓ 뽑음" if done else "↺ 되돌림 · 다음에 출력" if br["order_id"] in reverted
                  else "● 늦게 들어옴 · 다음에 출력" if late else "○ 다음에 출력")
            self.board.insert("", "end", iid=br["order_id"], tags=("done" if done else "late" if late else "todo",),
                              values=(br["pay_date"][5:], br["order_id"], br["buyer"], br["place"], br["items"], st))
            if i == last_done:
                self.board.insert("", "end", iid="__line__", tags=("line",),
                                  values=("", "▲ 여기까지 뽑음", "", "", "", ""))
        keep = [i for i in sel if self.board.exists(i)]
        if keep:
            self.board.selection_set(keep)
        self.board.see("__line__")
        todo = [o for o, done, _ in rows if not done]
        self._render_tiles(todo)
        self._set_status("지금 새 주문", "ok", "")
        late_n = sum(1 for _, d, l in rows if l)
        if late_n:
            self._alerts["late"] = f"[확인 필요] 늦게 들어온 주문 {late_n}건 — 다음 출력에 함께 나옵니다"
        else:
            self._alerts.pop("late", None)
        self._render_alerts()
        # 어디까지 뽑았나
        if last_done >= 0:
            o = op.order_brief(rows[last_done][0])
            late_n = sum(1 for _, d, l in rows if l)
            self.last_lb.configure(text=f"마지막으로 뽑은 주문: {o['order_id']}  {o['buyer']}\n"
                                        f"결제 {o['pay_date'][5:]} · {o['place']}"
                                        + (f"\n늦게 들어온 주문 {late_n}건은 다음 출력에 나옵니다." if late_n else ""))
        else:
            self.last_lb.configure(text="아직 뽑은 것으로 표시된 주문이 없습니다.\n"
                                        "오른쪽 주문 현황에서 카페24에서 마지막으로 뽑은 주문을 골라\n"
                                        "[선택한 주문까지 뽑은 것으로]를 눌러 위치를 맞춰 주세요.")

    def _board_selected(self):
        ids = [i for i in self.board.selection() if i != "__line__"]
        idx = {o["order_id"]: n for n, (o, _, _) in enumerate(self.board_rows)}
        return sorted((idx[i] for i in ids if i in idx))

    def board_find(self):
        t = self.bsearch.get().strip()
        if not t:
            return
        for o, _, _ in self.board_rows:
            br = op.order_brief(o)
            if t in br["order_id"] or t in br["buyer"] or t in br["receiver"]:
                self.board.selection_set(br["order_id"]); self.board.see(br["order_id"])
                return
        messagebox.showinfo("찾기", f"주문 현황에서 '{t}'을(를) 찾지 못했습니다.\n"
                                   "이미 배송된 주문이면 '주문 찾기' 탭의 [카페24에서 찾기]를 이용하세요.")

    def set_line(self):
        sel = self._board_selected()
        if len(sel) != 1:
            messagebox.showinfo("위치 맞추기", "주문 현황에서 '마지막으로 뽑은 주문' 하나를 골라 주세요.")
            return
        i = sel[0]
        above = [o for o, _, _ in self.board_rows[:i + 1]]
        below = [o for o, _, _ in self.board_rows[i + 1:]]
        br = op.order_brief(above[-1])
        late_n = sum(1 for _, _, l in self.board_rows[:i + 1] if l)
        msg = (f"{br['order_id']} {br['buyer']} (결제 {br['pay_date'][5:]})까지 뽑은 것으로 맞춥니다.\n\n"
               f"· 뽑음: {len(above)}건\n· 다음에 출력: {len(below)}건\n")
        if late_n:
            msg += (f"\n※ 선 위쪽에 '늦게 들어온' 주문 {late_n}건이 있습니다. 카페24에서 이 주문도 뽑으셨다면 계속하고, "
                    f"아니라면 '아니요'를 누른 뒤 [선택한 주문만 출력]으로 먼저 뽑아 주세요.\n")
        msg += "\n인쇄는 하지 않습니다. 계속할까요?"
        if not messagebox.askyesno("위치 맞추기", msg):
            return
        op.set_printed_line(above, below)
        self.refresh_status(); self.load_board()

    def add_courier_selected(self):
        sel = self._board_selected()
        rows = [self.board_rows[i] for i in sel]
        if not rows:
            messagebox.showinfo("택배·라벨에 넣기", "주문 현황에서 넣을 주문을 골라 주세요. (Ctrl·Shift+클릭으로 여러 개)")
            return
        orders = [o for o, _, _ in rows]
        not_printed = [o["order_id"] for o, done, _ in rows if not done]
        done_c = op.read_json(op.COURIER_DONE_FILE, {})
        in_courier = [o["order_id"] for o in orders if o["order_id"] in done_c]
        AddCourierDialog(self, orders, not_printed, in_courier, lambda mark: self._do_add_courier(orders, mark))

    def _do_add_courier(self, orders, mark):
        n, skipped = op.add_to_courier(orders, mark)
        msg = f"{n}건을 택배 대기에 넣었습니다."
        extra = [f"{k} {len(v)}건은 뺐습니다" for k, v in skipped.items() if v]
        self.flash(msg + (" (" + ", ".join(extra) + ")" if extra else ""))
        self.load_board(); self.courier_tab.refresh(); self.show_history()

    def revert_selected(self):
        sel = self._board_selected()
        rows = [self.board_rows[i] for i in sel]
        targets = [o for o, done, _ in rows if done]
        if not targets:
            messagebox.showinfo("안 뽑은 상태로", "주문 현황에서 이미 뽑은(회색) 주문을 골라 주세요. (Ctrl·Shift+클릭으로 여러 개)")
            return
        ids = [o["order_id"] for o in targets]
        in_courier = [i for i in ids if i in op.read_json(op.COURIER_DONE_FILE, {})]
        RevertDialog(self, ids, in_courier, lambda recourier: self._do_revert(ids, recourier))

    def _do_revert(self, ids, recourier):
        op.revert_printed(ids, recourier)
        self.flash(f"{len(ids)}건을 안 뽑은 상태로 되돌렸습니다." + (" (택배 파일에도 다시 넣음)" if recourier else ""))
        self.load_board()
        self.courier_tab.refresh()

    def undo_line(self):
        t = op.undo_line()
        if not t:
            messagebox.showinfo("되돌리기", "되돌릴 위치 조정 기록이 없습니다.")
            return
        messagebox.showinfo("되돌리기", f"{t[5:16].replace('T', ' ')}에 옮긴 위치를 되돌렸습니다.")
        self.load_board()

    def print_from(self):
        sel = self._board_selected()
        if len(sel) != 1:
            messagebox.showinfo("이 고객부터 출력", "주문 현황에서 출력을 시작할 주문 하나를 골라 주세요.")
            return
        i = sel[0]
        # 선택한 주문 앞쪽 중 '늦게 들어온' 주문은 아직 안 뽑은 것이므로 함께 인쇄
        late_above = [o for o, _, l in self.board_rows[:i] if l]
        before = [o for o, _, l in self.board_rows[:i] if not l]
        target = late_above + [o for o, _, _ in self.board_rows[i:]]
        br = op.order_brief(self.board_rows[i][0])
        msg = (f"{br['order_id']} {br['buyer']} (결제 {br['pay_date'][5:]})부터 끝까지 인쇄합니다.\n"
               f"· 인쇄: {len(target)}건 ({self._breakdown(target)})\n")
        if late_above:
            msg += f"   └ 이 중 늦게 들어온 주문 {len(late_above)}건 포함\n"
        msg += f"· 그 앞 {len(before)}건은 '뽑음'으로 표시\n\n계속할까요?"
        if not messagebox.askyesno("이 고객부터 출력", msg):
            return

        def work(prog):
            token = op.get_access_token(self.cfg)
            with op.run_lock():
                if before:
                    op.set_printed_line(before, [])
                return op.print_orders(self.cfg, token, target, "수동", prog)
        self.bg(work, lambda r: self._printed(len(target), r), "주문서 준비 중...", progress=True)

    def print_selected(self):
        sel = self._board_selected()
        if not sel:
            messagebox.showinfo("선택한 주문만 출력", "주문 현황에서 인쇄할 주문을 골라 주세요 (Ctrl·Shift+클릭으로 여러 개).")
            return
        target = [self.board_rows[i][0] for i in sel]
        if not messagebox.askyesno("선택한 주문만 출력", f"고른 주문 {len(target)}건을 인쇄할까요?\n({self._breakdown(target)})"):
            return

        def work(prog):
            token = op.get_access_token(self.cfg)
            with op.run_lock():
                return op.print_orders(self.cfg, token, target, "선택 출력", prog)
        self.bg(work, lambda r: self._printed(len(target), r), "주문서 준비 중...", progress=True)

    def _printed(self, n, res):
        pdf, pages = res
        messagebox.showinfo("출력 완료", f"{n}건 ({pages}장)을 프린터로 보냈습니다.")
        self.refresh_all()

    # ---------------------------------------------------------------- 출력주문 엑셀
    def export_csv(self):
        try:
            day = dt.date.fromisoformat(self.xdate.get().strip())
        except ValueError:
            messagebox.showwarning("날짜 형식", "날짜는 2026-09-29 처럼 입력해 주세요.")
            return
        ids = op.printed_ids_on(day)
        if not ids:
            messagebox.showinfo("출력주문 엑셀", f"{day:%m/%d}에 이 프로그램으로 인쇄한 주문이 없습니다.\n"
                                              "(출력 기록은 최근 30일까지 보관됩니다)")
            return

        def work(prog):
            return op.export_day_csv(self.cfg, op.get_access_token(self.cfg), day, prog)

        def done(res):
            path, n, nrows, excluded = res
            msg = f"{path.name}\n\n주문 {n}건 · {nrows}줄을 저장했습니다."
            if excluded:
                msg += f"\n\n인쇄 후 취소된 주문 {len(excluded)}건은 제외했습니다:\n" + "\n".join(excluded[:10]) + \
                       ("\n…" if len(excluded) > 10 else "")
            messagebox.showinfo("출력주문 엑셀 완료", msg)
            op.open_file(op.CSV_DIR)
        self.bg(work, done, f"카페24에서 {len(ids)}건 불러오는 중...", progress=True)

    # ---------------------------------------------------------------- 출력 기록
    def show_history(self):
        self.hist.delete(*self.hist.get_children())
        fmt = lambda o: f"{o.get('order_id', '')} {o.get('buyer', '')}"
        for i, b in enumerate(op.load_history()):
            f, l = (b["orders"][0], b["orders"][-1]) if b["orders"] else ({}, {})
            self.hist.insert("", "end", iid=str(i), values=(b["time"][5:16].replace("T", " "), b["kind"],
                                                          b["count"] if b["kind"] != "기준 조정" else "-",
                                                          fmt(f) if b["kind"] != "기준 조정" else "", fmt(l)))

    def show_batch(self):
        sel = self.hist.selection()
        if not sel:
            return
        b = op.load_history()[int(sel[0])]
        self.blist.delete(*self.blist.get_children())
        for o in b["orders"]:
            self.blist.insert("", "end", values=(o["order_id"], o["place"], o["buyer"], o["receiver"], o["pay_date"]))

    def _fill_orders(self, rows, title):
        self.olist.delete(*self.olist.get_children())
        for o, printed in rows:
            if not self.olist.exists(o["order_id"]):
                self.olist.insert("", "end", iid=o["order_id"],
                                  values=(o["order_id"], o["place"], o["buyer"], o["receiver"], o["pay_date"], printed))
        self.olist_title.configure(text=title)

    # ---------------------------------------------------------------- 버튼 동작
    def _confirm_print(self, orders, what):
        extra = f"\n\n가장 이른 결제: {str(orders[0].get('payment_date') or '')[:16].replace('T', ' ')}" \
                f"\n가장 늦은 결제: {str(orders[-1].get('payment_date') or '')[:16].replace('T', ' ')}" if orders else ""
        return messagebox.askyesno("인쇄 확인", f"{what} {len(orders)}건을 인쇄할까요?\n({self._breakdown(orders)}){extra}")

    def print_now(self, split=None):
        split = op.split_on() if split is None else split

        def got(orders):
            if not orders:
                messagebox.showinfo("지금 출력", "새로 출력할 주문이 없습니다.")
                self.load_board()
                return
            what = "새 주문"
            if split:
                smart, rest = op.split_orders(orders)
                what = f"새 주문 (스마트스토어 쪽 {len(smart)}건 먼저 → 구분 용지 → 나머지 {len(rest)}건)"
            if not self._confirm_print(orders, what):
                return

            def work(prog):
                token = op.get_access_token(self.cfg)
                with op.run_lock():
                    op.log.info(f"[수동 출력] {len(orders)}건" + (" · 스마트스토어 나눠서" if split else ""))
                    return op.print_orders(self.cfg, token, orders, "수동", prog, split=split)

            self.bg(work, lambda r: self._printed(len(orders), r), "주문서 준비 중...", progress=True)
        self.bg(lambda: op.new_orders(self.cfg, op.get_access_token(self.cfg)), got, "새 주문 확인 중...")

    def preview(self):
        def got(orders):
            if not orders:
                messagebox.showinfo("미리보기", "새로 출력할 주문이 없습니다.")
                return
            self.bg(lambda prog: op.make_pdf(self.cfg, op.get_access_token(self.cfg), orders, "미리보기", prog),
                    lambda res: op.open_file(res[0]), "미리보기 만드는 중...", progress=True)
        self.bg(lambda: op.new_orders(self.cfg, op.get_access_token(self.cfg)), got, "새 주문 확인 중...")

    def reprint_batch(self):
        sel = self.hist.selection()
        if not sel:
            messagebox.showinfo("다시 뽑기", "위의 출력 기록에서 다시 뽑을 묶음을 먼저 눌러 주세요.")
            return
        b = op.load_history()[int(sel[0])]
        when = b["time"][5:16].replace("T", " ")
        if b["kind"] in (op.COURIER_ADD_KIND, "기준 조정", "자동(중지)"):
            messagebox.showinfo("다시 뽑기", f"'{b['kind']}' 기록은 이 프로그램이 인쇄한 묶음이 아니라 다시 뽑을 수 없습니다.\n"
                                         "필요한 주문은 주문 찾기 탭에서 골라 [선택한 주문 다시 뽑기]를 쓰세요.")
            return
        if not messagebox.askyesno("다시 뽑기", f"{when} {b['kind']} 출력 {b['count']}건({b.get('pages', '?')}장)을 다시 인쇄할까요?"):
            return
        if Path(b["pdf"]).exists():
            self.bg(lambda: op.print_pdf(self.cfg, b["pdf"]),
                    lambda _: messagebox.showinfo("완료", "프린터로 보냈습니다."), "인쇄 중...")
        else:   # 보관 기간이 지나 PDF가 지워졌으면 카페24에서 다시 불러와 만듦
            ids = [o["order_id"] for o in b["orders"]]
            self._reprint_ids(ids, "다시 뽑기")

    def reprint_selected(self):
        ids = list(self.olist.selection())
        if not ids:
            messagebox.showinfo("다시 뽑기", "아래 주문 목록에서 다시 뽑을 주문을 먼저 선택해 주세요.")
            return
        if not messagebox.askyesno("다시 뽑기", f"선택한 주문 {len(ids)}건을 카페24에서 불러와 인쇄할까요?\n" + "\n".join(ids[:10])
                                   + ("\n..." if len(ids) > 10 else "")):
            return
        self._reprint_ids(ids, "개별 다시 뽑기")

    def _reprint_ids(self, ids, kind):
        def work(prog):
            token = op.get_access_token(self.cfg)
            orders = op.fetch_orders_by_ids(self.cfg, token, ids)
            if not orders:
                raise RuntimeError("카페24에서 주문을 찾지 못했습니다 (취소된 주문일 수 있습니다).")
            with op.run_lock():
                return len(orders), op.print_orders(self.cfg, token, orders, kind, prog)

        def done(res):
            n, (pdf, pages) = res
            messagebox.showinfo("완료", f"{n}건 ({pages}장)을 프린터로 보냈습니다.")
            self.refresh_status()
        self.bg(work, done, "카페24에서 주문 불러오는 중...", progress=True)

    def find(self):
        text = self.search.get().strip()
        if not text:
            return
        rows = op.find_in_history(text)
        self._fill_orders([(o, f"{when} {kind}") for o, when, kind in rows],
                          f"출력 기록에서 '{text}' 검색 결과 {len(rows)}건" +
                          ("" if rows else "  → 없으면 [카페24에서 찾기]를 눌러 보세요"))

    def find_cafe24(self):
        text = self.search.get().strip()
        if not text:
            return
        hist = {}
        for b in op.load_history():
            for o in b["orders"]:
                hist.setdefault(o["order_id"], f"{b['time'][5:16].replace('T', ' ')} {b['kind']}")
        printed = op.read_json(op.PRINTED_FILE, {})

        def done(orders):
            rows = []
            for o in orders:
                br = op.order_brief(o)
                if o.get("canceled") == "T" or not o.get("items"):
                    mark = "취소된 주문"
                else:
                    mark = hist.get(br["order_id"]) or ("출력함" if br["order_id"] in printed else "아직 안 뽑음")
                rows.append((br, mark))
            self._fill_orders(rows, f"카페24에서 '{text}' 검색 결과 {len(rows)}건 (최근 3개월)")
        self.bg(lambda: op.search_cafe24(self.cfg, op.get_access_token(self.cfg), text), done, "카페24에서 찾는 중...")


class UpdateDialog(tk.Toplevel):
    """프로그램을 켰을 때 새 버전이 있으면 뜨는 작은 창 (업데이트는 버튼을 눌러야만 진행)"""

    def __init__(self, app, upd, on_update):
        super().__init__(app)
        import updater
        self.title("새 버전이 있습니다")
        self.configure(background=T.CARD)
        self.resizable(False, False)
        self.transient(app)
        self.on_update = on_update
        f = ttk.Frame(self, padding=20); f.pack(fill="both")
        ttk.Label(f, text="새 버전이 있습니다", style="Title.TLabel").pack(anchor="w")
        T.Pill(f, text=f"지금 v{updater.local_info().get('version', '?')}   →   새 버전 v{upd['version']}",
               bg="#E8F0FE", fg="#1A56C4").pack(anchor="w", pady=(8, 10))
        ttk.Label(f, text="바뀐 내용", font=T.f(10, True)).pack(anchor="w")
        notes = tk.Text(f, width=58, height=min(10, max(3, str(upd.get("notes", "")).count("\n") + 2)), wrap="word")
        T.text_box(notes)
        notes.insert("1.0", upd.get("notes") or "(바뀐 내용 설명 없음)")
        notes.configure(state="disabled")
        notes.pack(fill="x", pady=(4, 10))
        ttk.Label(f, text="설정·인증·출력 기록은 그대로 유지됩니다. 업데이트가 끝나면 창이 다시 열립니다.\n"
                          "아침 자동 출력은 업데이트와 상관없이 예정대로 진행됩니다.",
                  style="Hint.TLabel", justify="left").pack(anchor="w")
        bf = ttk.Frame(f); bf.pack(fill="x", pady=(16, 0))
        ttk.Button(bf, text="지금 업데이트", style="Accent.TButton", command=self.go).pack(side="right")
        ttk.Button(bf, text="나중에", command=self.destroy).pack(side="right", padx=6)
        self.update_idletasks()
        x = app.winfo_rootx() + (app.winfo_width() - self.winfo_width()) // 2
        y = app.winfo_rooty() + (app.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.lift(); self.focus_force()

    def go(self):
        self.destroy()
        self.on_update()


class AddCourierDialog(tk.Toplevel):
    """택배·라벨에 넣기 확인 창"""

    def __init__(self, app, orders, not_printed, in_courier, on_ok):
        super().__init__(app)
        self.title("택배·라벨에 넣기")
        self.configure(background=T.CARD)
        self.resizable(False, False)
        self.transient(app)
        self.on_ok = on_ok
        n_ok = len(orders) - len(in_courier)
        f = ttk.Frame(self, padding=18); f.pack(fill="both")
        ttk.Label(f, text=f"선택한 주문 {len(orders)}건을 택배 대기에 넣습니다", style="Title.TLabel").pack(anchor="w")
        ttk.Label(f, text="인쇄는 하지 않습니다. 택배 탭에서 택배 파일을 만들면 라벨도 같은 주문으로 준비됩니다.",
                  foreground=T.MUTED, wraplength=400, justify="left").pack(anchor="w", pady=(6, 0))
        self.mark = tk.BooleanVar(value=True)
        if not_printed:
            box = tk.Frame(f, bg="#F1FAEC", highlightbackground="#B7E4B0", highlightthickness=1); box.pack(fill="x", pady=(12, 0))
            tk.Label(box, text=f"이 중 {len(not_printed)}건은 아직 안 뽑은 주문입니다.", bg="#F1FAEC", fg=T.INK,
                     font=T.f(10, True), anchor="w").pack(fill="x", padx=10, pady=(8, 2))
            ttk.Checkbutton(box, text="뽑은 것으로도 표시 (다음 출력에 다시 안 나오게)", variable=self.mark,
                            style="Split.TCheckbutton").pack(anchor="w", padx=8)
            tk.Label(box, text="카페24에서 직접 뽑은 주문이면 그대로 두세요. 주문서를 나중에 이 프로그램으로 뽑을 거라면 체크를 끄세요.",
                     bg="#F1FAEC", fg=T.MUTED, font=T.f(9), justify="left", anchor="w", wraplength=380).pack(fill="x", padx=10, pady=(2, 8))
        if in_courier:
            box = tk.Frame(f, bg="#FFF8E6", highlightbackground="#F2D7A0", highlightthickness=1); box.pack(fill="x", pady=(10, 0))
            tk.Label(box, text=f"이 중 {len(in_courier)}건은 이미 택배 파일에 들어가서 빼고 넣습니다 (송장 중복 방지).\n"
                               + ", ".join(in_courier[:4]) + (" …" if len(in_courier) > 4 else ""),
                     bg="#FFF8E6", fg=T.INK, font=T.f(9), justify="left", anchor="w").pack(fill="x", padx=10, pady=8)
        bf = ttk.Frame(f); bf.pack(fill="x", pady=(16, 0))
        okb = ttk.Button(bf, text=f"{n_ok}건 넣기", style="Accent.TButton", command=self.ok); okb.pack(side="right")
        if n_ok == 0:
            okb.state(["disabled"])
        ttk.Button(bf, text="취소", command=self.destroy).pack(side="right", padx=6)
        self.update_idletasks()
        x = app.winfo_rootx() + (app.winfo_width() - self.winfo_width()) // 2
        y = app.winfo_rooty() + (app.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.grab_set()

    def ok(self):
        mark = self.mark.get()
        self.destroy()
        self.on_ok(mark)


class RevertDialog(tk.Toplevel):
    """안 뽑은 상태로 되돌리기 확인 창 (택배 파일에 다시 넣을지 선택)"""

    def __init__(self, app, ids, in_courier, on_ok):
        super().__init__(app)
        self.title("안 뽑은 상태로 되돌리기")
        self.configure(background=T.CARD)
        self.resizable(False, False)
        self.transient(app)
        self.on_ok = on_ok
        f = ttk.Frame(self, padding=18); f.pack(fill="both")
        ttk.Label(f, text=f"{len(ids)}건을 '안 뽑음'으로 되돌립니다", style="Title.TLabel").pack(anchor="w")
        ttk.Label(f, text="\n".join(ids[:8]) + ("\n…" if len(ids) > 8 else ""), foreground=T.MUTED).pack(anchor="w", pady=(6, 8))
        ttk.Label(f, text="다음 출력(자동 출력·지금 출력)에 이 주문서가 다시 인쇄됩니다.", wraplength=380,
                  justify="left").pack(anchor="w")
        self.recourier = tk.BooleanVar(value=False)
        if in_courier:
            box = tk.Frame(f, bg="#FFF8E6", highlightbackground="#F2D7A0", highlightthickness=1)
            box.pack(fill="x", pady=(12, 0))
            tk.Label(box, text=f"이 중 {len(in_courier)}건은 이미 택배 파일에 들어갔습니다.", bg="#FFF8E6", fg=T.INK,
                     font=T.f(10, True), anchor="w").pack(fill="x", padx=10, pady=(8, 2))
            ttk.Checkbutton(box, text="택배 파일에도 다시 넣기", variable=self.recourier,
                            style="Warn.TCheckbutton").pack(anchor="w", padx=8)
            tk.Label(box, text="체크하지 않으면 주문서만 다시 뽑히고, 택배 파일에는 다시 들어가지 않습니다.\n"
                               "체크하면 다음 택배 파일에 또 들어가서 송장이 두 번 나올 수 있어요.",
                     bg="#FFF8E6", fg=T.MUTED, font=T.f(9), justify="left", anchor="w").pack(fill="x", padx=10, pady=(2, 8))
        bf = ttk.Frame(f); bf.pack(fill="x", pady=(16, 0))
        ttk.Button(bf, text="되돌리기", style="Accent.TButton", command=self.ok).pack(side="right")
        ttk.Button(bf, text="취소", command=self.destroy).pack(side="right", padx=6)
        self.update_idletasks()
        x = app.winfo_rootx() + (app.winfo_width() - self.winfo_width()) // 2
        y = app.winfo_rooty() + (app.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.grab_set()

    def ok(self):
        recourier = self.recourier.get()
        self.destroy()
        self.on_ok(recourier)


if __name__ == "__main__":
    try:
        App().mainloop()
    except Exception as e:      # 창 없이 실행되므로 오류를 기록하고 알림
        op.log.exception("관리 창 오류")
        try:
            messagebox.showerror("오류", f"프로그램을 여는 중 오류가 발생했습니다.\n\n{e}\n\nlogs 폴더의 기록을 Claude에게 보여주세요.")
        except Exception:
            pass
