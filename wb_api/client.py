"""Khách gọi Wealbee Data API (https://data.wealbee.com/v1) có đo thời gian từng lượt gọi.

Mỗi lượt gọi trả về `Luot`: mã HTTP, thời gian tới byte đầu (TTFB) và tổng, kích thước, các header quan trọng
(RateLimit, RateLimit-Policy, Wealbee-Effective-Time, request id, Content-Type), mã lỗi (RFC 9457) và JSON.
Tự giãn nhịp theo RateLimit-Policy để bộ đo không tự làm vượt giới hạn (gói Free 30 request/phút dùng chung mọi khoá).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

BASE = "https://data.wealbee.com/v1"
UA = "wealbee-api-monitor/1.0 (+https://github.com/VietNhat-1305/wealbee-api)"


@dataclass
class Luot:
    ep: str                       # tên bài đo (VD "statements_list")
    duong_dan: str
    status: int = 0
    ms_ttfb: float = 0.0
    ms_tong: float = 0.0
    bytes: int = 0
    loi_mang: str | None = None   # timeout / DNS / TLS...
    code: str | None = None       # mã lỗi RFC 9457
    ct: str = ""
    req_id: str | None = None
    rl: dict = field(default_factory=dict)        # {"q":30,"w":60,"r":29,"t":0}
    hieu_luc: str | None = None   # Wealbee-Effective-Time
    retry_after: str | None = None
    lanh: bool = False            # lượt đầu của kết nối (có bắt tay TLS)
    luc: str = ""
    json: object = None

    def ban_ghi(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "json"}
        return {k: v for k, v in d.items() if v not in (None, "", {}, False) or k in ("status",)}


def _rl(h: httpx.Headers) -> dict:
    out = {}
    m = re.search(r";q=(\d+)", h.get("ratelimit-policy", ""))
    if m:
        out["q"] = int(m[1])
    m = re.search(r";w=(\d+)", h.get("ratelimit-policy", ""))
    if m:
        out["w"] = int(m[1])
    m = re.search(r";r=(\d+)", h.get("ratelimit", ""))
    if m:
        out["r"] = int(m[1])
    m = re.search(r";t=(\d+)", h.get("ratelimit", ""))
    if m:
        out["t"] = int(m[1])
    return out


class WB:
    def __init__(self, khoa: str | None, goi: str, nhip_toi_thieu: float = 0.0):
        self.khoa, self.ten_goi = khoa, goi
        self.http = httpx.Client(base_url=BASE, timeout=httpx.Timeout(30.0, connect=10.0), headers={"User-Agent": UA},
                                 follow_redirects=False)
        self.nhip = nhip_toi_thieu      # giây tối thiểu giữa 2 lượt gọi
        self.tu_giu_nhip = True         # tự giãn nhịp theo header RateLimit; bài bắn dồn tắt đi để thật sự vượt giới hạn
        self._lan_cuoi = 0.0
        self._da_ket_noi = False

    def close(self):
        self.http.close()

    def _cho(self):
        con = self.nhip - (time.monotonic() - self._lan_cuoi)
        if con > 0:
            time.sleep(con)

    def goi(self, ep: str, duong_dan: str, params: dict | None = None, khoa: str | None | bool = True) -> Luot:
        """khoa=True: dùng khoá của gói; False/None: không gửi khoá; chuỗi: gửi khoá đó (VD khoá sai để đo 401)."""
        self._cho()
        h = {}
        k = self.khoa if khoa is True else (khoa or None)
        if k:
            h["Authorization"] = f"Bearer {k}"
        l = Luot(ep=ep, duong_dan=duong_dan + (("?" + str(httpx.QueryParams(params))) if params else ""),
                 luc=datetime.now(timezone.utc).isoformat(timespec="seconds"), lanh=not self._da_ket_noi)
        t0 = time.perf_counter()
        try:
            req = self.http.build_request("GET", duong_dan, params=params, headers=h)
            r = self.http.send(req, stream=True)
            l.ms_ttfb = (time.perf_counter() - t0) * 1000
            body = r.read()
            l.ms_tong = (time.perf_counter() - t0) * 1000
            self._da_ket_noi = True
            l.status, l.bytes, l.ct = r.status_code, len(body), r.headers.get("content-type", "")
            l.req_id = r.headers.get("x-request-id")
            l.rl, l.hieu_luc, l.retry_after = _rl(r.headers), r.headers.get("wealbee-effective-time"), r.headers.get("retry-after")
            try:
                l.json = r.json()
            except ValueError:
                l.json = None
            if l.status >= 400 and isinstance(l.json, dict):
                l.code = l.json.get("code")
            r.close()
            q, w = l.rl.get("q"), l.rl.get("w")
            if q and w and self.tu_giu_nhip:               # giữ nhịp an toàn ~80% giới hạn
                self.nhip = max(self.nhip, w / q / 0.8)
        except httpx.HTTPError as e:
            l.ms_tong = (time.perf_counter() - t0) * 1000
            l.loi_mang = f"{type(e).__name__}: {str(e)[:120]}"
            self._da_ket_noi = False
        self._lan_cuoi = time.monotonic()
        return l
