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


def bao_thay_doi_moi() -> None:
    """Máy Windows: GitHub vừa viết báo cáo thay đổi mới (đã kéo về bằng git pull) -> hiện thông báo góc màn hình."""
    import hashlib
    import subprocess
    f, da_xem = ROOT / "docs" / "bao-cao" / "thay_doi.enc", ROOT / "data" / ".thay_doi_da_xem"
    if not f.exists() or sys.platform != "win32":
        return
    bam = hashlib.sha256(f.read_bytes()).hexdigest()
    if da_xem.exists() and da_xem.read_text(encoding="utf-8").strip() == bam:
        return
    lan_dau = not da_xem.exists()
    da_xem.write_text(bam, encoding="utf-8")
    if lan_dau:
        return
    try:
        from . import ma_hoa
        b = ma_hoa.mo_goi(json.loads(f.read_text(encoding="utf-8")))[0]
        chu = (b["tieu_de"] + " - xem: vietnhat-1305.github.io/wealbee-api/bao-cao").replace("'", "")[:230]
        ps = ("[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]>$null;"
              "$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(2);$t=$x.GetElementsByTagName('text');"
              "$t[0].AppendChild($x.CreateTextNode('Wealbee API: bao cao thay doi moi'))>$null;"
              f"$t[1].AppendChild($x.CreateTextNode('{chu}'))>$null;"
              "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Wealbee API').Show("
              "[Windows.UI.Notifications.ToastNotification]::new($x))")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=20)
        print("đã báo: có báo cáo thay đổi mới")
    except Exception as e:  # noqa: BLE001
        print("không hiện được thông báo:", str(e)[:120])


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
    if a.nguon == "may-vn":
        bao_thay_doi_moi()
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
            print(f"{r['goi']}: {r.get('bo_qua') or r.get('sai_goi') or r.get('loi_cau_hinh') or r.get('loi')}")
    if a.dong_bo or a.nguon == "github":
        for d in dong_bo.chay():
            print("đồng bộ", json.dumps(d, ensure_ascii=False))
        from . import tin_tuc
        try:
            print("tin tức", json.dumps(tin_tuc.cap_nhat(), ensure_ascii=False))
        except Exception as e:  # noqa: BLE001 - tin lỗi không chặn báo cáo
            print("tin tức lỗi:", str(e)[:200])
        from . import vietstock
        try:
            print("vietstock", json.dumps(vietstock.chay(), ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            print("vietstock lỗi:", str(e)[:200])
    if not a.khong_bao_cao:
        bc = bao_cao.tao()
        print("báo cáo:", {k: v["diem"] for k, v in bc["goi"].items()}, "| lượt quét:", bc["so_luot"])
        if bc.get("thay_doi_moi"):
            print("BÁO CÁO THAY ĐỔI MỚI:", bc["thay_doi_moi"]["tieu_de"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
