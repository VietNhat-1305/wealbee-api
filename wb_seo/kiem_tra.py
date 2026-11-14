"""Các phép kiểm SEO kỹ thuật cho wealbee.com (không cần trình duyệt): index được không, thẻ on-page, sitemap, robots,
link nguồn trích dẫn, bảo mật. Mỗi phép kiểm trả số đo thô; việc chấm Đạt / Cảnh báo / Lỗi nằm ở chi_so.py.
"""
from __future__ import annotations

import json
import random
import re
import socket
import ssl
import string
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

GOC = "https://wealbee.com"
UA = "WealbeeSEOMonitor/1.0 (+https://github.com/VietNhat-1305/wealbee-api)"
UA_TRINH_DUYET = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
BOT_TIM_KIEM = ["Googlebot", "Bingbot", "OAI-SearchBot", "ChatGPT-User", "Claude-SearchBot", "Claude-User", "PerplexityBot"]
BOT_HUAN_LUYEN = ["GPTBot", "ClaudeBot", "Google-Extended", "Applebot-Extended", "CCBot"]


class _Trang(HTMLParser):
    """Đọc HTML gốc (không chạy JavaScript) như bot tìm kiếm AI: thẻ head, H1, link, JSON-LD, chữ hiển thị."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.meta, self.canonical, self.h1, self.links, self.ld = "", {}, [], [], [], []
        self.chu, self._bo_qua, self._trong, self._ld, self._h1 = [], 0, None, None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript", "template"):
            self._bo_qua += 1
            if tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
                self._ld = []
        elif tag == "title":
            self._trong = "title"
        elif tag == "meta":
            k = (a.get("name") or a.get("property") or "").lower()
            if k:
                self.meta[k] = a.get("content") or ""
        elif tag == "link" and "canonical" in (a.get("rel") or "").lower():
            self.canonical.append(a.get("href") or "")
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "h1":
            self._h1 = []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template"):
            self._bo_qua = max(0, self._bo_qua - 1)
            if tag == "script" and self._ld is not None:
                self.ld.append("".join(self._ld))
                self._ld = None
        elif tag == "title":
            self._trong = None
        elif tag == "h1" and self._h1 is not None:
            self.h1.append(" ".join("".join(self._h1).split()))
            self._h1 = None

    def handle_data(self, data):
        if self._ld is not None:
            self._ld.append(data)
        if self._bo_qua:
            return
        if self._trong == "title":
            self.title += data
        if self._h1 is not None:
            self._h1.append(data)
        self.chu.append(data)


def doc_trang(html: str) -> dict:
    p = _Trang()
    p.feed(html)
    loai = []
    for blk in p.ld:
        try:
            j = json.loads(blk)
        except ValueError:
            continue
        for x in (j if isinstance(j, list) else j.get("@graph", [j]) if isinstance(j, dict) else []):
            if isinstance(x, dict) and x.get("@type"):
                loai += x["@type"] if isinstance(x["@type"], list) else [x["@type"]]
    chu = " ".join(" ".join(p.chu).split())
    return {"title": " ".join(p.title.split()), "description": p.meta.get("description", ""), "robots": p.meta.get("robots", ""),
            "og": sorted(k for k in p.meta if k.startswith("og:")), "canonical": p.canonical, "h1": p.h1,
            "so_link": len(p.links), "links": p.links, "jsonld": sorted(set(loai)), "so_ky_tu": len(chu)}


def _client() -> httpx.Client:
    return httpx.Client(timeout=30, headers={"User-Agent": UA}, follow_redirects=False)


def lay(c: httpx.Client, url: str, theo=False) -> tuple[httpx.Response | None, str | None, float]:
    t0 = time.perf_counter()
    try:
        r = c.get(url, follow_redirects=theo)
        return r, None, (time.perf_counter() - t0) * 1000
    except httpx.HTTPError as e:
        return None, f"{type(e).__name__}: {str(e)[:100]}", (time.perf_counter() - t0) * 1000


def bai_moi(c: httpx.Client, n: int = 30) -> list[dict]:
    """Bài mới nhất từ API công khai của app (mục Đề xuất) + nguồn trích dẫn của từng bài."""
    r, loi, _ = lay(c, f"{GOC}/api/insights/for-you")
    if loi or r.status_code != 200:
        return []
    ds = (r.json() or {}).get("items") or []
    out = []
    for x in ds[:n]:
        d, _, _ = lay(c, f"{GOC}/api/insights/{x.get('id')}/detail")
        nguon = []
        if d is not None and d.status_code == 200:
            nguon = [s.get("url") or s.get("link") for s in (d.json() or {}).get("sources") or [] if isinstance(s, dict)]
        out.append({"id": x.get("id"), "nguon": [u for u in nguon if u]})
        time.sleep(0.25)
    return out


def _gay_that(s) -> bool:
    """Chỉ 404 / 410 hoặc tên miền không tồn tại mới là link gãy; quá thời gian, 403, 429, 5xx là lỗi tạm (báo chậm, chặn bot)."""
    return s in (404, 410) or (isinstance(s, str) and s.startswith("DNS"))


def kiem_link(urls: list[str]) -> dict:
    """Link nguồn trích dẫn còn sống không. Mỗi tên miền gọi tuần tự (không dồn request vào một báo), lỗi tạm thì thử lại 1 lần."""
    def mot(u, timeout=20):
        try:
            r = httpx.get(u, headers={"User-Agent": UA_TRINH_DUYET}, timeout=timeout, follow_redirects=True)
            return r.status_code
        except httpx.ConnectError as e:
            return "DNS" if "getaddrinfo" in str(e) or "Name or service" in str(e) else type(e).__name__
        except httpx.HTTPError as e:
            return type(e).__name__

    def theo_mien(ds):
        out = []
        for u in ds:
            s = mot(u)
            if not (isinstance(s, int) and s < 400) and not _gay_that(s):
                time.sleep(2)
                s = mot(u, timeout=40)
            out.append((u, s))
            time.sleep(0.5)
        return out
    nhom = {}
    for u in sorted(set(urls)):
        nhom.setdefault(urlparse(u).netloc, []).append(u)
    with ThreadPoolExecutor(6) as ex:
        kq = [x for ds in ex.map(theo_mien, nhom.values()) for x in ds]
    hong = [(u, s) for u, s in kq if _gay_that(s)]
    tam = [(u, s) for u, s in kq if not (isinstance(s, int) and s < 400) and not _gay_that(s)]
    return {"tong": len(kq), "hong": len(hong), "ty_le_hong": round(100 * len(hong) / len(kq), 2) if kq else None, "mau_hong": hong[:10],
            "chua_kiem_duoc": len(tam), "mau_chua_kiem_duoc": tam[:10]}


def kiem_robots(c: httpx.Client) -> dict:
    r, loi, _ = lay(c, f"{GOC}/robots.txt")
    if loi or r.status_code != 200 or "html" in r.headers.get("content-type", ""):
        return {"co": False, "loi": loi or f"HTTP {r.status_code}"}
    nhom, hien, chan = {}, [], {}
    for ln in r.text.splitlines():
        ln = ln.split("#", 1)[0].strip()
        if not ln or ":" not in ln:
            continue
        k, v = (x.strip() for x in ln.split(":", 1))
        k = k.lower()
        if k == "user-agent":
            if not hien or nhom.get("_mo_rong"):
                hien = []
            hien.append(v.lower())
            nhom["_mo_rong"] = False
        elif k in ("disallow", "allow"):
            nhom["_mo_rong"] = True
            for ua in hien:
                chan.setdefault(ua, []).append((k, v))
    def bi_chan(bot):
        luat = chan.get(bot.lower()) or chan.get("*") or []
        return any(k == "disallow" and v == "/" for k, v in luat) and not any(k == "allow" and v == "/" for k, v in luat)
    sm = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", r.text)
    return {"co": True, "sitemap": sm, "chan_bot_tim_kiem": [b for b in BOT_TIM_KIEM if bi_chan(b)],
            "chan_bot_huan_luyen": [b for b in BOT_HUAN_LUYEN if bi_chan(b)],
            "ghi_ro_bot_ai": [b for b in BOT_TIM_KIEM + BOT_HUAN_LUYEN if b.lower() in chan]}


def kiem_sitemap(c: httpx.Client, urls: list[str]) -> dict:
    tat_ca, loi = [], []
    hang = list(urls) or [f"{GOC}/sitemap.xml"]
    da = set()
    while hang and len(da) < 30:
        u = hang.pop(0)
        if u in da:
            continue
        da.add(u)
        r, e, _ = lay(c, u, theo=True)
        if e or r.status_code != 200:
            loi.append(f"{u}: {e or r.status_code}")
            continue
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text)
        if "<sitemapindex" in r.text:
            hang += locs
        else:
            tat_ca += locs
    mau = random.Random(len(tat_ca)).sample(tat_ca, min(40, len(tat_ca)))
    hong = []
    for u in mau:
        r, e, _ = lay(c, u)
        if e or r.status_code != 200:
            hong.append(f"{u} -> {e or r.status_code}")
    return {"so_file": len(da), "so_url": len(tat_ca), "loi_file": loi, "mau": len(mau), "url_khong_200": hong[:10],
            "co_bai_viet": any(re.search(r"/(tin|bai|news|share)/|\?a=", u) for u in tat_ca)}


def kiem_bao_mat() -> dict:
    out = {}
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection(("wealbee.com", 443), timeout=10) as s, ctx.wrap_socket(s, server_hostname="wealbee.com") as ss:
            out["tls"] = ss.version()
            het = datetime.strptime(ss.getpeercert()["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            out["chung_chi_con_ngay"] = (het - datetime.now(timezone.utc)).days
    except Exception as e:  # noqa: BLE001
        out["tls_loi"] = str(e)[:120]
    c = _client()
    r, e, _ = lay(c, GOC + "/")
    if r is not None:
        h = {k.lower(): v for k, v in r.headers.items()}
        csp = h.get("content-security-policy", "")
        out.update({"hsts": "strict-transport-security" in h, "hsts_preload": "preload" in h.get("strict-transport-security", ""),
                    "csp": bool(csp), "csp_day_du": bool(re.search(r"default-src|script-src", csp)),
                    "x_frame": "x-frame-options" in h or "frame-ancestors" in csp, "nosniff": h.get("x-content-type-options") == "nosniff",
                    "referrer_policy": "referrer-policy" in h, "cloudflare": h.get("server") == "cloudflare"})
    r, e, _ = lay(c, "http://wealbee.com/")
    out["http_sang_https"] = r is not None and r.status_code in (301, 308) and r.headers.get("location", "").startswith("https://")
    r, e, _ = lay(c, "https://www.wealbee.com/")
    out["www_chuyen_ve_goc"] = r is not None and r.status_code in (301, 308) and urlparse(r.headers.get("location", "")).netloc == "wealbee.com"
    out["www_qua_cloudflare"] = r is not None and r.headers.get("server") == "cloudflare"
    return out


def kiem_trang(c: httpx.Client, url: str) -> dict:
    r, e, ms = lay(c, url)
    if e:
        return {"url": url, "loi": e}
    out = {"url": url, "status": r.status_code, "ms": round(ms), "chuyen_toi": r.headers.get("location")}
    if r.status_code == 200 and "html" in r.headers.get("content-type", ""):
        out.update(doc_trang(r.text))
        out.pop("links", None)
    return out


def chay() -> dict:
    """Một lượt kiểm đầy đủ (không gồm tốc độ: xem toc_do.py)."""
    c = _client()
    robots = kiem_robots(c)
    bai = bai_moi(c)
    trang = {"trang_chu": kiem_trang(c, GOC + "/")}
    if bai:
        trang["bai_viet"] = kiem_trang(c, f"{GOC}/?a={bai[0]['id']}")
        trang["bai_chia_se"] = kiem_trang(c, f"{GOC}/share/{bai[0]['id']}")
    for ten in ("privacy.html", "terms.html"):
        trang[ten] = kiem_trang(c, f"{GOC}/{ten}")
    la = "".join(random.choice(string.ascii_lowercase) for _ in range(12))
    r404, e404, _ = lay(c, f"{GOC}/khong-ton-tai-{la}")
    rl, el, _ = lay(c, f"{GOC}/llms.txt")
    return {
        "luc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "robots": robots, "sitemap": kiem_sitemap(c, robots.get("sitemap") or []), "trang": trang,
        "soft_404": {"status": r404.status_code if r404 is not None else None, "loi": e404},
        "llms_txt": {"status": rl.status_code if rl is not None else None,
                     "la_van_ban": rl is not None and rl.status_code == 200 and "text/plain" in rl.headers.get("content-type", "")},
        "link_nguon": kiem_link([u for b in bai for u in b["nguon"]]) if bai else {"tong": 0},
        "so_bai_kiem": len(bai), "bao_mat": kiem_bao_mat(),
    }
