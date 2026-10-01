# -*- coding: utf-8 -*-
"""깃허브 저장소에서 새 버전을 확인하고 업데이트합니다.
- 저장소: awdjkk-ops/cafe24-order-print (공개). config.json의 "update_repo"로 바꿀 수 있음
- version.json 에 적힌 프로그램 파일만 받아서 교체합니다.
- config.json, settings.json, data 폴더 등 설정·인증·기록은 절대 건드리지 않습니다.
- 받은 파일을 모두 검사한 뒤에만 교체하고, 교체 전 파일은 backups 폴더에 보관합니다."""
import json
import py_compile
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
LOCAL_VERSION = BASE / "version.json"
BACKUP_DIR = BASE / "backups"
DEFAULT_REPO = "awdjkk-ops/cafe24-order-print"
BRANCH = "main"
# 이 이름들은 업데이트로 절대 덮어쓰지 않음
PROTECTED = {"config.json", "settings.json", "data", "pdf", "logs", "backups", "출력주문 엑셀파일", "택배발송 파일"}


class UpdateError(Exception):
    pass


def _ver(v):
    try:
        return tuple(int(x) for x in str(v).strip().lstrip("vV").split("."))
    except ValueError:
        return (0,)


def local_info():
    try:
        return json.loads(LOCAL_VERSION.read_text(encoding="utf-8"))
    except Exception:
        return {"version": "0.0.0", "files": []}


def repo_of(cfg):
    return (cfg or {}).get("update_repo") or DEFAULT_REPO


def _get(url, **kw):
    r = requests.get(url, timeout=20, headers={"User-Agent": "order-print-updater",
                                               "Accept": "application/vnd.github+json"}, **kw)
    if r.status_code == 404:
        raise UpdateError("깃허브 저장소나 파일을 찾을 수 없습니다 (저장소 이름·공개 여부 확인).")
    if r.status_code == 403 and "rate limit" in r.text.lower():
        raise UpdateError("깃허브 확인 횟수 제한에 걸렸습니다. 1시간 뒤 다시 시도해 주세요.")
    if r.status_code != 200:
        raise UpdateError(f"깃허브 응답 오류 {r.status_code}")
    return r


def check(cfg):
    """새 버전 확인. 돌려줌: None(최신) 또는 {"version", "notes", "sha", "info"}"""
    repo = repo_of(cfg)
    sha = _get(f"https://api.github.com/repos/{repo}/commits/{BRANCH}").json()["sha"]
    # 같은 순간의 파일들을 받기 위해 커밋 번호(sha)로 고정해서 받음
    info = _get(f"https://raw.githubusercontent.com/{repo}/{sha}/version.json").json()
    if _ver(info.get("version")) <= _ver(local_info().get("version")):
        return None
    return {"version": info.get("version"), "notes": info.get("notes", ""), "sha": sha, "info": info}


def _safe_name(name):
    p = Path(name)
    if p.is_absolute() or ".." in p.parts or not p.parts or p.parts[0] in PROTECTED:
        raise UpdateError(f"허용되지 않는 파일 이름: {name}")
    return p


def apply(cfg, upd, progress=None):
    """새 버전을 받아 검사 후 교체. 돌려줌: 설치한 버전"""
    repo, sha, info = repo_of(cfg), upd["sha"], upd["info"]
    files = [_safe_name(f) for f in info.get("files", [])] + [Path("version.json")]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # 1) 모두 받기
        for n, rel in enumerate(files, 1):
            r = _get(f"https://raw.githubusercontent.com/{repo}/{sha}/{rel.as_posix()}")
            if not r.content:
                raise UpdateError(f"빈 파일을 받았습니다: {rel}")
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp / rel).write_bytes(r.content)
            if progress:
                progress(n, len(files))
        # 2) 검사: 파이썬 파일이 깨지지 않았는지
        for rel in files:
            if rel.suffix == ".py":
                try:
                    py_compile.compile(str(tmp / rel), doraise=True)
                except py_compile.PyCompileError as e:
                    raise UpdateError(f"받은 파일에 오류가 있어 업데이트를 멈췄습니다: {rel}\n{e.msg[:200]}")
        # 3) 필요한 부품 설치
        pkgs = info.get("packages", [])
        if pkgs:
            r = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", *pkgs],
                               capture_output=True, text=True, creationflags=0x08000000 if sys.platform == "win32" else 0)
            if r.returncode != 0:
                raise UpdateError("필요한 부품 설치에 실패했습니다. 인터넷 연결을 확인해 주세요.\n" + r.stderr[-300:])
        # 4) 지금 파일 보관 → 교체
        old_ver = local_info().get("version", "0.0.0")
        bdir = BACKUP_DIR / f"{old_ver}_{time.strftime('%Y%m%d_%H%M%S')}"
        bdir.mkdir(parents=True, exist_ok=True)
        for rel in files:
            cur = BASE / rel
            if cur.exists():
                (bdir / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cur, bdir / rel)
        (bdir / "_files.json").write_text(json.dumps([r.as_posix() for r in files], ensure_ascii=False), encoding="utf-8")
        for rel in files:
            (BASE / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(tmp / rel, BASE / rel)
    _prune_backups()
    return info.get("version")


def backups():
    """되돌릴 수 있는 이전 버전 목록 (최신 먼저)"""
    if not BACKUP_DIR.exists():
        return []
    return sorted([d for d in BACKUP_DIR.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime, reverse=True)


def rollback():
    """가장 최근 보관본으로 되돌림. 돌려줌: 되돌린 버전"""
    bs = backups()
    if not bs:
        raise UpdateError("되돌릴 이전 버전이 없습니다.")
    b = bs[0]
    files = json.loads((b / "_files.json").read_text(encoding="utf-8"))
    for rel in files:
        src = b / rel
        if src.exists():
            shutil.copy2(src, BASE / _safe_name(rel) if rel != "version.json" else BASE / rel)
    shutil.rmtree(b, ignore_errors=True)
    return local_info().get("version")


def _prune_backups(keep=5):
    for d in backups()[keep:]:
        shutil.rmtree(d, ignore_errors=True)


def restart_manager():
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    subprocess.Popen([str(pyw if pyw.exists() else exe), str(BASE / "order_manager.py")], cwd=str(BASE))
