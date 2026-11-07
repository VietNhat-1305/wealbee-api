"""Chạy 1 lượt: quét hiệu suất -> (đồng bộ dữ liệu 2 web) -> dựng lại báo cáo.

    python -m wb_api.chay --nguon github      # GitHub Actions mỗi giờ (máy chủ ở Mỹ): quét + đồng bộ + báo cáo
    python -m wb_api.chay --nguon may-vn      # máy ở Việt Nam (lịch Windows mỗi giờ): quét + báo cáo
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def nap_env() -> None:
    f = ROOT / ".env"
    if not f.exists():
        return
    for ln in f.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k, v = ln.split("=", 1)
            if v.strip() and not os.environ.get(k.strip()):
                os.environ[k.strip()] = v.strip()


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--nguon", default="may-vn")
    ap.add_argument("--dong-bo", action="store_true", help="đồng bộ dữ liệu 2 web (mặc định chỉ khi nguồn github)")
    ap.add_argument("--khong-bao-cao", action="store_true")
    a = ap.parse_args(argv)
    nap_env()
    from . import bao_cao, dong_bo, ma_hoa, quet
    if not os.environ.get("MAT_KHAU_NOI_BO", "").strip():          # chưa cài secret: bỏ qua, không ghi dữ liệu hở
        print("Chưa có MAT_KHAU_NOI_BO (file .env / GitHub secret): bỏ qua lượt này")
        return 0
    rs = quet.chay(a.nguon)
    f = ROOT / "data" / "do" / a.nguon / f"{datetime.now(timezone.utc):%Y-%m}.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        for r in rs:
            fh.write(ma_hoa.dong(r) + "\n")
    for r in rs:
        if r["goi"] == "chung":
            ok = sum(bool(h.get("dung")) for h in r["health"])
            print(f"health: {ok}/{len(r['health'])} ok, {[round(h['ms_tong']) for h in r['health']]} ms")
        elif r.get("luot"):
            ms = sorted(l["ms_tong"] for l in r["luot"] if l.get("dung") and not l.get("lanh"))
            print(f"{r['goi']}: {sum(bool(l.get('dung')) for l in r['luot'])}/{len(r['luot'])} đúng kỳ vọng, "
                  f"p50 {round(ms[len(ms) // 2]) if ms else '-'} ms" + (f" | lỗi: {r['loi']}" if r.get("loi") else ""))
        else:
            print(f"{r['goi']}: {r.get('bo_qua') or r.get('loi')}")
    if a.dong_bo or a.nguon == "github":
        for d in dong_bo.chay():
            print("đồng bộ", json.dumps(d, ensure_ascii=False))
    if not a.khong_bao_cao:
        bc = bao_cao.tao()
        print("báo cáo:", {k: v["diem"] for k, v in bc["goi"].items()}, "| lượt quét:", bc["so_luot"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
