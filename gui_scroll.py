# -*- coding: utf-8 -*-
"""탭 내용을 스크롤할 수 있게 감싸는 틀. 창이 작아도 오른쪽·아래 스크롤바와 마우스 휠로 전부 볼 수 있음."""
import sys
import tkinter as tk
from tkinter import ttk

_AREAS = []


class ScrollArea(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, style="Page.TFrame")
        import theme
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, background=theme.BG)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.hbar = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1); self.columnconfigure(0, weight=1)
        self.inner = None
        self._win = None
        self.canvas.bind("<Configure>", lambda e: self._fit())
        _AREAS.append(self)
        if len(_AREAS) == 1:
            root = self.winfo_toplevel()
            if sys.platform.startswith("linux"):
                root.bind_all("<Button-4>", lambda e: _wheel(e, -1), add="+")
                root.bind_all("<Button-5>", lambda e: _wheel(e, 1), add="+")
            else:
                root.bind_all("<MouseWheel>", lambda e: _wheel(e, -1 if e.delta > 0 else 1), add="+")

    def set_inner(self, widget):
        """widget은 반드시 self.canvas를 부모로 만들어야 함"""
        self.inner = widget
        self._win = self.canvas.create_window(0, 0, window=widget, anchor="nw")
        widget.bind("<Configure>", lambda e: self._fit(), add="+")

    def _fit(self):
        if not self.inner:
            return
        rw, rh = self.inner.winfo_reqwidth(), self.inner.winfo_reqheight()
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        # 창이 크면 내용을 창 크기에 맞춰 늘리고, 작으면 원래 크기 그대로 두고 스크롤
        self.canvas.itemconfigure(self._win, width=max(rw, cw), height=max(rh, ch))
        self.canvas.configure(scrollregion=(0, 0, max(rw, cw), max(rh, ch)))
        # 스크롤할 필요가 없으면 스크롤바 숨기기
        (self.vbar.grid if rh > ch else self.vbar.grid_remove)()
        (self.hbar.grid if rw > cw else self.hbar.grid_remove)()


def _wheel(event, direction):
    w = event.widget
    try:
        if isinstance(w, str) or w.winfo_class() in ("Treeview", "Text", "Listbox", "TCombobox", "TSpinbox"):
            return            # 목록·글상자는 자기 스크롤을 씀
    except tk.TclError:
        return
    while w is not None:
        for a in _AREAS:
            if w is a:
                try:
                    if a.winfo_ismapped() and a.vbar.winfo_ismapped():
                        a.canvas.yview_scroll(direction * 2, "units")
                except tk.TclError:
                    pass
                return
        w = getattr(w, "master", None)


def scrolled(notebook, build):
    """build(부모) → 탭 위젯. 스크롤 틀에 넣어 돌려줌: (틀, 탭)"""
    area = ScrollArea(notebook)
    tab = build(area.canvas)
    area.set_inner(tab)
    return area, tab
