# -*- coding: utf-8 -*-
"""자동 출력 진행·결과 작은 창.
자동 출력과는 '따로' 실행되어 진행 상황 파일(data/auto_status.json)만 읽습니다.
이 창이 떠 있든, 잠금 화면 뒤에 있든, 닫히든 인쇄에는 아무 영향이 없습니다."""
import datetime as dt
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

BASE = Path(__file__).resolve().parent
STATUS = BASE / "data" / "auto_status.json"
STOPFILE = BASE / "data" / "auto_stop.flag"
PIDFILE = BASE / "data" / "notify.pid"

import theme as T  # noqa: E402


def read_status():
    try:
        return json.loads(STATUS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def pid_alive(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if sys.platform == "win32":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return code.value == 259
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def close_previous():
    """이전 결과 창이 남아 있으면 닫고 새 창으로 대신함 (창이 쌓이지 않게)"""
    try:
        old = int(PIDFILE.read_text().strip())
        if old != os.getpid() and pid_alive(old):
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(old), "/F"], capture_output=True, creationflags=0x08000000)
            else:
                os.kill(old, 15)
    except Exception:
        pass
    try:
        PIDFILE.parent.mkdir(exist_ok=True)
        PIDFILE.write_text(str(os.getpid()))
    except Exception:
        pass


class Notice(tk.Tk):
    W, H = 420, 250

    def __init__(self):
        super().__init__()
        T.apply(self)
        self.title("주문서 자동 출력")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{self.W}x{self.H}+{sw - self.W - 24}+{sh - self.H - 70}")
        self.configure(background=T.CARD)
        self.protocol("WM_DELETE_WINDOW", self.ok)
        self.dead_since = None

        head = tk.Frame(self, bg=T.CARD); head.pack(fill="x", padx=16, pady=(14, 4))
        self.dot = tk.Canvas(head, width=14, height=14, bg=T.CARD, highlightthickness=0)
        self.dot.create_oval(2, 2, 12, 12, fill=T.GREEN, outline="", tags="d"); self.dot.pack(side="left")
        self.title_lb = tk.Label(head, text="자동 출력 중", bg=T.CARD, fg=T.INK, font=T.f(12, True))
        self.title_lb.pack(side="left", padx=6)
        self.time_lb = tk.Label(head, text="", bg=T.CARD, fg=T.MUTED, font=T.f(9)); self.time_lb.pack(side="right")

        self.body = tk.Label(self, text="", bg=T.CARD, fg=T.INK, font=T.f(10), justify="left", anchor="w", wraplength=390)
        self.body.pack(fill="x", padx=16)
        self.pbar = ttk.Progressbar(self, length=388); self.pbar.pack(padx=16, pady=(8, 2), anchor="w")
        self.hint = tk.Label(self, text="", bg=T.CARD, fg=T.MUTED, font=T.f(9), justify="left", anchor="w", wraplength=390)
        self.hint.pack(fill="x", padx=16, pady=(4, 0))
        self.btns = tk.Frame(self, bg=T.CARD); self.btns.pack(side="bottom", fill="x", padx=16, pady=12)
        self.b_ok = ttk.Button(self.btns, text="확인", style="Accent.TButton", command=self.ok)
        self.b_ok.pack(side="right")
        self.b_reprint = ttk.Button(self.btns, text="이 묶음 다시 뽑기", command=self.reprint)
        self.b_stop = ttk.Button(self.btns, text="자동 출력 중지", style="Stop.TButton", command=self.stop)
        self.b_stop.pack(side="right", padx=6)
        self.stopping = False
        self.b_open = ttk.Button(self.btns, text="프로그램 열기", command=self.open_manager)
        self.b_open.pack(side="left")
        self.tick()

    # ------------------------------------------------------------
    def _dot(self, color):
        self.dot.itemconfigure("d", fill=color)

    def tick(self):
        st = read_status()
        started = str(st.get("started", ""))
        self.time_lb.configure(text=f"{started[5:10].replace('-', '/')} {started[11:16]}" if started else "")
        if not st.get("final"):
            self.show_running(st)
            self.after(700, self.tick)
        else:
            self.show_final(st)

    def show_running(self, st):
        self._dot(T.GREEN)
        phase = st.get("phase", "진행 중")
        self.title_lb.configure(text=f"자동 출력 중 · {phase}")
        lines = []
        if st.get("count"):
            lines.append(f"주문 {st['count']}건" + (f"  ({st['breakdown']})" if st.get("breakdown") else ""))
        if st.get("printer_progress"):
            lines.append(f"프린터: {st['printer_progress']}")
        if st.get("printer_issues"):
            lines.append("⚠ " + ", ".join(st["printer_issues"]))
        self.body.configure(text="\n".join(lines) or "카페24에서 새 주문을 확인하고 있습니다.")
        done, total = st.get("done", 0), st.get("total") or st.get("count") or 0
        if phase == "주문서 만드는 중" and total:
            self.pbar.configure(mode="determinate", maximum=total, value=done)
        else:
            self.pbar.configure(mode="indeterminate"); self.pbar.start(15)
        if not self.stopping:
            self.hint.configure(text="인쇄는 이 창과 상관없이 진행됩니다. 창을 닫아도 괜찮습니다.")
        # 자동 출력 프로그램이 도중에 사라졌는지
        if not pid_alive(st.get("pid")):
            self.dead_since = self.dead_since or dt.datetime.now()
            if (dt.datetime.now() - self.dead_since).seconds > 15:
                st.update(final=True, result="fail", phase="중간에 멈춤",
                          message="자동 출력이 끝까지 진행되지 않았습니다. 주문서 출력 관리 → 관리 탭 → 실행 기록을 확인해 주세요.")
                self.show_final(st)
                return
        else:
            self.dead_since = None

    def show_final(self, st):
        self.pbar.stop(); self.pbar.pack_forget()
        self.b_stop.pack_forget()
        res = st.get("result")
        slot = str(st.get("started", ""))[11:16]
        last = st.get("last") or {}
        if res == "none":
            self._dot(T.MUTED)
            self.title_lb.configure(text=f"{slot} 자동 출력 · 새 주문 없음")
            self.body.configure(text="새로 출력할 주문이 없어 인쇄하지 않았습니다.")
            self.hint.configure(text="")
        elif res in ("ok", "unknown"):
            self._dot(T.GREEN)
            self.title_lb.configure(text=f"✓ {slot} 자동 출력 완료")
            self.body.configure(text=f"주문 {st.get('count', 0)}건 · 주문서 {st.get('pages', '?')}장 + 출력 확인 용지 {st.get('end_pages', 1)}장\n"
                                     f"({st.get('breakdown', '')})\n마지막 주문: {last.get('order_id', '')}  {last.get('receiver') or last.get('buyer', '')}")
            self.hint.configure(text="프린터에서 맨 마지막 '출력 확인 용지'가 나왔는지 확인하세요. 나왔다면 모두 인쇄된 것입니다."
                                     + ("\n(이 프린터는 상태를 알려주지 않아 인쇄 완료를 직접 확인하지 못했습니다)" if res == "unknown" else ""))
        elif res == "problem":
            self._dot(T.RED)
            self.title_lb.configure(text=f"⚠ {slot} 자동 출력 확인 필요", fg=T.RED)
            issues = ", ".join(st.get("printer_issues") or [])
            self.body.configure(text=f"프린터 문제: {issues or '알 수 없음'}\n주문 {st.get('count', 0)}건 · {st.get('pages', '?')}장\n"
                                     f"{st.get('printer_note', '')}")
            self.hint.configure(text="종이를 채우거나 걸린 종이를 빼면 대부분 멈춘 곳부터 이어서 인쇄됩니다. "
                                     "'출력 확인 용지'가 끝내 안 나오면 [이 묶음 다시 뽑기]를 누르세요.")
            if st.get("pdf") and Path(st["pdf"]).exists():
                self.b_reprint.pack(side="right", padx=6)
        elif res == "stopped":
            self._dot(T.ORANGE)
            self.title_lb.configure(text=f"■ {slot} 자동 출력 중지됨", fg=T.ORANGE)
            n = st.get("count", 0)
            if st.get("sent"):
                self.body.configure(text=f"이미 프린터로 보낸 인쇄는 취소했습니다.\n이번 주문 {n}건은 '안 뽑음'으로 되돌려서 다음 출력에 다시 나옵니다.")
                self.hint.configure(text="프린터에서 이미 나온 몇 장은 다음 출력 때 한 번 더 나옵니다. 겹치는 종이는 버려 주세요. "
                                         "바로 다시 뽑으려면 [프로그램 열기] → 지금 출력.")
            else:
                self.body.configure(text=f"인쇄하기 전에 중지했습니다." + (f"\n이번 주문 {n}건은 다음 출력에 나옵니다." if n else ""))
                self.hint.configure(text="인쇄된 종이는 없습니다. 바로 뽑으려면 [프로그램 열기] → 지금 출력.")
        else:   # fail
            self._dot(T.RED)
            self.title_lb.configure(text=f"⚠ 자동 출력 실패", fg=T.RED)
            self.body.configure(text=str(st.get("message", ""))[:300])
            self.hint.configure(text="주문서 출력 관리를 열어 확인한 뒤 '지금 출력'으로 다시 뽑아 주세요.")
        self.geometry(f"{self.W}x{max(self.H, self.winfo_reqheight())}")

    # ------------------------------------------------------------
    def stop(self):
        from tkinter import messagebox
        if self.stopping:
            return
        if not messagebox.askyesno("자동 출력 중지", "자동 출력을 중지할까요?\n\n이번 묶음은 전부 '안 뽑음'으로 되돌려서 다음 출력에 다시 나옵니다.\n"
                                                 "이미 프린터에서 나온 몇 장은 다음에 한 번 더 나올 수 있어요.", parent=self):
            return
        self.stopping = True
        try:
            STOPFILE.write_text(dt.datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
        except Exception:
            pass
        self.b_stop.state(["disabled"])
        self.hint.configure(text="중지하는 중입니다... 잠시만 기다려 주세요.")

    def ok(self):
        st = read_status()
        if st.get("final"):
            st["acknowledged"] = dt.datetime.now().isoformat(timespec="seconds")
            try:
                STATUS.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
        self.destroy()

    def reprint(self):
        st = read_status()
        self.b_reprint.state(["disabled"])
        self.hint.configure(text="다시 인쇄를 보내는 중입니다...")

        def work():
            try:
                sys.path.insert(0, str(BASE))
                import order_print as op
                op.print_pdf(op.load_config(), st["pdf"])
                op.log.info(f"[결과 창] 자동 출력 묶음 다시 뽑기: {Path(st['pdf']).name}")
                msg = "다시 인쇄를 보냈습니다. '출력 확인 용지'까지 나오는지 확인하세요."
            except Exception as e:
                msg = f"다시 뽑기 실패: {e}"
            self.after(0, lambda: self.hint.configure(text=msg))
        threading.Thread(target=work, daemon=True).start()

    def open_manager(self):
        exe = Path(sys.executable)
        pyw = exe.with_name("pythonw.exe")
        subprocess.Popen([str(pyw if pyw.exists() else exe), str(BASE / "order_manager.py")], cwd=str(BASE))


if __name__ == "__main__":
    close_previous()
    try:
        Notice().mainloop()
    finally:
        try:
            if PIDFILE.read_text().strip() == str(os.getpid()):
                PIDFILE.unlink()
        except Exception:
            pass
