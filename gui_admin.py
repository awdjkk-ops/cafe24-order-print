# -*- coding: utf-8 -*-
"""통합 창 - '관리' 탭 (인증, 프린터, 저장 공간, 운영 시작 도구, 폴더·기록)"""
import json
import os
import sys
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox

import order_print as op
import print_schedule as sch
from gui_schedule import hint
import theme as T

DEFAULT_PRINTER = "(윈도우 기본 프린터 사용)"
SAME_PRINTER = "(주문서와 같은 프린터)"
DEFAULT_TRAY = "(프린터 기본 트레이)"


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024


class AdminTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=12, style="Page.TFrame")
        self.app = app
        left = ttk.Frame(self, style="Page.TFrame"); left.grid(row=0, column=0, sticky="nw")
        right = ttk.Frame(self, style="Page.TFrame"); right.grid(row=0, column=1, sticky="nw", padx=(16, 0))

        # 1. 카페24 연결
        f = ttk.LabelFrame(left, text=" 카페24 연결 ", padding=10); f.grid(row=0, column=0, sticky="we")
        self.auth_lb = ttk.Label(f, text=""); self.auth_lb.grid(row=0, column=0, columnspan=3, sticky="w")
        hint(f, "인증이 만료되었거나, 앱 권한을 바꿨을 때만 다시 인증하면 됩니다.\n"
                "① [브라우저 열기]를 누르고 쇼핑몰 '대표운영자' 계정으로 로그인해 앱을 승인합니다.\n"
                "② 쇼핑몰 화면으로 이동하면 주소창 전체를 복사해 아래 칸에 붙여넣고 [인증 완료]를 누릅니다. (1분 이내)",
             row=1, column=0, columnspan=3, sticky="w", pady=(4, 6))
        ttk.Button(f, text="① 브라우저 열기", command=self.open_auth).grid(row=2, column=0, sticky="w")
        self.paste = ttk.Entry(f, width=38); self.paste.grid(row=2, column=1, padx=6)
        ttk.Button(f, text="② 인증 완료", command=self.finish_auth).grid(row=2, column=2)

        # 1-2. 구글 시트 (블랙리스트·추가배송)
        f = ttk.LabelFrame(left, text=" 구글 시트 연결 (블랙리스트·추가배송) ", padding=10)
        f.grid(row=2, column=0, sticky="we", pady=(10, 0))
        hint(f, "웹 도구에서 쓰던 Apps Script 주소(https://script.google.com/macros/s/.../exec)를 넣으세요. "
                "웹 도구와 같은 구글 시트를 함께 씁니다. 이 주소는 이 PC의 config.json에만 저장됩니다.",
             row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        self.sheet_url = ttk.Entry(f, width=46, show="•"); self.sheet_url.grid(row=1, column=0, sticky="w")
        ttk.Button(f, text="저장", command=self.save_sheet).grid(row=1, column=1, padx=6)
        ttk.Button(f, text="연결 확인", command=self.test_sheet).grid(row=1, column=2)
        self.sheet_lb = ttk.Label(f, text=""); self.sheet_lb.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

        # 2. 프린터
        f = ttk.LabelFrame(left, text=" 프린터 ", padding=10); f.grid(row=3, column=0, sticky="we", pady=(10, 0))
        hint(f, "주문서를 뽑을 프린터를 고르세요. 택배 송장 프린터가 같은 PC에 있다면 꼭 주문서용 프린터를 직접 "
                "지정해 두세요. '기본 프린터 사용'을 고른 경우, 윈도우 설정의 'Windows에서 기본 프린터 관리'는 꺼두는 것이 안전합니다.",
             row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        self.printer = ttk.Combobox(f, width=36, state="readonly", values=[DEFAULT_PRINTER])
        self.printer.grid(row=1, column=0, sticky="w")
        ttk.Button(f, text="저장", command=self.save_printer).grid(row=1, column=1, padx=6)
        ttk.Button(f, text="테스트 인쇄", command=self.test_print).grid(row=1, column=2)
        self.sumatra_lb = ttk.Label(f, text=""); self.sumatra_lb.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        hint(f, "테스트 인쇄는 안내문 1장만 나오며, 주문 기록에는 영향이 없습니다.",
             row=3, column=0, columnspan=3, sticky="w")

        # 2-2. 라벨 인쇄 위치
        f = ttk.LabelFrame(left, text=" 라벨 인쇄 위치 (폼텍 LS-3145) ", padding=10)
        f.grid(row=4, column=0, sticky="we", pady=(10, 0))
        hint(f, "① [맞춤 확인용 인쇄]로 일반 A4에 칸 테두리를 뽑아 라벨지와 겹쳐 불빛에 비춰봅니다.\n"
                "② 테두리가 오른쪽으로 밀렸으면 가로를 −, 아래로 밀렸으면 세로를 − 방향으로 옮깁니다 (0.1mm 단위).\n"
                "③ 위쪽은 맞는데 아래로 갈수록 밀리면 배율을 조정합니다. 저장 후 다시 확인하세요.",
             row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
        self.cal = {}
        for i, (key, label, lo, hi) in enumerate((("offset_x", "가로 위치(mm)", -15, 15), ("offset_y", "세로 위치(mm)", -15, 15),
                                                  ("scale_x", "가로 배율(%)", -5, 5), ("scale_y", "세로 배율(%)", -5, 5))):
            r, c = divmod(i, 2)
            ttk.Label(f, text=label).grid(row=1 + r, column=c * 2, sticky="e", padx=(0 if c == 0 else 12, 4), pady=2)
            sp = ttk.Spinbox(f, from_=lo, to=hi, increment=0.1, width=7, format="%.1f")
            sp.grid(row=1 + r, column=c * 2 + 1, sticky="w")
            self.cal[key] = sp
        self.ldialog = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="라벨 인쇄할 때 인쇄 창 열기 (프린터·뒷면 트레이를 직접 고르기)", variable=self.ldialog,
                        command=self._dialog_changed).grid(row=3, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self.ldialog_hint = ttk.Label(f, text="", style="Hint.TLabel", wraplength=560, justify="left")
        self.ldialog_hint.grid(row=4, column=0, columnspan=4, sticky="w")
        pf = ttk.Frame(f); pf.grid(row=5, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self.lpf = pf
        ttk.Label(pf, text="라벨 프린터").grid(row=0, column=0, sticky="e", padx=(0, 4))
        self.lprinter = ttk.Combobox(pf, width=30, state="readonly", values=[SAME_PRINTER])
        self.lprinter.grid(row=0, column=1, sticky="w")
        self.lprinter.bind("<<ComboboxSelected>>", lambda e: self.load_trays())
        ttk.Label(pf, text="급지 트레이").grid(row=1, column=0, sticky="e", padx=(0, 4), pady=(4, 0))
        self.ltray = ttk.Combobox(pf, width=30, state="readonly", values=[DEFAULT_TRAY])
        self.ltray.grid(row=1, column=1, sticky="w", pady=(4, 0))
        ttk.Button(pf, text="트레이 목록", command=self.load_trays).grid(row=1, column=2, padx=4, pady=(4, 0))
        hint(pf, "라벨지를 뒷면(수동) 트레이에 넣는다면 여기서 그 트레이를 고르세요. 이름은 프린터마다 달라요 "
                 "(예: 뒷면 트레이, 수동 급지, Manual Feed, MP 트레이). 주문서는 기본 트레이에서 그대로 나옵니다.",
             row=2, column=0, columnspan=3, sticky="w", pady=(4, 0), wrap=560)
        bb = ttk.Frame(f); bb.grid(row=6, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Button(bb, text="저장", command=self.save_cal).pack(side="left")
        ttk.Button(bb, text="맞춤 확인용 인쇄", command=self.print_cal).pack(side="left", padx=6)
        ttk.Button(bb, text="0으로 되돌리기", command=self.reset_cal).pack(side="left")

        # 3. 저장 공간
        f = ttk.LabelFrame(right, text=" 저장 공간 ", padding=10); f.grid(row=0, column=0, sticky="we")
        hint(f, "출력할 때마다 보관 기간이 지난 파일을 자동으로 지웁니다. 지워도 '이미 출력한 주문' 기록은 남아 있어서 "
                "예전 주문이 다시 출력되지 않고, 개별 주문 다시 뽑기는 카페24에서 새로 불러와 언제든 가능합니다.",
             row=0, column=0, columnspan=3, sticky="w", pady=(0, 6), wrap=430)
        self.usage = ttk.Frame(f); self.usage.grid(row=1, column=0, columnspan=3, sticky="w")
        ttk.Label(f, text="주문서 PDF 보관 기간").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.keep = ttk.Combobox(f, values=["1일", "3일", "5일", "7일"], width=6, state="readonly")
        self.keep.grid(row=2, column=1, sticky="w", pady=(8, 0), padx=6)
        self.keep.bind("<<ComboboxSelected>>", lambda e: self.save_keep())
        ttk.Button(f, text="지금 정리하기", command=self.clean_now).grid(row=2, column=2, rowspan=2, pady=(8, 0))
        ttk.Label(f, text="엑셀·택배·라벨 파일 보관 기간").grid(row=3, column=0, sticky="w", pady=(4, 0))
        self.keep_csv = ttk.Combobox(f, values=["1일", "3일", "5일", "7일"], width=6, state="readonly")
        self.keep_csv.grid(row=3, column=1, sticky="w", pady=(4, 0), padx=6)
        self.keep_csv.bind("<<ComboboxSelected>>", lambda e: self.save_keep())
        hint(f, "상품 사진은 60일, 화면용 출력 기록(고객 이름 포함)은 30일, 실행 기록은 6개월 뒤 자동 삭제됩니다. "
                "지워진 날짜의 엑셀도 출력 탭에서 날짜를 골라 다시 만들 수 있습니다(최근 30일).",
             row=4, column=0, columnspan=3, sticky="w", pady=(4, 0), wrap=430)

        # 4. 문제 확인 도구
        f = ttk.LabelFrame(right, text=" 문제 확인 도구 ", padding=10); f.grid(row=1, column=0, sticky="we", pady=(10, 0))
        hint(f, "처음 시작할 때나 카페24에서 직접 뽑은 뒤 '어디까지 뽑았나'를 맞추는 기능은 출력 탭 → 주문 현황의 "
                "[선택한 주문까지 뽑은 것으로]로 옮겼습니다.", row=0, column=0, sticky="w", pady=(0, 8), wrap=430)
        ttk.Button(f, text="카페24 엑셀과 비교 검사", command=self.compare).grid(row=3, column=0, sticky="w", pady=(8, 0))
        hint(f, "카페24에서 '엑셀 바로 다운로드'로 받은 CSV를 고르면, 같은 주문으로 프로그램이 만든 엑셀과 칸별로 "
                "비교합니다. 고객 정보는 가린 채 형식 차이만 보여줍니다.", row=4, column=0, sticky="w", pady=(2, 0), wrap=430)
        ttk.Button(f, text="데이터 확인 파일 만들기", command=self.dump).grid(row=1, column=0, sticky="w")
        hint(f, "주문 몇 건의 원본 데이터를 고객정보를 가린 채 파일로 저장합니다. 문제 확인용입니다.",
             row=2, column=0, sticky="w", pady=(2, 0), wrap=430)

        # 6. 프로그램 업데이트
        f = ttk.LabelFrame(right, text=" 프로그램 업데이트 ", padding=10); f.grid(row=3, column=0, sticky="we", pady=(10, 0))
        import updater
        self.ver_lb = ttk.Label(f, text="", font=T.f(11, True)); self.ver_lb.grid(row=0, column=0, columnspan=2, sticky="w")
        hint(f, f"깃허브 저장소({updater.DEFAULT_REPO})에서 새 버전을 받습니다. 프로그램을 켤 때마다 자동으로 확인해서 "
                "머리글에 알려줍니다. 설정·인증·출력 기록은 업데이트해도 그대로입니다.", row=1, column=0, columnspan=2,
             sticky="w", pady=(2, 6), wrap=430)
        ttk.Button(f, text="업데이트 확인", command=lambda: self.app.check_update(manual=True)).grid(row=2, column=0, sticky="w")
        ttk.Button(f, text="이전 버전으로 되돌리기", command=self.rollback).grid(row=2, column=1, sticky="w", padx=6)
        self.bak_lb = ttk.Label(f, text="", style="Hint.TLabel"); self.bak_lb.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # 5. 폴더·기록
        f = ttk.LabelFrame(right, text=" 폴더 · 기록 ", padding=10); f.grid(row=4, column=0, sticky="we", pady=(10, 0))
        ttk.Button(f, text="주문서 PDF 폴더 열기", command=lambda: op.open_file(op.PDF_DIR)).grid(row=0, column=0, sticky="w")
        ttk.Button(f, text="출력주문 엑셀 폴더 열기", command=lambda: op.open_file(op.CSV_DIR)).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Button(f, text="실행 기록 보기", command=self.open_log).grid(row=0, column=2, sticky="w")
        hint(f, "오류가 났을 때 '실행 기록 보기'의 마지막 부분을 Claude에게 보여주면 원인을 찾을 수 있습니다.",
             row=1, column=0, columnspan=3, sticky="w", pady=(4, 0), wrap=430)
        self.refresh()

    # ------------------------------------------------------------
    def refresh(self):
        st, txt = op.token_status()
        self.auth_lb.configure(text=f"상태: {txt}", foreground={"ok": "#1B7F3B", "warn": "#B25B00", "bad": "#C62828"}[st])
        cfg = self.app.cfg or {}
        self.sumatra_lb.configure(
            text="인쇄 프로그램(SumatraPDF): 설치됨" if op.find_sumatra(cfg) else
            "인쇄 프로그램(SumatraPDF): 없음 → sumatrapdfreader.org 에서 설치해 주세요",
            foreground="#1B7F3B" if op.find_sumatra(cfg) else "#C62828")
        self.printer.set(cfg.get("printer_name") or DEFAULT_PRINTER)
        self.sheet_url.delete(0, "end"); self.sheet_url.insert(0, cfg.get("sheet_api_url", ""))
        cal = op.label_calibration()
        for k, w in self.cal.items():
            w.set(f"{float(cal.get(k, 0)):.1f}")
        self.ldialog.set(cfg.get("label_print_dialog", True))
        self._dialog_changed()
        self.lprinter.set(cfg.get("label_printer") or SAME_PRINTER)
        self.ltray.set(cfg.get("label_tray") or DEFAULT_TRAY)
        if not cfg.get("sheet_api_url"):
            self.sheet_lb.configure(text="연결 안 됨 (블랙리스트·추가배송을 쓰려면 주소를 넣어주세요)", foreground="#B25B00")
        elif not self.sheet_lb.cget("text").startswith("연결됨"):
            self.sheet_lb.configure(text="주소 저장됨 · [연결 확인]을 눌러 확인하세요", foreground="#555555")
        st_ = sch.load_settings()
        self.keep.set(f"{st_.get('pdf_keep_days', 3)}일")
        if hasattr(self, "ver_lb"):
            self.refresh_update()
        self.keep_csv.set(f"{st_.get('csv_keep_days', 3)}일")
        for w in self.usage.winfo_children():
            w.destroy()
        for r, (k, (n, size)) in enumerate(op.storage_usage().items()):
            ttk.Label(self.usage, text=k, width=16).grid(row=r, column=0, sticky="w")
            ttk.Label(self.usage, text=f"{n}개" if k != "출력 기록" else f"{n}묶음", width=8).grid(row=r, column=1, sticky="e")
            ttk.Label(self.usage, text=human(size), width=10).grid(row=r, column=2, sticky="e")
        self.app.bg(lambda: op.list_printers(), self._set_printers, busy=False)

    def _dialog_changed(self):
        on = self.ldialog.get()
        self.ldialog_hint.configure(text=(
            "켜짐: 라벨 인쇄(맞춤 확인용 포함) 때 인쇄 창이 뜹니다. 프린터를 고르고 [기본 설정]에서 급지를 뒷면 트레이로 "
            "바꾼 뒤 인쇄하세요. 크기 옵션이 보이면 '실제 크기'를 고르세요. 아래의 라벨 프린터·트레이 칸은 쓰지 않습니다."
            if on else "꺼짐: 아래에서 고른 라벨 프린터·트레이로 창 없이 바로 인쇄합니다."))
        for w in self.lpf.winfo_children():
            try:
                w.state(["disabled"] if on else ["!disabled"])
            except (AttributeError, tk.TclError):
                pass

    def load_trays(self):
        lp = self.lprinter.get()
        printer = "" if lp == SAME_PRINTER else lp.replace("  (현재 기본)", "")
        if not printer:
            printer = (self.app.cfg or {}).get("printer_name", "")

        def done(trays):
            self.tray_kinds = {nm: kind for nm, kind in trays}
            self.ltray.configure(values=[DEFAULT_TRAY] + [nm for nm, _ in trays])
            if not trays:
                messagebox.showinfo("트레이 목록", "이 프린터의 트레이 목록을 가져오지 못했습니다.\n"
                                              "프린터가 켜져 있는지 확인하거나, 프린터 이름을 직접 골라 다시 눌러 주세요.")
        self.app.bg(lambda: op.list_trays(printer), done, busy=False)

    def save_cal(self):
        try:
            vals = {k: round(float(w.get()), 1) for k, w in self.cal.items()}
        except ValueError:
            messagebox.showwarning("입력 확인", "숫자로 입력해 주세요 (예: 0.3, -1.2)")
            return
        s = sch.load_settings(); s["label_cal"] = vals; sch.save_settings(s)
        cfg = op.read_json(op.CONFIG_FILE, {})
        lp, lt = self.lprinter.get(), self.ltray.get()
        cfg["label_printer"] = "" if lp in (SAME_PRINTER, "") else lp.replace("  (현재 기본)", "")
        cfg["label_print_dialog"] = self.ldialog.get()
        cfg["label_tray"] = "" if lt in (DEFAULT_TRAY, "") else lt
        if cfg["label_tray"] and lt in getattr(self, "tray_kinds", {}):
            cfg["label_tray_kind"] = self.tray_kinds[lt]
        elif not cfg["label_tray"]:
            cfg["label_tray_kind"] = ""
        op.write_json(op.CONFIG_FILE, cfg)
        self.app.cfg = op.load_config()
        messagebox.showinfo("저장 완료", "라벨 인쇄 설정(위치·프린터·트레이)을 저장했습니다.\n[맞춤 확인용 인쇄]로 확인해 보세요.")

    def reset_cal(self):
        for w in self.cal.values():
            w.set("0.0")

    def print_cal(self):
        if not messagebox.askyesno("맞춤 확인용 인쇄", "일반 A4 용지에 라벨 칸 테두리 1장을 인쇄할까요?\n(저장한 보정값이 적용됩니다)"):
            return
        self.app.bg(lambda: op.print_calibration(self.app.cfg),
                    lambda _: messagebox.showinfo("맞춤 확인용 인쇄", "프린터로 보냈습니다. 라벨지와 겹쳐서 확인해 보세요."),
                    "인쇄 중...")

    def save_sheet(self):
        cfg = op.read_json(op.CONFIG_FILE, {})
        cfg["sheet_api_url"] = self.sheet_url.get().strip()
        op.write_json(op.CONFIG_FILE, cfg)
        self.app.cfg = op.load_config()
        messagebox.showinfo("저장 완료", "구글 시트 연결 주소를 저장했습니다. [연결 확인]으로 확인해 보세요.")
        self.refresh()

    def test_sheet(self):
        import courier as C
        url = (self.app.cfg or {}).get("sheet_api_url", "")

        def work():
            bl = C.sheet_call(url, "list").get("items", [])
            ex = C.sheet_call(url, "listExtra").get("items", [])
            return len(bl), len(ex)
        self.app.bg(work, lambda r: (self.sheet_lb.configure(text=f"연결됨 · 블랙리스트·경계대상 {r[0]}명 · 추가배송 대기 {r[1]}건",
                                                              foreground="#1B7F3B")), "구글 시트 확인 중...")

    def _set_printers(self, res):
        names, default = res
        vals = [DEFAULT_PRINTER] + [n + ("  (현재 기본)" if n == default else "") for n in names]
        self.printer.configure(values=vals)
        self.lprinter.configure(values=[SAME_PRINTER] + names)

    def open_auth(self):
        if not self.app.cfg:
            return
        webbrowser.open(op.auth_url(self.app.cfg))

    def finish_auth(self):
        text = self.paste.get().strip()
        if "code=" not in text and "error=" not in text:
            messagebox.showwarning("주소 확인", "승인 후 이동한 쇼핑몰 주소(…?code=… 가 들어 있는 주소) 전체를 붙여넣어 주세요.")
            return
        def done(_):
            self.paste.delete(0, "end")
            messagebox.showinfo("인증 완료", "카페24 인증이 완료되었습니다.")
            self.app.refresh_all()
        self.app.bg(lambda: op.finish_auth(self.app.cfg, text), done, "인증하는 중...")

    def save_printer(self):
        v = self.printer.get().replace("  (현재 기본)", "")
        cfg = op.read_json(op.CONFIG_FILE, {})
        cfg["printer_name"] = "" if v == DEFAULT_PRINTER else v
        op.write_json(op.CONFIG_FILE, cfg)
        self.app.cfg = op.load_config()
        messagebox.showinfo("저장 완료", f"주문서 프린터: {v}")
        self.app.refresh_status()

    def test_print(self):
        if not messagebox.askyesno("테스트 인쇄", "프린터로 안내문 1장을 인쇄할까요?"):
            return
        self.app.bg(lambda: op.print_test_page(self.app.cfg),
                    lambda _: messagebox.showinfo("테스트 인쇄", "프린터로 보냈습니다. 종이가 나왔는지 확인해 주세요."),
                    "테스트 인쇄 중...")

    def save_keep(self):
        s = sch.load_settings()
        s["pdf_keep_days"] = int(self.keep.get().rstrip("일"))
        s["csv_keep_days"] = int(self.keep_csv.get().rstrip("일"))
        sch.save_settings(s)

    def clean_now(self):
        r = op.cleanup()
        messagebox.showinfo("정리 완료", f"PDF {r['pdf']}개, 엑셀 {r.get('csv', 0)}개, 사진 {r['images']}개, 로그 {r['logs']}개, "
                                        f"출력 기록 {r['history']}묶음을 정리했습니다.")
        self.refresh()

    def dump(self):
        self.app.bg(lambda: op.dump(self.app.cfg, op.get_access_token(self.app.cfg)),
                    lambda _: (messagebox.showinfo("완료", "프로그램 폴더에 '데이터확인_날짜.json' 파일을 만들었습니다."),
                               op.open_file(op.BASE_DIR)), "데이터 확인 파일 만드는 중...")

    def compare(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(title="카페24에서 받은 주문 CSV 고르기", filetypes=[("CSV 파일", "*.csv")])
        if not path:
            return

        def done(res):
            report, out = res
            win = tk.Toplevel(self); win.title("비교 검사 결과")
            txt = tk.Text(win, width=100, height=32, font=T.f(9)); txt.pack(fill="both", expand=True)
            txt.insert("1.0", report + f"\n\n(이 결과는 {out.name} 파일로도 저장했습니다. Claude에게 보여주세요.)")
            txt.configure(state="disabled")
        self.app.bg(lambda prog: op.compare_with_cafe24(self.app.cfg, op.get_access_token(self.app.cfg), path, prog),
                    done, "카페24에서 주문 불러와 비교하는 중...", progress=True)

    def refresh_update(self):
        import updater
        up = getattr(self.app, "pending_update", None)
        cur = updater.local_info().get("version", "?")
        state = getattr(self.app, "update_state", "checking")
        tail = (f"  →  새 버전 v{up['version']} 있음" if up else "  (최신)" if state == "ok"
                else "  (새 버전 확인 못 함 · 인터넷 연결 확인)" if state == "fail" else "  (확인 중...)")
        self.ver_lb.configure(text=f"지금 버전 v{cur}" + tail,
                              foreground=T.BLUE if up else T.ORANGE if state == "fail" else T.INK)
        bs = updater.backups()
        self.bak_lb.configure(text=f"되돌릴 수 있는 이전 버전: v{bs[0].name.split('_')[0]}" if bs else "되돌릴 이전 버전 없음")

    def rollback(self):
        import updater
        bs = updater.backups()
        if not bs:
            messagebox.showinfo("이전 버전", "되돌릴 이전 버전이 없습니다.")
            return
        prev = bs[0].name.split("_")[0]
        if not messagebox.askyesno("이전 버전으로 되돌리기", f"v{updater.local_info().get('version')} → v{prev}로 되돌릴까요?\n"
                                                         "설정·인증·출력 기록은 그대로입니다. 끝나면 창을 다시 엽니다."):
            return
        try:
            ver = updater.rollback()
        except Exception as e:
            messagebox.showerror("되돌리기 실패", str(e)); return
        op.log.info(f"[업데이트] v{ver}로 되돌림")
        messagebox.showinfo("되돌리기 완료", f"v{ver}로 되돌렸습니다. 창을 다시 엽니다.")
        updater.restart_manager()
        self.app.destroy()

    def open_log(self):
        logs = sorted(op.LOG_DIR.glob("*.log"))
        if logs:
            op.open_file(logs[-1])
