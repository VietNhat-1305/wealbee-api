"""Tin tức cho 2 web: Wealbee Data API KHÔNG có endpoint tin tức (đã thử /news, /articles, /feed... đều 404; /events chỉ có
filing.detected / statement.published). Tin lấy từ API tin của app Wealbee (mục "Đề xuất"), công khai, không cần khoá:

    GET https://wealbee.com/api/insights/for-you?limit=100&cursor=...   tin mới nhất (có "related" = các mã liên quan)
    GET https://wealbee.com/api/symbols/{MA}/insights                   tin theo mã

API này không cho trình duyệt ở trang khác gọi thẳng (không có CORS) -> mỗi giờ lấy về, xuất thành "endpoint" tĩnh dùng chung:

    docs/tin/moi.json        60 tin mới nhất
    docs/tin/ma/<MA>.json    tin liên quan tới 1 mã (30 tin gần nhất)
    docs/tin/chi_muc.json    {mã: số tin} để web biết mã nào có tin
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
RA = ROOT / "docs" / "tin"
CACHE = ROOT / "data" / "tin_cache.json"
API = "https://wealbee.com/api"
UA = "wealbee-api-monitor/1.0 (+https://github.com/VietNhat-1305/wealbee-api)"
GIU_NGAY = 30


def _gon(x: dict) -> dict:
    ss = x.get("supersector") or {}
    return {"id": x["id"], "loai": x.get("category"), "nganh": ss.get("name") if isinstance(ss, dict) else None,
            "luc": x.get("publishedAt"), "sua": x.get("updatedAt"), "tieu_de": (x.get("title") or "").replace("**", ""),
            "tom_tat": (x.get("teaser") or "").replace("**", ""),
            "ma": x.get("related") or [], "sac_thai": x.get("sentiment"), "so_nguon": x.get("sources"), "anh": x.get("image"),
            "link": f"https://wealbee.com/share/{x['id']}"}


def _ghi(f: Path, obj) -> bool:
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if f.exists() and hashlib.sha256(f.read_bytes()).hexdigest() == hashlib.sha256(s.encode("utf-8")).hexdigest():
        return False
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(s, encoding="utf-8")
    return True


def do(c: httpx.Client, ep: str, path: str, params: dict | None = None) -> tuple[dict, object]:
    """1 lượt gọi có đo thời gian (dùng cho cả bộ quét hiệu suất)."""
    rec = {"ep": ep, "duong_dan": path, "luc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "kv": 200}
    t0 = time.perf_counter()
    j = None
    try:
        r = c.get(API + path, params=params)
        rec.update(status=r.status_code, ms_tong=round((time.perf_counter() - t0) * 1000, 1), bytes=len(r.content))
        j = r.json() if r.status_code == 200 else None
        rec["dung"] = r.status_code == 200 and j is not None
    except (httpx.HTTPError, ValueError) as e:
        rec.update(ms_tong=round((time.perf_counter() - t0) * 1000, 1), loi_mang=f"{type(e).__name__}: {str(e)[:120]}", dung=False)
    return rec, j


def do_hieu_suat(ma: str = "FPT") -> list[dict]:
    """2 bài đo API tin của app Wealbee cho bộ quét mỗi giờ."""
    with httpx.Client(timeout=30, headers={"User-Agent": UA}) as c:
        a, _ = do(c, "tin_moi", "/insights/for-you", {"limit": 30})
        b, _ = do(c, "tin_theo_ma", f"/symbols/{ma}/insights")
    return [a, b]


def cap_nhat(so_trang: int = 3) -> dict:
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    moi, cur = 0, None
    with httpx.Client(timeout=30, headers={"User-Agent": UA}) as c:
        for _ in range(so_trang):
            _, j = do(c, "tin_moi", "/insights/for-you", {"limit": 100, **({"cursor": cur} if cur else {})})
            if not isinstance(j, dict):
                break
            da_co = 0
            for x in j.get("items") or []:
                if not isinstance(x, dict) or not x.get("id"):
                    continue
                g = _gon(x)
                if cache.get(x["id"], {}).get("sua") == g["sua"]:
                    da_co += 1
                else:
                    moi += 1
                cache[x["id"]] = g
            cur = j.get("nextCursor")
            if not cur or da_co >= 90:                      # gần hết trang là tin đã có -> phần sau đã lấy từ trước
                break
            time.sleep(0.5)
    moc = (datetime.now(timezone.utc) - timedelta(days=GIU_NGAY)).isoformat()
    ds = sorted((x for x in cache.values() if (x.get("luc") or "") >= moc), key=lambda x: x.get("luc") or "", reverse=True)[:4000]
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({x["id"]: x for x in ds}, ensure_ascii=False), encoding="utf-8")
    bay_gio = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _ghi(RA / "moi.json", {"nguon": "Wealbee (tin trong app, mục Đề xuất)", "ds": ds[:60]})
    theo_ma: dict[str, list] = {}
    for x in ds:
        for m in x["ma"]:
            theo_ma.setdefault(m, []).append(x)
    doi = sum(_ghi(RA / "ma" / f"{m}.json", {"ma": m, "ds": v[:30]}) for m, v in theo_ma.items())
    _ghi(RA / "chi_muc.json", {m: len(v) for m, v in sorted(theo_ma.items())})
    (RA / "trang_thai.json").write_text(json.dumps({"lan_kiem": bay_gio, "so_tin": len(ds), "so_ma": len(theo_ma)}), encoding="utf-8")
    return {"tin_moi": moi, "tong": len(ds), "so_ma_co_tin": len(theo_ma), "file_ma_doi": doi}
