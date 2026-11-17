"""Một lượt theo dõi sức khoẻ SEO wealbee.com: kiểm tra → chấm điểm → lưu lịch sử (mã hoá) → báo cáo web → cảnh báo.

    python -m wb_seo.chay                 # đầy đủ (gồm đo tốc độ bằng Chrome)
    python -m wb_seo.chay --khong-toc-do  # nhanh, bỏ đo tốc độ

GitHub Actions (.github/workflows/seo.yml) chạy mỗi ngày 08:15 giờ Việt Nam. Có cảnh báo mới thì ghi file theo biến
SEO_CANH_BAO (workflow dùng file đó mở / bình luận issue "Cảnh báo sức khoẻ SEO"). Nội dung issue công khai nên chỉ ghi
tên chỉ số và điểm, chi tiết nằm trong báo cáo có mật khẩu (docs/seo/).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from wb_api import ma_hoa
from wb_api.chay import nap_env

from . import chi_so, kiem_tra

ROOT = Path(__file__).resolve().parent.parent
LICH_SU = ROOT / "data" / "seo"
RA = ROOT / "docs" / "seo" / "bao_cao.enc"
WEB = "https://vietnhat-1305.github.io/wealbee-api/seo/"
TEN_XEP = {"dat": "Đạt", "canh_bao": "Cảnh báo", "loi": "Lỗi", "chua_do": "Chưa đo"}


def doc_lich_su() -> list[dict]:
    out = []
    for f in sorted(LICH_SU.glob("*.jsonl")):
        for ln in f.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                try:
                    out.append(ma_hoa.mo_dong(ln.strip()))
                except Exception:  # noqa: BLE001 - dòng hỏng / khác mật khẩu
                    pass
    return sorted(out, key=lambda r: r["luc"])


def so_sanh(truoc: dict | None, moi: dict) -> list[dict]:
    """Cảnh báo: chỉ số mới chuyển sang Lỗi, điểm tụt ≥ 5, trang chủ không 200, chứng chỉ sắp hết hạn."""
    cb = []
    cu = (truoc or {}).get("chi_so") or {}
    for c in moi["ds"]:
        x0 = (cu.get(c["id"]) or [None])[0]
        if c["xep"] == "loi" and x0 != "loi":
            cb.append({"muc": "cao", "id": c["id"], "ten": c["ten"], "chu": f"{c['ten']}: {TEN_XEP.get(x0, 'chưa đo')} → Lỗi ({c['gia_tri']})"})
        elif c["xep"] == "canh_bao" and x0 == "dat":
            cb.append({"muc": "trung_binh", "id": c["id"], "ten": c["ten"], "chu": f"{c['ten']}: Đạt → Cảnh báo ({c['gia_tri']})"})
        elif c["xep"] == "dat" and x0 in ("loi", "canh_bao"):
            cb.append({"muc": "tot", "id": c["id"], "ten": c["ten"], "chu": f"{c['ten']}: {TEN_XEP[x0]} → Đạt ({c['gia_tri']})"})
    d0 = (truoc or {}).get("diem")
    if d0 is not None and moi["diem"] is not None and moi["diem"] <= d0 - 5:
        cb.append({"muc": "cao", "id": "diem", "ten": "Điểm sức khoẻ", "chu": f"Điểm sức khoẻ SEO giảm {d0} → {moi['diem']}"})
    return cb


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--khong-toc-do", action="store_true")
    a = ap.parse_args(argv)
    nap_env()
    if not os.environ.get("MAT_KHAU_NOI_BO", "").strip():
        print("Thiếu MAT_KHAU_NOI_BO: bỏ qua (không ghi dữ liệu hở)")
        return 0
    kq = kiem_tra.chay()
    if not a.khong_toc_do:
        bv = (kq.get("trang") or {}).get("bai_viet") or {}
        bai = bv.get("url_cuoi") or bv.get("url")
        try:
            from . import toc_do
            kq["toc_do"] = toc_do.do({"trang_chu": kiem_tra.GOC + "/", **({"bai_viet": bai} if bai else {})})
        except Exception as e:  # noqa: BLE001 - không đo được tốc độ không chặn phần còn lại
            kq["toc_do_loi"] = f"{type(e).__name__}: {str(e)[:160]}"
    ds, diem = chi_so.cham(kq)
    ls = doc_lich_su()
    moi = {"luc": kq["luc"], "diem": diem, "ds": ds}
    canh_bao = so_sanh(ls[-1] if ls else None, moi) if ls else \
        [{"muc": "cao", "id": c["id"], "ten": c["ten"], "chu": f"Lượt kiểm đầu tiên: {c['ten']} đang Lỗi ({c['gia_tri']})"} for c in ds if c["xep"] == "loi"]
    ban_ghi = {"luc": kq["luc"], "diem": diem, "chi_so": {c["id"]: [c["xep"], c["gia_tri"]] for c in ds},
               "toc_do": {k: {m: v.get(m) for m in ("lcp", "cls", "tbt", "kb")} for k, v in (kq.get("toc_do") or {}).items() if isinstance(v, dict)},
               "canh_bao": canh_bao}
    f = LICH_SU / f"{datetime.now(timezone.utc):%Y-%m}.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(ma_hoa.dong(ban_ghi) + "\n")
    ls.append(ban_ghi)
    bc = {"tao_luc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "diem": diem, "chi_so": ds, "nhom": chi_so.NHOM,
          "kiem_tra": kq, "lich_su": [{"luc": r["luc"], "diem": r["diem"], "toc_do": r.get("toc_do") or {},
                                       "dem": {x: sum(1 for v in r["chi_so"].values() if v[0] == x) for x in ("dat", "canh_bao", "loi")}}
                                      for r in ls[-180:]],
          "canh_bao": [{"luc": r["luc"], **c} for r in reversed(ls) for c in r.get("canh_bao") or []][:100]}
    RA.parent.mkdir(parents=True, exist_ok=True)
    RA.write_text(json.dumps(ma_hoa.goi(bc), separators=(",", ":")), encoding="utf-8")
    dem = {x: sum(1 for c in ds if c["xep"] == x) for x in ("dat", "canh_bao", "loi")}
    print(f"Điểm sức khoẻ SEO: {diem} | Đạt {dem['dat']} · Cảnh báo {dem['canh_bao']} · Lỗi {dem['loi']} | cảnh báo mới: {len(canh_bao)}")
    for c in canh_bao:
        print("  -", c["chu"])
    xau = [c for c in canh_bao if c["muc"] in ("cao", "trung_binh")]
    if xau and os.environ.get("SEO_CANH_BAO"):
        cong_khai = lambda c: c["ten"] if chi_so.DINH_NGHIA.get(c["id"], ("",))[0] == "bao_mat" else c["chu"]  # noqa: E731
        Path(os.environ["SEO_CANH_BAO"]).write_text(
            f"**Sức khoẻ SEO wealbee.com: {diem}/100** (Đạt {dem['dat']} · Cảnh báo {dem['canh_bao']} · Lỗi {dem['loi']})\n\n"
            + "\n".join(f"- {'🔴' if c['muc'] == 'cao' else '🟠'} {cong_khai(c)}" for c in xau)
            + f"\n\nChi tiết và cách sửa: {WEB} (cần mật khẩu nhóm).", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
