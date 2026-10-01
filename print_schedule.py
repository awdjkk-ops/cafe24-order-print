# -*- coding: utf-8 -*-
"""출력 일정 계산과 윈도우 작업 스케줄러 등록 (설정 창과 본 프로그램이 함께 사용)"""
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = BASE_DIR / "settings.json"

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
TASK_MAIN = "Cafe24OrderPrint"

SLOTS = ("am", "pm")
SLOT_NAMES = {"am": "오전", "pm": "오후"}

DEFAULT_SETTINGS = {
    "auto_enabled": False,          # 테스트 기간에는 꺼둠
    "power_mode": "sleep",          # "sleep" 또는 "rtc"
    "skip_public_holidays": True,
    "pdf_keep_days": 3,
    "weekdays": {                   # 0=월 ... 6=일, 요일마다 오전·오후
        str(i): {"am": {"on": i < 5, "time": "09:00"}, "pm": {"on": False, "time": "14:00"}} for i in range(7)
    },
    # 날짜 지정: 그날의 오전·오후를 통째로 정함. 둘 다 off면 쉬는 날
    # [{"date": "2026-10-15", "am": {"on": true, "time": "10:00"}, "pm": {"on": false, "time": "14:00"}}]
    "exceptions": [],
}


def _slot(v, on, time):
    return {"on": bool(v.get("on", on)) if isinstance(v, dict) else on,
            "time": (v.get("time") if isinstance(v, dict) else None) or time}


def _migrate_day(w):
    """예전 형식 {"on", "time"} → 새 형식 {"am", "pm"}"""
    if "am" in w or "pm" in w:
        return {"am": _slot(w.get("am") or {}, False, "09:00"), "pm": _slot(w.get("pm") or {}, False, "14:00")}
    return {"am": {"on": bool(w.get("on")), "time": w.get("time", "09:00")}, "pm": {"on": False, "time": "14:00"}}


def _migrate_exc(e):
    if "am" in e or "pm" in e:
        return {"date": e["date"], "am": _slot(e.get("am") or {}, False, "09:00"),
                "pm": _slot(e.get("pm") or {}, False, "14:00")}
    if e.get("type") == "off":
        return {"date": e["date"], "am": {"on": False, "time": "09:00"}, "pm": {"on": False, "time": "14:00"}}
    return {"date": e["date"], "am": {"on": True, "time": e.get("time", "09:00")}, "pm": {"on": False, "time": "14:00"}}


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            s = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        s = {}
    merged = json.loads(json.dumps(DEFAULT_SETTINGS))
    merged.update({k: v for k, v in s.items() if k not in ("weekdays", "exceptions")})
    for k, v in (s.get("weekdays") or {}).items():
        merged["weekdays"][k] = _migrate_day(v)
    merged["exceptions"] = [_migrate_exc(e) for e in s.get("exceptions", []) if e.get("date")]
    merged.setdefault("csv_keep_days", merged.get("pdf_keep_days", 3))   # 처음엔 PDF와 같은 기간
    return merged


def save_settings(s):
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SETTINGS_FILE)


def holiday_name(day):
    try:
        import holidays
        return holidays.KR(years=day.year).get(day)
    except ImportError:
        return None


def plan_for(day, s):
    """그날 출력 시각 목록(['09:00', '14:00'])과 설명. 출력 안 하는 날이면 ([], 이유)."""
    iso = day.isoformat()
    for e in s.get("exceptions", []):
        if e.get("date") == iso:
            times = sorted(e[k]["time"] for k in SLOTS if e[k]["on"])
            return times, ("날짜 지정" if times else "지정한 쉬는 날")
    if s.get("skip_public_holidays", True):
        name = holiday_name(day)
        if name:
            return [], f"공휴일({name})"
    w = s["weekdays"][str(day.weekday())]
    times = sorted(w[k]["time"] for k in SLOTS if w[k]["on"])
    if not times:
        return [], f"{WEEKDAYS[day.weekday()]}요일 출력 안 함"
    return times, f"{WEEKDAYS[day.weekday()]}요일 기본"


def upcoming(s, days=14, start=None):
    start = start or dt.date.today()
    return [(d, *plan_for(d, s)) for d in (start + dt.timedelta(days=i) for i in range(days))]


def earliest_time(s):
    times = [w[k]["time"] for w in s["weekdays"].values() for k in SLOTS if w[k]["on"]]
    times += [e[k]["time"] for e in s.get("exceptions", []) for k in SLOTS if e[k]["on"]]
    return min(times) if times else None


def times_text(times):
    return " · ".join(times) + " 출력" if times else ""


def valid_time(t):
    try:
        h, m = map(int, t.split(":"))
        return 0 <= h < 24 and 0 <= m < 60
    except Exception:
        return False


# ---------------------------------------------------------------- 작업 스케줄러
_PS_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _ps_time(t, date=None):
    """지역 설정과 상관없이 정확히 읽히도록 날짜/시각을 고정 형식으로 전달"""
    if date:
        return f"([datetime]::ParseExact('{date} {t}','yyyy-MM-dd HH:mm',$null))"
    return f"([datetime]::ParseExact('{t}','HH:mm',$null))"


def build_task_script(s):
    """작업 스케줄러 등록용 PowerShell 스크립트 (요일별 트리거 + 날짜 지정 트리거)"""
    d = str(BASE_DIR).replace("'", "''")
    lines = [
        "$ErrorActionPreference = 'Stop'",
        f"$dir = '{d}'",
        f"Unregister-ScheduledTask -TaskName '{TASK_MAIN}' -Confirm:$false -ErrorAction SilentlyContinue",
        "$startup = [Environment]::GetFolderPath('Startup')",
        "$bootLnk = Join-Path $startup 'Cafe24OrderPrint_BootCheck.lnk'",
        "if (Test-Path $bootLnk) { Remove-Item $bootLnk -Force }",
    ]
    if not s.get("auto_enabled"):
        lines.append("Write-Output 'AUTO_OFF'")
        return "\r\n".join(lines)

    trig = []
    for i in range(7):
        w = s["weekdays"][str(i)]
        for k in SLOTS:
            if w[k]["on"]:
                trig.append(f"New-ScheduledTaskTrigger -Weekly -DaysOfWeek {_PS_DAYS[i]} -At {_ps_time(w[k]['time'])}")
    today = dt.date.today()
    for e in s.get("exceptions", []):
        if dt.date.fromisoformat(e["date"]) >= today:
            for k in SLOTS:
                if e[k]["on"]:
                    trig.append(f"New-ScheduledTaskTrigger -Once -At {_ps_time(e[k]['time'], e['date'])}")
    if trig:
        lines.append("$triggers = @(" + ", ".join(f"({t})" for t in trig) + ")")
        lines += [
            # 검은 창 없이 실행 (pythonw). 없으면 bat 파일로
            "$pyw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source",
            "if ($pyw) { $action = New-ScheduledTaskAction -Execute $pyw -Argument ('\"' + (Join-Path $dir 'order_print.py') + '\" --auto') -WorkingDirectory $dir }",
            "else { $action = New-ScheduledTaskAction -Execute (Join-Path $dir 'auto_print.bat') -WorkingDirectory $dir }",
            "$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable "
            "-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)",
            f"Register-ScheduledTask -TaskName '{TASK_MAIN}' -Action $action -Trigger $triggers "
            "-Settings $settings -Description 'Cafe24 order sheet auto print' -Force | Out-Null",
        ]
    if s.get("power_mode") == "rtc":
        # RTC 방식: 로그인할 때 '오늘이 쉬는 날이면 종료' 검사 (시작프로그램 폴더 사용, 관리자 권한 불필요)
        lines += [
            "$ws = New-Object -ComObject WScript.Shell",
            "$l = $ws.CreateShortcut($bootLnk)",
            "$l.TargetPath = Join-Path $dir 'boot_check.bat'",
            "$l.WorkingDirectory = $dir",
            "$l.WindowStyle = 7",
            "$l.Save()",
        ]
    lines.append("Write-Output 'OK'")
    return "\r\n".join(lines)


def register_tasks(s):
    """설정을 작업 스케줄러에 반영. (성공여부, 메시지)"""
    if sys.platform != "win32":
        return True, "(윈도우가 아니라 작업 스케줄러 등록은 건너뜀)"
    ps1 = BASE_DIR / "data" / "register_tasks.ps1"
    ps1.parent.mkdir(exist_ok=True)
    ps1.write_text(build_task_script(s), encoding="utf-8-sig")  # BOM: 한글 경로 대응
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
                       capture_output=True, text=True, creationflags=0x08000000)  # 창 숨김
    if r.returncode != 0:
        return False, (r.stderr or r.stdout)[-800:]
    return True, "자동 출력 예약을 저장했습니다." if "OK" in r.stdout else "자동 출력을 껐습니다."
