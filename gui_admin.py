# -*- coding: utf-8 -*-
"""통합 창 - '관리' 탭 (인증, 프린터, 저장 공간, 운영 시작 도구, 폴더·기록)"""
import json
import os
import sys
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox

import courier as C
import data_backup as DB
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

        # 2-3. 중요 배송메세지 제외 목록 (택배 탭 '중요 배송메세지 확인'에서 뺄 문구)
        f = ttk.LabelFrame(left, text=" 중요 배송메세지 제외 목록 ", padding=10)
        f.grid(row=5, column=0, sticky="we", pady=(10, 0))
        hint(f, "여기 있는 문구와 완전히 같은 배송메세지는 택배 탭 '중요 배송메세지 확인'에 나오지 않습니다 (앞뒤 공백만 무시, "
                "띄어쓰기·마침표가 다르면 다른 문구). 택배 탭에서 메세지를 우클릭 → [제외 목록에 추가]로도 넣을 수 있습니다. "
                "이 PC의 data 폴더에 저장되며, 업데이트해도 그대로입니다.", row=0, column=0, columnspan=3, sticky="w",
             pady=(0, 6), wrap=560)
        self.ex_entry = ttk.Entry(f, width=44); self.ex_entry.grid(row=1, column=0, sticky="we")
        self.ex_entry.bind("<Return>", lambda e: self.ex_add())
        ttk.Button(f, text="추가", style="Accent.TButton", command=self.ex_add).grid(row=1, column=1, padx=6)
        ttk.Button(f, text="여러 개 붙여넣기", command=lambda: ExcludeImport(self)).grid(row=1, column=2, sticky="w")
        sf = ttk.Frame(f); sf.grid(row=2, column=0, columnspan=3, sticky="we", pady=(8, 0))
        ttk.Label(sf, text="검색").pack(side="left")
        self.ex_q = tk.StringVar()
        self.ex_q.trace_add("write", lambda *a: self.ex_show())
        ttk.Entry(sf, textvariable=self.ex_q, width=20).pack(side="left", padx=(4, 8))
        self.ex_cnt = ttk.Label(sf, text="", style="Hint.TLabel"); self.ex_cnt.pack(side="left")
        tf = ttk.Frame(f); tf.grid(row=3, column=0, columnspan=3, sticky="we", pady=(6, 0))
        self.ex_tv = ttk.Treeview(tf, columns=("msg", "day", "pc"), show="headings", height=7, selectmode="extended")
        for c, t_, w in (("msg", "메세지", 330), ("day", "추가한 날", 90), ("pc", "추가한 PC", 110)):
            self.ex_tv.heading(c, text=t_); self.ex_tv.column(c, width=w, stretch=(c == "msg"))
        self.ex_tv.tag_configure("new", background=T.HILITE)
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.ex_tv.yview)
        self.ex_tv.configure(yscrollcommand=sb.set)
        self.ex_tv.pack(side="left", fill="both", expand=True); sb.pack(side="left", fill="y")
        self.ex_tv.bind("<Delete>", lambda e: self.ex_delete())
        bf = ttk.Frame(f); bf.grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Button(bf, text="선택한 문구 삭제", command=self.ex_delete).pack(side="left")
        ttk.Button(bf, text="새로고침", command=self.ex_show).pack(side="left", padx=6)
        ttk.Button(bf, text="제외 목록 내보내기", command=self.ex_export).pack(side="left")
        ttk.Button(bf, text="제외 목록 가져오기", command=self.ex_import).pack(side="left", padx=6)
        hint(f, "다른 PC로 옮기기: [제외 목록 내보내기]로 엑셀을 저장해 옮긴 뒤, 그 PC에서 [제외 목록 가져오기] → '합치기'. "
                "초록색 줄은 오늘 추가한 문구입니다.", row=5, column=0, columnspan=3, sticky="w", pady=(4, 0), wrap=560)
        self.ex_map = {}
        self.ex_show()

        # 2-4. 데이터 백업
        f = ttk.LabelFrame(left, text=" 데이터 백업 ", padding=10)
        f.grid(row=6, column=0, sticky="we", pady=(10, 0))
        hint(f, "수제 코드·배송메세지 제외 목록·출력 기록·세금계산서 내역·확인 기록 등 data 폴더 전체와 설정(config.json·settings.json, "
                "카페24 접속 정보 포함)을 압축파일 하나로 저장합니다. 상품 사진은 크고 다시 받아지므로 빼고 저장합니다.",
             row=0, column=0, columnspan=2, sticky="w", pady=(0, 6), wrap=560)
        bkf = ttk.Frame(f); bkf.grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Button(bkf, text="전체 데이터 백업 받기", style="Accent.TButton", command=self.backup_now).pack(side="left")
        ttk.Button(bkf, text="백업에서 되돌리기", command=self.backup_restore).pack(side="left", padx=6)
        self.bk_lb = ttk.Label(f, text="", style="Hint.TLabel"); self.bk_lb.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        hint(f, "되돌리기: 되돌리기 직전 상태를 data_backups 폴더에 자동으로 한 번 더 저장한 뒤 바꿉니다. 이미 뽑은 주문·택배 파일에 "
                "넣은 주문 기록은 합쳐서 다시 출력되거나 송장이 겹치지 않게 하고, 카페24 인증은 지금 PC 것을 그대로 씁니다. "
                "되돌린 뒤에는 프로그램을 다시 켭니다.", row=3, column=0, columnspan=2, sticky="w", pady=(4, 0), wrap=560)
        self.bk_show()

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
        # --- 수제 제작 상품 코드 (택배 탭 '수제 제작 상품 확인'에 보여 줄 상품)
        f = ttk.LabelFrame(right, text=" 수제 제작 상품 코드 ", padding=10); f.grid(row=2, column=0, sticky="we", pady=(10, 0))
        hint(f, "상품명 맨 앞 코드(예: PDT2431) 또는 코드가 없는 상품은 상품명 전체를 등록하면, 그 상품이 든 주문을 택배 탭 "
                "'수제 제작 상품 확인'에 보여 줍니다. 코드는 정확히 같은 코드만(PDT07과 PDT007은 다름), 상품명은 완전히 같은 "
                "상품명만 잡습니다 (앞뒤 공백·겹친 띄어쓰기는 무시).", row=0, column=0, columnspan=4, sticky="w",
             pady=(0, 6), wrap=430)
        ttk.Label(f, text="코드·상품명").grid(row=1, column=0, sticky="e", padx=(0, 4))
        self.hm_code = ttk.Entry(f, width=16); self.hm_code.grid(row=1, column=1, sticky="w")
        ttk.Label(f, text="메모").grid(row=1, column=2, sticky="e", padx=(8, 4))
        self.hm_memo = ttk.Entry(f, width=18); self.hm_memo.grid(row=1, column=3, sticky="w")
        self.hm_code.bind("<Return>", lambda e: self.hm_add())
        self.hm_memo.bind("<Return>", lambda e: self.hm_add())
        bf = ttk.Frame(f); bf.grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Button(bf, text="추가", style="Accent.TButton", command=self.hm_add).pack(side="left")
        ttk.Button(bf, text="선택한 코드 삭제", command=self.hm_delete).pack(side="left", padx=6)
        self.hm_tv = ttk.Treeview(f, columns=("code", "memo", "day"), show="headings", height=5, selectmode="extended")
        for c, t_, w in (("code", "코드 / 상품명", 190), ("memo", "메모", 130), ("day", "등록한 날", 80)):
            self.hm_tv.heading(c, text=t_); self.hm_tv.column(c, width=w)
        self.hm_tv.grid(row=3, column=0, columnspan=4, sticky="we", pady=(6, 0))
        self.hm_tv.bind("<Delete>", lambda e: self.hm_delete())
        self.hm_cnt = ttk.Label(f, text="", style="Hint.TLabel"); self.hm_cnt.grid(row=4, column=0, columnspan=4, sticky="w", pady=(4, 0))
        bf2 = ttk.Frame(f); bf2.grid(row=5, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Button(bf2, text="여러 개 붙여넣기", command=lambda: HandmadeImport(self)).pack(side="left")
        ttk.Button(bf2, text="파일에서 가져오기", command=self.hm_from_file).pack(side="left", padx=6)
        ttk.Button(bf2, text="양식 받기", command=self.hm_template).pack(side="left")
        ttk.Button(bf2, text="엑셀로 내보내기", command=self.hm_export).pack(side="left", padx=6)
        hint(f, "한꺼번에 넣기: 메모장·엑셀에서 복사해 [여러 개 붙여넣기]에 붙이거나, 엑셀(A열 코드 또는 상품명·B열 메모)·CSV·메모장 파일을 "
                "[파일에서 가져오기]로 고릅니다. 양식은 [양식 받기]로 받을 수 있습니다.", row=6, column=0, columnspan=4, sticky="w",
             pady=(4, 0), wrap=430)
        self.hm_show()

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
    # ---------------------------------------------------------------- 수제 제작 상품 코드
    def hm_show(self):
        self.hm_tv.delete(*self.hm_tv.get_children())
        items = sorted(op.load_handmade(), key=lambda e: e.get("code", ""))
        for e in items:
            self.hm_tv.insert("", "end", iid=e["code"], values=(e["code"], e.get("memo", ""), e.get("added", "")))
        n_code = sum(1 for e in items if op.is_code(e.get("code")))
        self.hm_cnt.configure(text=f"{len(items)}개 등록됨 (코드 {n_code} · 상품명 {len(items) - n_code}) · 이 PC의 data 폴더에 저장됩니다")

    def hm_add(self):
        code = op.hm_key(self.hm_code.get().strip().rstrip("-") if op.is_code(self.hm_code.get().strip()) else self.hm_code.get())
        if not code:
            return
        items = op.load_handmade()
        if any(op.hm_key(e.get("code")) == code for e in items):
            messagebox.showinfo("수제 제작", f"'{code}'는 이미 등록돼 있습니다.")
            return
        items.append({"code": code, "memo": self.hm_memo.get().strip(), "added": op.dt.date.today().isoformat()})
        op.save_handmade(items)
        kind = "코드" if op.is_code(code) else "상품명"
        op.log.info(f"[수제 제작] {kind} 추가: {code}")
        self.hm_code.delete(0, "end"); self.hm_memo.delete(0, "end")
        self.hm_show()
        self.hm_code.focus_set()
        self.app.flash(f"수제 제작 {kind} '{code[:30]}'를 추가했습니다. 택배 탭 확인 목록에 반영됩니다.")
        self._hm_refresh_courier()

    def hm_delete(self):
        sel = list(self.hm_tv.selection())
        if not sel:
            messagebox.showinfo("수제 제작 코드", "목록에서 지울 코드를 골라 주세요.")
            return
        if not messagebox.askyesno("수제 제작 코드", f"코드 {len(sel)}개를 지울까요?\n\n" + ", ".join(sel)):
            return
        op.save_handmade([e for e in op.load_handmade() if e.get("code") not in sel])
        op.log.info(f"[수제 제작] 코드 삭제: {', '.join(sel)}")
        self.hm_show()
        self._hm_refresh_courier()

    def hm_from_file(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(title="수제 제작 코드 파일 고르기",
                                          filetypes=[("엑셀·CSV·메모장", "*.xlsx *.xlsm *.csv *.txt"), ("모든 파일", "*.*")])
        if not path:
            return
        try:
            text = op.read_handmade_file(path)
        except Exception as e:
            messagebox.showerror("파일에서 가져오기", f"파일을 읽지 못했습니다.\n\n{e}")
            return
        HandmadeImport(self, text, source=os.path.basename(path))

    def _hm_save_xlsx(self, title, name, items=None):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(title=title, initialfile=name, defaultextension=".xlsx",
                                            filetypes=[("엑셀 파일", "*.xlsx")])
        if not path:
            return
        try:
            op.write_handmade_xlsx(path, items)
        except Exception as e:
            messagebox.showerror(title, f"저장하지 못했습니다 (파일이 열려 있으면 닫고 다시 해 주세요).\n\n{e}")
            return
        self.app.flash(f"{os.path.basename(path)} 를 저장했습니다.")
        op.open_file(os.path.dirname(path))

    def hm_template(self):
        self._hm_save_xlsx("양식 받기", "수제제작코드_양식.xlsx")

    def hm_export(self):
        items = [(e["code"], e.get("memo", "")) for e in sorted(op.load_handmade(), key=lambda e: e["code"])]
        if not items:
            messagebox.showinfo("엑셀로 내보내기", "등록된 코드가 없습니다.")
            return
        self._hm_save_xlsx("엑셀로 내보내기", f"수제제작코드_{op.dt.date.today():%Y%m%d}.xlsx", items)

    # ---------------------------------------------------------------- 중요 배송메세지 제외 목록
    def ex_show(self):
        if not hasattr(self, "ex_tv"):
            return
        self.ex_tv.delete(*self.ex_tv.get_children())
        items = C.load_exclude()
        today = op.dt.date.today().isoformat()
        mine = sorted([i for i in reversed(items) if i.get("added") != "기본"], key=lambda i: str(i.get("added", "")), reverse=True)
        base = sorted([i for i in items if i.get("added") == "기본"], key=lambda i: str(i["msg"]))
        q = self.ex_q.get().strip()
        self.ex_map = {}
        shown = 0
        for n, i in enumerate(mine + base):
            msg = str(i["msg"])
            if q and q not in msg:
                continue
            iid = f"x{n}"
            self.ex_map[iid] = msg
            self.ex_tv.insert("", "end", iid=iid, values=(msg.replace("\n", " ⏎ "), i.get("added", ""), i.get("pc", "")),
                              tags=("new",) if i.get("added") == today else ())
            shown += 1
        self.ex_cnt.configure(text=f"총 {len(items)}개" + (f" · 검색 결과 {shown}개" if q else "")
                                   + f" · 기본 {len(base)} · 추가 {len(mine)}")

    def ex_refresh(self):
        self.ex_show()
        self._hm_refresh_courier()

    def ex_add(self):
        msg = self.ex_entry.get().strip()
        if not msg:
            return
        if not C.add_exclude([msg]):
            messagebox.showinfo("제외 목록", f"'{msg}'는 이미 제외 목록에 있습니다.")
            return
        op.log.info(f"[제외 목록] 추가: {msg}")
        self.ex_entry.delete(0, "end")
        self.ex_q.set("")
        self.ex_refresh()
        self.app.flash(f"'{msg[:30]}'를 제외 목록에 추가했습니다.")

    def ex_delete(self):
        sel = [self.ex_map[i] for i in self.ex_tv.selection() if i in self.ex_map]
        if not sel:
            messagebox.showinfo("제외 목록", "목록에서 지울 문구를 골라 주세요.")
            return
        show = "\n".join(f"· {m}" for m in sel[:12]) + ("\n…" if len(sel) > 12 else "")
        if not messagebox.askyesno("제외 목록", f"문구 {len(sel)}개를 제외 목록에서 지울까요?\n지우면 이 메세지가 다시 "
                                              f"'중요 배송메세지 확인'에 나옵니다.\n\n{show}"):
            return
        C.remove_exclude(sel)
        op.log.info(f"[제외 목록] 삭제: {', '.join(sel)}")
        self.ex_refresh()

    def ex_export(self):
        from tkinter import filedialog
        items = C.load_exclude()
        path = filedialog.asksaveasfilename(title="제외 목록 내보내기", defaultextension=".xlsx",
                                            initialfile=f"배송메세지제외목록_{op.dt.date.today():%Y%m%d}.xlsx",
                                            filetypes=[("엑셀 파일", "*.xlsx")])
        if not path:
            return
        try:
            C.write_exclude_xlsx(path, items)
        except Exception as e:
            messagebox.showerror("제외 목록 내보내기", f"저장하지 못했습니다 (파일이 열려 있으면 닫고 다시 해 주세요).\n\n{e}")
            return
        self.app.flash(f"{os.path.basename(path)} 를 저장했습니다 ({len(items)}개).")
        op.open_file(os.path.dirname(path))

    def ex_import(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(title="제외 목록 파일 고르기",
                                          filetypes=[("엑셀·CSV·메모장", "*.xlsx *.xlsm *.csv *.txt"), ("모든 파일", "*.*")])
        if not path:
            return
        try:
            rows = C.read_exclude_file(path)
        except Exception as e:
            messagebox.showerror("제외 목록 가져오기", f"파일을 읽지 못했습니다.\n\n{e}")
            return
        if not rows:
            messagebox.showinfo("제외 목록 가져오기", "파일에서 문구를 찾지 못했습니다.")
            return
        ExcludeImport(self, rows, source=os.path.basename(path))

    # ---------------------------------------------------------------- 데이터 백업
    def bk_show(self):
        b = DB.last_backup()
        if b:
            t = str(b.get("time", "")).replace("T", " ")[:16]
            self.bk_lb.configure(text=f"마지막 백업: {t}" + (f" ({b['pc']})" if b.get("pc") else ""))
        else:
            self.bk_lb.configure(text="마지막 백업: 아직 없음")

    def backup_now(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(title="전체 데이터 백업 저장", defaultextension=".zip",
                                            initialfile=f"데이터백업_{op.dt.datetime.now():%Y%m%d_%H%M}.zip",
                                            filetypes=[("압축 파일", "*.zip")])
        if not path:
            return
        try:
            p, n = DB.make_backup(path)
        except Exception as e:
            messagebox.showerror("데이터 백업", f"백업하지 못했습니다.\n\n{e}")
            return
        op.log.info(f"[데이터 백업] {p} ({n}개 파일)")
        self.bk_show()
        messagebox.showinfo("데이터 백업", f"백업했습니다 ({n}개 파일).\n\n{p}\n\n"
                                         "카페24 접속 정보가 들어 있으니 사무실 밖으로 보내지 마세요.")
        op.open_file(os.path.dirname(str(p)))

    def backup_restore(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(title="되돌릴 백업 파일 고르기", filetypes=[("압축 파일", "*.zip")])
        if not path:
            return
        try:
            info = DB.read_info(path)
        except Exception as e:
            messagebox.showerror("백업에서 되돌리기", str(e))
            return
        t = str(info.get("time", "")).replace("T", " ")[:16]
        if not messagebox.askyesno("백업에서 되돌리기",
                                   f"이 백업으로 되돌릴까요?\n\n백업한 때: {t}\n백업한 PC: {info.get('pc') or '-'}\n"
                                   f"프로그램 버전: {info.get('version') or '-'} · 파일 {info.get('files', 0)}개\n\n"
                                   "수제 코드·제외 목록·설정·세금계산서 내역 등이 이 백업 때로 바뀝니다.\n"
                                   "(지금 상태는 data_backups 폴더에 자동으로 저장해 둡니다. "
                                   "이미 뽑은 주문·택배 파일 기록은 합쳐서 다시 출력되지 않습니다.)", icon="warning"):
            return
        try:
            auto, _ = DB.restore(path)
        except Exception as e:
            op.log.exception("[데이터 백업] 되돌리기 실패")
            messagebox.showerror("백업에서 되돌리기", f"되돌리지 못했습니다.\n\n{e}")
            return
        op.log.info(f"[데이터 백업] 되돌림: {path} (되돌리기 전 자동 백업: {auto})")
        if messagebox.askyesno("백업에서 되돌리기", "되돌렸습니다. 바뀐 내용을 쓰려면 프로그램을 다시 켜야 합니다.\n\n지금 다시 켤까요?"):
            import updater
            updater.restart_manager()
            self.app.destroy()

    def _hm_refresh_courier(self):
        ct = getattr(self.app, "courier_tab", None)
        if ct is not None:
            ct._auto_key = None                     # 다음에 택배 탭을 열면 다시 확인

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


class ExcludeImport(tk.Toplevel):
    """제외 목록 한꺼번에 넣기: 붙여넣기(한 줄에 하나) 또는 파일 → 합치기 / 바꾸기"""

    def __init__(self, tab, rows=None, source=None):
        super().__init__(tab.app)
        self.tab, self.rows = tab, rows
        self.title("제외 목록 가져오기" if rows is not None else "제외 목록 여러 개 붙여넣기")
        self.configure(background=T.CARD)
        self.transient(tab.app)
        f = ttk.Frame(self, padding=18); f.pack(fill="both", expand=True)
        f.columnconfigure(0, weight=1)
        ttk.Label(f, text=f"파일: {source}" if source else "문구 붙여넣기", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.box = None
        if rows is None:
            hint(f, "한 줄에 문구 하나. 앞뒤 공백만 지우고 그대로 넣습니다 (완전히 같은 메세지만 제외).",
                 row=1, column=0, sticky="w", pady=(4, 6), wrap=480)
            self.box = T.text_box(tk.Text(f, width=56, height=12, wrap="none"))
            self.box.grid(row=2, column=0, sticky="nsew"); f.rowconfigure(2, weight=1)
            self.box.bind("<KeyRelease>", lambda e: self.summary())
            self.box.bind("<<Paste>>", lambda e: self.after(50, self.summary))
        self.sum_lb = ttk.Label(f, text="", justify="left", wraplength=480)
        self.sum_lb.grid(row=3, column=0, sticky="w", pady=(10, 0))
        self.mode = tk.StringVar(value="add")
        mf = ttk.Frame(f); mf.grid(row=4, column=0, sticky="w", pady=(10, 0))
        ttk.Radiobutton(mf, text="합치기 — 지금 목록은 그대로 두고 없는 것만 추가 (추천)", value="add",
                        variable=self.mode, command=self.summary).pack(anchor="w")
        ttk.Radiobutton(mf, text="바꾸기 — 지금 목록을 지우고 이 내용으로 교체", value="replace",
                        variable=self.mode, command=self.summary).pack(anchor="w")
        bf = ttk.Frame(f); bf.grid(row=5, column=0, sticky="we", pady=(12, 0))
        ttk.Button(bf, text="가져오기", style="Accent.TButton", command=self.ok).pack(side="right")
        ttk.Button(bf, text="취소", command=self.destroy).pack(side="right", padx=6)
        self.summary()
        self.update_idletasks()
        app = tab.app
        x = app.winfo_rootx() + (app.winfo_width() - self.winfo_width()) // 2
        self.geometry(f"+{max(0, x)}+{max(0, app.winfo_rooty() + 80)}")
        self.grab_set()
        (self.box or self).focus_set()

    def _rows(self):
        if self.rows is not None:
            src = self.rows
        else:
            src = [{"msg": l} for l in self.box.get("1.0", "end").splitlines()]
        out, seen = [], set()
        for r in src:
            m = str(r.get("msg", "")).strip()
            if m and m not in seen:
                seen.add(m); out.append({**r, "msg": m})
        return out

    def summary(self):
        rows = self._rows()
        have = {str(i["msg"]).strip() for i in C.load_exclude()}
        new = [r["msg"] for r in rows if r["msg"] not in have]
        lines = [f"넣을 문구 {len(rows)}개", f"· 새로 추가될 문구 {len(new)}개"]
        lines += [f"     {m}" for m in new[:3]] + ([f"     … 외 {len(new) - 3}개"] if len(new) > 3 else [])
        lines.append(f"· 이미 있는 문구 {len(rows) - len(new)}개 (그대로 둠)")
        if self.mode.get() == "replace":
            gone = len(have - {r["msg"] for r in rows})
            lines.append(f"· 바꾸기: 지금 목록에서 빠지는 문구 {gone}개")
        self.sum_lb.configure(text="\n".join(lines))

    def ok(self):
        rows = self._rows()
        if not rows:
            messagebox.showwarning("가져오기", "넣을 문구가 없습니다.", parent=self)
            return
        replace = self.mode.get() == "replace"
        if replace:
            cur = len(C.load_exclude())
            if not messagebox.askyesno("바꾸기", f"지금 목록 {cur}개를 지우고 {len(rows)}개로 바꿀까요?", parent=self):
                return
        added = C.add_exclude(rows, replace=replace)
        op.log.info(f"[제외 목록] 가져오기({'바꾸기' if replace else '합치기'}): 새 {len(added)}개, 전체 {len(rows)}개")
        self.destroy()
        self.tab.ex_q.set("")
        self.tab.ex_refresh()
        self.tab.app.flash(f"제외 목록 가져오기: {'바꾸기 완료' if replace else f'새 문구 {len(added)}개 추가'}")


class HandmadeImport(tk.Toplevel):
    """수제 제작 코드 한꺼번에 넣기: 붙여넣기(또는 파일 내용) → 추가하기 / 목록 바꾸기"""

    def __init__(self, tab, text="", source=None):
        super().__init__(tab.app)
        self.tab = tab
        self.title("수제 제작 코드 한꺼번에 넣기")
        self.configure(background=T.CARD)
        self.transient(tab.app)
        f = ttk.Frame(self, padding=18); f.pack(fill="both", expand=True)
        f.columnconfigure(0, weight=1); f.rowconfigure(2, weight=1)
        ttk.Label(f, text=f"파일: {source}" if source else "코드 붙여넣기", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        hint(f, "한 줄에 하나. 코드(PDT2431)는 뒤에 쉼표(,)나 탭으로 메모를 붙일 수 있고, 엑셀에서 두 칸을 복사해 붙여도 됩니다.\n"
                "'PDT2431-수제 진주 귀걸이'처럼 코드로 시작하는 상품명은 코드만 씁니다. 코드가 없는 상품은 상품명을 그대로 붙이세요 "
                "(완전히 같은 상품명만 잡음, 메모는 탭 뒤에).",
             row=1, column=0, sticky="w", pady=(4, 6), wrap=520)
        self.box = T.text_box(tk.Text(f, width=64, height=14, wrap="none"))
        self.box.grid(row=2, column=0, sticky="nsew")
        self.box.insert("1.0", text or "")
        self.mode = tk.StringVar(value="add")
        mf = ttk.Frame(f); mf.grid(row=3, column=0, sticky="w", pady=(10, 0))
        ttk.Radiobutton(mf, text="추가하기 (지금 목록은 두고 새 코드만 더함)", value="add", variable=self.mode).pack(anchor="w")
        ttk.Radiobutton(mf, text="목록 바꾸기 (지금 목록을 지우고 이 내용으로)", value="replace", variable=self.mode).pack(anchor="w")
        bf = ttk.Frame(f); bf.grid(row=4, column=0, sticky="we", pady=(12, 0))
        ttk.Button(bf, text="가져오기", style="Accent.TButton", command=self.ok).pack(side="right")
        ttk.Button(bf, text="취소", command=self.destroy).pack(side="right", padx=6)
        self.update_idletasks()
        app = tab.app
        x = app.winfo_rootx() + (app.winfo_width() - self.winfo_width()) // 2
        y = app.winfo_rooty() + 80
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.grab_set()
        self.box.focus_set()

    def ok(self):
        rows, bad = op.parse_handmade_text(self.box.get("1.0", "end"))
        if not rows:
            messagebox.showwarning("가져오기", "넣을 코드를 찾지 못했습니다." + (f"\n\n형식이 안 맞는 줄:\n" + "\n".join(bad[:10]) if bad else ""),
                                   parent=self)
            return
        replace = self.mode.get() == "replace"
        plan = op.plan_handmade(rows, replace)
        if bad and not messagebox.askyesno("가져오기", f"형식이 안 맞는 줄 {len(bad)}개는 빼고 넣습니다:\n\n" + "\n".join(bad[:10])
                                         + ("\n…" if len(bad) > 10 else "") + "\n\n계속할까요?", parent=self):
            return
        if replace:
            cur = len(op.load_handmade())
            if not messagebox.askyesno("목록 바꾸기", f"지금 목록 {cur}개를 지우고 {len(rows)}개로 바꿀까요?"
                                                  + (f"\n\n빠지는 코드 {len(plan['gone'])}개: " + ", ".join(plan["gone"][:15])
                                                     + ("…" if len(plan["gone"]) > 15 else "") if plan["gone"] else ""), parent=self):
                return
        change = False
        if plan["memo"]:
            lines = "\n".join(f"{c}: \"{o or '(없음)'}\" → \"{n}\"" for c, o, n in plan["memo"][:12])
            change = messagebox.askyesno("메모 바꾸기", f"이미 있는 코드 {len(plan['memo'])}개의 메모가 다릅니다.\n\n{lines}"
                                                     + ("\n…" if len(plan["memo"]) > 12 else "")
                                                     + "\n\n[예] 메모를 새것으로 바꾸기   [아니요] 그대로 두기", parent=self)
        total = op.apply_handmade(rows, replace, change)
        op.log.info(f"[수제 제작] 한꺼번에 넣기({'바꾸기' if replace else '추가'}): 새 {len(plan['new'])}, 메모 변경 "
                    f"{len(plan['memo']) if change else 0}, 빠짐 {len(plan['gone'])}, 형식 오류 {len(bad)}")
        self.destroy()
        self.tab.hm_show()
        self.tab._hm_refresh_courier()
        msg = (f"추가 {len(plan['new'])}개 · 이미 있음 {len(plan['same']) + len(plan['memo'])}개"
               + (f" (메모 바꿈 {len(plan['memo'])}개)" if change and plan["memo"] else "")
               + (f" · 빠진 코드 {len(plan['gone'])}개" if replace else "")
               + (f" · 형식이 안 맞아 뺀 줄 {len(bad)}개" if bad else "") + f"\n\n지금 등록된 코드: {total}개")
        messagebox.showinfo("가져오기 완료", msg)

