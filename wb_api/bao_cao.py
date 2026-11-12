"""Báo cáo đánh giá Wealbee Data API theo tiêu chí của một API dữ liệu cho doanh nghiệp (mã hoá cho trang docs/bao-cao).

Viết lại 12/11/2026 để số liệu phản ánh đúng API, không lẫn sự cố của máy đo:
- Lỗi mạng phía máy đo (DNS không phân giải; hoặc cùng lượt đó API Vietstock và API tin của app cũng lỗi mạng) bị loại khỏi
  phép tính và đếm riêng. Chỉ lỗi do API (5xx, quá thời gian khi mạng máy đo vẫn bình thường) mới bị trừ điểm.
- Lượt đo của 1 gói chỉ tính khi /me xác nhận đúng gói; máy mất mạng ngay từ /me thì bỏ cả lượt
  (trước đây các lượt này bị ghi vào "gói Free" dù khoá Free đã thành gói Doanh nghiệp).
- Độ trễ chấm theo góc đo ở Việt Nam (trải nghiệm của khách hàng thật); góc đo GitHub (Mỹ) để đối chiếu. Không gộp 2 góc đo.
- Độ tươi và chất lượng dữ liệu tính trên toàn bộ BCTC đã đồng bộ về web Doanh nghiệp, không chỉ vài BCTC mẫu mỗi lượt.
- Bảo mật lấy kết quả hợp lệ mới nhất của từng phép kiểm (lượt kiểm bị mất mạng không ghi đè).
- Gói chỉ được chấm khi có ít nhất TOI_THIEU lượt đo hợp lệ.

Tiêu chí (ngưỡng theo thông lệ API dữ liệu tài chính cho doanh nghiệp + mục tiêu Wealbee tự công bố):
  1 Tính sẵn sàng       request thành công / request hợp lệ                     Đạt ≥ 99,9% · Khá ≥ 99%
  2 Độ trễ p95          đo từ Việt Nam, kết nối đã mở                           Đạt ≤ 500 ms · Khá ≤ 1.000 ms
  3 Phản hồi đầu p50    TTFB, đo từ Việt Nam                                    Đạt ≤ 300 ms · Khá ≤ 600 ms
  4 Lỗi phía máy chủ    5xx + quá thời gian / lỗi kết nối khi mạng máy đo ổn     Đạt ≤ 0,1% · Khá ≤ 1%
  5 Request chậm        tỷ lệ request quá 1 giây (đo từ Việt Nam)               Đạt ≤ 1% · Khá ≤ 5%
  6 Chuẩn lỗi           400/401/404 đúng mã + đúng RFC 9457                     Đạt 100% · Khá ≥ 90%
  7 Giới hạn tốc độ     header RateLimit đủ + 429 đúng lúc, có Retry-After      Đạt / Khá / Chưa đạt
  8 Độ tươi BCTC        thấy file -> có số trên API (trung vị)                  Đạt ≤ 15 phút (Wealbee cam kết) · Khá ≤ 60
  9 BCTC đã kiểm chứng  tỷ lệ BCTC "verified"                                   Đạt ≥ 95% · Khá ≥ 85%
 10 Độ phủ              số công ty có BCTC quý gần nhất                         Đạt ≥ 700 · Khá ≥ 600
 11 Bảo mật             TLS ≥ 1.2, HSTS, http -> https, từ chối khoá qua URL     Đạt 4/4 · Khá 3/4
"""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import ma_hoa

ROOT = Path(__file__).resolve().parent.parent
DO = ROOT / "data" / "do"
RA = ROOT / "docs" / "bao-cao" / "bao_cao.enc"
WEB_DN = ROOT / "docs" / "doanh-nghiep" / "data"
LOI_CO_Y = ("err_400", "err_404", "err_401")
THONG_TIN = ("info_ma_la",)                     # bài đo chỉ ghi nhận, không chấm
TOI_THIEU = 12                                  # số lượt đo hợp lệ tối thiểu để chấm 1 gói
DNS = ("getaddrinfo", "11001", "name or service not known", "temporary failure in name resolution",
       "nodename nor servname", "no address associated")
LY_DO = {"extractor_note": "bộ chép số để lại ghi chú", "missing_data": "thiếu số liệu",
         "cross_reference_mismatch": "số không khớp giữa các bảng", "comparative_mismatch": "số kỳ so sánh không khớp BCTC kỳ trước",
         "cash_flow_withheld": "tạm giữ lưu chuyển tiền tệ", "independent_read_mismatch": "hai lần đọc độc lập ra số khác nhau",
         "balance_missing": "thiếu cân đối kế toán", "cell_corrected": "có ô số phải sửa", "comparative_incomplete": "thiếu số kỳ so sánh"}
TEN_EP = {"companies": "Danh sách công ty", "company": "Chi tiết công ty", "latest": "BCTC mới nhất của 1 mã",
          "statements_list": "Danh sách BCTC", "statements_page2": "Danh sách BCTC (trang 2)", "statement_full": "BCTC đầy đủ",
          "versions": "Lịch sử phiên bản BCTC", "filings": "Danh sách file BCTC", "events": "Sự kiện", "me": "Thông tin gói (/me)",
          "news": "Tin tức", "news_detail": "Chi tiết tin", "news_ma": "Tin theo mã"}


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
            "tb": round(tb, 1), "max": round(max(xs), 1), "tren_1s": round(100 * sum(x > 1000 for x in xs) / len(xs), 2)}


def _xep(gia_tri, dat, kha, lon_hon_tot=True) -> str:
    if gia_tri is None:
        return "chua_du"
    if lon_hon_tot:
        return "dat" if gia_tri >= dat else "kha" if gia_tri >= kha else "chua_dat"
    return "dat" if gia_tri <= dat else "kha" if gia_tri <= kha else "chua_dat"


def _tg(s) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def so_vn(x, d: int = 0) -> str:
    return "—" if x is None else f"{x:,.{d}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def pt_vn(x) -> str:
    """Phần trăm gọn: 100 -> "100", 99.95 -> "99,95"."""
    return "—" if x is None else (f"{x:.2f}".rstrip("0").rstrip(".")).replace(".", ",")


CUM = {"kha_dung": "tỷ lệ request thành công", "do_tre": "độ trễ p95", "ttfb": "thời gian phản hồi byte đầu",
       "loi_may_chu": "lỗi phía máy chủ", "on_dinh": "tỷ lệ request chậm trên 1 giây", "chuan_loi": "chuẩn báo lỗi",
       "rate_limit": "minh bạch giới hạn tốc độ", "do_tuoi": "độ tươi BCTC", "chat_luong": "tỷ lệ BCTC đã kiểm chứng",
       "do_phu": "độ phủ", "bao_mat": "bảo mật"}


def ngay_vn(s) -> str:
    t = _tg(s)
    return t.astimezone(timezone(timedelta(hours=7))).strftime("%d/%m") if t else "—"


# ---------------------------------------------------------------- làm sạch số đo
def _mat_mang(l: dict) -> bool:
    m = (l.get("loi_mang") or "").lower()
    return bool(m) and any(s in m for s in DNS)


def lam_sach(rs: list[dict]) -> tuple[list[dict], dict[tuple, dict], dict]:
    """Bỏ lỗi do máy đo. Trả về (bản ghi gói đã làm sạch, bản ghi chung đã làm sạch theo lượt, thống kê phần bị loại)."""
    chung_goc = {(r["luc"], r["nguon"]): r for r in rs if r.get("goi") == "chung"}
    loai = {"luot_mat_mang": set(), "request": Counter(), "luot_goi": Counter()}
    chung = {}
    for k, c in chung_goc.items():
        dc = [x for t in ("health", "vietstock", "tin") for x in c.get(t, [])]
        hong = bool(dc) and all(x.get("loi_mang") for x in dc)              # mọi host đều lỗi mạng: máy đo mất mạng
        if hong or any(_mat_mang(x) for x in dc):
            loai["luot_mat_mang"].add(k)
        cc = dict(c)
        for t in ("health", "vietstock", "tin"):
            cc[t] = [x for x in c.get(t, []) if not (x.get("loi_mang") and (hong or _mat_mang(x)))]
        cc["_hong"] = hong
        chung[k] = cc
    out = []
    for r in rs:
        if r.get("goi") not in ("free", "dn"):
            continue
        k = (r["luc"], r["nguon"])
        if r.get("mat_mang"):
            loai["luot_mat_mang"].add(k)
            loai["luot_goi"][r["goi"]] += 1
            continue
        if not r.get("luot"):
            out.append(r)                                                      # bỏ qua / sai gói / lỗi cấu hình: giữ để hiện ghi chú
            continue
        hong = chung.get(k, {}).get("_hong", False)
        loi_md = lambda l: bool(l.get("loi_mang")) and (hong or _mat_mang(l))   # noqa: E731
        me = next((l for l in r["luot"] if l["ep"] == "me"), None)
        if me is not None and me.get("status") != 200 and loi_md(me):         # không xác nhận được gói: bỏ cả lượt
            loai["luot_mat_mang"].add(k)
            loai["luot_goi"][r["goi"]] += 1
            loai["request"][r["goi"]] += len(r["luot"])
            continue
        luot = [l for l in r["luot"] if not loi_md(l)]
        loai["request"][r["goi"]] += len(r["luot"]) - len(luot)
        out.append({**r, "luot": luot})
    return out, chung, {"luot_mat_mang": len(loai["luot_mat_mang"]), "request": dict(loai["request"]),
                        "luot_goi": dict(loai["luot_goi"])}


# ---------------------------------------------------------------- tổng hợp 1 gói
def tong_hop(rs: list[dict]) -> dict:
    """Số liệu của 1 gói (1 góc đo hoặc gộp) từ bản ghi đã làm sạch."""
    rs = [r for r in rs if r.get("luot")]
    luot = [l for r in rs for l in r["luot"]]
    thuong = [l for l in luot if l["ep"] not in LOI_CO_Y + THONG_TIN]
    am = [l for l in thuong if l.get("status") != 429]
    ok = [l for l in am if l.get("dung")]
    may_chu = [l for l in am if l.get("loi_mang") or (l.get("status") or 0) >= 500]
    am_nong = [l for l in ok if not l.get("lanh")]
    theo_ep = defaultdict(list)
    for l in am_nong:
        theo_ep[l["ep"]].append(l["ms_tong"])
    loi_cy = [l for l in luot if l["ep"] in LOI_CO_Y]
    loi_ds = Counter()
    for l in am:
        if not l.get("dung"):
            loi_ds[(l.get("loi_mang") or "").split(":")[0] or f"HTTP {l.get('status')} {l.get('code') or ''}".strip()] += 1
    co_rl = [l for l in ok if l.get("rl", {}).get("q") is not None and l.get("rl", {}).get("r") is not None]
    chuoi = []
    for r in rs:
        ms = [l["ms_tong"] for l in r["luot"] if l.get("dung") and l["ep"] not in LOI_CO_Y + THONG_TIN and not l.get("lanh")]
        n = [l for l in r["luot"] if l["ep"] not in LOI_CO_Y + THONG_TIN and l.get("status") != 429]
        chuoi.append({"luc": r["luc"], "nguon": r["nguon"], "p50": _pct(ms, 50), "p95": _pct(ms, 95),
                      "ok": sum(bool(l.get("dung")) for l in n), "n": len(n)})
    ma_la = [(r["luc"], l) for r in rs for l in r["luot"] if l["ep"] == "info_ma_la" and l.get("status")]
    return {
        "so_luot": len(rs), "so_request": len(luot), "so_request_cham": len(am),
        "kha_dung": round(100 * len(ok) / len(am), 3) if am else None,
        "loi_may_chu": round(100 * len(may_chu) / len(am), 3) if am else None,
        "do_tre": _thong_ke([l["ms_tong"] for l in am_nong]),
        "ttfb": _thong_ke([l["ms_ttfb"] for l in am_nong if l.get("ms_ttfb")]),
        "lanh": _thong_ke([l["ms_tong"] for l in ok if l.get("lanh")]),
        "theo_ep": {k: _thong_ke(v) for k, v in sorted(theo_ep.items())},
        "chuan_loi": {"n": len(loi_cy), "dung_ma": sum(bool(l.get("dung")) for l in loi_cy),
                      "rfc9457": sum(bool(l.get("rfc9457")) for l in loi_cy)},
        "co_header_rl": round(100 * len(co_rl) / len(ok), 1) if ok else None,
        "chinh_sach_rl": next(({"q": l["rl"].get("q"), "w": l["rl"].get("w")} for l in reversed(ok) if l.get("rl", {}).get("q")), None),
        "loi": dict(loi_ds), "chuoi": chuoi[-24 * 30:],
        "ma_la": {"hien_tai": (f"{ma_la[-1][1].get('status')} {ma_la[-1][1].get('code') or ''}".strip() if ma_la else None),
                  "lan_403_cuoi": next((t for t, l in reversed(ma_la) if l.get("status") == 403), None),
                  "dem": dict(Counter(f"{l.get('status')} {l.get('code') or ''}".strip() for _, l in ma_la))},
    }


def tong_hop_goi(rs: list[dict]) -> dict:
    """Gói: số liệu gộp + từng góc đo + các phần chỉ có ở bản ghi (quyền, độ phủ, tin, bắn dồn)."""
    co = [r for r in rs if r.get("luot")]
    tong = tong_hop(co)
    theo_nguon = {n: tong_hop([r for r in co if r["nguon"] == n]) for n in sorted({r["nguon"] for r in co})}
    vn = theo_nguon.get("may-vn") or {}
    goc = "may-vn" if (vn.get("do_tre") or {}).get("n", 0) >= 50 else max(theo_nguon, key=lambda n: theo_nguon[n]["do_tre"].get("n", 0), default=None)
    tin = {}
    for r in co:
        for i, p in (r.get("tin") or {}).get("tre") or []:
            tin[i] = p
    tin_moi = next((r["tin"] for r in reversed(co) if r.get("tin")), None)
    lk = sorted({x for r in co for x in (r.get("lech_ky") or [])})
    phu = next((r["phu"] for r in reversed(co) if (r.get("phu") or {}).get("so_cong_ty")), None)
    return {"tong": tong, "theo_nguon": theo_nguon, "goc_cham": goc,
            "quyen": next((r.get("me") for r in reversed(rs) if r.get("me")), None),
            "phu": phu, "lech_ky": lk,
            "ban_don": next((r["ban_don"] for r in reversed(co) if r.get("ban_don")), None),
            "tin": {"n": len(tin), "tre": _thong_ke(list(tin.values())) if tin else {"n": 0},
                    "trong_15p": round(100 * sum(v <= 15 for v in tin.values()) / len(tin), 1) if tin else None,
                    "trong_60p": round(100 * sum(v <= 60 for v in tin.values()) / len(tin), 1) if tin else None,
                    "mau": tin_moi},
            "tu": co[0]["luc"] if co else None, "den": co[-1]["luc"] if co else None,
            "ghi_chu": next((r.get("bo_qua") or r.get("sai_goi") or r.get("loi_cau_hinh") for r in reversed(rs)
                             if (r.get("bo_qua") or r.get("sai_goi") or r.get("loi_cau_hinh")) and (not co or r["luc"] > co[-1]["luc"])), None)}


# ---------------------------------------------------------------- dữ liệu BCTC đã đồng bộ (độ tươi, chất lượng)
def du_lieu_web() -> dict:
    """Toàn bộ BCTC gói Doanh nghiệp đã đồng bộ về web: độ tươi (thấy file -> có số) + trạng thái + phép kiểm."""
    tuoi, chep, am, tt, ly_do, kd, kt, n = [], [], [], Counter(), Counter(), 0, 0, 0
    for f in sorted((WEB_DN / "ma").glob("*.json")):
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for ky, st in (m.get("ky") or {}).items():
            n += 1
            tt[st.get("status") or "?"] += 1
            for x in st.get("review_reasons") or []:
                ly_do[x if isinstance(x, str) else str(x.get("code") if isinstance(x, dict) else x)] += 1
            kd += (st.get("kiem") or {}).get("dat") or 0
            kt += (st.get("kiem") or {}).get("tong") or 0
            ng = st.get("nguon_goc") or {}
            a, b, e = _tg(ng.get("detected_at")), _tg(ng.get("first_published_at")), _tg(ng.get("extracted_at"))
            if a and b:
                p = (b - a).total_seconds() / 60
                if p < 0:                                                      # công bố trước lúc "thấy file": mốc bất thường
                    am.append(st.get("id") or f"{m.get('ma')}.{ky}")
                else:
                    tuoi.append(p)
            if a and e and e >= a:
                chep.append((e - a).total_seconds() / 60)
    if not n:
        return {}
    chua_san = Counter()
    try:
        for c in json.loads((WEB_DN / "cong_ty.json").read_text(encoding="utf-8")).get("ds", []):
            if not (c.get("coverage") or {}).get("latest_period"):
                chua_san[c.get("exchange") or "?"] += 1
    except (OSError, ValueError):
        pass
    return {"so_bctc": n, "chua_co_so_theo_san": dict(chua_san.most_common()), "trang_thai": dict(tt), "verified": round(100 * tt.get("verified", 0) / n, 1),
            "ly_do": [[LY_DO.get(k, k), v] for k, v in ly_do.most_common(6)],
            "kiem_dat": round(100 * kd / kt, 1) if kt else None, "kiem": [kd, kt],
            "tuoi": {"n": len(tuoi), "p50": _pct(tuoi, 50), "p90": _pct(tuoi, 90),
                     "trong_15p": round(100 * sum(v <= 15 for v in tuoi) / len(tuoi), 1) if tuoi else None,
                     "trong_60p": round(100 * sum(v <= 60 for v in tuoi) / len(tuoi), 1) if tuoi else None,
                     "trong_24h": round(100 * sum(v <= 1440 for v in tuoi) / len(tuoi), 1) if tuoi else None,
                     "chep_p50": _pct(chep, 50), "bat_thuong": len(am), "bat_thuong_mau": am[:6]}}


def bao_mat_moi_nhat(chung: list[dict]) -> dict:
    """Kết quả hợp lệ mới nhất của từng phép kiểm bảo mật + mốc Wealbee sửa (nếu có)."""
    out, lich_su = {}, []
    for c in chung:
        b = c.get("bao_mat") or {}
        for k, v in b.items():
            if v is not None and not k.endswith("_loi"):
                out[k] = v
        if b.get("khoa_qua_query_bi_tu_choi") is not None:
            lich_su.append((c["luc"], b["khoa_qua_query_bi_tu_choi"]))
    if any(not v for _, v in lich_su) and lich_su and lich_su[-1][1]:
        out["khoa_query_loi_luc"] = max(t for t, v in lich_su if not v)
        out["khoa_query_sua_luc"] = next(t for t, v in lich_su if v and t > out["khoa_query_loi_luc"])
    return out


# ---------------------------------------------------------------- chấm điểm
def cham_diem(g: dict, web: dict, bm: dict) -> list[dict]:
    t, vn = g["tong"], g["theo_nguon"].get(g["goc_cham"]) or {}
    don = g.get("ban_don") or {}
    co_h = t.get("co_header_rl") or 0
    if don.get("luot_429"):
        rl = "dat" if don.get("retry_after") and don.get("rfc9457_429") and co_h >= 99 and don.get("sau_retry_after", 200) == 200 else "kha"
    elif t.get("co_header_rl") is None:
        rl = "chua_du"
    else:
        rl = "dat" if co_h >= 99 else "kha" if co_h >= 90 else "chua_dat"       # chưa chạm 429: chấm theo header
    cl = t["chuan_loi"]
    chuan = round(100 * min(cl["dung_ma"], cl["rfc9457"]) / cl["n"], 1) if cl["n"] else None
    bm_diem = None
    if bm.get("tls"):
        bm_diem = sum([bm.get("tls") in ("TLSv1.2", "TLSv1.3"), bool(bm.get("hsts")), bool(bm.get("http_sang_https")),
                       bool(bm.get("khoa_qua_query_bi_tu_choi"))])
    phu = g.get("phu") or {}
    co_so = (phu.get("so_cong_ty") or 0) - (phu.get("ky_moi_nhat") or {}).get("chưa có số", 0) if phu else None
    tuoi = (web.get("tuoi") or {}).get("p50")
    kq = [
        ("kha_dung", "Tính sẵn sàng", t["kha_dung"], "%", _xep(t["kha_dung"], 99.9, 99.0), 15, "≥ 99,9%"),
        ("do_tre", "Độ trễ p95", vn.get("do_tre", {}).get("p95"), "ms", _xep(vn.get("do_tre", {}).get("p95"), 500, 1000, False), 12, "≤ 500 ms"),
        ("ttfb", "Phản hồi byte đầu p50", vn.get("ttfb", {}).get("p50"), "ms", _xep(vn.get("ttfb", {}).get("p50"), 300, 600, False), 6, "≤ 300 ms"),
        ("loi_may_chu", "Lỗi phía máy chủ", t["loi_may_chu"], "%", _xep(t["loi_may_chu"], 0.1, 1.0, False), 10, "≤ 0,1%"),
        ("on_dinh", "Request chậm trên 1 giây", vn.get("do_tre", {}).get("tren_1s"), "%",
         _xep(vn.get("do_tre", {}).get("tren_1s"), 1, 5, False), 6, "≤ 1%"),
        ("chuan_loi", "Báo lỗi đúng chuẩn RFC 9457", chuan, "%", _xep(chuan, 100, 90), 6, "100%"),
        ("rate_limit", "Giới hạn tốc độ minh bạch", t.get("co_header_rl"), "% có header", rl, 7, "header đủ + 429 đúng"),
        ("do_tuoi", "Độ tươi BCTC (trung vị)", tuoi, "phút", _xep(tuoi, 15, 60, False), 14, "≤ 15 phút"),
        ("chat_luong", "BCTC đã kiểm chứng", web.get("verified"), "%", _xep(web.get("verified"), 95, 85), 10, "≥ 95%"),
        ("do_phu", "Công ty có BCTC quý mới nhất", co_so, "công ty", _xep(co_so, 700, 600), 7, "≥ 700"),
        ("bao_mat", "Bảo mật", bm_diem, "/4", _xep(bm_diem, 4, 3), 7, "4/4"),
    ]
    return [{"ma": a, "ten": b, "gia_tri": c, "don_vi": d, "xep": e, "trong_so": f, "nguong": h} for a, b, c, d, e, f, h in kq]


def diem_tong(tc: list[dict]) -> float | None:
    he = {"dat": 1.0, "kha": 0.6, "chua_dat": 0.15}
    co = [t for t in tc if t["xep"] in he]
    if not co:
        return None
    return round(100 * sum(he[t["xep"]] * t["trong_so"] for t in co) / sum(t["trong_so"] for t in co), 1)


def xep_tong(d: float | None) -> str:
    return "chua_du" if d is None else "dat" if d >= 85 else "kha" if d >= 65 else "chua_dat"


# ---------------------------------------------------------------- nhận định (viết bằng lời)
def nhan_dinh(g: dict, web: dict, bm: dict, loai: dict, bc: dict) -> dict:
    t, vn = g["tong"], g["theo_nguon"].get(g["goc_cham"]) or {}
    tc = {x["ma"]: x for x in g["tieu_chi"]}
    goc = "Việt Nam" if g["goc_cham"] == "may-vn" else "Mỹ (GitHub)"
    tuoi = web.get("tuoi") or {}
    manh, van_de, da_sua, gioi_han = [], [], [], []

    # --- điểm mạnh
    if tc["kha_dung"]["xep"] == "dat":
        manh.append(f"Ổn định: {pt_vn(t['kha_dung'])}% request thành công trên {so_vn(t['so_request_cham'])} request hợp lệ"
                    + (", không ghi nhận lỗi nào phía máy chủ." if not t["loi_may_chu"] else f", lỗi phía máy chủ {so_vn(t['loi_may_chu'], 2)}%."))
    if tc["do_tre"]["xep"] == "dat":
        manh.append(f"Nhanh: đo từ {goc}, một nửa số request xong trong {so_vn(vn['do_tre']['p50'])} ms và 95% xong trong "
                    f"{so_vn(vn['do_tre']['p95'])} ms (chuẩn API doanh nghiệp: 500 ms).")
    if tc["chuan_loi"]["xep"] == "dat":
        manh.append("Báo lỗi chuẩn: mọi lỗi 400 / 401 / 404 đều đúng mã HTTP và đúng định dạng RFC 9457 (có type, title, code), "
                    "lập trình viên phía khách xử lý lỗi dễ.")
    if tc["rate_limit"]["xep"] == "dat":
        q = (t.get("chinh_sach_rl") or {}).get("q")
        manh.append(f"Giới hạn tốc độ minh bạch: mọi phản hồi có header RateLimit{f' ({q} request/phút)' if q else ''}, "
                    "khách biết còn bao nhiêu lượt để tự giãn nhịp.")
    if tc["bao_mat"]["xep"] == "dat":
        manh.append(f"Bảo mật đủ chuẩn: {bm.get('tls')}, HSTS, tự chuyển http → https, từ chối khoá API gửi qua URL.")
    if tc["do_phu"]["xep"] == "dat":
        phu = g.get("phu") or {}
        manh.append(f"Độ phủ rộng: {so_vn(tc['do_phu']['gia_tri'])} công ty đã có BCTC quý mới nhất "
                    f"(danh mục {so_vn(phu.get('so_cong_ty'))} mã, gồm HOSE, HNX, UPCOM).")
    if web.get("kiem_dat") and web["kiem_dat"] >= 95:
        manh.append(f"Số liệu có kiểm tra: {so_vn(web['kiem_dat'], 1)}% phép kiểm tự động trên BCTC đạt "
                    f"({so_vn(web['kiem'][0])}/{so_vn(web['kiem'][1])}), mỗi BCTC có link file gốc và số trang để đối chiếu.")
    if (g.get("tin") or {}).get("n"):
        manh.append("Data API đã có endpoint tin tức /news (lọc theo mã, kèm nguồn bài gốc, sắc thái tích cực / tiêu cực, phân loại tin).")

    # --- vấn đề
    if tc["do_tuoi"]["xep"] in ("kha", "chua_dat") and tuoi.get("n"):
        van_de.append({"muc": "cao" if tc["do_tuoi"]["xep"] == "chua_dat" else "trung_binh",
                       "tieu_de": "BCTC về API chậm hơn cam kết 15 phút",
                       "chi_tiet": f"Từ lúc Wealbee thấy file BCTC đến lúc có số trên API: trung vị {so_vn(tuoi['p50'], 0)} phút. "
                                   f"Chỉ {so_vn(tuoi['trong_15p'], 0)}% BCTC có số trong 15 phút, {so_vn(tuoi['trong_60p'], 0)}% trong 1 giờ; "
                                   f"10% chậm nhất mất hơn {so_vn(tuoi['p90'] / 60, 1)} giờ (tính trên {so_vn(tuoi['n'])} BCTC).",
                       "de_xuat": "Hỏi Wealbee về cam kết độ tươi chính thức (SLA) và nhóm BCTC phải chờ lâu (file scan, file nặng?)."})
    if tc["chat_luong"]["xep"] in ("kha", "chua_dat") and web.get("so_bctc"):
        nr = web["trang_thai"].get("needs_review", 0)
        van_de.append({"muc": "trung_binh" if tc["chat_luong"]["xep"] == "kha" else "cao",
                       "tieu_de": f"{so_vn(100 - web['verified'], 0)}% BCTC chưa được kiểm chứng",
                       "chi_tiet": f"{so_vn(nr)}/{so_vn(web['so_bctc'])} BCTC ở trạng thái cần soát (needs_review). Lý do hay gặp: "
                                   + "; ".join(f"{a} ({b})" for a, b in web["ly_do"][:4]) + ".",
                       "de_xuat": "Khi hiển thị cho khách, gắn nhãn \"đang soát\" hoặc chỉ dùng BCTC verified; theo dõi tỷ lệ này hằng tuần."})
    if tuoi.get("bat_thuong"):
        van_de.append({"muc": "thap", "tieu_de": "Mốc thời gian bất thường",
                       "chi_tiet": f"{so_vn(tuoi['bat_thuong'])} BCTC có giờ công bố trên API sớm hơn giờ Wealbee \"thấy file\" "
                                   f"(VD {', '.join(tuoi['bat_thuong_mau'][:4])}). Có thể detected_at bị ghi lại khi file được phát hiện lần nữa.",
                       "de_xuat": "Hỏi Wealbee ý nghĩa detected_at khi BCTC có phiên bản mới; không dùng 2 mốc này để đo độ tươi các BCTC đó."})
    if g.get("lech_ky"):
        van_de.append({"muc": "thap", "tieu_de": "BCTC nghi gắn nhầm kỳ",
                       "chi_tiet": f"{len(g['lech_ky'])} BCTC có tên file PDF gốc ghi quý khác kỳ của số liệu: "
                                   f"{', '.join(g['lech_ky'][:8])}{'…' if len(g['lech_ky']) > 8 else ''}. "
                                   "Một phần có thể do năm tài chính lệch năm dương lịch.",
                       "de_xuat": "Đối chiếu tay vài trường hợp rồi gửi Wealbee nếu đúng là gắn nhầm."})
    cham = [(e, v) for e, v in (vn.get("theo_ep") or {}).items() if (v.get("p95") or 0) > 1000 and v.get("n", 0) >= 5]
    if cham or tc["on_dinh"]["xep"] in ("kha", "chua_dat"):
        ct = (f"{so_vn(vn['do_tre']['tren_1s'], 1)}% request (đo từ {goc}) mất hơn 1 giây, chậm nhất {so_vn(vn['do_tre']['max'])} ms. "
              if vn.get("do_tre", {}).get("n") else "")
        if cham:
            ct += "Tập trung ở: " + "; ".join(f"{TEN_EP.get(e, e)} ({e}) p95 {so_vn(v['p95'])} ms dù trung vị chỉ {so_vn(v['p50'])} ms"
                                            for e, v in cham) + ". Các endpoint khác p95 dưới 1 giây."
        van_de.append({"muc": "thap", "tieu_de": "Thỉnh thoảng có request chậm trên 1 giây", "chi_tiet": ct.strip(),
                       "de_xuat": "Báo Wealbee kèm khung giờ; phía khách nên đặt timeout ≥ 5 giây và tự thử lại 1 lần."})
    phu = g.get("phu") or {}
    chua = (phu.get("ky_moi_nhat") or {}).get("chưa có số")
    if chua:
        van_de.append({"muc": "thap", "tieu_de": f"{so_vn(chua)} công ty trong danh mục chưa có BCTC nào",
                       "chi_tiet": f"Danh mục có {so_vn(phu.get('so_cong_ty'))} mã nhưng {so_vn(chua)} mã chưa có số"
                                   + (f", phần lớn là mã UPCOM ({so_vn(web['chua_co_so_theo_san']['UPCOM'])} mã theo danh mục đồng bộ gần nhất)."
                                      if (web.get("chua_co_so_theo_san") or {}).get("UPCOM") else "."),
                       "de_xuat": "Khi hiển thị cho khách, ẩn hoặc ghi rõ \"chưa có dữ liệu\" với các mã này."})
    tin = g.get("tin") or {}
    if tin.get("n") and (tin["tre"].get("p50") or 0) > 30:
        van_de.append({"muc": "thap", "tieu_de": "Tin tức về chậm hơn bài gốc",
                       "chi_tiet": f"Trung vị {so_vn(tin['tre']['p50'])} phút từ lúc bài gốc đầu tiên đăng đến lúc Wealbee có tin; "
                                   f"{so_vn(tin['trong_60p'], 0)}% tin có trong 1 giờ (tính trên {so_vn(tin['n'])} tin).",
                       "de_xuat": "Nếu cần tin nóng, hỏi Wealbee cách nhận tin qua webhook thay vì gọi định kỳ."})
    mau = tin.get("mau") or {}
    if mau.get("n") and mau.get("co_tom_tat", 0) < 0.7 * mau["n"]:
        van_de.append({"muc": "thap", "tieu_de": "Nhiều tin chưa có tóm tắt",
                       "chi_tiet": f"Trong {mau['n']} tin mới nhất, chỉ {mau.get('co_tom_tat', 0)} tin có tóm tắt và {mau.get('co_phan_tich', 0)} tin có bài phân tích.",
                       "de_xuat": "Hiển thị tiêu đề + nguồn khi chưa có tóm tắt; hỏi Wealbee thời gian trung bình để có tóm tắt."})

    # --- Wealbee đã sửa trong kỳ theo dõi
    if bm.get("khoa_query_sua_luc"):
        da_sua.append(f"Từ chối khoá API gửi qua URL: lần kiểm ngày {ngay_vn(bm['khoa_query_loi_luc'])} API còn chấp nhận khoá trong URL "
                      f"(dễ lộ khoá qua log, lịch sử trình duyệt); lần kiểm ngày {ngay_vn(bm['khoa_query_sua_luc'])} đã trả lỗi 401 credentials_in_url.")
    ml = t.get("ma_la") or {}
    if ml.get("lan_403_cuoi") and (ml.get("hien_tai") or "").startswith("404"):
        da_sua.append(f"Gọi mã không tồn tại: đến ngày {ngay_vn(ml['lan_403_cuoi'])} còn trả 403 ticker_not_entitled (dễ hiểu nhầm là thiếu quyền), "
                      "sau đó trả đúng 404 not_found.")
    elif (ml.get("hien_tai") or "").startswith("403"):
        van_de.append({"muc": "thap", "tieu_de": "Mã không tồn tại trả 403 thay vì 404",
                       "chi_tiet": "Gọi BCTC của mã không có thật trả 403 ticker_not_entitled, dễ làm khách tưởng thiếu quyền.",
                       "de_xuat": "Đề nghị Wealbee trả 404 not_found cho mã không tồn tại."})
    if (g.get("tin") or {}).get("n"):
        da_sua.append("Bổ sung endpoint tin tức /news vào Data API (trước 11/2026 tin chỉ có ở API riêng của app).")

    # --- giới hạn của phép đo
    if loai.get("luot_mat_mang"):
        gioi_han.append(f"{so_vn(loai['luot_mat_mang'])} lượt quét bị loại vì máy đo mất mạng (lỗi DNS; cùng lúc Vietstock và API tin của app "
                        "cũng lỗi). Đây là sự cố phía máy đo, không tính vào điểm của Wealbee.")
    gh = g["theo_nguon"].get("github") or {}
    if gh.get("so_luot") is not None and bc.get("tu"):
        ngay = max(1, (_tg(bc["den"]) - _tg(bc["tu"])).days)
        if gh["so_luot"] < ngay * 12:
            gioi_han.append(f"Góc đo từ Mỹ chỉ có {so_vn(gh['so_luot'])} lượt trong {ngay} ngày: lịch chạy hằng giờ của GitHub Actions hay bị "
                            "trễ hoặc bỏ lượt. Điểm độ trễ dựa trên góc đo ở Việt Nam.")
    don = g.get("ban_don") or {}
    if don and not don.get("luot_429"):
        gioi_han.append(f"Chưa chạm tới lỗi 429: lần bắn dồn gần nhất gửi {don.get('so_luot')} request liên tục mà vẫn trong giới hạn "
                        f"{don.get('q')} request/phút. Từ 12/11 bài bắn dồn vượt giới hạn vài request để kiểm hành vi 429 và Retry-After.")
    gioi_han.append("Độ tươi BCTC tính theo mốc thời gian Wealbee tự ghi (detected_at → first_published_at), chưa đối chiếu với giờ "
                    "doanh nghiệp đăng BCTC lên sàn.")

    # --- kết luận
    yeu = [x for x in g["tieu_chi"] if x["xep"] in ("kha", "chua_dat")]
    mo = (f"Gói Doanh nghiệp đạt {so_vn(g['diem'], 1)}/100. " if g.get("diem") is not None else "")
    van_hanh = all(tc[k]["xep"] == "dat" for k in ("kha_dung", "do_tre", "loi_may_chu"))
    if van_hanh:
        mo += (f"Về vận hành, API ổn định và nhanh: {pt_vn(t['kha_dung'])}% request thành công, không có lỗi phía máy chủ; "
               f"đo từ {goc}, 95% request xong trong {so_vn(vn['do_tre']['p95'])} ms. ")
    else:
        mo += "Về vận hành, API chưa đạt chuẩn doanh nghiệp ở " + ", ".join(
            CUM[k] for k in ("kha_dung", "do_tre", "loi_may_chu") if tc[k]["xep"] != "dat") + ". "
    if yeu:
        gt = lambda x: (f"{so_vn(x['gia_tri'], 0 if x['ma'] == 'do_tuoi' else 1)} {x['don_vi']}".replace(" %", "%"))  # noqa: E731
        mo += "Điểm trừ chính: " + "; ".join(
            f"{CUM[x['ma']]} ({gt(x)}, mục tiêu {x['nguong']})" for x in sorted(yeu, key=lambda x: -x["trong_so"])[:3]) + "."
    else:
        mo += "Tất cả tiêu chí đều đạt."
    return {"ket_luan": mo.strip(), "diem_manh": manh, "van_de": van_de, "da_sua": da_sua, "gioi_han": gioi_han}


# ---------------------------------------------------------------- dựng báo cáo
def _api_khac(chung: list[dict], key: str) -> dict:
    xs = [l for c in chung for l in c.get(key, [])]
    return {"n": len(xs), "ok": sum(bool(l.get("dung")) for l in xs),
            "theo_ep": {e: _thong_ke([l["ms_tong"] for l in xs if l["ep"] == e and l.get("dung")]) for e in sorted({l["ep"] for l in xs})}}


def tao(ghi: bool = True) -> dict:
    rs = doc_tat_ca()
    sach, chung_d, loai = lam_sach(rs)
    chung = [chung_d[k] for k in sorted(chung_d)]
    hl = [h for c in chung for h in c.get("health", [])]
    bm = bao_mat_moi_nhat(chung)
    web = du_lieu_web()
    bc = {"tao_luc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "phien_ban": 2,
          "tu": rs[0]["luc"] if rs else None, "den": rs[-1]["luc"] if rs else None, "so_luot": len(rs),
          "nguon": sorted({r["nguon"] for r in rs}), "loai": loai,
          "health": {"n": len(hl), "ok": sum(bool(h.get("dung")) for h in hl),
                     "do_tre": _thong_ke([h["ms_tong"] for h in hl if h.get("dung") and not h.get("lanh")])},
          "bao_mat": bm, "web": web, "tin_app": _api_khac(chung, "tin"), "vietstock": _api_khac(chung, "vietstock"), "goi": {}}
    for ten in ("free", "dn"):
        g = tong_hop_goi([r for r in sach if r.get("goi") == ten])
        du = g["tong"]["so_luot"] >= TOI_THIEU
        g["tieu_chi"] = cham_diem(g, web if ten == "dn" else {}, bm)
        g["du_lieu_du"] = du
        g["diem"] = diem_tong(g["tieu_chi"]) if du else None
        g["xep"] = xep_tong(g["diem"])
        bc["goi"][ten] = g
    dn = bc["goi"]["dn"]
    bc["nhan_dinh"] = nhan_dinh(dn, web, bm, loai, bc) if dn["du_lieu_du"] else \
        {"ket_luan": "Chưa đủ lượt đo hợp lệ của gói Doanh nghiệp để kết luận.", "diem_manh": [], "van_de": [], "da_sua": [], "gioi_han": []}
    fr = bc["goi"]["free"]
    fr["ghi_chu_goi"] = ("Từ 08/11/2026 tài khoản được nâng lên hợp đồng nên mọi khoá của tài khoản đều thành gói Doanh nghiệp; "
                         f"chỉ có {fr['tong']['so_luot']} lượt đo hợp lệ của gói Free"
                         + (f" ({ngay_vn(fr['tu'])}–{ngay_vn(fr['den'])}, lúc API mới ra mắt)" if fr["tu"] else "")
                         + ". Chưa đủ để chấm điểm. Muốn đánh giá gói Free cần khoá của một tài khoản tự phục vụ khác.") \
        if not fr["du_lieu_du"] else None
    if ghi:
        from . import thay_doi
        try:
            bc["thay_doi_moi"] = thay_doi.cap_nhat(sach + [c for c in chung], bc)
        except Exception as e:  # noqa: BLE001 - lỗi phần so sánh không chặn báo cáo chính
            bc["thay_doi_loi"] = str(e)[:200]
        RA.parent.mkdir(parents=True, exist_ok=True)
        RA.write_text(json.dumps(ma_hoa.goi(bc), separators=(",", ":")), encoding="utf-8")
    return bc
