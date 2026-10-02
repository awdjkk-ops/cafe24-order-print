# -*- coding: utf-8 -*-
"""통합 창 - '자동 출력 설정' 탭 (요일별 시간, 공휴일, 날짜 지정, 달력, PC 켜는 방식)"""
import calendar
import datetime as dt
import tkinter as tk
from collections import Counter
from tkinter import ttk, messagebox

import print_schedule as sch
import theme as T

HOURS = [f"{h:02d}" for h in range(24)]
MINUTES = [f"{m:02d}" for m in range(0, 60, 5)]

GREEN, GREEN_TXT = "#BFE8C8", "#14532D"
PAST_BG, PAST_TXT = "#E4E4E4", "#9A9A9A"


def hint(parent, text, **grid):
    style = "PageHint.TLabel" if grid.pop("page", False) else "Hint.TLabel"
    lb = ttk.Label(parent, text=text, style=style, wraplength=grid.pop("wrap", 470), justify="left")
    lb.grid(**grid)
    return lb


class ScheduleTab(ttk.Frame):
    def __init__(self, master, on_saved=None):
        super().__init__(master, padding=12, style="Page.TFrame")
        self.on_saved = on_saved
        self.s = sch.load_settings()
        self.dirty = False

        left = ttk.Frame(self, style="Page.TFrame"); left.grid(row=0, column=0, sticky="nw")
        right = ttk.Frame(self, style="Page.TFrame"); right.grid(row=0, column=1, sticky="nw", padx=(16, 0))

        # 자동 출력 켜기
        self.auto = tk.BooleanVar(value=self.s["auto_enabled"])
        ttk.Checkbutton(left, text="자동 출력 사용", variable=self.auto, command=self.changed,
                        style="PageBig.TCheckbutton").grid(row=0, column=0, sticky="w")
        hint(left, "체크하면 아래에서 정한 날·시간에 새 주문이 저절로 인쇄됩니다. 끄면 예약이 모두 멈춥니다.\n"
                   "(출력 탭의 '지금 출력'은 이 설정과 상관없이 항상 쓸 수 있습니다.)",
             row=1, column=0, sticky="w", pady=(0, 8), page=True)

        # 요일별 (오전·오후)
        wf = ttk.LabelFrame(left, text=" 요일별 출력 시간 ", padding=10)
        wf.grid(row=2, column=0, sticky="we")
        hint(wf, "요일마다 오전·오후 출력을 따로 켜고 시간을 고르세요. 오후 출력은 오전 이후 새 주문만 나옵니다.",
             row=0, column=0, sticky="w", pady=(0, 6))
        rows = ttk.Frame(wf); rows.grid(row=1, column=0, sticky="w")
        ttk.Label(rows, text="오전", font=T.f(9, True)).grid(row=0, column=1, columnspan=4)
        ttk.Label(rows, text="오후", font=T.f(9, True)).grid(row=0, column=6, columnspan=4)
        self.wd = []
        for i, name in enumerate(sch.WEEKDAYS):
            ttk.Label(rows, text=f"{name}요일").grid(row=i + 1, column=0, sticky="w", padx=(0, 10))
            slots = {}
            for k, c0 in (("am", 1), ("pm", 6)):
                slots[k] = self._slot_widgets(rows, self.s["weekdays"][str(i)][k], i + 1, c0)
            ttk.Label(rows, text="   ").grid(row=i + 1, column=5)
            self.wd.append(slots)

        # 스마트스토어 따로 작업 요일
        spf = ttk.LabelFrame(left, text=" 스마트스토어 따로 작업 (요일 기본값) ", padding=10)
        spf.grid(row=7, column=0, sticky="we", pady=(10, 0))
        hint(spf, "체크한 요일에는 자동 출력·지금 출력·택배 파일·라벨에서 스마트스토어 쪽 주문이 맨 앞에 모이고, 주문서 사이에 "
                  "'여기까지 스마트스토어' 구분 용지가 들어갑니다. 그날그날은 출력 탭의 스위치로 바꿀 수 있습니다.",
             row=0, column=0, columnspan=7, sticky="w", pady=(0, 6))
        self.split_days = []
        sd = self.s.get("smart_split_weekdays", {})
        for i, name in enumerate(sch.WEEKDAYS):
            v = tk.BooleanVar(value=bool(sd.get(str(i))))
            ttk.Checkbutton(spf, text=name, variable=v, command=self.changed).grid(row=1, column=i, sticky="w", padx=(0, 8))
            self.split_days.append(v)

        self.holi = tk.BooleanVar(value=self.s["skip_public_holidays"])
        ttk.Checkbutton(left, text="공휴일은 자동으로 건너뛰기 (설·추석 연휴, 대체공휴일 포함)",
                        variable=self.holi, command=self.changed, style="Page.TCheckbutton").grid(row=3, column=0, sticky="w", pady=(8, 0))
        hint(left, "공휴일 달력을 따로 입력하지 않아도 됩니다.", row=4, column=0, sticky="w", pady=(0, 8), page=True)

        # 날짜 지정
        ef = ttk.LabelFrame(left, text=" 날짜 지정 (요일 규칙보다 우선) ", padding=10)
        ef.grid(row=5, column=0, sticky="we")
        hint(ef, "특정 날의 오전·오후 출력을 따로 정합니다. 둘 다 끄면 쉬는 날입니다. 오른쪽 달력에서 날짜를 누르면 "
                 "그 날짜가 아래 칸에 채워지니, 시간을 고른 뒤 [추가·수정]을 누르세요.",
             row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.tree = ttk.Treeview(ef, columns=("date", "am", "pm"), show="headings", height=4)
        for col, txt, w in (("date", "날짜", 120), ("am", "오전", 120), ("pm", "오후", 120)):
            self.tree.heading(col, text=txt); self.tree.column(col, width=w, anchor="center")
        self.tree.grid(row=1, column=0, columnspan=2, sticky="we")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._load_selected())
        self._exc = {e["date"]: e for e in self.s["exceptions"]}
        ed = ttk.Frame(ef); ed.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.e_date = ttk.Entry(ed, width=11); self.e_date.grid(row=0, column=0, padx=(0, 8))
        self.e_date.insert(0, (dt.date.today() + dt.timedelta(days=1)).isoformat())
        self.e_slots = {}
        ttk.Label(ed, text="오전").grid(row=0, column=1)
        self.e_slots["am"] = self._slot_widgets(ed, {"on": True, "time": "09:00"}, 0, 2, dirty=False)
        ttk.Label(ed, text="   오후").grid(row=0, column=6)
        self.e_slots["pm"] = self._slot_widgets(ed, {"on": False, "time": "14:00"}, 0, 7, dirty=False)
        bb = ttk.Frame(ef); bb.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Button(bb, text="추가·수정", command=self.add_exc).pack(side="left")
        ttk.Button(bb, text="선택 삭제 (원래 규칙으로)", command=self.del_exc).pack(side="left", padx=6)
        hint(ef, "날짜는 2026-10-15 형식.", row=4, column=0, sticky="w")
        self._fill_tree()

        # PC 켜는 방식
        pf = ttk.LabelFrame(left, text=" PC 켜는 방식 ", padding=10)
        pf.grid(row=6, column=0, sticky="we", pady=(8, 0))
        self.power = tk.StringVar(value=self.s["power_mode"])
        ttk.Radiobutton(pf, text="절전 모드 (퇴근 시 절전 → 출력 시간에 자동으로 깨어남)", value="sleep",
                        variable=self.power, command=self.changed).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(pf, text="완전 종료 + BIOS 알람(RTC) (쉬는 날 켜지면 2분 뒤 자동 종료)", value="rtc",
                        variable=self.power, command=self.changed).grid(row=1, column=0, sticky="w")
        self.rtc_hint = ttk.Label(pf, text="", foreground="#B25B00")
        self.rtc_hint.grid(row=2, column=0, sticky="w", pady=(4, 0))

        # 저장
        bf = ttk.Frame(left, style="Page.TFrame"); bf.grid(row=9, column=0, sticky="we", pady=(10, 0))
        self.dirty_lb = ttk.Label(bf, text="", foreground=T.ORANGE, style="Page.TLabel"); self.dirty_lb.pack(side="left")
        ttk.Button(bf, text="저장", command=self.save, style="Page.Accent.TButton").pack(side="right")
        ttk.Button(bf, text="되돌리기", style="Page.TButton", command=self.revert).pack(side="right", padx=6)

        # 오른쪽: 2주 목록 + 달력
        vf = ttk.LabelFrame(right, text=" 앞으로 2주 자동 출력 일정 ", padding=8)
        vf.grid(row=0, column=0, sticky="we")
        self.preview = tk.Text(vf, width=36, height=15, font=T.f(9), relief="flat", background=T.CARD,
                               highlightthickness=0)
        self.preview.grid()
        self.preview.tag_configure("off", foreground="#999999")
        self.preview.tag_configure("on", foreground="#1A1A1A")

        self.cal_frame = ttk.LabelFrame(right, text=" 달력 (날짜를 눌러 출력 켜기/끄기) ", padding=8)
        self.cal_frame.grid(row=1, column=0, sticky="we", pady=(8, 0))
        lg = ttk.Frame(right, style="Page.TFrame"); lg.grid(row=2, column=0, sticky="w", pady=(4, 0))
        for bg, txt in ((GREEN, "출력하는 날"), ("white", "쉬는 날"), (PAST_BG, "지난 날")):
            tk.Label(lg, text="  ", background=bg, relief="solid", borderwidth=1).pack(side="left", padx=(0, 3))
            ttk.Label(lg, text=txt, style="PageHint.TLabel").pack(side="left", padx=(0, 10))
        ttk.Label(lg, text="• 직접 바꾼 날   빨간 숫자: 공휴일", style="PageHint.TLabel").pack(side="left")
        self.refresh()

    # ------------------------------------------------------------ 값 읽기
    def _slot_widgets(self, parent, val, row, c0, dirty=True):
        on = tk.BooleanVar(value=val["on"])
        hh, mm = val["time"].split(":")
        cb = ttk.Checkbutton(parent, variable=on, command=self.changed if dirty else None)
        h = ttk.Combobox(parent, values=HOURS, width=3, state="readonly"); h.set(hh)
        m = ttk.Combobox(parent, values=MINUTES + ([mm] if mm not in MINUTES else []), width=3, state="readonly"); m.set(mm)
        cb.grid(row=row, column=c0); h.grid(row=row, column=c0 + 1)
        ttk.Label(parent, text=":").grid(row=row, column=c0 + 2); m.grid(row=row, column=c0 + 3)
        if dirty:
            for c in (h, m):
                c.bind("<<ComboboxSelected>>", lambda e: self.changed())
        return on, h, m

    @staticmethod
    def _slot_val(w):
        on, h, m = w
        return {"on": on.get(), "time": f"{h.get()}:{m.get()}"}

    @staticmethod
    def _slot_set(w, v):
        on, h, m = w
        on.set(v["on"]); h.set(v["time"][:2]); m.set(v["time"][3:])

    @staticmethod
    def _slot_txt(v):
        return v["time"] if v["on"] else "안 함"

    def _fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        for d in sorted(self._exc):
            e = self._exc[d]
            self.tree.insert("", "end", iid=d, values=(d, self._slot_txt(e["am"]), self._slot_txt(e["pm"])))

    def _set_exceptions(self, ex):
        self._exc = {e["date"]: e for e in ex}
        self._fill_tree()

    def _load_selected(self):
        sel = self.tree.selection()
        if sel and sel[0] in self._exc:
            self._fill_editor(self._exc[sel[0]])

    def _fill_editor(self, e):
        self.e_date.delete(0, "end"); self.e_date.insert(0, e["date"])
        for k in sch.SLOTS:
            self._slot_set(self.e_slots[k], e[k])

    def collect(self):
        s = dict(self.s)
        s["auto_enabled"] = self.auto.get()
        s["skip_public_holidays"] = self.holi.get()
        s["power_mode"] = self.power.get()
        s["weekdays"] = {str(i): {k: self._slot_val(sl[k]) for k in sch.SLOTS} for i, sl in enumerate(self.wd)}
        s["smart_split_weekdays"] = {str(i): v.get() for i, v in enumerate(self.split_days)}
        s["exceptions"] = [self._exc[d] for d in sorted(self._exc)]
        return s

    def changed(self):
        self.dirty = True
        self.refresh()

    # ------------------------------------------------------------ 화면 갱신
    def refresh(self):
        s = self.collect()
        self.dirty_lb.configure(text="● 저장하지 않은 변경이 있습니다" if self.dirty else "")
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        if not s["auto_enabled"]:
            self.preview.insert("end", "자동 출력이 꺼져 있습니다.\n", "off")
        for d, t, why in sch.upcoming(s, 14):
            line = f"{d:%m/%d}({sch.WEEKDAYS[d.weekday()]})  " + (sch.times_text(t) if t else f"쉼 · {why}")
            self.preview.insert("end", line + "\n", "on" if t and s["auto_enabled"] else "off")
        self.preview.configure(state="disabled")
        early = sch.earliest_time(s)
        if s["power_mode"] == "rtc" and early:
            h, m = map(int, early.split(":"))
            b = (dt.datetime(2000, 1, 1, h, m) - dt.timedelta(minutes=10)).strftime("%H:%M")
            self.rtc_hint.configure(text=f"BIOS 알람을 매일 {b}로 맞춰 주세요 (가장 이른 출력 {early}의 10분 전).")
        else:
            self.rtc_hint.configure(text="")
        self.draw_calendar(s)

    # 달력: 칸 크기·글자 (크게, 굵게, 둥근 모서리)
    CAL_W, CAL_H, CAL_GAP, CAL_R = 46, 36, 4, 9

    def draw_calendar(self, s):
        for w in self.cal_frame.winfo_children():
            w.destroy()
        today = dt.date.today()
        first, last = today - dt.timedelta(days=15), today + dt.timedelta(days=15)
        months = [(first.year, first.month)]
        if (last.year, last.month) != months[0]:
            months.append((last.year, last.month))
        exc_dates = {e["date"] for e in s["exceptions"]}
        cal = calendar.Calendar(firstweekday=6)   # 일요일 시작
        cw, ch, gap = self.CAL_W, self.CAL_H, self.CAL_GAP
        for mi, (y, mo) in enumerate(months):
            weeks = cal.monthdatescalendar(y, mo)
            head_h = 58
            cv = tk.Canvas(self.cal_frame, width=7 * (cw + gap) + 4, height=head_h + len(weeks) * (ch + gap) + 4,
                           background=T.CARD, highlightthickness=0)
            cv.grid(row=mi, column=0, sticky="w", pady=(0 if mi == 0 else 12, 0))
            cv.create_text(4, 12, text=f"{y}년 {mo}월", anchor="w", font=T.f(12, True), fill=T.INK)
            for c, wd in enumerate("일월화수목금토"):
                cv.create_text(2 + c * (cw + gap) + cw / 2, 42, text=wd, font=T.f(11, True),
                               fill="#C62828" if c == 0 else "#1565C0" if c == 6 else "#555555")
            for r, week in enumerate(weeks):
                for c, d in enumerate(week):
                    if d.month != mo:
                        continue
                    x, y0 = 2 + c * (cw + gap), head_h + r * (ch + gap)
                    self._day_cell(cv, d, x, y0, c, s, today, first, last, exc_dates)

    @staticmethod
    def _round_rect(cv, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
               x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return cv.create_polygon(pts, smooth=True, **kw)

    def _day_cell(self, cv, d, x, y, col, s, today, first, last, exc_dates):
        in_range = first <= d <= last
        holiday = bool(sch.holiday_name(d))
        planned, why = sch.plan_for(d, s)
        num_fg = "#C62828" if (holiday or d.weekday() == 6) else "#1565C0" if d.weekday() == 5 else "#1A1A1A"
        text = f"{d.day}{'•' if d.isoformat() in exc_dates else ''}"
        tag = f"d{d.isoformat()}"
        if not in_range:
            fill, outline, fg, width = "", "", "#D0D0D0", 0
        elif d < today:
            fill, outline, fg, width = PAST_BG, PAST_BG, PAST_TXT, 1
        else:
            fill = GREEN if (planned and s["auto_enabled"]) else ("#E6F4EA" if planned else "white")
            outline = "#8CCB9F" if planned else T.LINE_STRONG
            fg, width = (GREEN_TXT if planned else num_fg), 1
        if d == today:
            outline, width = T.INK, 2
        if in_range:
            self._round_rect(cv, x, y, x + self.CAL_W, y + self.CAL_H, self.CAL_R, fill=fill, outline=outline,
                             width=width, tags=tag)
        cv.create_text(x + self.CAL_W / 2, y + self.CAL_H / 2, text=text, font=T.f(11, True), fill=fg, tags=tag)
        if in_range and d >= today:
            cv.tag_bind(tag, "<Button-1>", lambda e, day=d: self.toggle_day(day))
            cv.tag_bind(tag, "<Enter>", lambda e: cv.configure(cursor="hand2"))
            tip = f"{d:%m/%d} " + (sch.times_text(planned) if planned else f"쉼 · {why}")
            cv.tag_bind(tag, "<Enter>", lambda e, t=tip: (cv.configure(cursor="hand2"), self.dirty_lb.configure(text=t)), add="+")
            cv.tag_bind(tag, "<Leave>", lambda e: (cv.configure(cursor=""), self.dirty_lb.configure(
                text="● 저장하지 않은 변경이 있습니다" if self.dirty else "")))

    def _default_slots(self, s):
        """쉬는 날을 출력으로 바꿀 때 쓸 시간: 평일에 가장 많이 쓰는 오전·오후 설정"""
        out = {}
        for k in sch.SLOTS:
            vals = [(w[k]["on"], w[k]["time"]) for i, w in s["weekdays"].items() if int(i) < 5]
            on, time = Counter(vals).most_common(1)[0][0] if vals else (k == "am", "09:00" if k == "am" else "14:00")
            out[k] = {"on": on, "time": time}
        if not out["am"]["on"] and not out["pm"]["on"]:
            out["am"]["on"] = True
        return out

    def toggle_day(self, d):
        s = self.collect()
        iso = d.isoformat()
        if iso in self._exc:                         # 이미 바꾼 날 → 원래 규칙으로
            del self._exc[iso]
            base = {"date": iso, **{k: dict(self._default_slots(s)[k]) for k in sch.SLOTS}}
        else:
            planned, _ = sch.plan_for(d, s)
            if planned:                              # 출력하는 날 → 쉬는 날
                base = {"date": iso, "am": {"on": False, "time": "09:00"}, "pm": {"on": False, "time": "14:00"}}
                w = s["weekdays"][str(d.weekday())]
                base["am"]["time"], base["pm"]["time"] = w["am"]["time"], w["pm"]["time"]
            else:                                    # 쉬는 날 → 출력 (평일 시간)
                base = {"date": iso, **self._default_slots(s)}
            self._exc[iso] = base
        self._fill_tree()
        self._fill_editor(base)
        if iso in self._exc:
            self.tree.selection_set(iso)
        self.changed()

    # ------------------------------------------------------------ 버튼
    def add_exc(self):
        d = self.e_date.get().strip()
        try:
            dt.date.fromisoformat(d)
        except ValueError:
            messagebox.showwarning("날짜 형식", "날짜는 2026-10-15 처럼 입력해 주세요.")
            return
        self._exc[d] = {"date": d, **{k: self._slot_val(self.e_slots[k]) for k in sch.SLOTS}}
        self._fill_tree()
        self.changed()

    def del_exc(self):
        for iid in self.tree.selection():
            self._exc.pop(iid, None)
        self._fill_tree()
        self.changed()

    def revert(self):
        self.s = sch.load_settings()
        self.auto.set(self.s["auto_enabled"]); self.holi.set(self.s["skip_public_holidays"])
        self.power.set(self.s["power_mode"])
        for i, sl in enumerate(self.wd):
            for k in sch.SLOTS:
                self._slot_set(sl[k], self.s["weekdays"][str(i)][k])
        for i, v in enumerate(self.split_days):
            v.set(bool(self.s.get("smart_split_weekdays", {}).get(str(i))))
        self._set_exceptions(self.s["exceptions"])
        self.dirty = False
        self.refresh()

    def save(self):
        s = self.collect()
        if s["auto_enabled"] and not sch.earliest_time(s):
            messagebox.showwarning("확인", "출력하는 요일이나 날짜가 하나도 없습니다.")
            return
        old = (dt.date.today() - dt.timedelta(days=30)).isoformat()
        s["exceptions"] = [e for e in s["exceptions"] if e["date"] >= old]
        latest = sch.load_settings()           # 다른 탭에서 바꾼 값(보관 기간·라벨 보정 등)은 그대로 두고
        for k in ("auto_enabled", "skip_public_holidays", "power_mode", "weekdays", "exceptions", "smart_split_weekdays"):
            latest[k] = s[k]                     # 이 탭의 항목만 바꿔서 저장
        s = latest
        sch.save_settings(s)
        ok, msg = sch.register_tasks(s)
        self.s = s
        self.dirty = False
        self.refresh()
        if ok:
            messagebox.showinfo("저장 완료", msg)
        else:
            messagebox.showerror("예약 등록 실패", "설정은 저장했지만 작업 스케줄러 등록에 실패했습니다.\n\n" + msg)
        if self.on_saved:
            self.on_saved()
