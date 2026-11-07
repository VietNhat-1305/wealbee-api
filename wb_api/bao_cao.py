"""Tổng hợp dữ liệu đo -> báo cáo đánh giá hiệu suất Wealbee API theo tiêu chí doanh nghiệp (mã hoá cho trang báo cáo).

Tiêu chí (ngưỡng theo thông lệ API dữ liệu tài chính cho doanh nghiệp + mục tiêu Wealbee tự công bố):
  1 Tính sẵn sàng      tỷ lệ request thành công (bỏ bài đo lỗi cố ý)        Đạt ≥ 99,9% · Khá ≥ 99%
  2 Độ trễ             p95 thời gian phản hồi (kết nối đã mở)              Đạt ≤ 500 ms · Khá ≤ 1.000 ms
  3 Thời gian byte đầu p50 TTFB                                            Đạt ≤ 300 ms · Khá ≤ 600 ms
  4 Lỗi máy chủ/mạng   5xx + timeout + lỗi mạng                            Đạt ≤ 0,1% · Khá ≤ 1%
  5 Ổn định            hệ số biến thiên độ trễ (độ lệch chuẩn / trung bình) Đạt ≤ 0,5 · Khá ≤ 1
  6 Chuẩn lỗi          lỗi 400/401/404 đúng mã + đúng RFC 9457             Đạt 100% · Khá ≥ 90%
  7 Giới hạn tốc độ    header RateLimit đủ + 429 đúng lúc, có Retry-After  Đạt / Khá / Chưa đạt
  8 Độ tươi dữ liệu    thấy file -> có số (trung vị)                       Đạt ≤ 15 phút (Wealbee cam kết) · Khá ≤ 60
  9 Chất lượng dữ liệu tỷ lệ BCTC "verified" + phép kiểm đạt               Đạt ≥ 95% · Khá ≥ 85%
 10 Độ phủ             số công ty được phủ                                 Đạt ≥ 700 (Wealbee công bố 705) · Khá ≥ 600
 11 Bảo mật            TLS ≥ 1.2, HSTS, http -> https, từ chối khoá qua URL Đạt 4/4 · Khá 3/4
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import ma_hoa

ROOT = Path(__file__).resolve().parent.parent
DO = ROOT / "data" / "do"
RA = ROOT / "docs" / "bao-cao" / "bao_cao.enc"
LOI_CO_Y = ("err_400", "err_404", "err_401")
THONG_TIN = ("info_ma_la",)                     # bài đo chỉ ghi nhận, không chấm


def doc_tat_ca(ngay: int = 30) -> list[dict]:
    moc = datetime.now(timezone.utc) - timedelta(days=ngay)
    out = []
    for f in sorted(DO.glob("*/*.jsonl")):
        for ln in f.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                r = ma_hoa.mo_dong(ln.strip())
            except Exception:  # noqa: BLE001 - dòng hỏng / khác mật khẩu
                continue
            if datetime.fromisoformat(r["luc"]) >= moc:
                out.append(r)
    return sorted(out, key=lambda r: r["luc"])


def _pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * p / 100
    f, c = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[f] + (xs[c] - xs[f]) * (k - f), 1)


def _thong_ke(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0}
    tb = statistics.fmean(xs)
    return {"n": len(xs), "p50": _pct(xs, 50), "p90": _pct(xs, 90), "p95": _pct(xs, 95), "p99": _pct(xs, 99),
            "tb": round(tb, 1), "max": round(max(xs), 1), "cv": round(statistics.pstdev(xs) / tb, 2) if tb else None}


def _xep(gia_tri, dat, kha, lon_hon_tot=True) -> str:
    if gia_tri is None:
        return "chua_du"
    if lon_hon_tot:
        return "dat" if gia_tri >= dat else "kha" if gia_tri >= kha else "chua_dat"
    return "dat" if gia_tri <= dat else "kha" if gia_tri <= kha else "chua_dat"


def tong_hop_goi(rs: list[dict]) -> dict:
    """Số liệu của 1 gói (1 nguồn đo hoặc gộp)."""
    luot = [l for r in rs for l in r.get("luot", [])]
    ma_la = [l for l in luot if l["ep"] == "info_ma_la"]
    thuong = [l for l in luot if l["ep"] not in LOI_CO_Y + THONG_TIN]
    am = [l for l in thuong if l.get("status") != 429]
    ok = [l for l in am if l.get("dung")]
    may_chu = [l for l in am if l.get("loi_mang") or (l.get("status") or 0) >= 500]
    am_lanh = [l["ms_tong"] for l in ok if not l.get("lanh")]
    theo_ep = defaultdict(list)
    for l in ok:
        if not l.get("lanh"):
            theo_ep[l["ep"]].append(l["ms_tong"])
    loi_cy = [l for l in luot if l["ep"] in LOI_CO_Y]
    tuoi, lk = {}, set()
    for r in rs:
        for t in r.get("tuoi_ds") or []:
            if t.get("phut") is not None and t.get("id"):
                tuoi[t["id"]] = t["phut"]
        t = r.get("tuoi") or {}
        if t.get("phut") is not None and r.get("mau_bc", {}).get("id"):
            tuoi[r["mau_bc"]["id"]] = t["phut"]
        lk.update(r.get("lech_ky") or [])
    cl = defaultdict(int)
    kiem = defaultdict(int)
    for r in rs[-48:]:                                         # chất lượng: 48 lượt gần nhất
        for k, v in ((r.get("chat_luong") or {}).get("trang_thai") or {}).items():
            cl[k] += v
        for k, v in ((r.get("chat_luong") or {}).get("kiem") or {}).items():
            kiem[k] += v
    tong_cl = sum(cl.values())
    tong_kiem = kiem["passed"] + kiem["failed"]
    co_rl = [l for l in ok if l.get("rl", {}).get("q") is not None and l.get("rl", {}).get("r") is not None]
    don = next((r["ban_don"] for r in reversed(rs) if r.get("ban_don")), None)
    tre = [r["do_tre_du_lieu_s"] for r in rs if r.get("do_tre_du_lieu_s") is not None]
    loi_ds = defaultdict(int)
    for l in am:
        if not l.get("dung"):
            loi_ds[l.get("loi_mang", "").split(":")[0] or f"HTTP {l.get('status')} {l.get('code') or ''}".strip()] += 1
    chuoi = []
    for r in rs:
        ms = [l["ms_tong"] for l in r.get("luot", []) if l.get("dung") and l["ep"] not in LOI_CO_Y and not l.get("lanh")]
        chuoi.append({"luc": r["luc"], "p50": _pct(ms, 50), "p95": _pct(ms, 95),
                      "ok": sum(1 for l in r.get("luot", []) if l.get("dung") and l["ep"] not in LOI_CO_Y),
                      "n": sum(1 for l in r.get("luot", []) if l["ep"] not in LOI_CO_Y)})
    return {
        "so_luot_quet": len(rs), "so_request": len(luot),
        "kha_dung": round(100 * len(ok) / len(am), 3) if am else None,
        "loi_may_chu": round(100 * len(may_chu) / len(am), 3) if am else None,
        "do_tre": _thong_ke(am_lanh), "ttfb": _thong_ke([l["ms_ttfb"] for l in ok if not l.get("lanh") and l.get("ms_ttfb")]),
        "lanh": _thong_ke([l["ms_tong"] for l in ok if l.get("lanh")]),
        "theo_ep": {k: _thong_ke(v) for k, v in sorted(theo_ep.items())},
        "chuan_loi": {"n": len(loi_cy), "dung_ma": sum(bool(l.get("dung")) for l in loi_cy),
                      "rfc9457": sum(bool(l.get("rfc9457")) for l in loi_cy)},
        "rate_limit": {"co_header": round(100 * len(co_rl) / len(ok), 1) if ok else None,
                       "chinh_sach": next(({"q": l["rl"].get("q"), "w": l["rl"].get("w")} for l in reversed(ok) if l.get("rl", {}).get("q")), None),
                       "ban_don": don},
        "do_tuoi": {"n": len(tuoi), "trung_vi_phut": _pct(list(tuoi.values()), 50), "p90_phut": _pct(list(tuoi.values()), 90),
                    "ty_le_15p": round(100 * sum(v <= 15 for v in tuoi.values()) / len(tuoi), 1) if tuoi else None},
        "do_tre_du_lieu_s": _thong_ke(tre),
        "chat_luong": {"trang_thai": dict(cl), "verified": round(100 * cl.get("verified", 0) / tong_cl, 1) if tong_cl else None,
                       "kiem_dat": round(100 * kiem["passed"] / tong_kiem, 1) if tong_kiem else None},
        "so_cong_ty": next(((r.get("phu") or {}).get("so_cong_ty") or r.get("so_cong_ty") for r in reversed(rs)
                            if (r.get("phu") or {}).get("so_cong_ty") or r.get("so_cong_ty")), None),
        "ky_moi_nhat": next(((r.get("phu") or {}).get("ky_moi_nhat") for r in reversed(rs) if (r.get("phu") or {}).get("ky_moi_nhat")), None),
        "lech_ky": sorted(lk),
        "ma_la": {"n": len(ma_la), "ma": sorted({f"{l.get('status')} {l.get('code') or ''}".strip() for l in ma_la})},
        "quyen": next((r.get("me") for r in reversed(rs) if r.get("me")), None),
        "loi": dict(loi_ds), "chuoi": chuoi[-24 * 30:],
        "bo_qua": next((r.get("bo_qua") for r in reversed(rs) if r.get("bo_qua")), None) if not luot else None,
    }


def cham_diem(g: dict, bao_mat: dict | None) -> list[dict]:
    rl = g["rate_limit"]
    don = rl.get("ban_don") or {}
    if don:
        dung_429 = don.get("luot_429") is not None and don.get("retry_after") and don.get("rfc9457_429")
        rl_xep = "dat" if dung_429 and (rl.get("co_header") or 0) >= 99 and don.get("sau_retry_after") == 200 else \
                 "kha" if (rl.get("co_header") or 0) >= 90 else "chua_dat"
        if don.get("luot_429") is None and (don.get("q") or 0) > 55:
            rl_xep = "dat" if (rl.get("co_header") or 0) >= 99 else "kha"       # giới hạn cao, không bắn tới 429
    else:
        rl_xep = "chua_du" if rl.get("co_header") is None else ("kha" if rl["co_header"] >= 99 else "chua_dat")
    cl = g["chuan_loi"]
    chuan = round(100 * min(cl["dung_ma"], cl["rfc9457"]) / cl["n"], 1) if cl["n"] else None
    bm_diem = None
    if bao_mat and "tls" in bao_mat:
        bm_diem = sum([bao_mat.get("tls") in ("TLSv1.2", "TLSv1.3"), bool(bao_mat.get("hsts")), bool(bao_mat.get("http_sang_https")),
                       bool(bao_mat.get("khoa_qua_query_bi_tu_choi", True))])
    kq = [
        ("kha_dung", "Tính sẵn sàng", g["kha_dung"], "%", _xep(g["kha_dung"], 99.9, 99.0), 15, "≥ 99,9%"),
        ("do_tre", "Độ trễ p95", g["do_tre"].get("p95"), "ms", _xep(g["do_tre"].get("p95"), 500, 1000, False), 12, "≤ 500 ms"),
        ("ttfb", "Byte đầu (TTFB) p50", g["ttfb"].get("p50"), "ms", _xep(g["ttfb"].get("p50"), 300, 600, False), 6, "≤ 300 ms"),
        ("loi_may_chu", "Lỗi máy chủ / mạng", g["loi_may_chu"], "%", _xep(g["loi_may_chu"], 0.1, 1.0, False), 10, "≤ 0,1%"),
        ("on_dinh", "Ổn định độ trễ (CV)", g["do_tre"].get("cv"), "", _xep(g["do_tre"].get("cv"), 0.5, 1.0, False), 6, "≤ 0,5"),
        ("chuan_loi", "Chuẩn lỗi RFC 9457", chuan, "%", _xep(chuan, 100, 90), 6, "100%"),
        ("rate_limit", "Giới hạn tốc độ minh bạch", rl.get("co_header"), "% có header", rl_xep, 7, "header đủ + 429 đúng"),
        ("do_tuoi", "Độ tươi (thấy file → có số)", g["do_tuoi"]["trung_vi_phut"], "phút",
         _xep(g["do_tuoi"]["trung_vi_phut"], 15, 60, False), 14, "≤ 15 phút"),
        ("chat_luong", "Chất lượng dữ liệu (verified)", g["chat_luong"]["verified"], "%", _xep(g["chat_luong"]["verified"], 95, 85), 10, "≥ 95%"),
        ("do_phu", "Độ phủ (số công ty)", g["so_cong_ty"], "mã", _xep(g["so_cong_ty"], 700, 600), 7, "≥ 700"),
        ("bao_mat", "Bảo mật", bm_diem, "/4", _xep(bm_diem, 4, 3), 7, "4/4"),
    ]
    return [{"ma": a, "ten": b, "gia_tri": c, "don_vi": d, "xep": e, "trong_so": f, "nguong": h} for a, b, c, d, e, f, h in kq]


def diem_tong(tc: list[dict]) -> float | None:
    he = {"dat": 1.0, "kha": 0.6, "chua_dat": 0.15}
    co = [t for t in tc if t["xep"] in he]
    if not co:
        return None
    return round(100 * sum(he[t["xep"]] * t["trong_so"] for t in co) / sum(t["trong_so"] for t in co), 1)


def so_vn(x, d: int = 0) -> str:
    return "—" if x is None else f"{x:,.{d}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def nhan_xet(goi: dict) -> list[str]:
    out = []
    for ten, g in goi.items():
        if not g["tong"].get("so_request"):
            continue
        t = {x["ma"]: x for x in g["tieu_chi"]}
        nhan = "gói Doanh nghiệp" if ten == "dn" else "gói Free"
        if t["kha_dung"]["xep"] != "dat" and t["kha_dung"]["gia_tri"] is not None:
            out.append(f"{nhan}: tỷ lệ thành công {t['kha_dung']['gia_tri']}% chưa đạt chuẩn 99,9% của API doanh nghiệp.")
        if t["do_tre"]["xep"] == "chua_dat":
            out.append(f"{nhan}: độ trễ p95 {t['do_tre']['gia_tri']} ms, cao hơn ngưỡng 1.000 ms; nên xem lại cache / vị trí máy chủ "
                       "(edge hiện ở Hồng Kông).")
        if t["do_tuoi"]["xep"] in ("kha", "chua_dat"):
            v = t["do_tuoi"]["gia_tri"]
            out.append(f"{nhan}: từ lúc thấy file tới lúc có số trung vị {so_vn(v)} phút (~{so_vn(v / 60, 1)} giờ), "
                       "chậm hơn nhiều so với mục tiêu 15 phút Wealbee công bố"
                       + (". Có thể do tồn đọng giai đoạn mới ra mắt API (v1, 11/2026): theo dõi thêm vài tuần." if v > 24 * 60 else "."))
        if t["chat_luong"]["xep"] in ("kha", "chua_dat"):
            out.append(f"{nhan}: chỉ {t['chat_luong']['gia_tri']}% BCTC ở trạng thái verified, còn lại cần soát (needs_review).")
        if g["tong"].get("lech_ky"):
            out.append(f"{nhan}: {len(g['tong']['lech_ky'])} BCTC có tên file PDF gốc ghi quý khác kỳ của số liệu: "
                       f"{', '.join(g['tong']['lech_ky'][:8])}{'…' if len(g['tong']['lech_ky']) > 8 else ''}. Một phần có thể do niên độ "
                       "lệch năm dương lịch (VD CMG, SBT, HSG), cần đối chiếu tay; không tính vào điểm.")
        ml = g["tong"].get("ma_la") or {}
        if ml.get("n") and any(not x.startswith("404") for x in ml.get("ma", [])):
            out.append(f"{nhan}: gọi mã không tồn tại trả {', '.join(ml['ma'])} thay vì 404 not_found (dễ làm khách hiểu nhầm là thiếu quyền).")
        if t["rate_limit"]["xep"] == "chua_dat":
            out.append(f"{nhan}: giới hạn tốc độ chưa minh bạch (thiếu header RateLimit hoặc 429 không kèm Retry-After).")
    for ten, g in goi.items():
        cham = [(e, v["p50"]) for e, v in (g["tong"].get("theo_ep") or {}).items() if v.get("n") and (v.get("p50") or 0) > 2000]
        if cham:
            out.append(("Gói Doanh nghiệp" if ten == "dn" else "Gói Free") + ": endpoint chậm bất thường (p50 > 2 giây): "
                       + ", ".join(f"{e} {so_vn(ms)} ms" for e, ms in cham) + ".")
    if "free" in goi and "dn" in goi and goi["free"]["tong"].get("so_request") and goi["dn"]["tong"].get("so_request"):
        a, b = goi["free"]["tong"]["do_tre"].get("p95"), goi["dn"]["tong"]["do_tre"].get("p95")
        if a and b:
            out.append(f"Độ trễ p95: Free {a} ms so với Doanh nghiệp {b} ms "
                       + ("(gần như nhau: cùng hạ tầng, gói chỉ khác quyền và giới hạn)." if abs(a - b) / max(a, b) < 0.15 else
                          "(gói Doanh nghiệp nhanh hơn rõ)." if b < a else "(gói Doanh nghiệp chậm hơn - cần xem lại)."))
        qa, qb = (goi["free"]["tong"]["rate_limit"].get("chinh_sach") or {}).get("q"), (goi["dn"]["tong"]["rate_limit"].get("chinh_sach") or {}).get("q")
        if qa and qb:
            out.append(f"Giới hạn tốc độ: Free {qa} request / phút, Doanh nghiệp {qb} request / phút.")
    return out or ["Chưa đủ dữ liệu để nhận xét (cần khoá API và vài giờ quét)."]


def tao(ghi: bool = True) -> dict:
    rs = doc_tat_ca()
    chung = [r for r in rs if r.get("goi") == "chung"]
    hl = [h for r in chung for h in r.get("health", [])]
    bao_mat = next((r["bao_mat"] for r in reversed(chung) if r.get("bao_mat")), None)
    goi = {}
    for ten in ("free", "dn"):
        cua = [r for r in rs if r.get("goi") == ten]
        theo_nguon = {n: tong_hop_goi([r for r in cua if r["nguon"] == n]) for n in sorted({r["nguon"] for r in cua})}
        tong = tong_hop_goi([r for r in cua if r.get("luot")]) if cua else tong_hop_goi([])
        tc = cham_diem(tong, bao_mat)
        goi[ten] = {"tong": tong, "theo_nguon": theo_nguon, "tieu_chi": tc, "diem": diem_tong(tc)}
    bc = {"tao_luc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
          "tu": rs[0]["luc"] if rs else None, "den": rs[-1]["luc"] if rs else None, "so_luot": len(rs),
          "nguon": sorted({r["nguon"] for r in rs}),
          "health": {"n": len(hl), "ok": sum(bool(h.get("dung")) for h in hl),
                     "do_tre": _thong_ke([h["ms_tong"] for h in hl if h.get("dung") and not h.get("lanh")])},
          "bao_mat": bao_mat, "goi": goi, "nhan_xet": nhan_xet(goi)}
    if ghi:
        RA.parent.mkdir(parents=True, exist_ok=True)
        RA.write_text(json.dumps(ma_hoa.goi(bc), separators=(",", ":")), encoding="utf-8")
    return bc
