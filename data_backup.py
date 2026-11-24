# -*- coding: utf-8 -*-
"""전체 데이터 백업·되돌리기 (관리 탭)
- 백업: data 폴더(상품 사진 제외) + config.json + settings.json → zip 하나
- 되돌리기: 되돌리기 직전 상태를 data_backups 폴더에 자동 백업한 뒤 zip 내용으로 바꿈
  · 이미 뽑은 주문·택배 파일에 넣은 주문 기록은 합침 (옛 백업으로 되돌려도 다시 출력·중복 송장이 생기지 않게)
  · 카페24 인증(tokens.json)은 지금 PC에 있으면 그대로 둠 (옛 인증으로 바꾸면 연결이 끊길 수 있음)"""
import datetime as dt
import json
import shutil
import socket
import tempfile
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
AUTO_DIR = BASE / "data_backups"
INFO_NAME = "_backup_info.json"
LAST_FILE = DATA / "last_backup.json"
ROOT_FILES = ("config.json", "settings.json")
SKIP_DIRS = {"images"}                                       # 상품 사진: 크고, 다시 받아짐
SKIP_FILES = {"running.lock", "auto_stop.flag"}
KEEP_CURRENT = {"tokens.json", "running.lock", "auto_stop.flag", "auto_status.json", "last_backup.json"}
MERGE_FILES = {"printed_orders.json", "courier_done.json"}  # {주문번호: ...} — 지금 기록 + 백업 기록


class BackupError(Exception):
    pass


def _pc():
    try:
        return socket.gethostname() or ""
    except Exception:
        return ""


def _version():
    try:
        return json.loads((BASE / "version.json").read_text(encoding="utf-8")).get("version", "")
    except Exception:
        return ""


def _data_files():
    if not DATA.exists():
        return []
    out = []
    for p in DATA.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(DATA)
        if rel.parts[0] in SKIP_DIRS or p.name in SKIP_FILES or p.suffix == ".tmp":
            continue
        out.append(p)
    return out


def make_backup(path):
    """zip 만들기. 돌려줌: (경로, 파일 수)"""
    path = Path(path)
    files = _data_files()
    info = {"time": dt.datetime.now().isoformat(timespec="seconds"), "pc": _pc(), "version": _version()}
    tmp = path.with_name(path.name + ".tmp")
    n = 0
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(INFO_NAME, json.dumps(info, ensure_ascii=False, indent=2))
        for p in files:
            z.write(p, "data/" + p.relative_to(DATA).as_posix()); n += 1
        for name in ROOT_FILES:
            if (BASE / name).exists():
                z.write(BASE / name, name); n += 1
    tmp.replace(path)
    if path.parent.resolve() != AUTO_DIR.resolve():
        _save_last(info, path)
    return path, n


def _save_last(info, path):
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        LAST_FILE.write_text(json.dumps({**info, "file": str(path)}, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def last_backup():
    try:
        return json.loads(LAST_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_info(path):
    """백업 파일 확인. 돌려줌: 백업 정보 dict (+ files 개수)"""
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if INFO_NAME not in names:
                raise BackupError("이 프로그램에서 만든 데이터 백업 파일이 아닙니다.")
            info = json.loads(z.read(INFO_NAME).decode("utf-8"))
    except zipfile.BadZipFile:
        raise BackupError("압축 파일이 깨졌거나 zip 파일이 아닙니다.")
    for n in names:
        if n.startswith("/") or ".." in Path(n).parts or ":" in n:
            raise BackupError("백업 파일 안에 이상한 경로가 있어 멈췄습니다.")
    info["files"] = sum(1 for n in names if n != INFO_NAME and not n.endswith("/"))
    return info


def _merge(cur_path, bak_path):
    try:
        cur = json.loads(cur_path.read_text(encoding="utf-8"))
        bak = json.loads(bak_path.read_text(encoding="utf-8"))
    except Exception:
        return
    if isinstance(cur, dict) and isinstance(bak, dict):
        bak.update(cur)
        bak_path.write_text(json.dumps(bak, ensure_ascii=False, indent=2), encoding="utf-8")


def restore(path):
    """zip 내용으로 되돌림. 돌려줌: (자동 백업 경로, 백업 정보)"""
    info = read_info(path)
    AUTO_DIR.mkdir(parents=True, exist_ok=True)
    auto = AUTO_DIR / f"되돌리기전_자동백업_{dt.datetime.now():%Y%m%d_%H%M%S}.zip"
    make_backup(auto)
    for old in sorted(AUTO_DIR.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)[5:]:
        try:
            old.unlink()
        except OSError:
            pass
    with tempfile.TemporaryDirectory(dir=str(BASE)) as td:
        td = Path(td)
        with zipfile.ZipFile(path) as z:
            z.extractall(td)
        new_data = td / "data"
        new_data.mkdir(exist_ok=True)
        for name in KEEP_CURRENT:                         # 지금 PC 것을 그대로 쓸 파일
            if (DATA / name).exists():
                shutil.copy2(DATA / name, new_data / name)
        for name in MERGE_FILES:
            if (DATA / name).exists():
                if (new_data / name).exists():
                    _merge(DATA / name, new_data / name)
                else:
                    shutil.copy2(DATA / name, new_data / name)
        # data 폴더 바꾸기 (상품 사진 폴더는 그대로)
        DATA.mkdir(parents=True, exist_ok=True)
        for p in list(DATA.iterdir()):
            if p.name in SKIP_DIRS:
                continue
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    p.unlink()
                except OSError:
                    pass
        for p in new_data.iterdir():
            if p.name in SKIP_DIRS:
                continue
            dst = DATA / p.name
            if p.is_dir():
                shutil.copytree(p, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(p, dst)
        for name in ROOT_FILES:
            if (td / name).exists():
                shutil.copy2(td / name, BASE / name)
    return auto, info
