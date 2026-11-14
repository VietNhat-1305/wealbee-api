"""Nền tảng phân tích đầu tư chủ động (docs/dau-tu): chấm điểm đa yếu tố + luồng tín hiệu, dữ liệu từ Wealbee Data API.

Đầu vào
- BCTC đã đồng bộ cho web Doanh nghiệp: docs/doanh-nghiep/data/ma/*.json (tối đa vài quý mỗi mã) + cong_ty.json
- Data API (gói Doanh nghiệp): /statements?updated_since=<7 ngày>&view=basic (BCTC mới công bố / cập nhật, kể cả khi web
  chưa đồng bộ kịp) và /news (tin có gắn mã, sắc thái). Tin được giữ tăng dần trong data/dau_tu_tin.json (30 ngày).

Đầu ra (docs/dau-tu/data/)
- diem.json      điểm 0-100 của 5 yếu tố + điểm tổng cho từng mã, kèm chỉ số gốc để người xem thấy VÌ SAO
- tin_hieu.json  luồng tín hiệu 30 ngày, mới nhất trước: BCTC có bất ngờ lớn, đổi điểm sức khoẻ, dòng tiền âm, nợ vay tăng,
                 tin tích cực / tiêu cực theo mã
- tin/<MÃ>.json  tin 30 ngày của từng mã (thẻ quyết định)

Cách chấm: mỗi chỉ số được xếp phân vị TRONG NHÓM NGÀNH (doanh nghiệp / ngân hàng / chứng khoán / bảo hiểm); điểm yếu tố =
trung bình phân vị các chỉ số có số liệu; điểm tổng = trung bình có trọng số các yếu tố có số liệu (TRONG_SO).

    python -m wb_api.dau_tu            # dựng lại dữ liệu (GitHub Actions gọi sau bước đồng bộ, mỗi giờ)
"""
from __future__ import annotations

import hashlib
import json
import os
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "docs" / "doanh-nghiep" / "data"
RA = ROOT / "docs" / "dau-tu" / "data"
CACHE_TIN = ROOT / "data" / "dau_tu_tin.json"
TRONG_SO = {"tang_truong": 0.25, "hieu_qua": 0.25, "an_toan": 0.20, "chat_luong": 0.15, "tin_tuc": 0.15}
YEU_TO = {  # yếu tố -> chỉ số (True = càng cao càng tốt)
    "tang_truong": {"dt_q": True, "ln_q": True, "dt_lk": True, "ln_lk": True},
    "hieu_qua": {"roe": True, "roa": True, "bien_gop": True, "bien_rong": True},
    "an_toan": {"no_vcsh": False, "vay_vcsh": False, "suc_khoe": True},
    "chat_luong": {"cfo_ln": True},
    "tin_tuc": {"tin": True},
}
NGAY_BCTC, NGAY_TIN_TH, NGAY_TIN = 30, 3, 30      # cửa sổ tín hiệu BCTC / tín hiệu tin / tin tính điểm
VN = timezone(timedelta(hours=7))


def _tg(s) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")) if s else None
    except ValueError:
        return None


def _ty(x) -> float | None:
    return None if x is None else round(x / 1e9, 1)


def _so(x, d: int = 0) -> str:
    return "—" if x is None else f"{x:,.{d}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def _q(m: dict | None, k: str):
    return (m or {}).get(k) if isinstance(m, dict) else None


def yoy(a, b) -> float | None:
    """Tăng trưởng so cùng kỳ (%), chịu được nền âm: lỗ -> lãi = +100, lãi -> lỗ = -100; giới hạn [-100, 300]."""
    if a is None or b is None:
        return None
    if b > 0:
        return round(max(-100.0, min(300.0, (a - b) / b * 100)), 1)
    if b < 0:
        return 100.0 if a > 0 else round(max(-100.0, min(300.0, (a - b) / abs(b) * 100)), 1)
    return 100.0 if a > 0 else (-100.0 if a < 0 else None)


# ---------------------------------------------------------------- chỉ số từ 1 BCTC
def chi_so(st: dict) -> dict:
    i, b, c = st.get("income_statement") or {}, st.get("balance_sheet") or {}, st.get("cash_flow") or {}
    nganh = st.get("industry_type") or "corporate"
    co_dt = _q(i.get("revenue"), "quarter") is not None
    dt = i.get("revenue") if co_dt else i.get("gross_profit")       # ngân hàng: không có doanh thu -> thu nhập hoạt động
    ln = i.get("net_profit") or {}
    vc, ts, no, vay = b.get("equity") or b.get("owners_equity") or {}, b.get("total_assets") or {}, b.get("total_liabilities") or {}, b.get("borrowings") or {}
    cfo = c.get("operating") or c.get("operating_cash_flow") or {}
    thang = st.get("months_ytd") or 12
    tb = lambda x: (None if _q(x, "end_of_period") is None else  # noqa: E731
                    _q(x, "end_of_period") if _q(x, "start_of_year") is None else (x["end_of_period"] + x["start_of_year"]) / 2)
    m = {"dt_q": yoy(_q(dt, "quarter"), _q(dt, "quarter_prior_year")), "ln_q": yoy(_q(ln, "quarter"), _q(ln, "quarter_prior_year")),
         "dt_lk": yoy(_q(dt, "ytd"), _q(dt, "ytd_prior_year")), "ln_lk": yoy(_q(ln, "ytd"), _q(ln, "ytd_prior_year"))}
    a_, b_ = _q(ln, "quarter"), _q(ln, "quarter_prior_year")
    if a_ is not None and b_ is not None and (a_ > 0) != (b_ > 0):          # đảo chiều lỗ / lãi: hiển thị chữ thay cho %
        m["ln_dao"] = 1 if a_ > 0 else -1
    lk = _q(ln, "ytd")
    if lk is not None and (tb(vc) or 0) > 0:
        m["roe"] = round(lk * 12 / thang / tb(vc) * 100, 1)
    if lk is not None and (tb(ts) or 0) > 0:
        m["roa"] = round(lk * 12 / thang / tb(ts) * 100, 2)
    dtq = _q(i.get("revenue"), "quarter")
    if nganh == "corporate" and dtq and dtq > 0:                      # biên chỉ có nghĩa với doanh nghiệp thường
        if _q(i.get("gross_profit"), "quarter") is not None:
            m["bien_gop"] = round(i["gross_profit"]["quarter"] / dtq * 100, 1)
        if _q(ln, "quarter") is not None:
            m["bien_rong"] = round(ln["quarter"] / dtq * 100, 1)
    e = _q(vc, "end_of_period")
    if e is not None:
        if e > 0:
            if _q(no, "end_of_period") is not None:
                m["no_vcsh"] = round(no["end_of_period"] / e, 2)
            if _q(vay, "end_of_period") is not None:
                m["vay_vcsh"] = round(vay["end_of_period"] / e, 2)
        else:                                                         # vốn chủ âm: an toàn tài chính kém nhất
            m["no_vcsh"] = 99.0
    hs = st.get("health_score") or {}
    if hs.get("value") is not None:
        m["suc_khoe"] = hs["value"]
    if nganh == "corporate" and lk and lk > 0 and _q(cfo, "ytd") is not None:
        m["cfo_ln"] = round(cfo["ytd"] / lk, 2)
    goc = {"dt_q": _ty(_q(dt, "quarter")), "dt_q_ck": _ty(_q(dt, "quarter_prior_year")), "ln_q": _ty(_q(ln, "quarter")),
           "ln_q_ck": _ty(_q(ln, "quarter_prior_year")), "ln_lk": _ty(lk), "cfo_lk": _ty(_q(cfo, "ytd")),
           "vay": _ty(_q(vay, "end_of_period")), "vay_dn": _ty(_q(vay, "start_of_year")), "vcsh": _ty(e), "dt_la_tn": not co_dt}
    return {k: v for k, v in m.items() if v is not None}, {k: v for k, v in goc.items() if v is not None}


# ---------------------------------------------------------------- dữ liệu vào
def doc_bctc() -> tuple[dict, dict]:
    cty = {c["ticker"]: c for c in json.loads((WEB / "cong_ty.json").read_text(encoding="utf-8")).get("ds", []) if c.get("ticker")}
    ds = {}
    for f in sorted((WEB / "ma").glob("*.json")):
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        ky = [m["ky"][k] for k in sorted(m.get("ky") or {}, reverse=True)]
        if ky:
            ds[m.get("ma") or f.stem] = ky
    return ds, cty


def _ds(j) -> list:
    return j.get("data", []) if isinstance(j, dict) else []


def lay_api(bctc: dict) -> dict:
    """BCTC mới công bố / cập nhật 7 ngày + tin tức (tăng dần). Không có khoá -> bỏ qua, dùng dữ liệu đã đồng bộ."""
    khoa = os.environ.get("WEALBEE_KEY_DN", "").strip()
    tin = _doc_cache()
    if not khoa:
        return {"loi": "chưa có WEALBEE_KEY_DN", "tin": tin, "moi": 0}
    from .client import WB
    wb = WB(khoa, "dn", nhip_toi_thieu=0.6)
    out = {"moi": 0, "trang_tin": 0}
    try:
        tu = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
        cur = None
        for _ in range(6):                                            # BCTC cập nhật 7 ngày qua (view basic: không có LCTT)
            l = wb.goi("dau_tu_bctc", "/statements", {"limit": 500, "view": "basic", "updated_since": tu, **({"cursor": cur} if cur else {})})
            if l.status != 200:
                out["loi_bctc"] = f"HTTP {l.status}"
                break
            for st in _ds(l.json):
                ma, cu = st.get("ticker"), None
                if not ma:
                    continue
                ds = bctc.setdefault(ma, [])
                cu = next((x for x in ds if x.get("period") == st.get("period")), None)
                if cu is None or (st.get("version") or 0) > (cu.get("version") or 0):
                    moi = dict(st)
                    moi["nguon_goc"] = st.get("provenance") or {}
                    if cu is not None and "cash_flow" not in moi:
                        moi["cash_flow"] = cu.get("cash_flow")           # view basic không có LCTT: giữ bản đã đồng bộ
                    ds[:] = sorted([x for x in ds if x.get("period") != st.get("period")] + [moi],
                                   key=lambda x: x.get("period") or "", reverse=True)
                    out["moi"] += 1
            cur = _q(l.json, "next_cursor")
            if not cur:
                break
        da_co = {x["i"] for x in tin}
        moc = datetime.now(timezone.utc) - timedelta(days=NGAY_TIN)
        moi_tin, cur = [], None
        for _ in range(60 if not tin else 25):                         # tin: đi lùi tới khi gặp tin đã có / quá 30 ngày
            l = wb.goi("dau_tu_tin", "/news", {"limit": 100, **({"cursor": cur} if cur else {})})
            out["trang_tin"] += 1
            if l.status != 200:
                out["loi_tin"] = f"HTTP {l.status}"
                break
            dung = False
            for x in _ds(l.json):
                t = _tg(x.get("first_published_at") or x.get("detected_at"))
                if x.get("id") in da_co or (t and t < moc):
                    dung = True
                    continue
                if not (x.get("tickers") or x.get("primary_ticker")):
                    continue
                src = sorted(x.get("sources") or [], key=lambda s: not s.get("official"))
                moi_tin.append({"i": x["id"], "t": (x.get("title") or "").strip(), "s": (x.get("sentiment") or "neutral")[:3],
                                "m": (x.get("tickers") or [])[:8], "p": x.get("primary_ticker"), "d": x.get("first_published_at"),
                                "n": x.get("source_count") or len(src), "c": x.get("category"),
                                "u": src[0].get("url") if src else None, "o": src[0].get("outlet") if src else None,
                                "tt": bool(x.get("summary"))})
            cur = _q(l.json, "next_cursor")
            if dung or not cur:
                break
        tin = sorted(moi_tin + tin, key=lambda x: x.get("d") or "", reverse=True)
        tin = [x for x in tin if (_tg(x.get("d")) or moc) >= moc]
        out["tin_moi"] = len(moi_tin)
    finally:
        wb.close()
    _ghi_cache(tin)
    out["tin"] = tin
    return out


def _doc_cache() -> list:
    try:
        return json.loads(CACHE_TIN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _ghi_cache(tin: list) -> None:
    CACHE_TIN.parent.mkdir(parents=True, exist_ok=True)                 # 1 tin / dòng: git chỉ lưu phần đổi
    CACHE_TIN.write_text("[\n" + ",\n".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in tin) + "\n]\n",
                         encoding="utf-8")


# ---------------------------------------------------------------- tin theo mã
def tin_theo_ma(tin: list) -> dict[str, list]:
    """Tin gắn với mã: mã chính của tin, hoặc tin chỉ nhắc ≤ 2 mã (tin điểm danh 8 mã của cả thị trường không tính)."""
    out = defaultdict(list)
    for x in tin:
        ma = [x["p"]] if x.get("p") else (x.get("m") if len(x.get("m") or []) <= 2 else [])
        for m in ma:
            out[m].append(x)
    return out


def diem_tin(ds: list) -> tuple[float | None, int]:
    """Điểm sắc thái tin 30 ngày: (tích cực - tiêu cực) / (tổng + 3), tin nhiều nguồn nặng hơn."""
    if not ds:
        return None, 0
    w = lambda x: 1 + min(2, (x.get("n") or 1) - 1) * 0.5           # noqa: E731
    duong = sum(w(x) for x in ds if x["s"] == "pos")
    am = sum(w(x) for x in ds if x["s"] == "neg")
    tong = sum(w(x) for x in ds)
    return round((duong - am) / (tong + 3), 3), len(ds)


# ---------------------------------------------------------------- chấm điểm
def phan_vi(gia_tri: dict[str, float], cao_tot: bool) -> dict[str, float]:
    """Phân vị 0-100 trong nhóm (hoà điểm lấy trung bình)."""
    xs = sorted(gia_tri.values())
    n = len(xs)
    if n == 1:
        return {k: 50.0 for k in gia_tri}
    out = {}
    import bisect
    for k, v in gia_tri.items():
        lo, hi = bisect.bisect_left(xs, v), bisect.bisect_right(xs, v)
        p = ((lo + hi - 1) / 2) / (n - 1) * 100
        out[k] = round(p if cao_tot else 100 - p, 1)
    return out


def cham(ds_cs: dict[str, dict], nhom_cua: dict[str, str]) -> tuple[dict, dict]:
    """ds_cs: mã -> chỉ số. Trả về (điểm yếu tố theo mã, trung vị theo nhóm)."""
    pv = defaultdict(dict)                                            # mã -> chỉ số -> phân vị
    trung_vi = defaultdict(dict)
    for nhom in set(nhom_cua.values()):
        ma_nhom = [m for m in ds_cs if nhom_cua[m] == nhom]
        for yt, cs in YEU_TO.items():
            for k, cao in cs.items():
                gt = {m: ds_cs[m][k] for m in ma_nhom if ds_cs[m].get(k) is not None}
                if k == "tin":                                         # tin: không phụ thuộc ngành -> xếp trên toàn thị trường
                    continue
                if len(gt) >= 5:
                    for m, p in phan_vi(gt, cao).items():
                        pv[m][k] = p
                    trung_vi[nhom][k] = round(statistics.median(gt.values()), 2)
    tin_gt = {m: v["tin"] for m, v in ds_cs.items() if v.get("tin") is not None}
    if len(tin_gt) >= 5:
        for m, p in phan_vi(tin_gt, True).items():
            pv[m]["tin"] = p
    diem = {}
    for m in ds_cs:
        yt_diem = {}
        for yt, cs in YEU_TO.items():
            ps = [pv[m][k] for k in cs if k in pv[m]]
            yt_diem[yt] = round(statistics.fmean(ps)) if ps else None
        co = {k: v for k, v in yt_diem.items() if v is not None}
        tong = round(sum(TRONG_SO[k] * v for k, v in co.items()) / sum(TRONG_SO[k] for k in co)) if co else None
        diem[m] = {"tong": tong, "yt": yt_diem}
    for nhom in trung_vi:                                             # trung vị điểm yếu tố của nhóm (vạch so sánh trên thẻ)
        for yt in YEU_TO:
            xs = [diem[m]["yt"][yt] for m in ds_cs if nhom_cua[m] == nhom and diem[m]["yt"].get(yt) is not None]
            if xs:
                trung_vi[nhom][yt] = round(statistics.median(xs))
        xs = [diem[m]["tong"] for m in ds_cs if nhom_cua[m] == nhom and diem[m]["tong"] is not None]
        if xs:
            trung_vi[nhom]["tong"] = round(statistics.median(xs))
    return diem, dict(trung_vi)


# ---------------------------------------------------------------- tín hiệu
def _ky_nhan(st: dict) -> str:
    return st.get("period_label") or st.get("period") or ""


def _link_bctc(st: dict) -> str | None:
    return (st.get("nguon_goc") or {}).get("document_url")


def tin_hieu_bctc(ma: str, ten: str, ky: list, nganh: str, now: datetime) -> list[dict]:
    st = ky[0]
    ng = st.get("nguon_goc") or {}
    luc = _tg(ng.get("first_published_at")) or _tg(ng.get("updated_at"))
    if not luc or now - luc > timedelta(days=NGAY_BCTC):
        return []
    _, g = chi_so(st)
    out, k, soat = [], _ky_nhan(st), st.get("status") == "needs_review"
    base = {"ma": ma, "ten": ten, "luc": luc.isoformat(), "ky": k, "link": _link_bctc(st), "nguon": "BCTC gốc", "can_soat": soat}
    a, b = g.get("ln_q"), g.get("ln_q_ck")
    if a is not None and b is not None:
        if b > 0 and a <= 0 and max(abs(a), abs(b)) >= 5:                 # bỏ biến động vài tỷ của doanh nghiệp rất nhỏ
            out.append({**base, "loai": "lai_sang_lo", "muc": "tieu_cuc", "manh": "cao", "tieu_de": "Chuyển từ lãi sang lỗ",
                        "chi_tiet": f"LNST {k} lỗ {_so(abs(a), 1)} tỷ, cùng kỳ năm trước lãi {_so(b, 1)} tỷ."})
        elif b <= 0 and a > 0 and max(abs(a), abs(b)) >= 5:
            out.append({**base, "loai": "lo_sang_lai", "muc": "tich_cuc", "manh": "cao", "tieu_de": "Có lãi trở lại",
                        "chi_tiet": f"LNST {k} lãi {_so(a, 1)} tỷ, cùng kỳ năm trước " + (f"lỗ {_so(abs(b), 1)} tỷ." if b < 0 else "không có lãi.")})
        elif b >= 5 and a > 0:
            p = (a - b) / b * 100
            if p >= 30:
                out.append({**base, "loai": "ln_tang", "muc": "tich_cuc", "manh": "cao" if p >= 100 else "trung_binh",
                            "tieu_de": f"Lợi nhuận quý tăng {_so(p)}%",
                            "chi_tiet": f"LNST {k} đạt {_so(a, 1)} tỷ, cùng kỳ {_so(b, 1)} tỷ (+{_so(p)}%)."})
            elif p <= -30:
                out.append({**base, "loai": "ln_giam", "muc": "tieu_cuc", "manh": "cao" if p <= -60 else "trung_binh",
                            "tieu_de": f"Lợi nhuận quý giảm {_so(-p)}%",
                            "chi_tiet": f"LNST {k} còn {_so(a, 1)} tỷ, cùng kỳ {_so(b, 1)} tỷ ({_so(p)}%)."})
    if len(ky) > 1:
        h0, h1 = (st.get("health_score") or {}).get("value"), (ky[1].get("health_score") or {}).get("value")
        if h0 is not None and h1 is not None and abs(h0 - h1) >= 2:
            tang = h0 > h1
            out.append({**base, "loai": "suc_khoe_tang" if tang else "suc_khoe_giam", "muc": "tich_cuc" if tang else "tieu_cuc",
                        "manh": "trung_binh", "tieu_de": f"Điểm sức khoẻ tài chính {'tăng' if tang else 'giảm'} {abs(h0 - h1)} điểm",
                        "chi_tiet": f"Điểm sức khoẻ Wealbee {_ky_nhan(ky[1])}: {h1}/10 → {k}: {h0}/10."})
    lk, cfo = g.get("ln_lk"), g.get("cfo_lk")
    if nganh == "corporate" and lk and cfo is not None and lk >= 20 and cfo < -0.5 * lk:    # âm đáng kể so với lợi nhuận
        out.append({**base, "loai": "cfo_am", "muc": "canh_bao", "manh": "cao" if cfo < -lk else "trung_binh",
                    "tieu_de": "Có lãi nhưng dòng tiền kinh doanh âm",
                    "chi_tiet": f"LNST luỹ kế {_so(lk, 1)} tỷ nhưng lưu chuyển tiền từ hoạt động kinh doanh luỹ kế âm {_so(abs(cfo), 1)} tỷ."})
    v1, v0 = g.get("vay"), g.get("vay_dn")
    if v1 is not None and v0 is not None and v0 > 0 and v1 - v0 >= 200 and v1 / v0 >= 1.5:
        out.append({**base, "loai": "no_vay_tang", "muc": "canh_bao", "manh": "cao" if v1 / v0 >= 2 else "trung_binh",
                    "tieu_de": f"Nợ vay tăng {_so((v1 / v0 - 1) * 100)}% từ đầu năm",
                    "chi_tiet": f"Vay nợ cuối {k} {_so(v1, 1)} tỷ, đầu năm {_so(v0, 1)} tỷ"
                                + (f"; vốn chủ {_so(g['vcsh'], 1)} tỷ." if g.get("vcsh") else ".")})
    return out


def tin_hieu_tin(ma: str, ten: str, ds: list, now: datetime) -> list[dict]:
    moc = now - timedelta(days=NGAY_TIN_TH)
    gan = [x for x in ds if (_tg(x.get("d")) or moc) > moc]
    out = []
    for s, loai, muc, chu in (("neg", "tin_tieu_cuc", "tieu_cuc", "tiêu cực"), ("pos", "tin_tich_cuc", "tich_cuc", "tích cực")):
        xs = [x for x in gan if x["s"] == s]
        if not xs:
            continue
        dau = max(xs, key=lambda x: (x.get("n") or 1, x.get("d") or ""))
        out.append({"ma": ma, "ten": ten, "loai": loai, "muc": muc, "manh": "cao" if len(xs) >= 3 or (dau.get("n") or 1) >= 4 else "trung_binh",
                    "luc": max(x.get("d") or "" for x in xs), "tieu_de": f"{len(xs)} tin {chu} trong {NGAY_TIN_TH} ngày",
                    "chi_tiet": f"Nổi bật: “{dau['t']}” ({dau.get('n') or 1} nguồn).",
                    "link": dau.get("u"), "nguon": dau.get("o") or "bài gốc", "can_soat": False})
    return out


# ---------------------------------------------------------------- dựng
def _ghi(path: Path, obj) -> bool:
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == hashlib.sha256(s.encode("utf-8")).hexdigest():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(s, encoding="utf-8")
    return True


def dung(goi_api: bool = True) -> dict:
    now = datetime.now(timezone.utc)
    bctc, cty = doc_bctc()
    api = lay_api(bctc) if goi_api else {"tin": _doc_cache(), "moi": 0}
    tin = api.get("tin") or []
    theo_ma = tin_theo_ma(tin)
    cs, goc, nhom_cua, meta = {}, {}, {}, {}
    for ma, ky in bctc.items():
        st = ky[0]
        m, g = chi_so(st)
        d, n = diem_tin(theo_ma.get(ma, []))
        if d is not None:
            m["tin"] = d
        m["tin_n"] = n
        cs[ma], goc[ma] = m, g
        nhom_cua[ma] = st.get("industry_type") or "corporate"
        c = cty.get(ma) or {}
        meta[ma] = {"t": c.get("short_name") or c.get("name") or ma, "s": c.get("exchange"), "n": nhom_cua[ma], "k": _ky_nhan(st),
                    "tt": st.get("status"), "pb": (st.get("nguon_goc") or {}).get("first_published_at")}
    diem, trung_vi = cham(cs, nhom_cua)
    ds = {}
    for ma in cs:
        d = diem[ma]
        ds[ma] = {**meta[ma], "d": d["tong"], "f": [d["yt"][k] for k in YEU_TO], "m": cs[ma]}   # số gốc: thẻ quyết định đọc file BCTC
    th = []
    for ma, ky in bctc.items():
        th += tin_hieu_bctc(ma, meta[ma]["t"], ky, nhom_cua[ma], now)
    for ma, xs in theo_ma.items():
        th += tin_hieu_tin(ma, (meta.get(ma) or {}).get("t") or (cty.get(ma) or {}).get("short_name") or ma, xs, now)
    th.sort(key=lambda x: x["luc"] or "", reverse=True)
    for x in th:
        x["id"] = hashlib.sha1(f"{x['ma']}|{x['loai']}|{x.get('ky') or x['luc'][:10]}".encode()).hexdigest()[:10]
    th = th[:900]
    out = {"cap_nhat": now.isoformat(timespec="seconds"), "trong_so": TRONG_SO, "yeu_to": {k: list(v) for k, v in YEU_TO.items()},
           "trung_vi": trung_vi, "so_tin": len(tin), "ds": ds}
    ghi = _ghi(RA / "diem.json", out)
    ghi |= _ghi(RA / "tin_hieu.json", {"cap_nhat": out["cap_nhat"], "ngay_bctc": NGAY_BCTC, "ngay_tin": NGAY_TIN_TH, "ds": th})
    giu = set()
    for ma, xs in theo_ma.items():
        giu.add(ma + ".json")
        _ghi(RA / "tin" / f"{ma}.json", [{k: x.get(k) for k in ("t", "s", "d", "n", "u", "o", "c")} for x in xs[:20]])
    for f in (RA / "tin").glob("*.json"):                              # mã không còn tin 30 ngày: xoá file cũ
        if f.name not in giu:
            f.unlink()
    dem = Counter(x["muc"] for x in th)
    return {"so_ma": len(ds), "tin_hieu": len(th), "theo_muc": dict(dem), "tin": len(tin), "bctc_moi_api": api.get("moi"),
            "trang_tin": api.get("trang_tin"), "loi": api.get("loi") or api.get("loi_bctc") or api.get("loi_tin")}


def chay() -> dict:
    """Gọi từ wb_api.chay (GitHub Actions, sau bước đồng bộ)."""
    return dung(goi_api=True)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from .chay import nap_env
    nap_env()
    print(json.dumps(dung(goi_api="--khong-api" not in sys.argv), ensure_ascii=False))
