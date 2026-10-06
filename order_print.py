# -*- coding: utf-8 -*-
"""
카페24 주문서 자동 출력 프로그램

  --auth      최초 인증 (처음 1번, 또는 인증 만료 시)
  --dump      데이터 확인: 주문 몇 건을 '고객정보를 가린 채' 파일로 저장
  --test      인쇄·기록 없이 주문서 PDF만 만들어서 열기
  --init      지금 배송준비중인 주문을 '출력 완료'로 표시 (운영 시작 직전 1번)
  --manual    지금 출력 (바탕화면 아이콘)
  --reprint   마지막 출력 다시 뽑기
  --auto      자동 출력 (작업 스케줄러가 실행)
  --boot      RTC 방식에서 PC가 켜질 때: 쉬는 날이면 종료
"""
import argparse
import base64
import datetime as dt
import json
import logging
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

import re

import requests

from netfix import prefer_ipv4

prefer_ipv4()          # IPv6 연결 대기(약 20초) 없이 바로 연결

import print_schedule as sch

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
DATA = BASE_DIR / "data"
TOKEN_FILE = DATA / "tokens.json"
PRINTED_FILE = DATA / "printed_orders.json"
STATE_FILE = DATA / "state.json"
LOCK_FILE = DATA / "running.lock"
IMG_DIR = DATA / "images"
PDF_DIR = BASE_DIR / "pdf"
CSV_DIR = BASE_DIR / "출력주문 엑셀파일"
COURIER_DIR = BASE_DIR / "택배발송 파일"
LOG_DIR = BASE_DIR / "logs"
for d in (DATA, IMG_DIR, PDF_DIR, LOG_DIR, CSV_DIR, COURIER_DIR):
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / f"{dt.date.today():%Y-%m}.log", encoding="utf-8")]
    + ([logging.StreamHandler(sys.stdout)] if sys.stdout else []))
log = logging.getLogger("order_print")


class AuthError(Exception):
    pass


class ConfigError(Exception):
    pass


HISTORY_FILE = DATA / "history.json"


# ---------------------------------------------------------------- 파일
def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        cfg = json.load(f)
    for key in ("mall_id", "client_id", "client_secret", "redirect_uri"):
        if not cfg.get(key) or "여기에" in str(cfg.get(key)):
            raise ConfigError(f"config.json 의 '{key}' 값을 먼저 입력해 주세요.")
    return cfg


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, data):
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ---------------------------------------------------------------- 인증
def api_base(cfg):
    return f"https://{cfg['mall_id']}.cafe24api.com/api/v2"


def request_token(cfg, form):
    url = f"{api_base(cfg)}/oauth/token"
    basic = base64.b64encode(f"{cfg['client_id']}:{cfg['client_secret']}".encode()).decode()
    r = requests.post(url, data=form, timeout=30, headers={
        "Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"})
    if r.status_code in (400, 401):
        r = requests.post(url, data=dict(form, client_id=cfg["client_id"], client_secret=cfg["client_secret"]),
                          timeout=30, headers={"Content-Type": "application/x-www-form-urlencoded"})
    if r.status_code != 200:
        raise AuthError(f"토큰 발급 실패 ({r.status_code}): {r.text[:300]}")
    return r.json()


def save_tokens(tok):
    write_json(TOKEN_FILE, {k: tok.get(k) for k in
                            ("access_token", "refresh_token", "expires_at", "refresh_token_expires_at", "scopes")}
               | {"saved_at": dt.datetime.now().isoformat(timespec="seconds")})


def _parse_time(v):
    try:
        return dt.datetime.fromisoformat(str(v)[:19])
    except Exception:
        return None


def get_access_token(cfg, force=False):
    """접속 토큰. 아직 10분 이상 유효하면 그대로 쓰고, 아니면 갱신(리프레시 토큰 수명도 연장됨)."""
    tok = read_json(TOKEN_FILE, None)
    if not tok:
        raise AuthError("저장된 인증 정보가 없습니다.")
    exp = _parse_time(tok.get("expires_at"))
    if not force and exp and exp - dt.datetime.now() > dt.timedelta(minutes=10):
        return tok["access_token"]
    new = request_token(cfg, {"grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
    save_tokens(new)
    return new["access_token"]


def token_status():
    """(상태, 설명) 상태: ok / warn / bad"""
    tok = read_json(TOKEN_FILE, None)
    if not tok:
        return "bad", "인증 전 (관리 탭에서 인증해 주세요)"
    rexp = _parse_time(tok.get("refresh_token_expires_at"))
    if not rexp:
        return "ok", "인증됨"
    days = (rexp - dt.datetime.now()).total_seconds() / 86400
    if days <= 0:
        return "bad", "인증 만료 (관리 탭에서 다시 인증해 주세요)"
    if days < 3:
        return "warn", f"인증 만료까지 {days:.0f}일 (PC가 켜지면 자동 연장)"
    return "ok", f"정상 (인증 {days:.0f}일 남음, 사용할 때마다 자동 연장)"


def auth_url(cfg):
    params = {"response_type": "code", "client_id": cfg["client_id"], "state": "orderprint",
              "redirect_uri": cfg["redirect_uri"], "scope": cfg.get("scope", "mall.read_order,mall.read_product")}
    return f"{api_base(cfg)}/oauth/authorize?{urlencode(params)}"


def finish_auth(cfg, pasted):
    pasted = pasted.strip()
    q = parse_qs(urlparse(pasted).query)
    if "error" in q:
        raise AuthError("승인이 거부되었습니다: " + q.get("error_description", q["error"])[0])
    code = q.get("code", [pasted])[0]
    save_tokens(request_token(cfg, {"grant_type": "authorization_code", "code": code,
                                    "redirect_uri": cfg["redirect_uri"]}))


def do_auth(cfg):
    print("\n브라우저가 열리면 쇼핑몰 대표운영자 계정으로 로그인하고 앱을 승인해 주세요.")
    print("승인 후 이동된 페이지의 '주소창 전체'를 복사해서 아래에 붙여넣고 Enter.")
    print("※ 인증 코드는 1분만 유효하니 바로 붙여넣어 주세요.\n")
    webbrowser.open(auth_url(cfg))
    finish_auth(cfg, input("주소 붙여넣기: "))
    print("\n인증 완료!")


# ---------------------------------------------------------------- 카페24 조회
def api_get(cfg, token, path, params):
    for attempt in range(4):
        r = requests.get(f"{api_base(cfg)}{path}", params=params, timeout=60,
                         headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        if r.status_code == 429:
            time.sleep(2 + attempt * 3)
            continue
        break
    if r.status_code == 401:
        raise AuthError("API 인증 실패(401)")
    if r.status_code != 200:
        raise RuntimeError(f"조회 실패 {path} ({r.status_code}): {r.text[:300]}")
    return r.json()


def fetch_orders(cfg, token, raw=False):
    """최근 N일 결제분 중 상품준비중·배송준비중 주문 (카페24·네이버페이·마켓 주문 모두)."""
    today = dt.date.today()
    start = today - dt.timedelta(days=int(cfg.get("lookback_days", 14)))
    statuses = cfg.get("order_status", ["N10", "N20"])
    orders, offset, limit = [], 0, 100
    while True:
        data = api_get(cfg, token, "/admin/orders", {
            "start_date": start.isoformat(), "end_date": today.isoformat(), "date_type": "pay_date",
            "order_status": ",".join(statuses), "embed": "items,receivers,buyer",
            "limit": limit, "offset": offset})
        batch = data.get("orders", [])
        orders.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
        time.sleep(0.4)
    # 나눠 받는 사이 새 주문이 들어오면 같은 주문이 두 번 올 수 있음 → 주문번호로 한 번만 남김
    uniq, seen = [], set()
    for o in orders:
        if o.get("order_id") not in seen:
            seen.add(o.get("order_id")); uniq.append(o)
    if len(uniq) != len(orders):
        log.info(f"같은 주문이 두 번 받아져 {len(orders) - len(uniq)}건을 뺐습니다.")
    orders = uniq
    if raw:
        return orders
    result = []
    for o in orders:
        if o.get("canceled") == "T":
            continue
        items = [i for i in (o.get("items") or []) if not i.get("order_status") or i.get("order_status") in statuses]
        if items:
            o["items"] = items
            result.append(o)
    result.sort(key=lambda o: (o.get("payment_date") or o.get("order_date") or "", o["order_id"]))
    return result


def _printable_items(o):
    """다시 뽑기용: 취소·반품된 품목만 빼고 모두"""
    return [i for i in (o.get("items") or []) if not str(i.get("order_status") or "").startswith(("C", "R"))]


BATCH = 100          # 한 번에 물어볼 주문 수


def _fetch_one(cfg, token, oid):
    try:
        return api_get(cfg, token, f"/admin/orders/{oid}", {"embed": "items,receivers,buyer"}).get("order")
    except RuntimeError as e:
        log.warning(f"주문 불러오기 실패({oid}): {e}")
        return None


def _fetch_batch(cfg, token, chunk):
    """주문번호 여러 개를 한 번에 물어봄. 돌려줌: {주문번호: 주문} (못 받은 건 빠짐)"""
    days = [dt.date(int(i[:4]), int(i[4:6]), int(i[6:8])) for i in chunk if i[:8].isdigit()]
    start = min(days) if days else dt.date.today() - dt.timedelta(days=60)
    data = api_get(cfg, token, "/admin/orders", {
        "order_id": ",".join(chunk), "embed": "items,receivers,buyer", "limit": len(chunk),
        "start_date": (start - dt.timedelta(days=1)).isoformat(), "end_date": dt.date.today().isoformat()})
    want = set(chunk)
    return {o["order_id"]: o for o in data.get("orders", []) if o.get("order_id") in want}


def _same_order(a, b):
    """묶음으로 받은 주문과 한 건씩 받은 주문이 같은지 (주문서·택배에 쓰는 값 기준)"""
    def key(o):
        rcv = (o.get("receivers") or [{}])[0] or {}
        buyer = o.get("buyer") or {}
        buyer = buyer[0] if isinstance(buyer, list) and buyer else buyer
        items = [(i.get("order_item_code"), i.get("product_name"), i.get("option_value"), str(i.get("quantity")),
                  str(i.get("product_price")), i.get("order_status")) for i in (o.get("items") or [])]
        return (o.get("order_id"), o.get("order_place_id"), str(o.get("payment_date")), o.get("canceled"),
                rcv.get("name"), rcv.get("zipcode"), rcv.get("address_full"), rcv.get("cellphone"), rcv.get("phone"),
                rcv.get("shipping_message"), buyer.get("name") if isinstance(buyer, dict) else None, sorted(items))
    return key(a) == key(b)


def _batch_usable(cfg, token, sample_batch):
    """묶음 방식이 믿을 만한지 한 번 비교해서 기억 (버전이 바뀌면 다시 비교)"""
    import updater
    ver = updater.local_info().get("version", "")
    st = read_json(STATE_FILE, {})
    chk = st.get("batch_check", {})
    if chk.get("version") == ver:
        return chk.get("ok", False)
    ok = False
    if sample_batch:
        oid, bo = next(iter(sample_batch.items()))
        so = _fetch_one(cfg, token, oid)
        ok = bool(so) and _same_order(bo, so)
        log.info(f"[빠른 불러오기] 묶음·한 건 비교 ({oid}): {'같음 → 묶음으로 불러옵니다' if ok else '다름 → 한 건씩 불러옵니다'}")
    st["batch_check"] = {"version": ver, "ok": ok, "time": dt.datetime.now().isoformat(timespec="seconds")}
    write_json(STATE_FILE, st)
    return ok


def fetch_orders_by_ids(cfg, token, ids, progress=None, excluded=None):
    """주문번호로 불러오기 (상태와 상관없이). 100건씩 묶어서 물어보고, 못 받은 건 한 건씩 다시.
    취소·반품된 품목은 빼고, 남은 품목이 없는 주문은 excluded 목록에 넣음. 순서는 ids 순서 그대로."""
    ids = list(dict.fromkeys(ids))          # 같은 주문번호는 한 번만
    got, done = {}, 0
    import updater
    chk = read_json(STATE_FILE, {}).get("batch_check", {})
    use_batch = not (chk.get("version") == updater.local_info().get("version", "") and chk.get("ok") is False)
    for k in range(0, len(ids), BATCH):
        chunk = ids[k:k + BATCH]
        if use_batch:
            try:
                part = _fetch_batch(cfg, token, chunk)
                if k == 0 and not _batch_usable(cfg, token, part):
                    use_batch = False
                    part = {}
                got.update(part)
            except Exception as e:
                log.warning(f"[빠른 불러오기] 묶음 요청 실패 → 한 건씩: {e}")
                use_batch = False
        for oid in chunk:                      # 묶음에서 못 받은 주문은 한 건씩
            if oid not in got:
                o = _fetch_one(cfg, token, oid)
                if o:
                    got[oid] = o
                time.sleep(0.1)
            done += 1
            if progress and (done % 10 == 0 or done == len(ids) or oid not in got):
                progress(done, len(ids))
    result = []
    for oid in ids:
        o = got.get(oid)
        if o and o.get("canceled") != "T":
            o["items"] = _printable_items(o)
            if o["items"]:
                result.append(o)
                continue
        if excluded is not None:
            excluded.append(oid)
    if progress:
        progress(len(ids), len(ids))
    return result


# ---------------------------------------------------------------- 카페24 '엑셀 바로 다운로드' 형식 CSV
CSV_HEADERS = ["쇼핑몰", "쇼핑몰번호", "주문번호", "발주일", "주문상품명", "상품번호", "옵션", "자체품목코드",
               "결제수단", "결제업체", "결제정보", "판매가", "수량", "수령인", "우편번호", "주소", "수령지전화",
               "전화번호", "핸드폰", "비고", "주문자", "주문자우편번호", "주문자주소", "주문자전화번호",
               "주문자핸드폰", "옵션추가 가격", "배송비 정보"]
SHOP_NAMES = {1: "한국어 쇼핑몰"}
PAY_METHODS = {"card": "신용카드", "cash": "현금결제", "tcash": "계좌이체", "icash": "가상계좌",
               "cell": "휴대폰", "deferpay": "후불", "point": "적립금", "mileage": "적립금",
               "credit": "선불금", "deposit": "선불금", "prepaid": "선불금", "etc": "기타"}
PAY_GATEWAYS = {"allat": "KG파이낸셜"}


def _s(v):
    return "" if v is None else str(v)


def _money(v):
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        return _s(v)
    return f"{f:.2f}"


def _nocomma(v):
    """카페24 엑셀은 쉼표를 공백으로 바꿈 (', ' → ' ', ',' → ' ')"""
    return re.sub(r", ?", " ", _s(v))


def _phone(v):
    """일반전화가 없으면 카페24 엑셀은 '02--'로 채움"""
    v = _s(v).strip()
    return v if v else "02--"


def _options_text(it):
    opts = it.get("options") or []
    parts = []
    for op_ in opts:
        val = op_.get("option_value") if isinstance(op_, dict) else None
        text = val.get("option_text") if isinstance(val, dict) else val
        if isinstance(op_, dict) and op_.get("option_name") is not None and text is not None:
            parts.append(f"{op_['option_name']}={_nocomma(text)}")
    if parts:
        return "; ".join(parts)
    return _nocomma(_s(it.get("option_value")).replace(", ", "; "))


def _balju_date(o):
    """발주일: 주문번호 날짜와 결제일 중 늦은 날"""
    oid = _s(o.get("order_id"))
    d1 = f"{oid[:4]}-{oid[4:6]}-{oid[6:8]}" if oid[:8].isdigit() else ""
    d2 = _s(o.get("payment_date") or o.get("order_date"))[:10]
    return max(d1, d2)


def order_csv_rows(o):
    """주문 1건 → CSV 줄 목록 (상품 1개당 1줄)"""
    buyer = o.get("buyer") or {}
    if isinstance(buyer, list):
        buyer = buyer[0] if buyer else {}
    rcv = (o.get("receivers") or [{}])[0] or {}
    methods = o.get("payment_method") or []
    methods = methods if isinstance(methods, list) else [methods]
    names = o.get("payment_method_name") or []
    names = names if isinstance(names, list) else [names]
    pay = next((PAY_METHODS[m] for m in methods if m in PAY_METHODS), None) or (names[0] if names else "")
    gws = o.get("payment_gateway_names") or []
    gws = gws if isinstance(gws, list) else [gws]
    gateway = next((PAY_GATEWAYS[g] for g in gws if g in PAY_GATEWAYS), "")
    amt = o.get("actual_order_amount") or {}
    ship_fee = float(amt.get("shipping_fee") or o.get("shipping_fee") or 0)
    pay_date = _balju_date(o)
    addr = _s(rcv.get("address_full")) or f"{_s(rcv.get('address1'))} {_s(rcv.get('address2'))}".strip()
    baddr = f"{_s(buyer.get('buyer_address1'))} {_s(buyer.get('buyer_address2'))}".strip()
    rows = []
    for it in o.get("items") or []:
        try:
            pno = int(it.get("product_no") or 0)
        except (TypeError, ValueError):
            pno = 0
        opt_price = float(it.get("option_price") or 0)
        rows.append([
            SHOP_NAMES.get(o.get("shop_no") or 1, ""), _s(o.get("shop_no") or 1), _s(o.get("order_id")), pay_date,
            _nocomma(it.get("product_name")), _s(pno if pno > 0 else it.get("product_code")), _options_text(it),
            _s(it.get("custom_product_code")), pay, gateway, "", _money(it.get("product_price")),
            _s(it.get("quantity")), _s(rcv.get("name")), _s(rcv.get("zipcode")), addr, "",
            _phone(rcv.get("phone")), _s(rcv.get("cellphone")), _nocomma(rcv.get("shipping_message")),
            _s(buyer.get("name")), _s(buyer.get("buyer_zipcode")), _nocomma(baddr), _phone(buyer.get("phone")),
            _s(buyer.get("cellphone")), _money(opt_price) if opt_price else "", "무료" if ship_fee == 0 else "선불",
        ])
    return rows


def write_csv(rows, path):
    import csv
    with open(path, "w", encoding="utf-8-sig", newline="") as f:   # BOM: 엑셀에서 열어도 한글 안 깨짐
        w = csv.writer(f)
        w.writerow(CSV_HEADERS)
        w.writerows(rows)


PRIVATE_COLS = {"수령인", "우편번호", "주소", "전화번호", "핸드폰", "비고", "주문자", "주문자우편번호",
                "주문자주소", "주문자전화번호", "주문자핸드폰"}


def _shape(v):
    """개인정보를 가리고 형식만 보이게: 한글→가, 숫자→9, 영문→a (공백·괄호·기호는 그대로)"""
    import re
    v = re.sub(r"[가-힣]", "가", v)
    v = re.sub(r"[0-9]", "9", v)
    return re.sub(r"[A-Za-z]", "a", v)


def compare_with_cafe24(cfg, token, original_csv, progress=None):
    """카페24 '엑셀 바로 다운로드' CSV와, 같은 주문번호로 프로그램이 만든 CSV를 칸별로 비교. (보고서 문자열, 저장 경로)"""
    import csv
    from collections import OrderedDict, defaultdict
    with open(original_csv, encoding="utf-8-sig") as f:
        orig = list(csv.reader(f))
    head, body = [h.strip() for h in orig[0]], orig[1:]
    lines = []
    if head != CSV_HEADERS:
        lines.append("※ 열 이름·순서가 다릅니다.")
        lines.append(f"   원본: {head}")
        lines.append(f"   프로그램: {CSV_HEADERS}")
    col = {h: i for i, h in enumerate(head)}
    by_order = OrderedDict()
    for r in body:
        if any(x.strip() for x in r):
            by_order.setdefault(r[col["주문번호"]], []).append(r)
    excluded = []
    orders = fetch_orders_by_ids(cfg, token, list(by_order), progress, excluded)
    mine = defaultdict(list)
    for o in orders:
        mine[o["order_id"]] = order_csv_rows(o)

    same, diff, examples = defaultdict(int), defaultdict(int), defaultdict(list)
    only_orig = only_mine = 0
    for oid, orows in by_order.items():
        mrows = mine.get(oid, [])
        if len(orows) != len(mrows):   # 품목 수가 다르면 상품번호+옵션으로 맞춰봄
            key = lambda r, c: (r[c["상품번호"]], r[c["옵션"]])
            mcol = {h: i for i, h in enumerate(CSV_HEADERS)}
            pool = list(mrows)
            pairs = []
            for r in orows:
                m = next((x for x in pool if key(x, mcol) == key(r, col)), None)
                if m is None:
                    only_orig += 1
                else:
                    pool.remove(m); pairs.append((r, m))
            only_mine += len(pool)
        else:
            pairs = list(zip(orows, mrows))
        for r, m in pairs:
            for h in CSV_HEADERS:
                if h not in col:
                    continue
                a, b = r[col[h]].strip(), m[CSV_HEADERS.index(h)].strip()
                if a == b:
                    same[h] += 1
                else:
                    diff[h] += 1
                    if len(examples[h]) < 3:
                        examples[h].append((oid, _shape(a) if h in PRIVATE_COLS else a,
                                            _shape(b) if h in PRIVATE_COLS else b))
    total_pairs = max((same[h] + diff[h] for h in CSV_HEADERS), default=0)
    lines.insert(0, f"비교한 원본: {Path(original_csv).name}")
    lines.insert(1, f"주문 {len(by_order)}건 / 원본 {len(body)}줄 → 비교한 줄 {total_pairs}줄")
    if excluded:
        lines.append(f"그사이 취소되어 빠진 주문: {len(excluded)}건 ({', '.join(excluded[:5])}{' …' if len(excluded) > 5 else ''})")
    if only_orig or only_mine:
        lines.append(f"짝이 맞지 않는 줄: 원본에만 {only_orig}줄 / 프로그램에만 {only_mine}줄 (취소된 상품 등)")
    ok = [h for h in CSV_HEADERS if diff[h] == 0]
    lines.append(f"\n완전히 같은 열: {len(ok)}개 / {len(CSV_HEADERS)}개")
    for h in CSV_HEADERS:
        if diff[h]:
            lines.append(f"\n[{h}] 다른 줄 {diff[h]}개 / 같은 줄 {same[h]}개" + ("  (개인정보라 형식만 표시)" if h in PRIVATE_COLS else ""))
            for oid, a, b in examples[h]:
                lines.append(f"   {oid}  원본: {a!r}")
                lines.append(f"   {' ' * len(oid)}  프로그램: {b!r}")
    report = "\n".join(lines)
    out = BASE_DIR / f"비교결과_{dt.datetime.now():%Y%m%d_%H%M}.txt"
    out.write_text(report, encoding="utf-8")
    log.info(f"[비교 검사] {out.name}")
    return report, out


PRINT_KINDS = ("자동", "수동", "선택 출력")   # 새로 인쇄한 것 (다시 뽑기·기준 조정은 제외)

# ---------------------------------------------------------------- 스마트스토어 따로 작업 (예: 주문 많은 월요일)
SMART = "shopn"
SPLIT_TODAY_FILE = DATA / "split_today.json"


def split_on(day=None):
    """오늘 '스마트스토어 따로 작업'이 켜져 있는지: 그날 스위치가 있으면 그걸, 없으면 요일 설정"""
    day = day or dt.date.today()
    t = read_json(SPLIT_TODAY_FILE, {})
    if t.get("date") == day.isoformat():
        return bool(t.get("on"))
    return bool(sch.load_settings().get("smart_split_weekdays", {}).get(str(day.weekday())))


def set_split_today(on):
    write_json(SPLIT_TODAY_FILE, {"date": dt.date.today().isoformat(), "on": bool(on)})


def _cust_key(o):
    import courier as C
    rcv = (o.get("receivers") or [{}])[0] or {}
    addr = rcv.get("address_full") or f"{rcv.get('address1') or ''} {rcv.get('address2') or ''}"
    return C.normalize_text(rcv.get("name")) + "||" + C.normalize_text(addr)


def split_orders(orders):
    """스마트스토어 쪽(스마트스토어 주문 + 그 고객의 다른 경로 주문)과 나머지로 나눔. 각각 원래 순서 유지."""
    smart_custs = {_cust_key(o) for o in orders if o.get("order_place_id") == SMART}
    smart = [o for o in orders if _cust_key(o) in smart_custs]
    rest = [o for o in orders if _cust_key(o) not in smart_custs]
    return smart, rest

# ---------------------------------------------------------------- 택배 발송용 파일
COURIER_DONE_FILE = DATA / "courier_done.json"
COURIER_HIST_FILE = DATA / "courier_history.json"


def courier_candidates():
    """출력한 주문 중 아직 택배 파일로 안 만든 주문 (뽑은 순서대로). [(주문요약, 출력한 때)]"""
    done = read_json(COURIER_DONE_FILE, {})
    done.update(read_json(COURIER_SKIP_FILE, {}))       # 대기에서 뺀 주문도 제외
    out, seen = [], set()
    for b in reversed(load_history()):
        if b["kind"] not in PRINT_KINDS + (COURIER_ADD_KIND,):
            continue
        for o in b["orders"]:
            if o["order_id"] not in seen and o["order_id"] not in done:
                seen.add(o["order_id"])
                out.append((o, b["time"][5:16].replace("T", " ")))
    return out


# ---------------------------------------------------------------- 검토용 라벨
def label_calibration():
    return {"offset_x": 0.0, "offset_y": 0.0, "scale_x": 0.0, "scale_y": 0.0,
            **sch.load_settings().get("label_cal", {})}


def _label_fonts(cfg):
    return cfg.get("font_path"), cfg.get("font_bold_path")


def make_labels(cfg, rows, used=None, kind="pdf", new_page_after_smart=False):
    """rows(카페24 엑셀 형식 줄) → 라벨 PDF(바로 인쇄용) 또는 엑셀. (경로, 라벨 칸 수, 장 수)"""
    import labels as L
    seq = L.build_sequence(rows)
    ykeys = L.yellow_keys(rows)
    pages = L.paginate(seq, used or {}, L.split_break(rows) if new_page_after_smart else None)
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    if kind == "xlsx":
        path = COURIER_DIR / f"라벨_{stamp}.xlsx"
        L.write_label_xlsx(pages, ykeys, path)
    else:
        path = PDF_DIR / f"라벨인쇄_{dt.datetime.now():%Y%m%d_%H%M%S}.pdf"
        L.write_label_pdf(pages, ykeys, path, label_calibration(), _label_fonts(cfg))
    log.info(f"[라벨] {Path(path).name}: {len(seq)}칸, {len(pages)}장")
    return path, len(seq), len(pages)


def print_calibration(cfg):
    import labels as L
    path = PDF_DIR / f"라벨맞춤확인_{dt.datetime.now():%Y%m%d_%H%M%S}.pdf"
    L.write_calibration_pdf(path, label_calibration(), _label_fonts(cfg))
    print_pdf(cfg, path, exact=True)


def _rows_with_place(orders, split_n=None):
    """카페24 엑셀 형식 줄 + 라벨용 정보(주문경로, 스마트스토어 쪽인지). 택배 파일에는 이 정보가 쓰이지 않음."""
    smart_ids = {o["order_id"] for o in split_orders(orders)[0]} if split_n is None else \
        {o["order_id"] for o in orders[:split_n]}
    out = []
    for o in orders:
        for r in order_csv_rows(o):
            d = dict(zip(CSV_HEADERS, r))
            d["_place"] = o.get("order_place_id") or ""
            d["_split"] = o["order_id"] in smart_ids if split_n is not None or split_on() else False
            out.append(d)
    return out


def rows_for_orders(cfg, token, ids, progress=None, split_n=0):
    """주문번호들 → 카페24 엑셀 형식 줄 (예전 택배 파일의 라벨을 다시 뽑을 때). 순서는 ids 순서 그대로."""
    orders = fetch_orders_by_ids(cfg, token, ids, progress)
    verify_orders(orders, "라벨 만들기")
    pos = {oid: i for i, oid in enumerate(ids)}
    orders.sort(key=lambda o: pos.get(o["order_id"], 10 ** 9))
    keep = set(ids[:split_n])
    smart_n = sum(1 for o in orders if o["order_id"] in keep)
    return _rows_with_place(orders, smart_n)


COURIER_ADD_KIND = "택배 대기 추가"     # 인쇄 없이 택배·라벨에만 넣은 주문 (카페24에서 직접 뽑은 경우 등)
COURIER_SKIP_FILE = DATA / "courier_skip.json"   # 사람이 택배 대기에서 뺀 주문 (택배·라벨에 넣기로 다시 넣을 수 있음)


def remove_from_courier_wait(ids):
    """택배 대기에서 뺌. 주문서 출력 기록(뽑음 표시)은 그대로."""
    skip = read_json(COURIER_SKIP_FILE, {})
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    for i in ids:
        skip[i] = stamp
    write_json(COURIER_SKIP_FILE, skip)
    log.info(f"[택배 대기 빼기] {len(ids)}건: " + ", ".join(list(ids)[:10]) + (" …" if len(ids) > 10 else ""))
    return len(ids)


def add_to_courier(orders, mark_printed=True):
    """주문 현황에서 고른 주문을 택배 대기에 넣음 (인쇄는 안 함).
    이미 택배 파일에 들어간 주문과 이미 대기 중인 주문은 뺌. 돌려줌: (넣은 건수, 빠진 이유별 주문번호)"""
    done = read_json(COURIER_DONE_FILE, {})
    waiting = {o["order_id"] for o, _ in courier_candidates()}
    skipped = {"이미 택배 파일에 들어감": [], "이미 택배 대기 중": []}
    targets = []
    for o in orders:
        oid = o["order_id"]
        if oid in done:
            skipped["이미 택배 파일에 들어감"].append(oid)
        elif oid in waiting:
            skipped["이미 택배 대기 중"].append(oid)
        else:
            targets.append(o)
    if targets:
        skip = read_json(COURIER_SKIP_FILE, {})
        if any(o["order_id"] in skip for o in targets):      # 대기에서 뺐던 주문을 다시 넣음
            for o in targets:
                skip.pop(o["order_id"], None)
            write_json(COURIER_SKIP_FILE, skip)
        add_history(COURIER_ADD_KIND, targets, "", 0)
        if mark_printed:
            printed = read_json(PRINTED_FILE, {})
            stamp = "택배추가 " + dt.datetime.now().isoformat(timespec="seconds")
            for o in targets:
                printed.setdefault(o["order_id"], stamp)
            write_json(PRINTED_FILE, printed)
    log.info(f"[택배 대기 추가] {len(targets)}건 (뽑음 표시: {'예' if mark_printed else '아니요'}) · "
             + ", ".join(f"{k} {len(v)}" for k, v in skipped.items() if v))
    return len(targets), skipped


def load_courier_history():
    return read_json(COURIER_HIST_FILE, [])


_SHEET_CACHE = {}          # {"list": (받은 시각, 결과), "listExtra": (...)} — 택배 탭을 열 때 미리 받아둠
SHEET_CACHE_SECONDS = {"list": 600, "listExtra": 60}   # 블랙리스트는 10분, 추가배송은 1분까지 미리 받은 것 사용


def prefetch_sheet(cfg):
    """블랙리스트·추가배송을 미리 받아둠 (택배 탭을 열 때). 실패해도 조용히 넘어감."""
    import courier as C
    url = cfg.get("sheet_api_url", "")
    if not url:
        return
    for action in ("list", "listExtra"):
        got = _SHEET_CACHE.get(action)
        if got and time.time() - got[0] < 60:
            continue
        try:
            _SHEET_CACHE[action] = (time.time(), C.sheet_call(url, action))
        except Exception as e:
            log.info(f"[구글 시트] 미리 받기 실패({action}): {e}")


def _sheet_cached(url, action):
    """10분 이내에 받아둔 게 있으면 그대로, 없으면 지금 받음"""
    import courier as C
    got = _SHEET_CACHE.get(action)
    if got and time.time() - got[0] < SHEET_CACHE_SECONDS.get(action, 60):
        return got[1]
    data = C.sheet_call(url, action)
    _SHEET_CACHE[action] = (time.time(), data)
    return data


def make_courier(cfg, token, ids, create=True, progress=None):
    """ids 주문으로 택배 파일 분석(create=False: 미리보기, 추가배송 안 지움) 또는 생성.
    돌려줌: {analysis, texts, popup, path, excluded, orders, rows, warnings}"""
    import courier as C
    url = cfg.get("sheet_api_url", "")
    warnings = []
    excluded = []
    from concurrent.futures import ThreadPoolExecutor
    pool = ThreadPoolExecutor(max_workers=2)
    t0 = time.time()
    f_black = pool.submit(_sheet_cached, url, "list") if url else None        # 구글 시트는 동시에 (미리 받은 게 있으면 그대로)
    f_extra = pool.submit(_sheet_cached, url, "listExtra") if url else None
    pool.shutdown(wait=False)
    orders = fetch_orders_by_ids(cfg, token, ids, progress, excluded)
    t_cafe = time.time() - t0
    verify_orders(orders, "택배 파일 만들기")
    split_n = 0
    if split_on():
        smart, rest = split_orders(orders)
        orders = smart + rest
        split_n = len(smart)
    rows = _rows_with_place(orders)

    blacklist = []
    if url:
        try:
            blacklist = f_black.result().get("items", [])
        except C.SheetError as e:
            if create:     # 실제 파일은 블랙리스트 확인 없이 만들지 않음
                raise C.SheetError(f"블랙리스트를 확인하지 못해 택배 파일을 만들지 않았습니다.\n{e}")
            warnings.append(f"블랙리스트 확인 실패: {e}")
    else:
        warnings.append("구글 시트 주소가 없어 블랙리스트·추가배송을 확인하지 않았습니다 (관리 탭에서 설정).")

    # 추가배송: 읽기만 하고, 택배 파일을 무사히 저장한 뒤에 한 건씩 지움 (응답이 끊겨도 사라지지 않게)
    extra = []
    if url:
        try:
            extra = f_extra.result().get("items", [])
        except C.SheetError as e:
            if create:
                raise C.SheetError(f"추가배송 목록을 확인하지 못해 택배 파일을 만들지 않았습니다.\n{e}")
            warnings.append(f"추가배송 확인 실패: {e}")

    t_sheet = time.time() - t0
    a = C.analyze(rows, extra, blacklist)
    result = {"analysis": a, "texts": C.summary_texts(a), "popup": C.popup_text(a), "path": None,
              "excluded": excluded, "orders": orders, "rows": rows, "warnings": warnings,
              "split_orders": split_n, "split_rows": sum(1 for r in rows if r.get("_split"))}
    if not create:
        return result

    path = COURIER_DIR / f"택배발송_{dt.datetime.now():%Y-%m-%d_%H%M}.xlsx"
    C.write_courier_xlsx(a, path)
    log.info(f"[택배 파일 시간] 카페24 {t_cafe:.1f}초 · 구글 시트까지 {t_sheet:.1f}초 · 파일 저장까지 {time.time() - t0:.1f}초"
             f" (주문 {len(ids)}건)")
    failed = []
    for it in extra:
        try:
            if it.get("id") in (None, ""):
                raise C.SheetError("번호 없음")
            C.sheet_call(url, "deleteExtra", id=it["id"])
            _SHEET_CACHE.pop("listExtra", None)           # 지웠으니 다음엔 새로 받음
        except C.SheetError as e:
            failed.append(it)
            log.error(f"추가배송 삭제 실패({it.get('name')}): {e}")
    if failed:
        write_json(DATA / f"추가배송_삭제실패_{dt.datetime.now():%Y%m%d_%H%M%S}.json", failed)
        warnings.append(f"택배 파일에는 넣었지만 구글 시트에서 지우지 못한 추가배송 {len(failed)}건: "
                        + ", ".join(str(it.get("name")) for it in failed)
                        + "\n→ 다음 택배 파일에 또 들어가지 않도록 [블랙리스트·추가배송] 탭에서 직접 삭제해 주세요.")
    now = dt.datetime.now().isoformat(timespec="seconds")
    done = read_json(COURIER_DONE_FILE, {})
    done.update({o["order_id"]: now for o in orders})
    done.update({oid: now + " 취소" for oid in excluded})     # 취소된 주문도 다시 대기에 안 나오게
    write_json(COURIER_DONE_FILE, done)
    hist = load_courier_history()
    hist.insert(0, {"time": now, "file": str(path), "orders": [o["order_id"] for o in orders], "split_orders": split_n,
                    "count": len(a["rows"]), "extra": len(a["extra"]), "texts": result["texts"],
                    "popup": result["popup"], "excluded": excluded})
    write_json(COURIER_HIST_FILE, hist[:60])
    log.info(f"[택배 파일] {path.name}: 주문 {len(orders)}건, 택배 {len(a['rows'])}줄 (추가배송 {len(a['extra'])}), "
             f"블랙리스트·경계 {len(a['blacklist'])}, 취소 제외 {len(excluded)}")
    result["path"] = path
    return result


def printed_ids_on(day):
    """그날 인쇄한 주문번호를 뽑은 순서대로 (중복 제거)"""
    ids = []
    for b in reversed(load_history()):           # 기록은 최신이 앞 → 뒤집어서 뽑은 순서대로
        if b["kind"] in PRINT_KINDS and b["time"][:10] == day.isoformat():
            for o in b["orders"]:
                if o["order_id"] not in ids:
                    ids.append(o["order_id"])
    return ids


def export_day_csv(cfg, token, day, progress=None):
    """그날 뽑은 주문 전체를 카페24 엑셀 형식 CSV 1개로. (경로, 주문 수, 줄 수, 제외된 주문번호)"""
    ids = printed_ids_on(day)
    if not ids:
        return None, 0, 0, []
    excluded = []
    orders = fetch_orders_by_ids(cfg, token, ids, progress, excluded)
    verify_orders(orders, "출력주문 엑셀 만들기")
    rows = [r for o in orders for r in order_csv_rows(o)]
    path = CSV_DIR / f"출력주문_{day.isoformat()}_{dt.datetime.now():%H%M}.csv"
    write_csv(rows, path)
    log.info(f"[엑셀] {path.name}: 주문 {len(orders)}건, {len(rows)}줄, 제외 {len(excluded)}건")
    return path, len(orders), len(rows), excluded


def search_cafe24(cfg, token, text):
    """주문번호 또는 주문자/수령자 이름으로 최근 3개월 주문 검색"""
    text = text.strip()
    if not text:
        return []
    if text[:8].isdigit() and "-" in text:
        try:
            return fetch_orders_by_ids(cfg, token, [text])
        except RuntimeError:
            return []
    today = dt.date.today()
    found = {}
    for field in ("buyer_name", "receiver_name"):
        data = api_get(cfg, token, "/admin/orders", {
            "start_date": (today - dt.timedelta(days=89)).isoformat(), "end_date": today.isoformat(),
            field: text, "embed": "items,receivers,buyer", "limit": 100})
        for o in data.get("orders", []):
            found[o["order_id"]] = o
    result = sorted(found.values(), key=lambda o: o.get("order_date") or "", reverse=True)
    for o in result:
        o["items"] = _printable_items(o)
    return result


_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
FAILED_IMG_FILE = IMG_DIR / "failed.json"


def _image_candidates(cfg, pr):
    """사진 주소 후보: 작은 사진 → 목록 사진 → 미니 → 상세, 각각 쇼핑몰 도메인과 카페24 도메인"""
    urls = []
    for k in ("small_image", "list_image", "tiny_image", "detail_image"):
        u = pr.get(k)
        if not u:
            continue
        if u.startswith("//"):
            u = "https:" + u
        urls.append(u)
        parts = urlparse(u)
        alt = f"{cfg['mall_id']}.cafe24.com"
        if parts.netloc and parts.netloc != alt:
            urls.append(parts._replace(netloc=alt).geturl())
    return list(dict.fromkeys(urls))


def _download_image(session, url):
    from PIL import Image as PILImage
    import io
    origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}/"
    r = session.get(url, timeout=20, headers={
        "User-Agent": _BROWSER_UA, "Referer": origin,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"})
    r.raise_for_status()
    im = PILImage.open(io.BytesIO(r.content)).convert("RGB")
    im.thumbnail((200, 200))
    return im


def fetch_images(cfg, token, orders):
    """상품번호별 사진 파일 경로. 사진이 없거나 끝내 실패하면 빠짐 → 주문서에서 빈칸."""
    def valid(no):   # 마켓 상품 중 카페24 상품과 연결 안 된 것은 번호가 -99999 등으로 옴 → 사진 없음
        try:
            return int(no) > 0
        except (TypeError, ValueError):
            return False
    nos = sorted({str(i.get("product_no")) for o in orders for i in o["items"] if valid(i.get("product_no"))})
    failed = read_json(FAILED_IMG_FILE, {})
    now = time.time()
    result, need = {}, []
    for no in nos:
        p = IMG_DIR / f"{no}.png"
        if p.exists() and now - p.stat().st_mtime < 30 * 86400:        # 받은 사진은 30일 보관
            result[no] = str(p)
        elif now - failed.get(no, 0) > 86400:                            # 실패한 사진은 하루 뒤 재시도
            need.append(no)

    session = requests.Session()
    ok_count = fail_count = 0
    for i in range(0, len(need), 100):
        chunk = need[i:i + 100]
        try:
            data = api_get(cfg, token, "/admin/products", {
                "product_no": ",".join(chunk),
                "fields": "product_no,tiny_image,small_image,list_image,detail_image", "limit": 100})
        except AuthError:
            raise
        except Exception as e:
            log.warning(f"상품 사진 정보 조회 실패(사진 없이 출력): {e}")
            break
        for pr in data.get("products", []):
            no = str(pr["product_no"])
            last_err = "사진 없음"
            for url in _image_candidates(cfg, pr):
                try:
                    im = _download_image(session, url)
                    p = IMG_DIR / f"{no}.png"
                    im.save(p)
                    result[no] = str(p)
                    failed.pop(no, None)
                    ok_count += 1
                    break
                except Exception as e:
                    last_err = str(e)[:120]
            else:
                failed[no] = now
                fail_count += 1
                log.warning(f"사진 내려받기 실패(상품 {no}): {last_err}")
    if need:
        log.info(f"상품 사진: 새로 받음 {ok_count}개, 실패 {fail_count}개, 보관분 사용 {len(result) - ok_count}개")
    write_json(FAILED_IMG_FILE, failed)
    return result


# ---------------------------------------------------------------- 데이터 확인(고객정보 가리기)
_SAFE_NAMES = {"product_name", "product_name_default", "option_name", "order_place_name", "payment_method_name",
               "payment_gateway_name", "payment_gateway_names", "carrier_name", "wished_carrier_name",
               "shipping_type_text", "status_text", "bank_code_name", "easypay_name", "supplier_name",
               "shipping_fee_type_text", "sub_payment_method_name", "social_name", "shipping_company_name",
               "option_value", "option_value_default", "additional_option_value", "product_bundle_name",
               "claim_reason_type", "claim_type", "tax_name", "country_name", "country_name_en"}
_PRIVATE_PARTS = ("phone", "cellphone", "email", "address", "zipcode", "member_id", "account_no",
                  "furigana", "shipping_message", "birthday", "street")
_PRIVATE_KEYS = {"ip", "ip_address", "user_ip", "city", "state", "city_en", "state_en", "name_en"}


def mask(obj, key=""):
    if isinstance(obj, dict):
        return {k: mask(v, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [mask(v, key) for v in obj]
    k = key.lower()
    private = (k == "name" or k in _PRIVATE_KEYS
               or (k.endswith("_name") or any(p in k for p in _PRIVATE_PARTS)) and k not in _SAFE_NAMES)
    if private and obj not in (None, "", 0):
        return f"●●●({len(str(obj))}자)"
    return obj


def dump(cfg, token):
    orders = fetch_orders(cfg, token, raw=True)
    # 주문경로가 다른 주문을 골고루 (카페24, 네이버페이, 쿠팡, 스마트스토어 ...)
    picked, seen = [], set()
    for o in orders:
        if o.get("order_place_id") not in seen:
            seen.add(o.get("order_place_id")); picked.append(o)
    for o in orders:
        if len(picked) >= 6:
            break
        if o not in picked and len(o.get("items") or []) > 1:
            picked.append(o)
    prod = {}
    try:
        nos = sorted({str(i.get("product_no")) for o in picked for i in (o.get("items") or []) if i.get("product_no")})[:20]
        if nos:
            prod = api_get(cfg, token, "/admin/products", {
                "product_no": ",".join(nos), "fields": "product_no,tiny_image,small_image,list_image", "limit": 100})
    except Exception as e:
        prod = {"error": str(e)}
    out = DATA.parent / f"데이터확인_{dt.datetime.now():%Y%m%d_%H%M}.json"
    write_json(out, {"설명": "고객 이름·연락처·주소 등은 ●●●로 가려져 있습니다.",
                     "전체_대상_주문수": len(orders),
                     "주문경로_종류": sorted({str(o.get('order_place_id')) for o in orders}),
                     "샘플_주문": mask(picked), "상품_사진_정보": prod})
    print(f"\n데이터 확인 파일을 만들었습니다: {out.name}")
    print("이 파일을 열어 ●●●로 가려졌는지 확인한 뒤 Claude에게 보여주세요.")


# ---------------------------------------------------------------- 인쇄
def find_sumatra(cfg):
    cands = [cfg.get("sumatra_path", ""), os.path.expandvars(r"%LOCALAPPDATA%\SumatraPDF\SumatraPDF.exe"),
             r"C:\Program Files\SumatraPDF\SumatraPDF.exe", r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe"]
    return next((c for c in cands if c and Path(c).exists()), None)


def print_pdf(cfg, path, exact=False):
    """exact=True: 라벨처럼 축소·확대 없이 실제 크기(100%)로 인쇄"""
    sumatra = find_sumatra(cfg)
    if sumatra and exact and cfg.get("label_print_dialog", True):
        # 라벨: 인쇄 창을 띄워서 프린터·트레이(뒷면)를 직접 고르고 인쇄
        try:
            subprocess.run([sumatra, "-print-dialog", "-exit-when-done", str(path)], timeout=1800)
        except subprocess.TimeoutExpired:
            log.warning("인쇄 창이 오래 열려 있어 닫았습니다.")
        log.info(f"인쇄 창으로 인쇄: {Path(path).name}")
        return
    if sumatra:
        printer = cfg.get("label_printer") if exact and cfg.get("label_printer") else cfg.get("printer_name")
        target = ["-print-to", printer] if printer else ["-print-to-default"]
        settings = ("noscale,portrait,paper=A4" if exact else "fit") + ",simplex"    # 항상 단면
        if exact and (cfg.get("label_tray_kind") or cfg.get("label_tray")):   # 라벨지를 넣는 트레이 (예: 뒷면 트레이)
            # 드라이버가 쓰는 트레이 번호가 있으면 번호로(더 확실), 없으면 이름으로 지정
            settings += f",bin={cfg.get('label_tray_kind') or cfg['label_tray']}"
        subprocess.run([sumatra, *target, "-print-settings", settings, "-silent", str(path)], check=True, timeout=900)
    elif sys.platform == "win32":
        log.warning("SumatraPDF가 없어 윈도우 기본 인쇄를 사용합니다.")
        os.startfile(str(path), "print")
        time.sleep(20)
    else:
        raise RuntimeError("인쇄 프로그램을 찾을 수 없습니다.")
    log.info(f"인쇄 전송: {Path(path).name}")


PLACE_NAMES = {"NCHECKOUT": "네이버페이", "shopn": "스마트스토어", "coupang": "쿠팡",
               "mobile": "모바일", "self": "PC", "cafe24": "PC"}


def order_brief(o):
    """출력 기록·검색 결과에 보여줄 요약 (고객 이름 포함, PC 안에만 저장)"""
    buyer = o.get("buyer") or {}
    if isinstance(buyer, list):
        buyer = buyer[0] if buyer else {}
    rcv = (o.get("receivers") or [{}])[0] or {}
    items = o.get("items") or []
    return {"order_id": o.get("order_id"), "place": PLACE_NAMES.get(o.get("order_place_id"), "기타"),
            "buyer": buyer.get("name") or o.get("buyer_name") or "",
            "receiver": rcv.get("name") or "",
            "pay_date": str(o.get("payment_date") or o.get("order_date") or "")[:16].replace("T", " "),
            "status": (items[0].get("status_text") if items else "") or "",
            "items": len(items)}


def load_history():
    return read_json(HISTORY_FILE, [])


def add_history(kind, orders, pdf, pages):
    h = load_history()
    h.insert(0, {"time": dt.datetime.now().isoformat(timespec="seconds"), "kind": kind,
                 "count": len(orders), "pages": pages, "pdf": str(pdf),
                 "orders": [order_brief(o) for o in orders]})
    write_json(HISTORY_FILE, h)


def last_regular_print():
    """자동·수동 출력 중 가장 최근 것 (어디까지 뽑았는지)"""
    return next((b for b in load_history() if b["kind"] in ("자동", "수동", "선택 출력", "기준 조정")), None)


def find_in_history(text):
    """출력 기록에서 주문번호·주문자·수령자로 찾기. [(주문요약, 출력한 때, 구분)]"""
    t = text.strip()
    out, seen = [], set()
    for b in load_history():
        for o in b["orders"]:
            if o["order_id"] in seen:
                continue
            if t and (t in (o["order_id"] or "") or t in (o["buyer"] or "") or t in (o["receiver"] or "")):
                seen.add(o["order_id"])
                out.append((o, b["time"][5:16].replace("T", " "), b["kind"]))
    return out


class Busy(Exception):
    pass


class OrderCheckError(Exception):
    """인쇄 전 검사에서 문제가 발견됨 → 인쇄·파일 만들기를 멈춤"""


def verify_orders(orders, what="인쇄"):
    """모든 상품이 그 주문의 상품인지(주문번호-품목번호), 주문이 중복되지 않는지, 받는 분 정보가 있는지 검사.
    문제가 하나라도 있으면 멈춤."""
    problems, seen = [], set()
    for o in orders:
        oid = str(o.get("order_id") or "")
        if not oid:
            problems.append("주문번호가 없는 주문이 있습니다")
            continue
        if oid in seen:
            problems.append(f"{oid}: 같은 주문이 두 번 들어 있습니다")
        seen.add(oid)
        items = o.get("items") or []
        if not items:
            problems.append(f"{oid}: 상품이 없습니다")
        for it in items:
            code = str(it.get("order_item_code") or "")
            if code and not code.startswith(oid + "-"):
                problems.append(f"{oid}: 다른 주문의 상품({code})이 섞여 있습니다")
            elif not code:
                log.warning(f"[검사] {oid}: 품목번호가 없는 상품이 있어 소속 확인을 건너뜀")
        rcv = (o.get("receivers") or [{}])[0] or {}
        if not str(rcv.get("name") or "").strip() or not str(rcv.get("address_full") or rcv.get("address1") or "").strip():
            problems.append(f"{oid}: 받는 분 이름 또는 주소가 비어 있습니다")
    if problems:
        log.error(f"[검사 실패] {what} 중단: " + " / ".join(problems[:20]))
        raise OrderCheckError(f"{what} 전 검사에서 문제가 발견되어 멈췄습니다. 카페24에서 해당 주문을 확인해 주세요.\n\n"
                              + "\n".join(problems[:15]) + ("\n…" if len(problems) > 15 else ""))
    log.info(f"[검사 통과] {what}: 주문 {len(orders)}건, 상품 {sum(len(o.get('items') or []) for o in orders)}개")


class run_lock:
    """동시에 두 번 출력되지 않도록 잠금.
    wait=초: 다른 작업(업데이트·지금 출력·택배 파일 등)이 끝날 때까지 기다림 (자동 출력용)"""
    def __init__(self, wait=0):
        self.wait = wait

    def __enter__(self):
        if another_running() and self.wait:
            log.info(f"[대기] 다른 작업이 진행 중이라 끝날 때까지 기다립니다 (최대 {self.wait // 60}분)")
            end = time.time() + self.wait
            while another_running() and time.time() < end:
                time.sleep(5)
            if not another_running():
                log.info("[대기] 다른 작업이 끝나서 이어서 진행합니다")
        if another_running():
            raise Busy("다른 출력 작업이 진행 중입니다. 끝난 뒤 다시 시도해 주세요.")
        LOCK_FILE.write_text(str(os.getpid()))
        return self

    def __exit__(self, *a):
        try:
            if LOCK_FILE.exists() and LOCK_FILE.read_text().strip() == str(os.getpid()):
                LOCK_FILE.unlink()
        except Exception:
            pass


UNDO_FILE = DATA / "undo_line.json"
REVERTED_FILE = DATA / "reverted.json"      # 사람이 '안 뽑음'으로 되돌린 주문 (다시 뽑히면 지워짐)


def load_reverted():
    return read_json(REVERTED_FILE, {})


def revert_printed(ids, recourier=False):
    """이미 뽑은 주문을 '안 뽑음'으로 되돌림 → 다음 출력에 다시 나옴.
    recourier=True면 택배 파일 기록도 지워서 다음 택배 파일에 다시 들어가게 함 (송장 중복 주의).
    되돌리기(undo)용으로 이전 상태를 저장."""
    printed = read_json(PRINTED_FILE, {})
    done = read_json(COURIER_DONE_FILE, {})
    reverted = load_reverted()
    write_json(UNDO_FILE, {"time": dt.datetime.now().isoformat(timespec="seconds"), "kind": "revert",
                           "before": {i: printed.get(i) for i in ids},
                           "courier_before": {i: done.get(i) for i in ids} if recourier else {},
                           "reverted_before": {i: reverted.get(i) for i in ids}})
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    for i in ids:
        printed.pop(i, None)
        reverted[i] = stamp + (" +택배" if recourier else "")
        if recourier:
            done.pop(i, None)
    write_json(PRINTED_FILE, printed)
    write_json(REVERTED_FILE, reverted)
    if recourier:
        write_json(COURIER_DONE_FILE, done)
    log.info(f"[되돌리기] {len(ids)}건을 안 뽑음으로 되돌림 (택배 파일 다시 넣기: {'예' if recourier else '아니요'}): "
             + ", ".join(ids[:10]))


def order_board(cfg, token):
    """지금 카페24의 대기 주문(상품준비중·배송준비중) 전체를 결제시각 순으로, 출력 여부와 함께.
    [(주문, 뽑았는지, 늦게 들어온 주문인지)]"""
    orders = fetch_orders(cfg, token)
    printed = read_json(PRINTED_FILE, {})
    reverted = load_reverted()
    last_printed_pay = max((str(o.get("payment_date") or "") for o in orders if o["order_id"] in printed), default="")
    rows = []
    for o in orders:
        done = o["order_id"] in printed
        late = (not done) and o["order_id"] not in reverted and str(o.get("payment_date") or "") < last_printed_pay
        rows.append((o, done, late))
    return rows


def set_printed_line(orders_above, orders_below):
    """'여기까지 뽑음' 선 옮기기: 위쪽은 뽑음, 아래쪽은 안 뽑음으로. 되돌리기용 이전 상태 저장."""
    printed = read_json(PRINTED_FILE, {})
    ids = [o["order_id"] for o in orders_above + orders_below]
    write_json(UNDO_FILE, {"time": dt.datetime.now().isoformat(timespec="seconds"),
                           "before": {i: printed.get(i) for i in ids}})
    stamp = "line " + dt.datetime.now().isoformat(timespec="seconds")
    for o in orders_above:
        printed.setdefault(o["order_id"], stamp)
    for o in orders_below:
        printed.pop(o["order_id"], None)
    write_json(PRINTED_FILE, printed)
    last = orders_above[-1] if orders_above else None
    add_history("기준 조정", [last] if last else [], "", 0)
    log.info(f"[기준 조정] 뽑음 {len(orders_above)}건 / 다음에 출력 {len(orders_below)}건")


def undo_line():
    u = read_json(UNDO_FILE, None)
    if not u:
        return False
    printed = read_json(PRINTED_FILE, {})
    for i, v in u["before"].items():
        if v is None:
            printed.pop(i, None)
        else:
            printed[i] = v
    write_json(PRINTED_FILE, printed)
    if u.get("courier_before"):
        done = read_json(COURIER_DONE_FILE, {})
        for i, v in u["courier_before"].items():
            if v is None:
                done.pop(i, None)
            else:
                done[i] = v
        write_json(COURIER_DONE_FILE, done)
    if "reverted_before" in u:
        rv = load_reverted()
        for i, v in u["reverted_before"].items():
            if v is None:
                rv.pop(i, None)
            else:
                rv[i] = v
        write_json(REVERTED_FILE, rv)
    UNDO_FILE.unlink(missing_ok=True)
    log.info("[기준 조정] 되돌리기")
    return u["time"]


def new_orders(cfg, token):
    printed = read_json(PRINTED_FILE, {})
    return [o for o in fetch_orders(cfg, token) if o["order_id"] not in printed]


LAST_END_PAGES = 0


def make_pdf(cfg, token, orders, prefix, progress=None, end_sheet=False, split=False, reverse=False):
    """주문서 PDF. split: 스마트스토어 쪽을 앞으로(출력 기록 순서도 이 순서).
    reverse: 인쇄할 때만 주문 순서를 거꾸로 — 주문서를 자르고 스테이플러로 찍어 옆에 쌓으면 다시 바른 순서가 됨.
    (한 주문 안의 장 순서는 그대로, 출력 기록·택배·라벨 순서는 그대로)"""
    verify_orders(orders, "주문서 만들기")
    sheet = setup_fonts(cfg)
    images = fetch_images(cfg, token, orders)
    if split:
        smart, rest = split_orders(orders)
        if smart and rest:
            orders[:] = smart + rest            # 스마트스토어 쪽을 맨 앞으로 (출력 기록도 이 순서)
    views = [sheet.to_view(o, images) for o in orders]
    if reverse:
        views = views[::-1]
    pdf = PDF_DIR / f"{prefix}_{dt.datetime.now():%Y%m%d_%H%M%S}.pdf"
    pages = sheet.build_orders_pdf(views, pdf, progress)
    global LAST_END_PAGES
    LAST_END_PAGES = 0
    log.info(f"PDF 생성: {pdf.name} ({len(orders)}건, {pages}장)")
    return pdf, pages


def print_orders(cfg, token, orders, kind, progress=None, record=True, end_sheet=False, stage=None, split=False):
    """주문서 만들기 → 인쇄 → (record면) 중복 방지 기록 → 출력 기록 추가"""
    verify_orders(orders, "주문서 인쇄")
    orders = list(orders)
    pdf, pages = make_pdf(cfg, token, orders, "주문서" if record else "다시뽑기", progress, False, split,
                          reverse=sch.load_settings().get("print_reverse", True))
    if stage:
        stage("인쇄 중", pdf=str(pdf), pages=pages)
    print_pdf(cfg, pdf)
    now = dt.datetime.now()
    if record:
        rv = load_reverted()
        if any(o["order_id"] in rv for o in orders):
            for o in orders:
                rv.pop(o["order_id"], None)
            write_json(REVERTED_FILE, rv)
        printed = read_json(PRINTED_FILE, {})
        stamp = now.isoformat(timespec="seconds")
        printed.update({o["order_id"]: printed.get(o["order_id"], stamp) for o in orders})
        write_json(PRINTED_FILE, printed)
    if kind in ("자동", "수동"):
        state = read_json(STATE_FILE, {})
        state["last_print"] = {"pdf": str(pdf), "time": now.strftime("%m/%d %H:%M"), "count": len(orders)}
        write_json(STATE_FILE, state)
    add_history(kind, orders, pdf, pages)
    return pdf, pages


# ---------------------------------------------------------------- 저장 공간 정리
def _files(folder, pattern="*"):
    return [p for p in Path(folder).glob(pattern) if p.is_file()]


def storage_usage():
    def size(files):
        return sum(p.stat().st_size for p in files)
    return {"주문서 PDF": (len(_files(PDF_DIR, "*.pdf")), size(_files(PDF_DIR, "*.pdf"))),
            "출력주문 엑셀": (len(_files(CSV_DIR, "*.csv")), size(_files(CSV_DIR, "*.csv"))),
            "택배·라벨 파일": (len(_files(COURIER_DIR, "*.xlsx")), size(_files(COURIER_DIR, "*.xlsx"))),
            "상품 사진": (len(_files(IMG_DIR, "*.png")), size(_files(IMG_DIR, "*.png"))),
            "실행 기록(로그)": (len(_files(LOG_DIR, "*.log")), size(_files(LOG_DIR, "*.log"))),
            "출력 기록": (len(load_history()), size([f for f in (HISTORY_FILE, PRINTED_FILE) if f.exists()]))}


def cleanup(settings=None):
    """보관 기간이 지난 파일·기록 삭제. 삭제한 개수를 돌려줌."""
    s = settings or sch.load_settings()
    now = time.time()
    keep_pdf = int(s.get("pdf_keep_days", 3)) * 86400
    removed = {"pdf": 0, "images": 0, "logs": 0, "history": 0, "printed": 0}
    for p in _files(PDF_DIR, "*.pdf"):
        if now - p.stat().st_mtime > keep_pdf:
            try:
                p.unlink(); removed["pdf"] += 1
            except OSError:
                pass
    keep_csv = int(s.get("csv_keep_days", s.get("pdf_keep_days", 3))) * 86400
    removed["csv"] = 0
    for p in _files(CSV_DIR, "*.csv") + _files(COURIER_DIR, "*.xlsx"):
        if now - p.stat().st_mtime > keep_csv:
            try:
                p.unlink(); removed["csv"] += 1
            except OSError:
                pass
    for p in _files(IMG_DIR, "*.png"):
        if now - p.stat().st_mtime > 60 * 86400:
            p.unlink(missing_ok=True); removed["images"] += 1
    for p in _files(LOG_DIR, "*.log"):
        if now - p.stat().st_mtime > 183 * 86400:
            p.unlink(missing_ok=True); removed["logs"] += 1
    cut = (dt.datetime.now() - dt.timedelta(days=30)).isoformat()
    h = load_history()
    h2 = [b for b in h if b["time"] >= cut]
    if len(h2) != len(h):
        removed["history"] = len(h) - len(h2)
        write_json(HISTORY_FILE, h2)
    printed = read_json(PRINTED_FILE, {})
    cut120 = (dt.datetime.now() - dt.timedelta(days=120)).isoformat()
    p2 = {k: v for k, v in printed.items() if v.replace("init ", "") >= cut120}
    if len(p2) != len(printed):
        removed["printed"] = len(printed) - len(p2)
        write_json(PRINTED_FILE, p2)
    return removed


def ask_yes(question):
    """Y를 입력해야만 진행. 그 외(엔터, N 등)는 모두 취소."""
    try:
        ans = input(f"\n{question} (Y/N): ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes", "ㅛ", "예", "네")


def _powershell(cmd):
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + cmd],
                       capture_output=True, timeout=30, creationflags=0x08000000)
    return r.stdout.decode("utf-8", "replace").strip()


def list_printers():
    """([프린터 이름...], 기본 프린터 이름)"""
    if sys.platform != "win32":
        return [], ""
    try:
        out = _powershell("Get-CimInstance Win32_Printer | Select-Object Name,Default | ConvertTo-Json -Compress")
        data = json.loads(out) if out else []
        if isinstance(data, dict):
            data = [data]
        names = [d["Name"] for d in data]
        default = next((d["Name"] for d in data if d.get("Default")), "")
        return names, default
    except Exception as e:
        log.warning(f"프린터 목록 확인 실패: {e}")
        return [], ""


def list_trays(printer=""):
    """프린터의 급지 트레이 이름 목록 (윈도우 프린터 드라이버가 알려주는 이름)"""
    if sys.platform != "win32":
        return []
    name = printer.replace("'", "''")
    cmd = ("Add-Type -AssemblyName System.Drawing; $p = New-Object System.Drawing.Printing.PrinterSettings; "
           + (f"$p.PrinterName = '{name}'; " if name else "")
           + "$p.PaperSources | ForEach-Object { \"$($_.RawKind)`t$($_.SourceName)\" }")
    try:
        out = _powershell(cmd)
        trays = []
        for line in out.splitlines():
            if "\t" in line:
                kind, nm = line.split("\t", 1)
                if nm.strip():
                    trays.append((nm.strip(), kind.strip()))
        return trays          # [(트레이 이름, 드라이버 번호)]
    except Exception as e:
        log.warning(f"트레이 목록 확인 실패: {e}")
        return []


def print_test_page(cfg):
    sheet = setup_fonts(cfg)
    p = PDF_DIR / f"프린터테스트_{dt.datetime.now():%Y%m%d_%H%M%S}.pdf"
    sheet.build_notice_pdf("프린터 테스트", "이 종이가 나왔다면 주문서 출력 프로그램과 프린터가 잘 연결된 것입니다.\n"
                           "A4 가로 방향으로, 글자가 잘리지 않고 나왔는지 확인해 주세요.", p)
    print_pdf(cfg, p)


def open_file(path):
    if sys.platform == "win32":
        os.startfile(str(path))


# ---------------------------------------------------------------- 실행
def setup_fonts(cfg):
    import order_sheet
    order_sheet.setup_fonts(cfg.get("font_path", r"C:\Windows\Fonts\malgun.ttf"),
                            cfg.get("font_bold_path", r"C:\Windows\Fonts\malgunbd.ttf"))
    return order_sheet


def uptime_minutes():
    if sys.platform != "win32":
        return 9999
    import ctypes
    return ctypes.windll.kernel32.GetTickCount64() / 60000


def run(cfg, mode):
    s = sch.load_settings()
    state = read_json(STATE_FILE, {})
    today = dt.date.today()
    now = dt.datetime.now()

    if mode == "boot":   # RTC 방식: 켜진 직후 쉬는 날이면 종료
        planned, why = sch.plan_for(today, s)
        if s.get("auto_enabled") and not planned and uptime_minutes() < 15:
            log.info(f"오늘은 쉬는 날({why})이라 2분 후 PC를 종료합니다.")
            try:
                get_access_token(cfg)   # 쉬는 날에도 인증 수명 연장
            except Exception as e:
                log.warning(f"인증 갱신 실패: {e}")
            if sys.platform == "win32":
                subprocess.run(["shutdown", "/s", "/t", "120", "/c",
                                f"오늘은 쉬는 날({why})이라 2분 후 종료합니다. 취소: Win+R → shutdown /a"])
        return

    if mode == "auto":
        if not s.get("auto_enabled"):
            log.info("자동 출력이 꺼져 있습니다(출력 설정에서 켤 수 있음).")
            return
        planned, why = sch.plan_for(today, s)
        if not planned:
            log.info(f"오늘은 쉬는 날({why})이라 자동 출력하지 않습니다.")
            try:
                get_access_token(cfg)
            except Exception as e:
                log.warning(f"인증 갱신 실패: {e}")
            return
        # 오전·오후 중 시각이 된(10분 전부터) 출력들
        due = [t for t in planned if now >= dt.datetime.combine(today, dt.time(*map(int, t.split(":"))))
               - dt.timedelta(minutes=10)]
        if not due:
            log.info(f"오늘 출력 시각은 {', '.join(planned)}이라 지금은 건너뜁니다.")
            return
        done = state.get("auto_done", {})
        done_slots = set(done.get("slots", [])) if done.get("date") == today.isoformat() else set()
        if set(due) <= done_slots:
            log.info(f"오늘 {', '.join(due)} 자동 출력은 이미 했습니다.")
            return
        auto_due = due

    if mode == "reprint":
        last = state.get("last_print")
        if not last or not Path(last["pdf"]).exists():
            print("\n다시 뽑을 출력 기록이 없습니다. (보관 기간이 지나 PDF가 정리되었을 수 있습니다)")
            return
        print(f"\n마지막 출력: {last['time']}, {last['count']}건")
        if not ask_yes("이 주문서를 다시 인쇄할까요?"):
            print("\n취소했습니다. 인쇄하지 않았습니다.")
            return
        print_pdf(cfg, last["pdf"])
        print(f"\n마지막 출력({last['time']}, {last['count']}건)을 다시 인쇄했습니다.")
        return

    token = get_access_token(cfg)
    if mode == "dump":
        dump(cfg, token)
        return

    if mode == "auto":
        AUTO_STOP_FILE.unlink(missing_ok=True)          # 예전 중지 요청은 지움
        auto_status(reset=True, pid=os.getpid(), started=now.isoformat(timespec="seconds"),
                    slot=", ".join(auto_due), phase="주문 확인 중", final=False)
        spawn_notifier()
    orders = new_orders(cfg, token)
    label = {"auto": "자동 출력", "manual": "수동 출력", "test": "테스트", "init": "표시"}[mode]
    log.info(f"[{label}] 새로 출력할 주문 {len(orders)}건")

    if mode == "init":
        printed = read_json(PRINTED_FILE, {})
        stamp = "init " + now.isoformat(timespec="seconds")
        printed.update({o["order_id"]: stamp for o in orders})
        write_json(PRINTED_FILE, printed)
        print(f"\n현재 주문 {len(orders)}건을 '출력 완료'로 표시했습니다. 다음 출력부터는 새 주문만 나옵니다.")
        return

    if mode == "auto" and stop_requested():
        AUTO_STOP_FILE.unlink(missing_ok=True)
        auto_status(phase="중지됨", final=True, result="stopped", sent=False, count=len(orders))
        log.info("[자동 출력 중지] 주문 확인 직후 중지")
        orders = []
        state = read_json(STATE_FILE, {})
        prev = state.get("auto_done", {})
        slots = set(prev.get("slots", [])) if prev.get("date") == today.isoformat() else set()
        state["auto_done"] = {"date": today.isoformat(), "slots": sorted(slots | set(auto_due))}
        write_json(STATE_FILE, state)
        return
    if not orders:
        if mode != "auto":
            print("\n새로 출력할 주문이 없습니다.")
        else:
            auto_status(phase="새 주문 없음", count=0, final=True, result="none")
    elif mode == "test":
        pdf, pages = make_pdf(cfg, token, orders, "미리보기")
        print(f"\n미리보기 PDF를 만들었습니다 (인쇄·기록 안 함): {pdf.name}  /  {len(orders)}건, {pages}장")
        open_file(pdf)
    else:
        if mode == "manual":
            from collections import Counter
            cnt = Counter(PLACE_NAMES.get(o.get("order_place_id"), "기타") for o in orders)
            print(f"\n새로 출력할 주문: {len(orders)}건  (" + ", ".join(f"{k} {v}" for k, v in cnt.most_common()) + ")")
            if not ask_yes(f"{len(orders)}건을 인쇄할까요?"):
                print("\n취소했습니다. 인쇄하지 않았고, 출력 기록도 바뀌지 않았습니다.")
                return
            print("\n주문서를 만드는 중입니다. 끝날 때까지 이 창을 닫지 마세요...")
        if mode == "auto":
            from collections import Counter
            cnt = Counter(PLACE_NAMES.get(o.get("order_place_id"), "기타") for o in orders)
            auto_status(phase="주문서 만드는 중", count=len(orders), done=0,
                        breakdown=", ".join(f"{k} {v}" for k, v in cnt.most_common()),
                        first=order_brief(orders[0]), last=order_brief(orders[-1]))
            def prog(d, t):
                check_stop()                                   # 주문서 만드는 중에도 중지 확인
                if d % 5 == 0 or d == t:
                    auto_status(done=d, total=t)

            def stage(phase, **kw):
                auto_status(phase=phase, **kw)
                if phase == "인쇄 중":
                    check_stop()                               # 프린터로 보내기 직전 마지막 확인
            sent = {"pdf": None}
            try:
                check_stop()
                orig_stage = stage

                def stage2(phase, **kw):
                    if phase == "인쇄 중":
                        sent["pdf"] = kw.get("pdf")
                    orig_stage(phase, **kw)
                pdf, pages = print_orders(cfg, token, orders, "자동", prog, end_sheet=True, stage=stage2,
                                          split=split_on(today))
                sent["pdf"] = str(pdf)
                sent["printed"] = True
                check_stop()
                w = watch_print_job(cfg, pdf, pages, stage)
                auto_status(phase="완료" if w["state"] != "problem" else "확인 필요", final=True,
                            result=w["state"], printer_issues=w["issues"], printer_note=w["note"],
                            pages=pages - LAST_END_PAGES, end_pages=LAST_END_PAGES, pdf=str(pdf))
            except AutoStopped:
                was_sent = bool(sent.get("printed"))
                if was_sent:
                    cancel_print_jobs(cfg, sent["pdf"])
                    rollback_batch(orders, sent["pdf"])
                auto_status(phase="중지됨", final=True, result="stopped", sent=was_sent, count=len(orders))
                log.info(f"[자동 출력 중지] {'인쇄 보낸 뒤' if was_sent else '인쇄 전'} 중지 · {len(orders)}건은 다음 출력에")
            finally:
                AUTO_STOP_FILE.unlink(missing_ok=True)
        else:
            prog = (lambda d, t: print(f"  {d}/{t}건") if d % 20 == 0 or d == t else None) if mode == "manual" else None
            pdf, pages = print_orders(cfg, token, orders, "수동", prog)
            if mode == "manual":
                print(f"\n{len(orders)}건 출력 완료! ({pages}장)")

    if mode == "auto":
        state = read_json(STATE_FILE, {})
        prev = state.get("auto_done", {})
        slots = set(prev.get("slots", [])) if prev.get("date") == today.isoformat() else set()
        state["auto_done"] = {"date": today.isoformat(), "slots": sorted(slots | set(auto_due))}
        write_json(STATE_FILE, state)
    try:
        cleanup(s)
    except Exception as e:
        log.warning(f"정리 중 오류: {e}")


# ---------------------------------------------------------------- 자동 출력 진행 상황 (결과 창이 읽음)
AUTO_STATUS_FILE = DATA / "auto_status.json"
AUTO_STOP_FILE = DATA / "auto_stop.flag"      # 결과 창에서 '자동 출력 중지'를 누르면 생김


class AutoStopped(Exception):
    """결과 창에서 사람이 자동 출력을 중지함"""


def stop_requested():
    return AUTO_STOP_FILE.exists()


def check_stop():
    if stop_requested():
        raise AutoStopped()


def cancel_print_jobs(cfg, pdf):
    """윈도우 인쇄 대기열에서 이번 주문서 인쇄를 취소 (이미 프린터로 넘어간 몇 장은 멈출 수 없음)"""
    if sys.platform != "win32":
        return False
    try:
        printer = cfg.get("printer_name") or list_printers()[1]
        name, stem = printer.replace("'", "''"), Path(pdf).stem.replace("'", "''")
        _powershell(f"Get-PrintJob -PrinterName '{name}' -ErrorAction SilentlyContinue | "
                    f"Where-Object {{ $_.DocumentName -like '*{stem}*' }} | Remove-PrintJob -ErrorAction SilentlyContinue")
        log.info(f"[자동 출력 중지] 인쇄 대기열에서 {Path(pdf).name} 취소")
        return True
    except Exception as e:
        log.warning(f"인쇄 취소 실패: {e}")
        return False


def rollback_batch(orders, pdf):
    """중지된 자동 출력 묶음을 통째로 '안 뽑음'으로 되돌림 (누락보다 중복이 안전)"""
    ids = {o["order_id"] for o in orders}
    printed = read_json(PRINTED_FILE, {})
    for i in ids:
        printed.pop(i, None)
    write_json(PRINTED_FILE, printed)
    h = load_history()
    for b in h:
        if b.get("pdf") == str(pdf) and b["kind"] == "자동":
            b["kind"] = "자동(중지)"         # 택배 대기·출력주문 엑셀에 들어가지 않음
            break
    write_json(HISTORY_FILE, h)
    log.info(f"[자동 출력 중지] {len(ids)}건을 안 뽑음으로 되돌림")


def auto_status(reset=False, **kw):
    st = {} if reset else read_json(AUTO_STATUS_FILE, {})
    st.update(kw)
    st["updated"] = dt.datetime.now().isoformat(timespec="seconds")
    try:
        write_json(AUTO_STATUS_FILE, st)
    except Exception as e:
        log.warning(f"진행 상황 기록 실패: {e}")


def spawn_notifier():
    """진행·결과 작은 창을 '따로' 띄움 → 창이 자동 출력을 절대 막지 않음"""
    try:
        exe = Path(sys.executable)
        pyw = exe.with_name("pythonw.exe")
        runner = str(pyw if pyw.exists() else exe)
        kw = {}
        if sys.platform == "win32":
            kw["creationflags"] = 0x00000008 | 0x00000200      # DETACHED_PROCESS | NEW_PROCESS_GROUP
        subprocess.Popen([runner, str(BASE_DIR / "notify.py")], cwd=str(BASE_DIR), close_fds=True, **kw)
    except Exception as e:
        log.warning(f"결과 창을 띄우지 못했습니다(인쇄에는 영향 없음): {e}")


_PRINTER_PROBLEMS = {"PaperOut": "용지 없음", "NoPaper": "용지 없음", "PaperJam": "용지 걸림", "PaperProblem": "용지 문제",
                     "Offline": "프린터 꺼짐·연결 끊김", "DoorOpen": "덮개 열림", "Error": "프린터 오류",
                     "UserIntervention": "프린터 확인 필요", "OutputBinFull": "출력함 가득 참", "NotAvailable": "프린터 사용 불가",
                     "OutOfMemory": "프린터 메모리 부족", "Blocked": "인쇄 막힘"}


def watch_print_job(cfg, pdf, pages, stage=None):
    """인쇄를 보낸 뒤 대기열과 프린터 상태를 지켜봄. 모든 프린터가 정확히 알려주지는 않으므로 참고용.
    돌려줌: {"state": ok/problem/unknown, "issues": [...], "note": str}"""
    if sys.platform != "win32":
        return {"state": "unknown", "issues": [], "note": "프린터 상태를 확인할 수 없는 환경"}
    printer = cfg.get("printer_name") or list_printers()[1]
    if not printer:
        return {"state": "unknown", "issues": [], "note": "기본 프린터를 찾지 못함"}
    name = printer.replace("'", "''")
    cmd = (f"$p=Get-Printer -Name '{name}' -ErrorAction SilentlyContinue; "
           f"$j=@(Get-PrintJob -PrinterName '{name}' -ErrorAction SilentlyContinue | Select-Object DocumentName,"
           "@{n='St';e={\"$($_.JobStatus)\"}},PagesPrinted,TotalPages); "
           "[pscustomobject]@{S=\"$($p.PrinterStatus)\"; J=$j} | ConvertTo-Json -Depth 3 -Compress")
    stem = Path(pdf).stem
    issues, gone_count, last_prog = [], 0, ""
    t_start = time.time()
    deadline = time.time() + min(max(180, pages * 10), 1500)
    while time.time() < deadline:
        check_stop()
        try:
            data = json.loads(_powershell(cmd) or "{}")
        except Exception:
            return {"state": "unknown", "issues": issues, "note": "프린터 상태를 읽지 못함"}
        pst = str(data.get("S") or "")
        jobs = data.get("J") or []
        jobs = jobs if isinstance(jobs, list) else [jobs]
        # 이번에 보낸 PDF와 이름이 같은 문서만 (예전에 남아 있는 다른 주문서 문서는 무시)
        mine = [j for j in jobs if stem in str(j.get("DocumentName") or "")]
        # '프린터로 보냄(Complete)'·'인쇄됨(Printed)'·'삭제됨'은 컴퓨터가 프린터에 다 넘겨준 것 → 끝난 것으로
        sent = [j for j in mine if any(k in str(j.get("St") or "") for k in ("Complete", "Printed", "Deleted"))]
        mine = [j for j in mine if j not in sent]
        for key, ko in _PRINTER_PROBLEMS.items():
            if key in pst or any(key in str(j.get("St") or "") for j in mine):
                if ko not in issues:
                    issues.append(ko)
                    log.warning(f"[프린터 감시] {ko} 감지 ({printer})")
        if mine:
            gone_count = 0
            j = mine[0]
            last_prog = f"{j.get('PagesPrinted') or 0}/{j.get('TotalPages') or '?'}장"
            if stage:
                stage("프린터 확인 중", printer_progress=last_prog, printer_issues=issues)
        else:
            gone_count += 1
            if gone_count >= 2 and not any(k in pst for k in _PRINTER_PROBLEMS):
                note = ("프린터로 모두 보냄" if sent else "인쇄 대기열을 모두 보냄") + \
                       (" (중간에 문제가 있었지만 이어서 인쇄됨)" if issues else "")
                log.info(f"[프린터 감시] 끝: {note} ({time.time() - t_start:.0f}초)")
                return {"state": "problem" if issues else "ok", "issues": issues, "note": note}
        time.sleep(5)
    log.warning(f"[프린터 감시] 시간 안에 끝나지 않음: 마지막 확인 {last_prog}, 프린터 상태 '{pst}'")
    return {"state": "problem", "issues": issues or ["인쇄가 끝나지 않음"],
            "note": f"시간 안에 인쇄가 끝나지 않았습니다 (마지막 확인 {last_prog})"}


def print_notice(cfg, message):
    try:
        sheet = setup_fonts(cfg)
        p = PDF_DIR / f"안내_{dt.datetime.now():%Y%m%d_%H%M%S}.pdf"
        sheet.build_notice_pdf("[확인 필요] 주문서 자동 출력 실패", message, p)
        print_pdf(cfg, p)
    except Exception as e:
        log.error(f"안내문 출력도 실패: {e}")


def _pid_alive(pid):
    if sys.platform == "win32":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return code.value == 259                        # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def another_running():
    """이전 실행이 아직 돌고 있으면 True. 창을 닫아 멈춘 경우엔 바로 False."""
    if not LOCK_FILE.exists():
        return False
    try:
        pid = int(LOCK_FILE.read_text().strip())
        if pid == os.getpid():
            return False
        return _pid_alive(pid)
    except Exception:
        return time.time() - LOCK_FILE.stat().st_mtime < 60   # 확인이 안 되면 1분 기준


def _auto_fail(msg):
    st = read_json(AUTO_STATUS_FILE, {})
    running_today = str(st.get("started", ""))[:10] == dt.date.today().isoformat() and not st.get("final")
    auto_status(reset=not running_today, pid=os.getpid(), phase="실패", final=True, result="fail", message=msg,
                started=st.get("started") if running_today else dt.datetime.now().isoformat(timespec="seconds"))
    if not running_today:
        spawn_notifier()


MODES = ("auth", "dump", "test", "init", "manual", "reprint", "auto", "boot")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    for m in MODES:
        g.add_argument(f"--{m}", action="store_true")
    mode = next(m for m in MODES if getattr(ap.parse_args(), m))
    try:
        cfg = load_config()
    except ConfigError as e:
        raise SystemExit(str(e))
    if mode == "auth":
        do_auth(cfg)
        return
    try:
        with run_lock(wait=600 if mode == "auto" else 0):      # 자동 출력은 최대 10분까지 기다렸다가 진행
            run(cfg, mode)
    except Busy as e:
        print("\n" + str(e))
        log.info(str(e))
        if mode == "auto":                                     # 10분이 지나도 안 끝나면 사람에게 알림
            msg = "자동 출력 시간에 다른 작업이 10분 넘게 진행 중이어서 자동 출력을 하지 못했습니다. '지금 출력'으로 뽑아 주세요."
            print_notice(cfg, msg)
            _auto_fail(msg)
    except AuthError as e:
        log.error(str(e))
        msg = ("카페24 인증이 만료되었거나 없습니다.\n\n"
               "조치: 바탕화면 '주문서 출력 관리' → 관리 탭 → '카페24 다시 인증하기'를 한 뒤, "
               "출력 탭에서 '지금 출력'을 눌러 주세요.\n\n"
               f"상세: {e}")
        if mode == "auto":
            print_notice(cfg, msg)
            _auto_fail(msg)
        print("\n" + msg)
    except Exception as e:
        log.exception("오류")
        msg = (f"주문서 출력 중 오류가 발생했습니다.\n\n상세: {e}\n\n"
               "잠시 후 '주문서 출력 관리'에서 '지금 출력'으로 다시 시도해 주세요. "
               "계속 실패하면 관리 탭 → '실행 기록 보기' 내용을 Claude에게 보여주세요.")
        if mode == "auto":
            print_notice(cfg, msg)
            _auto_fail(msg)
        print("\n" + msg)


if __name__ == "__main__":
    main()
