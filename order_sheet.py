# -*- coding: utf-8 -*-
"""카페24 '주문상세정보' 스타일 주문서 PDF. A4 가로 1장에 같은 주문서 2부."""
import datetime as dt
import io
from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter, Transformation, PageObject
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, Image, KeepTogether, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

SHEET_W, SHEET_H = landscape(A4)
HALF_W, HALF_H = SHEET_W / 2, SHEET_H
M = 9 * mm
CW = HALF_W - 2 * M
IMG = 7.5 * mm

GRID = colors.HexColor("#9A9A9A")
LABEL_BG = colors.HexColor("#F2F2F2")
BLUE = "#2F6FD6"

# 주문경로 아이콘 (카페24 관리자 화면과 같은 모양): 글자, 색, 모양(fill=꽉 찬 네모, line=테두리 네모, circle=동그라미)
ICONS = {
    "NCHECKOUT": ("N", "#03C75A", "fill"),     # 네이버페이
    "shopn": ("S", "#19B55A", "line"),         # 스마트스토어
    "coupang": ("C", "#E4432D", "circle"),     # 쿠팡
    "mobile": ("M", "#E0342B", "line"),        # 모바일
    "self": ("24", "#2B6FD6", "fill"),         # PC쇼핑몰
    "cafe24": ("24", "#2B6FD6", "fill"),
}
ICON_DIR = Path(__file__).resolve().parent / "data" / "icons"
_BOLD_PATH = None


def icon_img(key, size=8.2):
    """아이콘 PNG를 만들어 두고 문단에 넣을 <img> 태그를 돌려줌"""
    if key not in ICONS:
        return ""
    from PIL import Image as PImg, ImageDraw, ImageFont
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    path = ICON_DIR / f"{key}.png"
    if not path.exists():
        txt, color, shape = ICONS[key]
        n = 96
        im = PImg.new("RGBA", (n, n), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if shape == "circle":
            d.ellipse([2, 2, n - 3, n - 3], fill=color); fg = "white"
        elif shape == "fill":
            d.rounded_rectangle([2, 2, n - 3, n - 3], radius=10, fill=color); fg = "white"
        else:
            d.rounded_rectangle([4, 4, n - 5, n - 5], radius=10, fill="white", outline=color, width=8); fg = color
        font = ImageFont.truetype(_BOLD_PATH, 58 if len(txt) == 1 else 44)
        d.text((n / 2, n / 2 + 2), txt, font=font, fill=fg, anchor="mm")
        im.save(path)
    return f'<img src="{path}" width="{size}" height="{size}" valign="-1.6"/>'


STATUS = {"N00": "입금전", "N10": "상품준비중", "N20": "배송준비중", "N21": "배송대기",
          "N22": "배송보류", "N30": "배송중", "N40": "배송완료"}
PAID = {"T": "결제완료", "A": "결제완료", "P": "결제완료", "F": "입금전", "M": "추가입금대기"}

_fonts_ready = False


_MAIN_CHARS = set()
_FB_CHARS = set()
FALLBACK_FONTS = [r"C:\Windows\Fonts\seguisym.ttf", r"C:\Windows\Fonts\malgun.ttf",
                  r"C:\Windows\Fonts\gulim.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def setup_fonts(regular, bold):
    global _fonts_ready, _BOLD_PATH, _MAIN_CHARS, _FB_CHARS
    _BOLD_PATH = bold
    if not _fonts_ready:
        pdfmetrics.registerFont(TTFont("KR", regular))
        pdfmetrics.registerFont(TTFont("KRB", bold))
        _MAIN_CHARS = set(pdfmetrics.getFont("KR").face.charToGlyph) & set(pdfmetrics.getFont("KRB").face.charToGlyph)
        for fb in FALLBACK_FONTS:   # 기본 글꼴에 없는 기호(①② 등)를 대신 찍을 글꼴
            if fb != regular and Path(fb).exists():
                try:
                    pdfmetrics.registerFont(TTFont("FB", fb))
                    _FB_CHARS = set(pdfmetrics.getFont("FB").face.charToGlyph)
                    break
                except Exception:
                    continue
        _fonts_ready = True


def _st(n, f="KR", s=6.3, **k):
    return ParagraphStyle(n, fontName=f, fontSize=s, leading=s * 1.25, **k)


S = _st("n"); S_C = _st("c", alignment=1); S_R = _st("r", alignment=2)
S_TITLE = _st("t", "KRB", 11); S_H = _st("h", "KRB", 8.2); S_BIG = _st("big", "KRB", 7)

QTY_COL_W = 7 * mm          # 수량 칸 폭 (양식 그대로)
QTY_EMPH = 8.3              # 2개 이상 주문한 상품의 수량 글자 크기 (기본 6.3 + 2pt, 굵게)


NAME_COL_W = 61 * mm                    # 상품명/옵션 칸 폭
BLANK_COL_W = 15 * mm                   # 수량과 판매가 사이 빈칸 (펜으로 체크)
STATUS_COL_W = 13 * mm                  # 주문상태 칸 폭
NAME_PAD = 2 * mm                       # 상품명 글자와 칸 테두리 사이 — 좌우
NAME_PAD_V = 1.5 * mm                   # 상품명 글자와 칸 테두리 사이 — 위아래                       # 상품명 글자와 칸 테두리 사이 (굵은 펜으로 칸을 체크해도 글자가 안 가려지게)
MARKER = colors.HexColor("#FFF29A")    # 형광펜 (연한 노랑)
MARKER_H = 5.1 * mm                     # 형광펜 굵기


class _Marker(Flowable):
    """상품명 칸: 형광펜 한 줄을 상품명 시작부터 옆 수량 숫자까지 이어서 긋고, 그 위에 글자를 씀.
    색만 칠하므로 칸 크기·줄 높이는 그대로."""

    def __init__(self, para, qty_text, qty_size):
        super().__init__()
        self.para, self.qty_text, self.qty_size = para, qty_text, qty_size

    def wrap(self, aw, ah):
        self.aw = aw
        self.w, self.h = self.para.wrap(aw, ah)
        return self.w, self.h

    def draw(self):
        from reportlab.pdfbase.pdfmetrics import stringWidth
        c = self.canv
        num_w = stringWidth(self.qty_text, "KRB", self.qty_size)
        # 이 칸 오른쪽 여백 + 수량 칸 왼쪽 여백(2) + 수량 칸 가운데까지 + 숫자 절반 + 여유
        extend = NAME_PAD + 2 + (QTY_COL_W - 4) / 2 + num_w / 2 + 1.5
        y = (self.h - MARKER_H) / 2
        c.saveState()
        c.setFillColor(MARKER)
        c.rect(-1, y, self.aw + 1 + extend, MARKER_H, stroke=0, fill=1)
        c.restoreState()
        self.para.drawOn(c, 0, 0)


def qty_size(q):
    """수량 글자 크기 (2개 이상이면 크게, 칸에 맞게)"""
    if q < 2:
        return 6.3
    from reportlab.pdfbase.pdfmetrics import stringWidth
    room = QTY_COL_W - 4 - 0.5
    size = QTY_EMPH
    while size > 6.3 and stringWidth(str(q), "KRB", size) > room:
        size -= 0.2
    return size


def qty_para(q):
    """수량 칸: 2개 이상이면 굵고 크게. 칸을 넘지 않도록 필요하면 그 칸에 맞는 크기까지만."""
    if q < 2:
        return P(str(q), S_C)
    from reportlab.pdfbase.pdfmetrics import stringWidth
    room = QTY_COL_W - 4 - 0.5            # 좌우 여백 2pt씩 빼고 약간의 여유
    size = QTY_EMPH
    while size > 6.3 and stringWidth(str(q), "KRB", size) > room:
        size -= 0.2
    return P(str(q), ParagraphStyle(f"qty{size:.1f}", fontName="KRB", fontSize=size, leading=6.3 * 1.25,
                                    alignment=1))


def P(t, s=S):
    return Paragraph(t, s)


def _safe_char(ch):
    if not _MAIN_CHARS or ord(ch) < 128 or ord(ch) in _MAIN_CHARS or ch in "\n\r\t":
        return escape(ch)
    if ord(ch) in _FB_CHARS:
        return f'<font name="FB">{escape(ch)}</font>'
    if 0x2460 <= ord(ch) <= 0x2473:          # ①~⑳ → (1)~(20)
        return f"({ord(ch) - 0x245F})"
    if 0x2776 <= ord(ch) <= 0x277F:          # ❶~❿
        return f"({ord(ch) - 0x2775})"
    return escape(ch)


def E(t):
    """글자를 PDF용으로 변환. 글꼴에 없는 기호도 빈칸이 되지 않게 처리."""
    return "".join(_safe_char(c) for c in str(t if t is not None else "")).replace("\n", "<br/>")


def won(v):
    try:
        return f"{int(round(float(v or 0))):,}"
    except (TypeError, ValueError):
        return str(v)


def dtext(v, n=19):
    return (str(v or "")[:n]).replace("T", " ")


# ---------------------------------------------------------------- 카페24 데이터 → 주문서 항목
def _first(*vals):
    for v in vals:
        if v not in (None, "", [], {}):
            return v
    return None


def _amount(o, key):
    for src in (o.get("actual_order_amount"), o.get("initial_order_amount"), o):
        if isinstance(src, dict) and src.get(key) not in (None, ""):
            return src.get(key)
    return 0


def _join(v):
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v if x)
    return v or ""


def _market_no(o):
    v = _first(o.get("market_order_no"), o.get("market_order_info"))
    if isinstance(v, list):
        v = ", ".join(str(x.get("market_order_no", x)) if isinstance(x, dict) else str(x) for x in v)
    elif isinstance(v, dict):
        v = v.get("market_order_no") or ""
    return v or ""


def _option_text(it):
    opts = []
    for op in it.get("options") or []:
        val = (op.get("option_value") or {}) if isinstance(op, dict) else {}
        text = val.get("option_text") if isinstance(val, dict) else val
        if op.get("option_name") and text:
            opts.append(f"{op['option_name']} : {text}")
    if not opts:
        raw = _first(it.get("option_value"), it.get("option_value_default")) or ""
        opts = [part.strip().replace("=", " : ", 1) for part in raw.split(", ") if part.strip()]
    add = (it.get("additional_option_value") or "").strip()
    if add:
        opts.append(add.replace("=", " : "))
    return ", ".join(opts)


def to_view(o, images):
    """카페24 주문 1건을 주문서에 그릴 값으로 정리. 없는 값은 빈칸."""
    rcv = (o.get("receivers") or [{}])[0] or {}
    buyer = o.get("buyer") or {}
    if isinstance(buyer, list):
        buyer = buyer[0] if buyer else {}
    place = o.get("order_place_id") or ""
    paid_txt = PAID.get(o.get("payment_status") or "", "결제완료" if o.get("paid") == "T" else "")

    items = []
    for it in o.get("items") or []:
        unit = float(it.get("product_price") or 0) + float(it.get("option_price") or 0)
        qty = int(float(it.get("quantity") or 0))
        items.append({
            "name": it.get("product_name") or it.get("product_name_default") or "",
            "option": _option_text(it),
            "qty": qty, "unit": unit,
            "amount": _first(it.get("product_total_price"), unit * qty) or 0,
            "ship_type": it.get("shipping_fee_type_text") or "기본",
            "ship_fee": it.get("individual_shipping_fee") or 0,
            "tracking": it.get("tracking_no") or "-",
            "status": it.get("status_text") or STATUS.get(it.get("order_status") or "", ""),
            "image": images.get(str(it.get("product_no") or "")),
        })

    member_id = o.get("member_id") or buyer.get("member_id")
    buyer_name = _first(buyer.get("name"), o.get("buyer_name")) or ""
    return {
        "order_id": o.get("order_id", ""),
        "order_date": dtext(o.get("order_date")),
        "place": place, "market_no": _market_no(o),
        "first_order": o.get("first_order") == "T",
        "items": items,
        "paid_txt": paid_txt,
        "price_amount": _amount(o, "order_price_amount"),
        "points": float(_amount(o, "points_spent_amount") or 0) + float(_amount(o, "credits_spent_amount") or 0),
        "shipping_fee": _first(_amount(o, "shipping_fee"), o.get("shipping_fee")) or 0,
        "payment_amount": _first(o.get("payment_amount"), _amount(o, "payment_amount")) or 0,
        "billing_name": _first(o.get("billing_name"), o.get("bank_account_owner_name")) or "",
        "payment_method": _join(_first(o.get("payment_method_name"), o.get("payment_method"))),
        "buyer": {
            "name": f"{buyer_name} ({member_id})" if member_id else f"{buyer_name} (비회원)",
            "group": "회원" if member_id else "비회원",
            "phone": _first(buyer.get("phone"), o.get("buyer_phone")) or "",
            "cell": _first(buyer.get("cellphone"), o.get("buyer_cellphone")) or "",
            "email": _first(buyer.get("email"), o.get("buyer_email"), o.get("member_email")) or "",
            "notice": buyer.get("customer_notification") or "",
        },
        "rcv": {
            "name": rcv.get("name") or "",
            "phone": rcv.get("phone") or "",
            "cell": rcv.get("cellphone") or "",
            "zip": rcv.get("zipcode") or "",
            "addr": _first(rcv.get("address_full"),
                           f"{rcv.get('address1') or ''} {rcv.get('address2') or ''}".strip()) or "",
            "msg": rcv.get("shipping_message") or "",
        },
        "wished": _first(rcv.get("wished_delivery_date"), o.get("wished_delivery_date")) or "0000-00-00",
    }


# ---------------------------------------------------------------- 그리기
def _box(rows, widths, label_cols=(0,), extra=()):
    t = Table(rows, colWidths=widths)
    st = [("GRID", (0, 0), (-1, -1), 0.4, GRID), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("TOPPADDING", (0, 0), (-1, -1), 1.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
          ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    st += [("BACKGROUND", (c, 0), (c, -1), LABEL_BG) for c in label_cols]
    t.setStyle(TableStyle(st + list(extra)))
    return t


def _story(v, highlight=False):
    story = [P("주문상세정보", S_TITLE), Spacer(1, 3 * mm)]
    icon = icon_img(v["place"])
    head = f'<font name="KRB">주문번호 :</font> ' + (icon + "&nbsp;" if icon else "") + E(v["order_id"])
    if v["market_no"]:
        head += f' ({E(v["market_no"])})'
    if v["first_order"]:
        head += f'&nbsp;&nbsp;<font name="KRB" color="white" backColor="{BLUE}">&nbsp;첫주문&nbsp;</font>'
    story += [_box([[P(head)], [P(f'<font name="KRB">주문일자 :</font> {E(v["order_date"])}')]], [CW],
                   label_cols=()), Spacer(1, 3.5 * mm)]

    # 주문내역
    story += [P(f"주문내역({len(v['items'])} 건)", S_H), Spacer(1, 1.2 * mm)]
    # 사진 · 상품명 · 수량 · 빈칸(펜으로 체크하는 칸) · 판매가 · 상품구매금액 · 주문상태  (전체 폭은 예전과 같음)
    w = [9.5 * mm, NAME_COL_W, QTY_COL_W, BLANK_COL_W, 11.5 * mm, 13.5 * mm, STATUS_COL_W]
    rows = [[P("상품명/옵션", S_C), "", P("수량", S_C), "", P("판매가", S_C), P("상품구매금액", S_C),
             P("주문상태", S_C)]]
    tq = tu = ta = 0
    pay_badge = (icon_img("NCHECKOUT", 7) + " ") if v["place"] == "NCHECKOUT" else ""
    for it in v["items"]:
        tq += it["qty"]; tu += it["unit"]; ta += float(it["amount"] or 0)
        img = ""
        if it["image"]:
            try:
                img = Image(it["image"], IMG, IMG)
            except Exception:
                img = ""   # 사진 파일이 깨졌으면 빈칸
        name = E(it["name"])
        if it["option"]:
            name += f'<br/><font color="{BLUE}">{E(it["option"])}</font>'
        status = E(it["status"]) + (f"<br/>{pay_badge}{E(v['paid_txt'])}" if v["paid_txt"] else "")
        fee = float(it["ship_fee"] or 0)
        name_cell = P(name)
        if highlight and it["qty"] >= 2:                  # 오른쪽 주문서: 2개 이상 상품에 형광펜
            name_cell = _Marker(name_cell, str(it["qty"]), qty_size(it["qty"]))
        rows.append([img, name_cell, qty_para(it["qty"]), "", P(won(it["unit"]), S_R), P(won(it["amount"]), S_R),
                     P(status, S_C)])
    rows.append([P("계", S_C), "", P(str(tq), S_C), "", P(won(tu), S_R), P(won(ta), S_R), ""])
    t = Table(rows, colWidths=w, repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, GRID), ("BACKGROUND", (0, 0), (-1, 0), LABEL_BG),
        ("SPAN", (0, 0), (1, 0)), ("SPAN", (0, -1), (1, -1)),
        ("BACKGROUND", (0, -1), (-1, -1), LABEL_BG), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.1),
        ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        # 상품명 칸만 안쪽 여백 2mm (글자 크기는 그대로)
        ("TOPPADDING", (1, 1), (1, -2), NAME_PAD_V), ("BOTTOMPADDING", (1, 1), (1, -2), NAME_PAD_V),
        ("LEFTPADDING", (1, 1), (1, -2), NAME_PAD), ("RIGHTPADDING", (1, 1), (1, -2), NAME_PAD),
    ]))
    story += [t, Spacer(1, 3 * mm)]

    L, V = 26 * mm, CW / 2 - 26 * mm
    pay = [
        [P("상품구매금액"), P(won(v["price_amount"])), P("적립금사용"), P(won(v["points"]))],
        [P("배송비"), P(won(v["shipping_fee"])), "", ""],
        [P("총 실결제금액"), P(f'<font name="KRB" color="{BLUE}">{won(v["payment_amount"])}</font>'), "", ""],
        [P("결제(입금자)"), P(E(v["billing_name"])), P("결제수단"), P(f'<font color="#888888">{E(v["payment_method"])}</font>')],
    ]
    story += [KeepTogether([P("결제정보", S_H), Spacer(1, 1.2 * mm),
               _box(pay, [L, V, L, V], (0, 2), [("SPAN", (1, 1), (3, 1)), ("SPAN", (1, 2), (3, 2)),
                                               ("BACKGROUND", (2, 1), (3, 2), colors.white)])]),
              Spacer(1, 3 * mm)]

    b = v["buyer"]
    buyer = [
        [P("주문자명(ID)"), P(E(b["name"])), P("회원등급"), P(E(b["group"]))],
        [P("일반전화"), P(E(b["phone"])), P("이메일"), P(E(b["email"]))],
        [P("휴대전화"), P(E(b["cell"])), "", ""],
        [P("고객알림"), P(E(b["notice"])), "", ""],
    ]
    story += [KeepTogether([P("주문자정보", S_H), Spacer(1, 1.2 * mm),
               _box(buyer, [L, V, L, V], (0, 2), [("SPAN", (1, 2), (3, 2)), ("SPAN", (1, 3), (3, 3)),
                                                 ("BACKGROUND", (2, 2), (3, 3), colors.white)])]),
              Spacer(1, 3 * mm)]

    r = v["rcv"]
    addr = (f"({E(r['zip'])}) " if r["zip"] else "") + E(r["addr"])
    rcv = [
        [P("수령자명"), P(E(r["name"]), S_BIG), "", ""],
        [P("일반전화"), P(E(r["phone"])), P("휴대전화"), P(E(r["cell"]), S_BIG)],
        [P("배송지 주소"), P(addr, S_BIG), "", ""],
        [P("배송메시지"), P(E(r["msg"]), S_BIG), "", ""],
        [P("희망배송일"), P(E(v["wished"])), "", ""],
    ]
    story += [KeepTogether([P("수령자정보", S_H), Spacer(1, 1.2 * mm),
               _box(rcv, [L, V, L, V], (0, 2), [("SPAN", (1, 0), (3, 0)), ("SPAN", (1, 2), (3, 2)),
                                               ("SPAN", (1, 3), (3, 3)), ("SPAN", (1, 4), (3, 4)),
                                               ("BACKGROUND", (2, 0), (3, 0), colors.white),
                                               ("BACKGROUND", (2, 2), (3, 4), colors.white)])])]
    return story, tq


class _OrderStart(Flowable):
    """주문서 한 건의 시작 표시 (보이지 않음). 쪽 번호 계산에 사용."""
    def __init__(self, idx):
        super().__init__()
        self.idx = idx

    def wrap(self, *args):
        return (0, 0)

    def draw(self):
        pass


class _OrdersDoc(BaseDocTemplate):
    def afterFlowable(self, f):
        if isinstance(f, _OrderStart):
            self.cur, self.start = f.idx, self.page
            if self.progress:
                self.progress(f.idx + 1)


def _single_copy_pdf(views, totals, progress=None, highlight=False):
    """모든 주문서를 주문서 1부 크기로 한 PDF에 연속으로 그림 (글꼴·사진을 한 번만 넣어 용량 절약)."""
    buf = io.BytesIO()
    doc = _OrdersDoc(buf, pagesize=(HALF_W, HALF_H))
    doc.cur, doc.start, doc.progress, doc.counts = 0, 1, progress, {}
    frame = Frame(M, M + 2 * mm, CW, HALF_H - 2 * M - 2 * mm,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    def on_page_end(c, d):
        v = views[d.cur]
        k = d.page - d.start + 1
        d.counts[d.cur] = k
        T = totals.get(d.cur, "?")
        c.saveState()
        if k > 1:   # 여러 장짜리 주문의 2쪽부터만 맨 위에 '계속' 표시
            c.setFont("KRB", 7.5); c.setFillColor(colors.black)
            c.drawString(M, HALF_H - 6.5 * mm, f'주문번호 {v["order_id"]}  (계속 · {k}/{T}쪽)')
        c.restoreState()

    doc.addPageTemplates([PageTemplate(frames=[frame], onPageEnd=on_page_end)])
    story = []
    for i, v in enumerate(views):
        if i:
            story.append(PageBreak())
        story.append(_OrderStart(i))
        story += _story(v, highlight)[0]
    doc.build(story)
    return buf.getvalue(), doc.counts


def end_sheet_pdf(info):
    """자동 출력 묶음의 맨 마지막 '출력 확인 용지' (A4 세로). 이 장이 나왔다면 앞의 주문서도 모두 나온 것."""
    from reportlab.lib.pagesizes import A4 as A4P
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4P, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=14 * mm)
    frame = Frame(15 * mm, 14 * mm, A4P[0] - 30 * mm, A4P[1] - 28 * mm, leftPadding=0, rightPadding=0, topPadding=0,
                  bottomPadding=0)
    doc.addPageTemplates([PageTemplate(frames=[frame])])
    s_t = _st("et", "KRB", 16); s_b = _st("eb", "KRB", 10.5); s_n = _st("en", "KR", 8.5); s_c = _st("ec", "KR", 8.5, alignment=1)
    story = [P("출력 확인 용지", s_t), Spacer(1, 2 * mm),
             P(E(f"{info['when']} 자동 출력 · 주문 {info['count']}건 · 주문서 {info['pages']}장 (이 용지 제외)"), s_b),
             Spacer(1, 1.5 * mm),
             P("이 용지는 자동 출력의 <b>맨 마지막</b>에 인쇄됩니다. 이 용지가 나왔다면 앞의 주문서도 모두 인쇄된 것입니다. "
               "주문서 묶음과 아래 목록을 대조해 보세요.", s_n), Spacer(1, 4 * mm)]
    rows = [[P("", s_c), P("주문번호", s_c), P("주문자", s_c), P("받는 분", s_c), P("경로", s_c)]]
    for o in info["orders"]:
        rows.append(["□", P(E(o["order_id"]), s_n), P(E(o["buyer"]), s_n), P(E(o["receiver"]), s_n), P(E(o["place"]), s_n)])
    t = Table(rows, colWidths=[8 * mm, 45 * mm, 42 * mm, 42 * mm, 30 * mm], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, GRID), ("BACKGROUND", (0, 0), (-1, 0), LABEL_BG),
                           ("FONT", (0, 0), (-1, -1), "KR", 8.5), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("ALIGN", (0, 0), (0, -1), "CENTER"),
                           ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
    last = info["orders"][-1] if info["orders"] else {}
    story += [t, Spacer(1, 5 * mm),
              P(E(f"마지막 주문: {last.get('order_id', '')}  {last.get('buyer', '')}"), s_b), Spacer(1, 2 * mm),
              P("━━━━━━━━━━  여기까지가 이번 자동 출력의 끝입니다  ━━━━━━━━━━", _st("ee", "KRB", 11, alignment=1))]
    doc.build(story)
    return buf.getvalue()


def divider_pdf(info):
    """'여기까지 스마트스토어' 구분 용지 (A4 가로 1장)"""
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(SHEET_W, SHEET_H))
    c.setFillColor(colors.HexColor("#E3F6D8")); c.rect(0, SHEET_H * 0.42, SHEET_W, SHEET_H * 0.34, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.setFont("KRB", 44); c.drawCentredString(SHEET_W / 2, SHEET_H * 0.6, "▲ 여기까지 스마트스토어")
    c.setFont("KRB", 20); c.drawCentredString(SHEET_W / 2, SHEET_H * 0.49, f"스마트스토어 쪽 주문 {info['smart']}건")
    c.setFont("KR", 18); c.drawCentredString(SHEET_W / 2, SHEET_H * 0.3, f"▼ 다음 장부터 나머지 주문 {info['rest']}건")
    c.setFont("KR", 11); c.setFillColor(colors.HexColor("#666666"))
    c.drawCentredString(SHEET_W / 2, SHEET_H * 0.2, "스마트스토어 주문과, 같은 고객의 다른 경로 주문이 앞쪽에 모여 있습니다.")
    c.save()
    return buf.getvalue()


def build_orders_pdf(views, out_path, progress=None, end_info=None, divider=None):
    """주문서 여러 건 → A4 가로에 같은 주문서 2부씩 배치한 PDF. 주문마다 새 장에서 시작."""
    total = len(views)
    step = (lambda i: progress(i, total)) if progress else None
    _, totals = _single_copy_pdf(views, {}, None)            # 1회차: 주문별 쪽수 계산
    data, _ = _single_copy_pdf(views, totals, step)           # 2회차: 쪽수 넣어서 완성
    src = PdfReader(io.BytesIO(data))
    marked = src                                               # 오른쪽 주문서 (형광펜 있으면 따로)
    if any(it["qty"] >= 2 for v in views for it in v["items"]):
        data_hl, _ = _single_copy_pdf(views, totals, None, highlight=True)
        hl = PdfReader(io.BytesIO(data_hl))
        if len(hl.pages) == len(src.pages):                   # 색만 칠하므로 쪽수가 같아야 정상
            marked = hl
    w = PdfWriter()
    cut = sum(totals.get(i, 1) for i in range(divider["index"])) if divider else -1   # 구분 용지 넣을 자리
    for n, hp in enumerate(src.pages):
        if n == cut:
            for pg in PdfReader(io.BytesIO(divider_pdf(divider))).pages:
                w.add_page(pg)
        sheet = PageObject.create_blank_page(width=SHEET_W, height=SHEET_H)
        sheet.merge_transformed_page(hp, Transformation().translate(0, 0))                 # 왼쪽: 그대로
        sheet.merge_transformed_page(marked.pages[n], Transformation().translate(HALF_W, 0))  # 오른쪽: 형광펜
        w.add_page(sheet)
    if end_info:                      # 자동 출력: 맨 뒤에 출력 확인 용지
        for pg in PdfReader(io.BytesIO(end_sheet_pdf(end_info))).pages:
            w.add_page(pg)
    w.add_metadata({"/Title": Path(out_path).stem})
    try:
        w.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    except Exception:
        pass
    for pg in w.pages:
        try:
            pg.compress_content_streams()
        except Exception:
            pass
    with open(out_path, "wb") as f:
        w.write(f)
    return len(w.pages)


def build_notice_pdf(title, message, out_path):
    """오류 안내문 (A4 가로 1장)"""
    c = rl_canvas.Canvas(str(out_path), pagesize=(SHEET_W, SHEET_H))
    c.setFont("KRB", 20); c.drawString(20 * mm, SHEET_H - 30 * mm, title)
    from reportlab.lib.utils import simpleSplit
    c.setFont("KR", 12)
    y = SHEET_H - 48 * mm
    for para in message.split("\n"):
        for line in (simpleSplit(para, "KR", 12, SHEET_W - 40 * mm) or [""]):
            if y < 25 * mm:
                break
            c.drawString(20 * mm, y, line); y -= 7 * mm
    c.setFont("KR", 9); c.setFillColor(colors.grey)
    c.drawString(20 * mm, 15 * mm, dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
    c.save()
