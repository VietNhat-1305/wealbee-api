"""Quét hiệu suất Wealbee API (chạy mỗi giờ): bộ ~14 bài đo cho từng gói (free / doanh nghiệp), ghi vào
data/do/<nguon>/<YYYY-MM>.jsonl (mỗi dòng 1 lượt quét, mã hoá) để báo cáo tổng hợp.

Bài đo mỗi giờ:  health (không khoá) · me · companies · company · latest statement · statements (2 trang, đo phân trang)
                 · statement full · versions · filings · events · lỗi 400 (kỳ sai) · lỗi 404 · lỗi 401 (khoá sai)
Mỗi ngày 1 lần:  bắn dồn để kiểm giới hạn tốc độ (429 + Retry-After + header RateLimit có đúng), kiểm bảo mật
                 (TLS, HSTS, khoá qua query string phải bị từ chối, http -> https).
"""
from __future__ import annotations

import os
import socket
import ssl
import time
from datetime import datetime, timezone

import httpx

from .client import BASE, WB

VN30 = ["ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG", "LPB", "MBB", "MSN", "MWG", "PLX", "SAB", "SHB",
        "SSB", "SSI", "STB", "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE"]
GOI = {"free": "WEALBEE_KEY_FREE", "dn": "WEALBEE_KEY_DN"}


def ds(j) -> list:
    """Danh sách trong response (data / items / results...)."""
    if isinstance(j, list):
        return j
    if isinstance(j, dict):
        for k in ("data", "items", "results", "statements", "companies", "filings", "events"):
            if isinstance(j.get(k), list):
                return j[k]
    return []


def con_tro(j) -> str | None:
    if isinstance(j, dict):
        for k in ("next_cursor", "cursor", "next"):
            v = j.get(k)
            if isinstance(v, str) and v:
                return v
        if isinstance(j.get("meta"), dict):
            return con_tro(j["meta"])
    return None


def _thoi_gian(s) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def _do_tuoi(st: dict) -> dict | None:
    """provenance: lúc Wealbee thấy file -> lúc có số (các trường *_at)."""
    p = st.get("provenance") if isinstance(st, dict) else None
    if not isinstance(p, dict):
        return None
    moc = {k: v for k, v in p.items() if k.endswith("_at") and _thoi_gian(v)}
    thay = _thoi_gian(moc.get("detected_at")) if moc.get("detected_at") else None
    sau = [(_thoi_gian(v), k) for k, v in moc.items() if k != "detected_at"]
    sau = [(t, k) for t, k in sau if t and thay and t >= thay]
    out = {"moc": moc}
    if thay and sau:
        t, k = max(sau)
        out.update(phut=round((t - thay).total_seconds() / 60, 1), den=k)
    return out


def tom_tat_goi(me: dict) -> dict:
    """Chỉ giữ quyền của gói từ /me (bỏ email, tên tài khoản, tiền tố khoá...)."""
    plan = me.get("plan") if isinstance(me.get("plan"), dict) else (me.get("account") or {}).get("plan") or me
    giu = ("name", "rate_limit_per_minute", "delay_minutes", "include_score", "max_webhook_endpoints", "products", "exchanges",
           "valid_until", "allow_redisplay", "redisplay", "display")
    out = {k: v for k, v in plan.items() if k in giu or "display" in k} if isinstance(plan, dict) else {}
    if isinstance(plan, dict) and isinstance(plan.get("tickers"), list):
        out["so_ma_gioi_han"] = len(plan["tickers"])
    for k in ("environment", "env", "livemode"):
        if k in me:
            out["moi_truong"] = me[k]
    for k in ("usage", "calls_this_month", "requests_this_month"):
        if k in me:
            out["luot_goi_thang"] = me[k]
    return out


def _chat_luong(sts: list) -> dict:
    out = {"so": len(sts), "trang_thai": {}, "kiem": {"passed": 0, "failed": 0, "skipped": 0}}
    for s in sts:
        if not isinstance(s, dict):
            continue
        tt = s.get("status") or "?"
        out["trang_thai"][tt] = out["trang_thai"].get(tt, 0) + 1
        for c in s.get("checks") or []:
            if isinstance(c, dict) and c.get("status") in out["kiem"]:
                out["kiem"][c["status"]] += 1
    return out


def bo_do(goi: str, khoa: str, gio: int) -> dict:
    """Bộ đo hằng giờ cho 1 gói."""
    t = VN30[gio % len(VN30)]
    wb = WB(khoa, goi, nhip_toi_thieu=2.1)            # trước khi biết giới hạn: ~28 request/phút
    lu, ghi = [], {}

    def g(ep, path, params=None, kv=200, khoa_=True):
        l = wb.goi(ep, path, params, khoa_)
        rec = l.ban_ghi()
        rec["kv"] = kv
        rec["dung"] = (l.status == kv) and not l.loi_mang
        if kv >= 400:                                   # lỗi phải đúng chuẩn RFC 9457
            rec["rfc9457"] = bool(isinstance(l.json, dict) and "application/problem+json" in l.ct
                                  and all(k in l.json for k in ("type", "title", "status", "code")))
        lu.append(rec)
        return l
    try:
        me = g("me", "/me")
        if isinstance(me.json, dict):
            ghi["me"] = tom_tat_goi(me.json)
        c = g("companies", "/companies", {"limit": 20})
        ghi["so_cong_ty"] = (c.json or {}).get("total") if isinstance(c.json, dict) else None
        g("company", f"/companies/{t}")
        lat = g("latest", f"/companies/{t}/statements/latest")
        s1 = g("statements_list", "/statements", {"limit": 20, "view": "basic"})
        cur = con_tro(s1.json)
        if cur:
            g("statements_page2", "/statements", {"limit": 20, "view": "basic", "cursor": cur})
        sid = (lat.json or {}).get("id") if isinstance(lat.json, dict) else None
        sid = sid or next((x.get("id") for x in ds(s1.json) if isinstance(x, dict) and x.get("id")), None)
        if sid:
            full = g("statement_full", f"/statements/{sid}", {"view": "full"})
            if isinstance(full.json, dict):
                ghi["tuoi"] = _do_tuoi(full.json)
                ghi["mau_bc"] = {"id": sid, "status": full.json.get("status"),
                                 "kiem": _chat_luong([full.json])["kiem"], "provenance": bool(full.json.get("provenance"))}
            g("versions", f"/statements/{sid}/versions")
        f = g("filings", "/filings", {"limit": 20})
        ghi["filings"] = {}
        for x in ds(f.json):
            if isinstance(x, dict):
                ghi["filings"][x.get("status") or "?"] = ghi["filings"].get(x.get("status") or "?", 0) + 1
        g("events", "/events", {"limit": 20})
        ghi["chat_luong"] = _chat_luong(ds(s1.json))
        g("err_400", "/statements", {"period": "2026Q9"}, kv=400)
        g("err_404", "/statements/ZZZZ.2026Q1", kv=404)
        g("err_401", "/me", kv=401, khoa_="wb_live_sai_" + "0" * 24)
        hl = next((l for l in lu if l.get("hieu_luc")), None)
        if hl:
            dt = _thoi_gian(hl["hieu_luc"])
            if dt:
                ghi["do_tre_du_lieu_s"] = round((_thoi_gian(hl["luc"]) - dt).total_seconds())
    finally:
        wb.close()
    ghi["luot"] = lu
    return ghi


def suc_khoe(n: int = 3) -> list[dict]:
    wb = WB(None, "khong_khoa")
    try:
        out = []
        for _ in range(n):
            l = wb.goi("health", "/health", khoa=False)
            r = l.ban_ghi()
            r["kv"], r["dung"] = 200, l.status == 200 and isinstance(l.json, dict) and l.json.get("status") == "ok"
            out.append(r)
            time.sleep(0.5)
        return out
    finally:
        wb.close()


def ban_don(goi: str, khoa: str) -> dict:
    """Kiểm giới hạn tốc độ: gọi /me liên tục tới khi bị 429 (hoặc tối đa q+5 / 60 lượt)."""
    wb = WB(khoa, goi)
    lu = []
    try:
        dau = wb.goi("burst", "/me")
        q = dau.rl.get("q") or 30
        toi_da = min(q + 5, 60)
        lu.append(dau)
        wb.nhip = 0
        t0 = time.perf_counter()
        while len(lu) < toi_da:
            l = wb.goi("burst", "/me")
            lu.append(l)
            if l.status == 429:
                break
        giay = time.perf_counter() - t0
        bi = next((l for l in lu if l.status == 429), None)
        r_dung = all(b.rl.get("r", 0) >= a.rl.get("r", 0) - 1 for a, b in zip(lu, lu[1:]) if a.status == b.status == 200)
        out = {"q": q, "w": dau.rl.get("w"), "so_luot": len(lu), "so_200": sum(l.status == 200 for l in lu),
               "luot_429": (lu.index(bi) + 1) if bi else None, "retry_after": bi.retry_after if bi else None,
               "rfc9457_429": bool(bi and isinstance(bi.json, dict) and bi.json.get("code") == "rate_limited"),
               "header_r_giam_dung": r_dung, "rps": round(len(lu) / giay, 2) if giay else None,
               "ms_p50": sorted(l.ms_tong for l in lu)[len(lu) // 2]}
        if bi and bi.retry_after and str(bi.retry_after).isdigit():            # chờ hết hạn rồi thử lại: phải được 200
            time.sleep(int(bi.retry_after) + 1)
            out["sau_retry_after"] = wb.goi("burst", "/me").status
        return out
    finally:
        wb.close()


def bao_mat(khoa: str | None) -> dict:
    out = {}
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection(("data.wealbee.com", 443), timeout=10) as s, ctx.wrap_socket(s, server_hostname="data.wealbee.com") as ss:
            out["tls"] = ss.version()
            cert = ss.getpeercert()
            het = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            out["chung_chi_con_ngay"] = (het - datetime.now(timezone.utc)).days
            out["cap_boi"] = dict(x[0] for x in cert.get("issuer", ())).get("organizationName")
    except Exception as e:  # noqa: BLE001
        out["tls_loi"] = str(e)[:120]
    try:
        r = httpx.get(BASE + "/health", timeout=15)
        out["hsts"] = r.headers.get("strict-transport-security")
        r = httpx.get("http://data.wealbee.com/v1/health", timeout=15, follow_redirects=False)
        out["http_sang_https"] = r.status_code in (301, 302, 307, 308) and r.headers.get("location", "").startswith("https")
        out["http_status"] = r.status_code
        if khoa:
            r = httpx.get(BASE + "/me", params={"api_key": khoa}, timeout=15)          # khoá qua query phải bị từ chối
            out["khoa_qua_query_bi_tu_choi"] = r.status_code == 401
    except Exception as e:  # noqa: BLE001
        out["http_loi"] = str(e)[:120]
    return out


def chay(nguon: str) -> list[dict]:
    """1 lượt quét; trả về danh sách bản ghi (mỗi gói 1 bản ghi + 1 bản ghi health/bảo mật)."""
    now = datetime.now(timezone.utc)
    gio = int(now.timestamp() // 3600)
    out = []
    chung = {"luc": now.isoformat(timespec="seconds"), "nguon": nguon, "goi": "chung", "health": suc_khoe()}
    if now.hour == 2 or os.environ.get("QUET_HANG_NGAY"):
        chung["bao_mat"] = bao_mat(os.environ.get(GOI["free"]) or os.environ.get(GOI["dn"]))
    out.append(chung)
    for goi, env in GOI.items():
        khoa = os.environ.get(env, "").strip()
        rec = {"luc": now.isoformat(timespec="seconds"), "nguon": nguon, "goi": goi}
        if not khoa:
            rec["bo_qua"] = f"chưa có {env}"
            out.append(rec)
            continue
        try:
            rec.update(bo_do(goi, khoa, gio))
            if (now.hour == 2 or os.environ.get("QUET_HANG_NGAY")) and nguon == "github":
                time.sleep(61)                                               # trả lại hạn mức phút trước khi bắn dồn
                rec["ban_don"] = ban_don(goi, khoa)
        except Exception as e:  # noqa: BLE001 - 1 gói lỗi không dừng gói kia
            rec["loi"] = f"{type(e).__name__}: {str(e)[:200]}"
        out.append(rec)
    return out
