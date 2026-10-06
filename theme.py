# -*- coding: utf-8 -*-
"""주문서 출력 관리 — 디자인(엔비즈워크 스타일). 색·글꼴·부품 모양은 모두 여기서 정합니다.
새 화면을 만들 때도 이 파일의 스타일 이름만 쓰면 같은 모양이 됩니다. (자세한 규칙: 디자인규칙.md)"""
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

# ---------------------------------------------------------------- 색상표
BG = "#F4F4F2"          # 페이지 바탕 (연한 회색)
CARD = "#FFFFFF"        # 카드 (흰색)
LINE = "#E5E5E2"        # 카드 테두리
LINE_STRONG = "#D6D6D2" # 입력칸·보조 버튼 테두리
INK = "#1F2328"         # 기본 글자 (검정)
MUTED = "#8A8F98"       # 설명 글자 (회색)
DIM = "#A3A7AE"         # 비활성 (이미 뽑은 주문 등)
GREEN = "#1F9D6B"       # 강조 (주요 버튼, 켜짐, 오늘)
GREEN_D = "#16825A"     # 강조 (눌렀을 때)
GREEN_L = "#E7F5EE"     # 강조 연한 바탕 (선택된 줄, 상태 표시)
RED = "#F2464B"         # 알림 띠 (확인 필요)
BLUE = "#1565C0"        # 토요일 등
ORANGE = "#D9480F"      # 주의 글자

# 쇼핑몰(주문경로)별 파스텔 타일: (바탕, 테두리)
TILES = {
    "쿠팡": ("#FFE4CC", "#F5B784"), "네이버페이": ("#D7F3DE", "#8FD4A3"), "스마트스토어": ("#E3F6D8", "#A9DB8B"),
    "PC": ("#FFF6C2", "#EAD66C"), "모바일": ("#DCEBFF", "#93BDF0"), "기타": ("#EDE3FF", "#C2A8F2"),
}

FONT = "맑은 고딕"
RADIUS = 9              # 모서리 둥글기 (px)
_IMGS = []              # 그림이 지워지지 않게 붙잡아 둠


def _rr(w, h, r, fill, outline=None, bw=1, ss=4):
    """둥근 사각형 그림 (모서리 바깥은 투명). 4배로 그린 뒤 줄여서 매끄럽게."""
    from PIL import Image, ImageDraw, ImageTk
    W, H = w * ss, h * ss
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if outline:
        d.rounded_rectangle([0, 0, W - 1, H - 1], r * ss, fill=outline)
        k = bw * ss
        d.rounded_rectangle([k, k, W - 1 - k, H - 1 - k], max(1, r - bw) * ss, fill=fill)
    else:
        d.rounded_rectangle([0, 0, W - 1, H - 1], r * ss, fill=fill)
    img = ImageTk.PhotoImage(im.resize((w, h), Image.LANCZOS))
    _IMGS.append(img)
    return img


def _round_button(st, name, fill, line, hover, press, dis_fill, dis_line, r=RADIUS):
    el = name.replace(".", "_") + "_rb"
    n, h, p, d = (_rr(48, 34, r, c, b) for c, b in ((fill, line), (hover, line), (press, line), (dis_fill, dis_line)))
    st.element_create(el, "image", n, ("disabled", d), ("pressed", p), ("active", h), border=r + 2,
                      padding=(2, 1), sticky="nsew")
    st.layout(name, [(el, {"sticky": "nsew", "children": [
        ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})]})])


def _round_field(st, name, inner):
    el = name.replace(".", "_") + "_rf"
    n = _rr(48, 32, 7, CARD, LINE_STRONG)
    fo = _rr(48, 32, 7, CARD, GREEN, bw=2)
    di = _rr(48, 32, 7, "#F4F4F2", LINE)
    st.element_create(el, "image", n, ("disabled", di), ("focus", fo), border=8, padding=(2, 1), sticky="nsew")
    st.layout(name, [(el, {"sticky": "nsew", "children": inner})])


def pick_font(root):
    """윈도우는 맑은 고딕, 없으면 비슷한 한글 글꼴"""
    global FONT
    fams = set(tkfont.families(root))
    for f in ("맑은 고딕", "Malgun Gothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans KR"):
        if f in fams:
            FONT = f
            break
    return FONT


def f(size=10, bold=False):
    return (FONT, size, "bold") if bold else (FONT, size)


# ---------------------------------------------------------------- ttk 스타일
def apply(root):
    pick_font(root)
    root.configure(background=BG)
    root.option_add("*Font", f(10))
    root.option_add("*TCombobox*Listbox.font", f(10))
    st = ttk.Style(root)
    st.theme_use("clam")
    st.configure(".", background=CARD, foreground=INK, font=f(10), bordercolor=LINE, lightcolor=CARD,
                 darkcolor=CARD, troughcolor="#EEEEEB", focuscolor=GREEN, selectbackground=GREEN_L,
                 selectforeground=INK)

    # 바탕: 카드 안은 흰색(기본), 페이지는 회색(Page.*)
    st.configure("TFrame", background=CARD)
    st.configure("Page.TFrame", background=BG)
    st.configure("TLabel", background=CARD, foreground=INK)
    st.configure("Page.TLabel", background=BG, foreground=INK)
    st.configure("Hint.TLabel", background=CARD, foreground=MUTED, font=f(9))
    st.configure("PageHint.TLabel", background=BG, foreground=MUTED, font=f(9))
    st.configure("Title.TLabel", background=CARD, foreground=INK, font=f(12, True))
    st.configure("PageTitle.TLabel", background=BG, foreground=INK, font=f(12, True))
    st.configure("Big.TLabel", background=CARD, foreground=INK, font=f(13, True))

    # 카드 (테두리 있는 흰 상자)
    # 카드 제목은 카드 바깥 위쪽(회색 바탕)에, 카드는 흰 상자로
    st.configure("TLabelframe", background=CARD, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE,
                 relief="solid", borderwidth=1, labeloutside=True, labelmargins=(0, 0, 0, 6))
    st.configure("TLabelframe.Label", background=BG, foreground=INK, font=f(11, True))

    # 버튼: 기본 = 흰 바탕 + 테두리 / Accent·Main = 초록 / Ghost = 초록 글자 + 초록 테두리
    st.configure("TButton", background=CARD, foreground=INK, bordercolor=LINE_STRONG, lightcolor=CARD,
                 darkcolor=CARD, font=f(10, True), padding=(12, 6), relief="solid", borderwidth=1)
    st.map("TButton", background=[("disabled", "#F4F4F2"), ("pressed", "#EDEDEA"), ("active", "#F6F6F3")],
           foreground=[("disabled", DIM)], bordercolor=[("focus", LINE_STRONG)])
    for name, pad, size in (("Accent.TButton", (14, 6), 10), ("Main.TButton", (22, 10), 13)):
        st.configure(name, background=GREEN, foreground="white", bordercolor=GREEN, lightcolor=GREEN,
                     darkcolor=GREEN, font=f(size, True), padding=pad)
        st.map(name, background=[("disabled", "#BFDCCF"), ("pressed", GREEN_D), ("active", GREEN_D)],
               foreground=[("disabled", "white")], bordercolor=[("disabled", "#BFDCCF"), ("active", GREEN_D)],
               lightcolor=[("active", GREEN_D)], darkcolor=[("active", GREEN_D)])
    st.configure("Ghost.TButton", background=CARD, foreground=GREEN, bordercolor=GREEN, font=f(10, True), padding=(12, 6))
    st.configure("Stop.TButton", background=CARD, foreground=RED, bordercolor=RED, font=f(10, True), padding=(12, 6))
    st.map("Stop.TButton", background=[("active", "#FDEBEC")], foreground=[("disabled", DIM)],
           bordercolor=[("disabled", LINE_STRONG)])
    st.map("Ghost.TButton", background=[("active", GREEN_L)], foreground=[("disabled", DIM)])

    # 체크·라디오
    for base in ("TCheckbutton", "TRadiobutton"):
        st.configure(base, background=CARD, foreground=INK, indicatorbackground=CARD, indicatorforeground=GREEN)
        st.map(base, background=[("active", CARD)], indicatorbackground=[("selected", GREEN)],
               indicatorforeground=[("selected", "white")])
        st.configure("Page." + base, background=BG)
        st.map("Page." + base, background=[("active", BG)])
    st.configure("Big.TCheckbutton", font=f(12, True))
    st.configure("Warn.TCheckbutton", background="#FFF8E6", font=f(10, True))
    st.configure("Split.TCheckbutton", background="#F1FAEC", font=f(10, True))
    st.map("Split.TCheckbutton", background=[("active", "#F1FAEC")], indicatorbackground=[("selected", GREEN)],
           indicatorforeground=[("selected", "white")])
    st.map("Warn.TCheckbutton", background=[("active", "#FFF8E6")], indicatorbackground=[("selected", GREEN)],
           indicatorforeground=[("selected", "white")])
    st.configure("PageBig.TCheckbutton", background=BG, font=f(12, True))
    st.map("PageBig.TCheckbutton", background=[("active", BG)], indicatorbackground=[("selected", GREEN)],
           indicatorforeground=[("selected", "white")])

    # 입력칸
    for w in ("TEntry", "TCombobox", "TSpinbox"):
        st.configure(w, fieldbackground=CARD, background=CARD, bordercolor=LINE_STRONG, lightcolor=CARD,
                     darkcolor=CARD, arrowcolor=MUTED, padding=4)
        st.map(w, bordercolor=[("focus", GREEN)], lightcolor=[("focus", GREEN)],
               fieldbackground=[("readonly", CARD), ("disabled", "#F4F4F2")], foreground=[("disabled", DIM)])

    # 표
    st.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=INK, rowheight=28, borderwidth=0,
                 font=f(10))
    st.configure("Treeview.Heading", background="#F7F7F5", foreground=MUTED, font=f(10, True), relief="flat",
                 borderwidth=0, padding=6)
    st.map("Treeview", background=[("selected", GREEN_L)], foreground=[("selected", INK)])
    st.map("Treeview.Heading", background=[("active", "#EFEFEC")])

    # 안쪽 작은 탭(주문 현황/출력 기록 등)
    st.configure("TNotebook", background=CARD, borderwidth=0, tabmargins=(0, 0, 0, 0))
    st.configure("TNotebook.Tab", background="#F1F1EE", foreground=MUTED, padding=(14, 7), font=f(10, True),
                 bordercolor=LINE, lightcolor=LINE)
    st.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", INK)])
    # 바깥 큰 탭: 탭 머리는 숨기고 위쪽 메뉴 버튼으로 바꿈
    st.configure("Main.TNotebook", background=BG, borderwidth=0, tabmargins=0)
    st.layout("Main.TNotebook.Tab", [])

    # ---- 둥근 모서리 (웹 도구처럼). 바탕이 회색인 곳은 Page.* 스타일
    for prefix, under in (("", CARD), ("Page.", BG)):
        st.configure(prefix + "TButton", background=under)
        _round_button(st, prefix + "TButton", CARD, LINE_STRONG, "#F6F6F3", "#EDEDEA", "#F4F4F2", LINE)
        st.configure(prefix + "Accent.TButton", background=under, foreground="white", font=f(10, True), padding=(14, 6))
        _round_button(st, prefix + "Accent.TButton", GREEN, GREEN, GREEN_D, GREEN_D, "#BFDCCF", "#BFDCCF")
        st.configure(prefix + "Main.TButton", background=under, foreground="white", font=f(13, True), padding=(22, 10))
        _round_button(st, prefix + "Main.TButton", GREEN, GREEN, GREEN_D, GREEN_D, "#BFDCCF", "#BFDCCF", r=11)
        st.configure(prefix + "Ghost.TButton", background=under, foreground=GREEN, font=f(10, True), padding=(12, 6))
        _round_button(st, prefix + "Ghost.TButton", CARD, GREEN, GREEN_L, "#D5EEE2", "#F4F4F2", LINE)
        st.configure(prefix + "Stop.TButton", background=under, foreground=RED, font=f(10, True), padding=(12, 6))
        _round_button(st, prefix + "Stop.TButton", CARD, RED, "#FDEBEC", "#FAD7D9", "#F4F4F2", LINE)
    for name in ("Accent.TButton", "Main.TButton", "Page.Accent.TButton", "Page.Main.TButton"):
        st.map(name, foreground=[("disabled", "white")], background=[])
    for name in ("TButton", "Page.TButton", "Ghost.TButton", "Page.Ghost.TButton", "Stop.TButton", "Page.Stop.TButton"):
        st.map(name, background=[], foreground=[("disabled", DIM)])
    # 카드: 바깥(모서리)은 페이지 회색, 안은 흰색
    card = _rr(64, 64, RADIUS + 2, CARD, LINE)
    st.element_create("Card_border", "image", card, border=RADIUS + 4, padding=2, sticky="nsew")
    st.layout("TLabelframe", [("Card_border", {"sticky": "nsew"})])
    st.configure("TLabelframe", background=BG)
    # 입력칸
    _round_field(st, "TEntry", [("Entry.padding", {"sticky": "nsew", "children": [("Entry.textarea", {"sticky": "nsew"})]})])
    _round_field(st, "TCombobox", [("Combobox.downarrow", {"side": "right", "sticky": "ns"}),
                                   ("Combobox.padding", {"expand": "1", "sticky": "nsew",
                                                         "children": [("Combobox.textarea", {"sticky": "nsew"})]})])
    _round_field(st, "TSpinbox", [("Spinbox.uparrow", {"side": "top", "sticky": "e"}),
                                  ("Spinbox.downarrow", {"side": "bottom", "sticky": "e"}),
                                  ("Spinbox.padding", {"sticky": "nsew", "children": [("Spinbox.textarea", {"sticky": "nsew"})]})])
    for w in ("TEntry", "TCombobox", "TSpinbox"):
        st.configure(w, padding=(7, 3), background=CARD)

    st.configure("TProgressbar", background=GREEN, troughcolor="#EEEEEB", bordercolor=LINE, lightcolor=GREEN,
                 darkcolor=GREEN)
    # 스크롤바: 양쪽 화살표는 두고, 가운데 막대는 줄무늬 없는 민자
    for o in ("Vertical.TScrollbar", "Horizontal.TScrollbar", "TScrollbar"):
        st.configure(o, gripcount=0, background="#DADAD6", troughcolor="#F1F1EE", bordercolor="#F1F1EE",
                     lightcolor="#DADAD6", darkcolor="#DADAD6", arrowcolor=MUTED, relief="flat")
        st.map(o, background=[("pressed", "#BDBDB8"), ("active", "#CACAC5")],
               lightcolor=[("pressed", "#BDBDB8"), ("active", "#CACAC5")],
               darkcolor=[("pressed", "#BDBDB8"), ("active", "#CACAC5")])
    return st


# ---------------------------------------------------------------- 부품 (tk)
def _round_poly(cv, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
           x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kw)


class Pill(tk.Canvas):
    """둥근 알약 모양 글자 (상태 표시, 메뉴 버튼). configure(text=, bg=채우기색, fg=글자색, outline=테두리색)"""

    def __init__(self, parent, text="", bg=GREEN_L, fg=GREEN_D, outline=None, font=None, padx=12, pady=6,
                 under=CARD, radius=None):
        super().__init__(parent, highlightthickness=0, bd=0, background=under)
        self._o = {"text": text, "bg": bg, "fg": fg, "outline": outline}
        self._font, self._padx, self._pady, self._r = font or f(10, True), padx, pady, radius
        self._draw()

    def _draw(self):
        import tkinter.font as tkf
        fnt = tkf.Font(font=self._font)
        w = fnt.measure(self._o["text"]) + self._padx * 2
        h = fnt.metrics("linespace") + self._pady * 2
        tk.Canvas.configure(self, width=w + 2, height=h + 2)
        self.delete("all")
        r = self._r if self._r is not None else min(RADIUS, h // 2)
        _round_poly(self, 1, 1, w, h, r, fill=self._o["bg"], outline=self._o["outline"] or self._o["bg"])
        self.create_text(w / 2 + 1, h / 2 + 1, text=self._o["text"], fill=self._o["fg"], font=self._font)

    def configure(self, cnf=None, **kw):
        if "highlightbackground" in kw:
            kw["outline"] = kw.pop("highlightbackground")
        mine = {k: kw.pop(k) for k in ("text", "bg", "fg", "outline") if k in kw}
        if mine:
            self._o.update(mine)
            self._draw()
        if kw or cnf:
            return tk.Canvas.configure(self, cnf, **kw)
    config = configure

    def cget(self, key):
        return self._o[key] if key in self._o else tk.Canvas.cget(self, key)


class RoundBox(tk.Canvas):
    """폭에 맞춰 늘어나는 둥근 상자 (알림 띠 등). 글자는 자동 줄바꿈."""

    def __init__(self, parent, text="", fill=RED, fg="white", outline=None, under=BG, font=None, pad=(14, 9),
                 on_close=None):
        super().__init__(parent, highlightthickness=0, bd=0, background=under, height=36)
        self._t, self._fill, self._fg, self._ol, self._font, self._pad = text, fill, fg, outline, font or f(10, True), pad
        self._on_close = on_close
        self.bind("<Configure>", lambda e: self._draw())

    def _draw(self):
        w = max(self.winfo_width(), 50)
        self.delete("all")
        close_w = 0
        if self._on_close:                      # 오른쪽 [확인 ✕] — 누르면 이 경고를 닫음
            cid = self.create_text(w - self._pad[0], self._pad[1], text="확인 ✕", fill=self._fg, font=f(10, True),
                                   anchor="ne", tags="close")
            close_w = self.bbox(cid)[2] - self.bbox(cid)[0] + 14
            self.tag_bind("close", "<Button-1>", lambda e: self._on_close())
            self.tag_bind("close", "<Enter>", lambda e: self.configure(cursor="hand2"))
            self.tag_bind("close", "<Leave>", lambda e: self.configure(cursor=""))
        tid = self.create_text(self._pad[0], self._pad[1], text=self._t, fill=self._fg, font=self._font, anchor="nw",
                               width=w - self._pad[0] * 2 - close_w)
        x1, y1, x2, y2 = self.bbox(tid)
        h = y2 + self._pad[1]
        if int(self.cget("height")) != h:
            tk.Canvas.configure(self, height=h)
        bg = _round_poly(self, 0, 0, w - 1, h - 1, RADIUS, fill=self._fill, outline=self._ol or self._fill)
        self.tag_lower(bg)


class Tile(tk.Canvas):
    """쇼핑몰별 파스텔 타일 (둥근 모서리, 마우스를 올리면 진한 테두리)"""

    def __init__(self, parent, name, count, width=140, height=76, under=BG):
        super().__init__(parent, width=width, height=height, highlightthickness=0, bd=0, background=under)
        self.name, self.count, self.w, self.h = name, count, width, height
        self.bg_c, self.bd_c = TILES.get(name, TILES["기타"])
        self.hover(False)

    def hover(self, on):
        self.delete("all")
        _round_poly(self, 1, 1, self.w - 2, self.h - 2, RADIUS + 2, fill=self.bg_c,
                    outline=INK if on else self.bd_c, width=2 if on else 1)
        self.create_text(self.w / 2, self.h * 0.32, text=self.name, fill=INK, font=f(10, True))
        self.create_text(self.w / 2, self.h * 0.68, text=f"{self.count}건", fill=INK, font=f(16, True))


def text_box(t):
    """tk.Text를 카드 안 글상자 모양으로"""
    t.configure(background=CARD, foreground=INK, relief="flat", highlightthickness=1,
                highlightbackground=LINE_STRONG, highlightcolor=GREEN, font=f(9), padx=6, pady=4)
    return t


def alert(parent, text, on_close=None):
    """빨간 알림 띠 (둥근 모서리). on_close가 있으면 오른쪽에 [확인 ✕]"""
    return RoundBox(parent, text=text, fill=RED, fg="white", under=BG, on_close=on_close)


def pill(parent, text, on=False, under=CARD):
    """상태 표시 알약 (켜짐=초록, 꺼짐=회색)"""
    return Pill(parent, text=text, bg=GREEN_L if on else "#EFEFEC", fg=GREEN_D if on else MUTED, under=under)


def tile(parent, name, count, width=140, height=76):
    """쇼핑몰별 파스텔 타일"""
    return Tile(parent, name, count, width, height)
