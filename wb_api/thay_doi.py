"""Báo cáo thay đổi: sau mỗi lần dựng báo cáo, so lượt quét mới với trước đó; có cải thiện hoặc tệ đi rõ rệt thì viết 1 bản
báo cáo mới (docs/bao-cao/thay_doi.enc, mã hoá, hiện đầu trang báo cáo).

Chống báo nhầm vì nhiễu mạng:
- Xu hướng: trung vị 3 lượt gần nhất so với 24 lượt trước đó (cùng gói, cùng nơi đo), chỉ báo khi vượt ngưỡng rõ ràng.
- Lỗi: báo ngay lượt đầu xuất hiện.
- Mỗi tình trạng chỉ báo 1 lần lúc bắt đầu và 1 lần khi hết ("đã hồi phục"), không lặp lại mỗi giờ.
- Một lần: điểm tổng đổi ≥ 3, tiêu chí đổi xếp hạng, số công ty được phủ đổi, có BCTC nghi lệch kỳ mới.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from . import ma_hoa

ROOT = Path(__file__).resolve().parent.parent
TRANG_THAI = ROOT / "data" / "thay_doi.enc"
PHIEN_BAN = 2                                   # cách tính báo cáo (2: viết lại 12/11/2026, loại lỗi mạng của máy đo)
RA = ROOT / "docs" / "bao-cao" / "thay_doi.enc"
LOI_CO_Y = ("err_400", "err_404", "err_401", "info_ma_la")
TEN_GOI = {"free": "Gói Free", "dn": "Gói Doanh nghiệp"}
TEN_NGUON = {"github": "đo từ Mỹ (GitHub)", "may-vn": "đo từ Việt Nam"}
XEP = {"dat": "Đạt", "kha": "Khá", "chua_dat": "Chưa đạt", "chua_du": "Chưa đủ dữ liệu"}
HANG = {"chua_dat": 0, "kha": 1, "dat": 2}


def _doc(f: Path, mac_dinh):
    try:
        return ma_hoa.mo_goi(json.loads(f.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 - chưa có / khác mật khẩu
        return mac_dinh


def _ms(r: dict, ep: str | None = None) -> list[float]:
    return [l["ms_tong"] for l in r.get("luot", []) if l.get("dung") and not l.get("lanh") and l["ep"] not in LOI_CO_Y
            and (ep is None or l["ep"] == ep)]


def _med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def _so(x, d=0):
    return "—" if x is None else f"{x:,.{d}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def tinh_trang(rs: list[dict]) -> dict[str, dict]:
    """Các tình trạng đang có (khoá -> {loai: te_di|cai_thien, chu}) từ toàn bộ bản ghi đo."""
    out = {}
    nhom = {}
    for r in rs:
        if r.get("goi") in ("free", "dn") and r.get("luot"):
            nhom.setdefault((r["goi"], r["nguon"]), []).append(r)
    for (goi, nguon), ds in nhom.items():
        ten = f"{TEN_GOI[goi]} ({TEN_NGUON.get(nguon, nguon)})"
        moi = ds[-1]
        loi = [l for l in moi["luot"] if not l.get("dung") and l["ep"] not in LOI_CO_Y and l.get("status") != 429]
        if loi:
            out[f"{goi}|{nguon}|loi"] = {"loai": "te_di", "chu": f"{ten}: lượt mới nhất có {len(loi)} request lỗi ("
                                         + ", ".join(sorted({f"{l['ep']} {l.get('status') or l.get('loi_mang', '')[:30]}" for l in loi})[:4]) + ")"}
        gan, nen = ds[-3:], ds[-27:-3]
        if len(nen) < 6:
            continue
        a, b = _med([_med(_ms(r)) for r in gan]), _med([_med(_ms(r)) for r in nen])
        if a and b:
            if a > 1.5 * b and a - b > 100:
                out[f"{goi}|{nguon}|tre"] = {"loai": "te_di", "chu": f"{ten}: độ trễ trung vị tăng từ {_so(b)} ms lên {_so(a)} ms"}
            elif a < 0.67 * b and b - a > 100:
                out[f"{goi}|{nguon}|tre"] = {"loai": "cai_thien", "chu": f"{ten}: độ trễ trung vị giảm từ {_so(b)} ms còn {_so(a)} ms"}
        for ep in sorted({l["ep"] for r in gan for l in r["luot"]} - set(LOI_CO_Y)):
            a, b = _med([_med(_ms(r, ep)) for r in gan]), _med([_med(_ms(r, ep)) for r in nen])
            if not (a and b):
                continue
            if a > 2 * b and a - b > 300:
                out[f"{goi}|{nguon}|{ep}"] = {"loai": "te_di", "chu": f"{ten}: {ep} chậm đi, từ {_so(b)} ms lên {_so(a)} ms"}
            elif a < 0.5 * b and b - a > 300:
                out[f"{goi}|{nguon}|{ep}"] = {"loai": "cai_thien", "chu": f"{ten}: {ep} nhanh hơn, từ {_so(b)} ms còn {_so(a)} ms"}
        tg = lambda rr: _med([t["phut"] for r in rr for t in (r.get("tuoi_ds") or []) if t.get("phut") is not None])   # noqa: E731
        a, b = tg(gan), tg(nen)
        if a is not None and b:
            if a > 1.3 * b and a - b > 15:
                out[f"{goi}|{nguon}|tuoi"] = {"loai": "te_di", "chu": f"{ten}: độ tươi dữ liệu xấu đi (thấy file → có số) từ {_so(b)} lên {_so(a)} phút"}
            elif a < 0.7 * b and b - a > 15:
                out[f"{goi}|{nguon}|tuoi"] = {"loai": "cai_thien", "chu": f"{ten}: độ tươi dữ liệu tốt lên, từ {_so(b)} còn {_so(a)} phút"}
    chung = [r for r in rs if r.get("goi") == "chung"]
    if chung:
        moi = chung[-1]
        for k, ten in (("health", "Health check Wealbee API"), ("tin", "API tin tức app Wealbee"), ("vietstock", "API miễn phí Vietstock")):
            hong = [l for l in moi.get(k, []) if not l.get("dung")]
            if hong:
                out[f"chung|{k}"] = {"loai": "te_di", "chu": f"{ten}: lỗi ở lượt mới nhất ({len(hong)}/{len(moi.get(k, []))} request)"}
    return out


def chup(bc: dict) -> dict:
    """Ảnh chụp số liệu tổng hợp để so lần sau."""
    out = {}
    for goi, g in bc["goi"].items():
        out[goi] = {"diem": g["diem"], "xep": {t["ma"]: [t["ten"], t["xep"], t["gia_tri"], t["don_vi"]] for t in g["tieu_chi"]},
                    "so_cong_ty": (g.get("phu") or {}).get("so_cong_ty"), "lech_ky": g.get("lech_ky") or []}
    return out


def cap_nhat(rs: list[dict], bc: dict) -> dict | None:
    """Gọi sau mỗi lần dựng báo cáo; có thay đổi đáng kể thì ghi 1 bản báo cáo mới. Trả về bản mới (hoặc None)."""
    if not TRANG_THAI.exists():                                       # lần đầu: chỉ ghi mốc, chưa có gì để so
        TRANG_THAI.parent.mkdir(parents=True, exist_ok=True)
        TRANG_THAI.write_text(json.dumps(ma_hoa.goi({"tinh_trang": tinh_trang(rs), "chup": chup(bc), "phien_ban": PHIEN_BAN})),
                              encoding="utf-8")
        return None
    tt = _doc(TRANG_THAI, {"tinh_trang": {}, "chup": None})
    if tt.get("phien_ban") != PHIEN_BAN:                              # đổi cách tính: ghi mốc mới, không so với số tính theo cách cũ
        ban = {"luc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "cai_thien": [], "te_di": [], "diem": {},
               "diem_hien_tai": {g: v["diem"] for g, v in chup(bc).items()}, "loai_ban": "ghi_chu",
               "tieu_de": "Đổi cách tính báo cáo: không còn tính lỗi mạng của máy đo thành lỗi API",
               "ghi_chu": ["Lỗi mạng phía máy đo (DNS, máy mất mạng) được loại khỏi phép tính; trước đây chúng bị tính thành lỗi API "
                           "và kéo điểm xuống.",
                           "Độ trễ chấm theo góc đo ở Việt Nam; độ tươi và tỷ lệ kiểm chứng tính trên toàn bộ BCTC đã đồng bộ.",
                           "Gói Free chưa được chấm vì từ 08/11 không còn khoá Free hợp lệ.",
                           "Các bản thay đổi bên dưới mốc này dùng cách tính cũ."]}
        ds = _doc(RA, [])
        ds.insert(0, ban)
        RA.parent.mkdir(parents=True, exist_ok=True)
        RA.write_text(json.dumps(ma_hoa.goi(ds[:300]), separators=(",", ":")), encoding="utf-8")
        TRANG_THAI.write_text(json.dumps(ma_hoa.goi({"tinh_trang": tinh_trang(rs), "chup": chup(bc), "phien_ban": PHIEN_BAN})),
                              encoding="utf-8")
        return ban
    cu, moi = tt.get("tinh_trang") or {}, tinh_trang(rs)
    cai, te = [], []
    for k, v in moi.items():
        if k not in cu or cu[k]["loai"] != v["loai"]:
            (cai if v["loai"] == "cai_thien" else te).append(v["chu"])
    for k, v in cu.items():
        if k not in moi and v["loai"] == "te_di":
            cai.append("Đã hồi phục: " + v["chu"])
    truoc, sau = tt.get("chup"), chup(bc)
    diem = {}
    if truoc:
        for goi, s in sau.items():
            t = truoc.get(goi) or {}
            if s["diem"] is not None and t.get("diem") is not None and abs(s["diem"] - t["diem"]) >= 3:
                diem[goi] = [t["diem"], s["diem"]]
                (cai if s["diem"] > t["diem"] else te).append(f"{TEN_GOI[goi]}: điểm tổng {_so(t['diem'], 1)} → {_so(s['diem'], 1)}/100")
            for ma, (ten, xep, gt, dv) in s["xep"].items():
                cx = (t.get("xep") or {}).get(ma, [None, None])[1]
                if cx in HANG and xep in HANG and cx != xep:
                    (cai if HANG[xep] > HANG[cx] else te).append(f"{TEN_GOI[goi]}: {ten} {XEP[cx]} → {XEP[xep]} ({_so(gt, 1)} {dv})")
            if s["so_cong_ty"] and t.get("so_cong_ty") and s["so_cong_ty"] != t["so_cong_ty"]:
                (cai if s["so_cong_ty"] > t["so_cong_ty"] else te).append(
                    f"{TEN_GOI[goi]}: số công ty được phủ {_so(t['so_cong_ty'])} → {_so(s['so_cong_ty'])}")
            them = sorted(set(s["lech_ky"]) - set(t.get("lech_ky") or []))
            if them:
                te.append(f"{TEN_GOI[goi]}: thêm {len(them)} BCTC nghi lệch kỳ: {', '.join(them[:6])}")
    ban = None
    if cai or te:
        ban = {"luc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "cai_thien": cai, "te_di": te, "diem": diem,
               "diem_hien_tai": {g: v["diem"] for g, v in sau.items()},
               "tieu_de": ("Có cải thiện và có điểm tệ đi" if cai and te else "Cải thiện" if cai else "Tệ đi")
                          + f": {(te or cai)[0][:90]}"}
        ds = _doc(RA, [])
        ds.insert(0, ban)
        RA.parent.mkdir(parents=True, exist_ok=True)
        RA.write_text(json.dumps(ma_hoa.goi(ds[:300]), separators=(",", ":")), encoding="utf-8")
    TRANG_THAI.parent.mkdir(parents=True, exist_ok=True)
    TRANG_THAI.write_text(json.dumps(ma_hoa.goi({"tinh_trang": moi, "chup": sau, "phien_ban": PHIEN_BAN})), encoding="utf-8")
    return ban
