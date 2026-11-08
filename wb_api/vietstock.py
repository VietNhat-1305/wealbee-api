"""Nguồn miễn phí của Vietstock cho web bản Free (API chính thức Vietstock DataFeed phải mua; đây là các nguồn công khai):

    Giá:  https://api.vietstock.vn/tvnew/history?symbol=FPT&resolution=D&from=..&to=..   (API biểu đồ TradingView của Vietstock)
    Tin:  https://vietstock.vn/<id>/<chuyên-mục>.rss                                      (RSS chính thức)

Không có CORS -> mỗi giờ lấy về, xuất tĩnh:
    docs/vietstock/gia/<MA>.json     giá đóng cửa 1 năm theo ngày (mỗi mã làm mới tối đa 1 lần / ngày, xoay vòng)
    docs/vietstock/tin_moi.json      60 tin mới nhất · docs/vietstock/tin_ma/<MA>.json tin theo mã · chi_muc.json
Lấy chậm rãi (giãn nhịp) để không làm phiền máy chủ Vietstock.
"""
from __future__ import annotations

import html
import json
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

from .tin_tuc import _ghi

ROOT = Path(__file__).resolve().parent.parent
RA = ROOT / "docs" / "vietstock"
CACHE = ROOT / "data" / "vietstock_tin_cache.json"
API = "https://api.vietstock.vn/tvnew"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
H = {"User-Agent": UA, "Referer": "https://stockchart.vietstock.vn/"}
RSS = {"Cổ phiếu": "/830/chung-khoan/co-phieu.rss", "Doanh nghiệp": "/733/doanh-nghiep.rss", "Chứng khoán": "/144/chung-khoan.rss",
       "Giao dịch nội bộ": "/739/chung-khoan/giao-dich-noi-bo.rss", "Niêm yết": "/741/chung-khoan/niem-yet.rss",
       "Phân tích cơ bản": "/582/nhan-dinh-phan-tich/phan-tich-co-ban.rss", "Tài chính": "/734/tai-chinh.rss"}
VN = timezone(timedelta(hours=7))


def _do(c: httpx.Client, ep: str, url: str, params=None) -> tuple[dict, httpx.Response | None]:
    rec = {"ep": ep, "duong_dan": url.split("vietstock.vn")[-1], "luc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "kv": 200}
    t0 = time.perf_counter()
    try:
        r = c.get(url, params=params)
        rec.update(status=r.status_code, ms_tong=round((time.perf_counter() - t0) * 1000, 1), bytes=len(r.content), dung=r.status_code == 200)
        return rec, r
    except httpx.HTTPError as e:
        rec.update(ms_tong=round((time.perf_counter() - t0) * 1000, 1), loi_mang=f"{type(e).__name__}: {str(e)[:120]}", dung=False)
        return rec, None


def _lich_su(c: httpx.Client, ma: str, ngay: int = 370) -> tuple[dict, dict | None]:
    to = int(time.time())
    rec, r = _do(c, "vs_gia", f"{API}/history", {"symbol": ma, "resolution": "D", "from": to - ngay * 86400, "to": to})
    j = None
    if r is not None and r.status_code == 200:
        try:
            j = r.json()
            if isinstance(j, str):                      # một số endpoint trả JSON lồng trong chuỗi
                j = json.loads(j)
        except ValueError:
            j = None
    if not (isinstance(j, dict) and j.get("t") and j.get("c")):
        rec["dung"] = False
        rec.setdefault("loi", "không có dữ liệu giá")
        j = None
    return rec, j


def do_hieu_suat(ma: str = "FPT") -> list[dict]:
    """Bài đo mỗi giờ cho API miễn phí của Vietstock (so với Wealbee Free trong báo cáo)."""
    with httpx.Client(timeout=30, headers=H, follow_redirects=True) as c:
        a, _ = _lich_su(c, ma, 30)
        b, _ = _do(c, "vs_tin_rss", "https://vietstock.vn" + RSS["Cổ phiếu"])
    return [a, b]


def cap_nhat_gia(ds_ma: list[str], toi_da: int = 80) -> dict:
    """Xoay vòng: mã chưa có file hoặc dữ liệu cũ hơn phiên gần nhất (sau 15h30 giờ VN) được làm mới, tối đa `toi_da` mã / lượt."""
    now = datetime.now(VN)
    moc = now.date() if (now.hour, now.minute) >= (15, 30) else (now - timedelta(days=1)).date()
    can = []
    for ma in ds_ma:
        f = RA / "gia" / f"{ma}.json"
        if not f.exists():
            can.append((0, ma))
            continue
        try:
            lan = json.loads(f.read_text(encoding="utf-8")).get("lay_ngay", "")
        except ValueError:
            lan = ""
        if lan < moc.isoformat():
            can.append((1, ma))
    can.sort()
    ok, loi = 0, 0
    with httpx.Client(timeout=30, headers=H, follow_redirects=True) as c:
        for _, ma in can[:toi_da]:
            _, j = _lich_su(c, ma)
            if j:
                k = 1000 if max(j["c"]) < 1000 else 1               # đổi về đồng nếu API trả nghìn đồng
                _ghi(RA / "gia" / f"{ma}.json", {"ma": ma, "lay_ngay": now.date().isoformat(), "nguon": "Vietstock",
                                                 "t": [int(x) for x in j["t"]], "c": [round(x * k) for x in j["c"]],
                                                 "v": [int(x) for x in (j.get("v") or [])]})
                ok += 1
            else:
                loi += 1
            time.sleep(0.6)
    return {"lam_moi": ok, "loi": loi, "con_cho": max(0, len(can) - toi_da)}


MA_SAN = re.compile(r"(?:HOSE|HNX|UPCoM|UPCOM|HSX)\s*:\s*([A-Z0-9]{3})")
MA_LE = re.compile(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9]{2})(?![A-Za-z0-9])")


def cap_nhat_tin(ds_ma: set[str]) -> dict:
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    moi = 0
    with httpx.Client(timeout=30, headers={"User-Agent": UA}, follow_redirects=True) as c:
        for muc, path in RSS.items():
            _, r = _do(c, "vs_tin_rss", "https://vietstock.vn" + path)
            if r is None or r.status_code != 200:
                continue
            s = r.content.decode("utf-8", "replace")
            for it in re.findall(r"<item>(.*?)</item>", s, re.S):
                g = lambda tag: html.unescape((re.search(rf"<{tag}>(.*?)</{tag}>", it, re.S) or [None, ""])[1]).strip()   # noqa: E731
                link = g("link").replace("http://", "https://")
                if not link or link in cache:
                    if link in cache and muc not in cache[link]["muc"]:
                        cache[link]["muc"].append(muc)
                    continue
                mo_ta = g("description")
                anh = re.search(r"src='([^']+)'", mo_ta) or re.search(r'src="([^"]+)"', mo_ta)
                chu = re.sub(r"<[^>]+>", "", mo_ta).strip()
                tieu_de = g("title")
                ma = set(MA_SAN.findall(tieu_de + " " + chu)) | {m for m in MA_LE.findall(tieu_de) if m in ds_ma}
                try:
                    luc = parsedate_to_datetime(g("pubDate")).astimezone(timezone.utc).isoformat(timespec="seconds")
                except (TypeError, ValueError):
                    luc = None
                cache[link] = {"tieu_de": tieu_de, "tom_tat": chu[:300], "link": link.replace("http://", "https://"), "luc": luc,
                               "anh": anh.group(1) if anh else None, "muc": [muc], "ma": sorted(m for m in ma if m in ds_ma or not ds_ma)}
                moi += 1
            time.sleep(0.5)
    moc = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    ds = sorted((x for x in cache.values() if (x.get("luc") or "") >= moc), key=lambda x: x.get("luc") or "", reverse=True)[:3000]
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({x["link"]: x for x in ds}, ensure_ascii=False), encoding="utf-8")
    _ghi(RA / "tin_moi.json", {"nguon": "Vietstock (RSS)", "ds": ds[:60]})
    theo_ma: dict[str, list] = {}
    for x in ds:
        for m in x["ma"]:
            theo_ma.setdefault(m, []).append(x)
    for m, v in theo_ma.items():
        _ghi(RA / "tin_ma" / f"{m}.json", {"ma": m, "ds": v[:30]})
    _ghi(RA / "chi_muc.json", {m: len(v) for m, v in sorted(theo_ma.items())})
    return {"tin_moi": moi, "tong": len(ds), "so_ma_co_tin": len(theo_ma)}


def ds_ma_free() -> list[str]:
    """Các mã của web bản Free (đọc từ trạng thái đồng bộ), dự phòng: danh sách công ty gói Doanh nghiệp."""
    tt = ROOT / "data" / "dong_bo_free.json"
    if tt.exists():
        ma = sorted(k.split("/", 1)[1] for k in json.loads(tt.read_text(encoding="utf-8")).get("bam", {}) if k.startswith("ma/"))
        if ma:
            return ma
    f = ROOT / "docs" / "doanh-nghiep" / "data" / "cong_ty.json"
    return sorted(x.get("ticker") for x in json.loads(f.read_text(encoding="utf-8")).get("ds", []) if x.get("ticker")) if f.exists() else []


def chay() -> dict:
    ma = ds_ma_free()
    tat_ca = set(ma)
    f = ROOT / "docs" / "doanh-nghiep" / "data" / "cong_ty.json"
    if f.exists():
        tat_ca |= {x.get("ticker") for x in json.loads(f.read_text(encoding="utf-8")).get("ds", []) if x.get("ticker")}
    return {"gia": cap_nhat_gia(ma), "tin": cap_nhat_tin(tat_ca)}
