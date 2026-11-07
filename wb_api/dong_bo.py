"""Đồng bộ dữ liệu BCTC từ Wealbee cho 2 web tra cứu (cùng tính năng, khác gói API):

    docs/doanh-nghiep/data/  (khoá gói Doanh nghiệp, được phép hiển thị cho khách -> JSON thường)
    docs/free/data/          (khoá gói Free, CHỈ DÙNG NỘI BỘ theo điều khoản -> mã hoá, xem bằng mật khẩu)

Đồng bộ tăng dần: GET /statements?view=full&updated_since=<lần trước> theo con trỏ, mỗi lượt chạy có hạn mức request
(gói Free 30 request/phút dùng chung với bộ đo) -> lần đầu chạy nhiều giờ mới đủ, sau đó chỉ lấy bản mới / bị sửa.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from . import ma_hoa
from .client import WB
from .quet import GOI, con_tro, ds, tom_tat_goi

ROOT = Path(__file__).resolve().parent.parent
THU_MUC = {"dn": ROOT / "docs" / "doanh-nghiep" / "data", "free": ROOT / "docs" / "free" / "data"}
MA_HOA = {"dn": False, "free": True}
SO_KY = 12                                       # giữ tối đa 12 kỳ gần nhất mỗi mã
HAN_MUC = {"free": 20, "dn": 60}                 # số request đồng bộ tối đa mỗi lượt chạy


def _trang_thai_f(goi: str) -> Path:
    return ROOT / "data" / f"dong_bo_{goi}.json"


def _doc_tt(goi: str) -> dict:
    f = _trang_thai_f(goi)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def _ghi_tt(goi: str, tt: dict) -> None:
    _trang_thai_f(goi).parent.mkdir(parents=True, exist_ok=True)
    _trang_thai_f(goi).write_text(json.dumps(tt, ensure_ascii=False, indent=1), encoding="utf-8")


def _ghi(goi: str, ten: str, obj) -> bool:
    """Ghi file dữ liệu web; chỉ ghi khi nội dung đổi (đỡ phình lịch sử git). Trả về có ghi hay không."""
    tt = _doc_tt(goi)
    bam = hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    if tt.get("bam", {}).get(ten) == bam and (THU_MUC[goi] / (ten + ".json" + (".enc" if MA_HOA[goi] else ""))).exists():
        return False
    f = THU_MUC[goi] / (ten + ".json" + (".enc" if MA_HOA[goi] else ""))
    f.parent.mkdir(parents=True, exist_ok=True)
    data = ma_hoa.goi(obj) if MA_HOA[goi] else obj
    f.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tt = _doc_tt(goi)
    tt.setdefault("bam", {})[ten] = bam
    _ghi_tt(goi, tt)
    return True


def _doc(goi: str, ten: str):
    f = THU_MUC[goi] / (ten + ".json" + (".enc" if MA_HOA[goi] else ""))
    if not f.exists():
        return None
    j = json.loads(f.read_text(encoding="utf-8"))
    return ma_hoa.mo_goi(j) if MA_HOA[goi] else j


def _gon(st: dict) -> dict:
    """Bản gọn của 1 statement cho web (bỏ phần nặng không hiển thị)."""
    keep = ("id", "ticker", "period", "period_label", "fiscal_year", "fiscal_quarter", "months_ytd", "status", "scope",
            "industry_type", "original_unit", "currency", "income_statement", "balance_sheet", "cash_flow", "review_reasons",
            "derived", "version")
    out = {k: st[k] for k in keep if k in st}
    out.update({k: v for k, v in st.items() if ("score" in k or "health" in k) and k not in out})
    ch = [c for c in st.get("checks") or [] if isinstance(c, dict)]
    out["kiem"] = {"tong": len(ch), "dat": sum(c.get("status") == "passed" for c in ch),
                   "loi": [c.get("code") for c in ch if c.get("status") == "failed"]}
    p = st.get("provenance") or {}
    if isinstance(p, dict):
        out["nguon_goc"] = {k: p[k] for k in ("document_url", "pages", "source", "ir_url", "detected_at", "first_published_at",
                                               "updated_at") if k in p}
        if isinstance(p.get("extraction"), dict):
            out["nguon_goc"]["extracted_at"] = p["extraction"].get("extracted_at")
            out["nguon_goc"]["model"] = p["extraction"].get("model")
    return out


def _ma_ky(st: dict) -> tuple[str, str]:
    sid = str(st.get("id", ""))
    ma = st.get("ticker") or sid.split(".")[0]
    ky = st.get("period") or (sid.split(".")[1] if "." in sid else "")
    return ma, ky


def dong_bo(goi: str) -> dict:
    khoa = os.environ.get(GOI[goi], "").strip()
    if not khoa:
        return {"goi": goi, "bo_qua": f"chưa có {GOI[goi]}"}
    tt = _doc_tt(goi)
    wb = WB(khoa, goi, nhip_toi_thieu=2.1)
    so_req, moi, bat_dau = 0, {}, datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = {"goi": goi}
    try:
        me = wb.goi("me", "/me")
        so_req += 1
        if me.status != 200:
            return {"goi": goi, "loi": f"/me trả {me.status} {me.code or ''}"}
        # danh sách công ty: làm mới mỗi ngày
        if tt.get("ngay_cong_ty") != bat_dau[:10] or _doc(goi, "cong_ty") is None:
            cty, cur = [], None
            while so_req < HAN_MUC[goi]:
                l = wb.goi("companies", "/companies", {"limit": 500, **({"cursor": cur} if cur else {})})
                so_req += 1
                if l.status != 200:
                    break
                cty += [x for x in ds(l.json) if isinstance(x, dict)]
                cur = con_tro(l.json)
                if not cur:
                    tt = _doc_tt(goi)
                    tt["ngay_cong_ty"] = bat_dau[:10]
                    _ghi_tt(goi, tt)
                    break
            if cty:
                _ghi(goi, "cong_ty", {"cap_nhat": bat_dau, "ds": cty})
        # BCTC: tăng dần theo updated_since + con trỏ dở dang
        tt = _doc_tt(goi)
        params = {"view": "full", "limit": 200}
        if tt.get("updated_since"):
            params["updated_since"] = tt["updated_since"]
        cur = tt.get("cursor")
        het = False
        while so_req < HAN_MUC[goi]:
            l = wb.goi("sync", "/statements", {**params, **({"cursor": cur} if cur else {})})
            so_req += 1
            if l.status != 200:
                out["loi"] = f"/statements trả {l.status} {l.code or ''}"
                break
            for st in ds(l.json):
                if isinstance(st, dict) and st.get("id"):
                    ma, ky = _ma_ky(st)
                    moi.setdefault(ma, {})[ky] = _gon(st)
            cur = con_tro(l.json)
            if not cur:
                het = True
                break
        tt = _doc_tt(goi)
        tt["cursor"] = None if het else cur
        if het:
            tt["updated_since"] = tt.get("dang_tu") or bat_dau          # lần đồng bộ đã đi hết -> mốc mới
            tt["dang_tu"] = None
        elif not tt.get("dang_tu"):
            tt["dang_tu"] = bat_dau                                        # nhớ mốc bắt đầu của đợt đang đi dở
        tt["lan_cuoi"] = bat_dau
        _ghi_tt(goi, tt)
        # gộp vào file từng mã
        doi = 0
        for ma, kys in moi.items():
            cu = _doc(goi, f"ma/{ma}") or {"ma": ma, "ky": {}}
            cu["ky"].update(kys)
            cu["ky"] = dict(sorted(cu["ky"].items(), reverse=True)[:SO_KY])
            doi += _ghi(goi, f"ma/{ma}", cu)
        # chỉ mục cho trang tra cứu
        idx = _doc(goi, "index") or {"cong_ty": {}}
        for ma, kys in moi.items():
            cu = _doc(goi, f"ma/{ma}")
            ky, st = next(iter(cu["ky"].items()))
            inc = st.get("income_statement") or {}
            val = lambda k: (inc.get(k) or {}).get("quarter") if isinstance(inc.get(k), dict) else inc.get(k)   # noqa: E731
            idx["cong_ty"][ma] = {"ky": ky, "tt": st.get("status"), "dt": val("revenue"), "ln": val("net_profit"),
                                  "nganh": st.get("industry_type"),
                                  **{k: v for k, v in st.items() if "score" in k and isinstance(v, (int, float))}}
        if moi or "quyen" not in idx:                                      # chỉ mục chỉ ghi lại khi dữ liệu đổi
            idx.update(cap_nhat=bat_dau, goi=goi, quyen=tom_tat_goi(me.json if isinstance(me.json, dict) else {}),
                       so_ma=len(idx["cong_ty"]))
            _ghi(goi, "index", idx)
        # trạng thái nhỏ, không nhạy cảm (giờ kiểm gần nhất), luôn ghi thường để trang hiện "kiểm lúc ..."
        (THU_MUC[goi] / "trang_thai.json").write_text(json.dumps({"lan_kiem": bat_dau, "so_ma": len(idx["cong_ty"]),
                                                                   "dang_dong_bo_lan_dau": not het and not tt.get("updated_since")}),
                                                       encoding="utf-8")
        out.update(so_request=so_req, so_bc_moi=sum(len(v) for v in moi.values()), so_ma_doi=doi, het=het)
        return out
    finally:
        wb.close()


def chay() -> list[dict]:
    out = []
    for goi in ("dn", "free"):
        try:
            out.append(dong_bo(goi))
        except Exception as e:  # noqa: BLE001
            out.append({"goi": goi, "loi": f"{type(e).__name__}: {str(e)[:200]}"})
        time.sleep(1)
    return out
