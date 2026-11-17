"""Đưa bản kế hoạch SEO (markdown) lên web dạng mã hoá: docs/seo/ke-hoach/ke_hoach.enc, mở bằng mật khẩu nhóm.

Kế hoạch có điểm yếu bảo mật của wealbee.com (VD host www đi thẳng vào máy chủ gốc) nên không để bản đọc được trong repo công khai.

    python -m wb_seo.ke_hoach <file.md> [--anh khoa=duong_dan.png ...]
    python -m wb_seo.ke_hoach <file.md> --ra docs/seo/huong-dan/huong_dan.enc --tieu-de "..." --mo-ta "..."

Trong markdown, ảnh viết dạng ![chú thích](anh:<khoá>); ảnh được nhúng (base64) vào gói mã hoá.
Cùng khung trang (docs/assets/ke-hoach.js) dùng cho hướng dẫn kỹ thuật sửa lỗi (docs/seo/huong-dan/).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from wb_api import ma_hoa
from wb_api.chay import nap_env

ROOT = Path(__file__).resolve().parent.parent
RA = ROOT / "docs" / "seo" / "ke-hoach" / "ke_hoach.enc"


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("md")
    ap.add_argument("--anh", nargs="*", default=[], help="khoa=duong_dan.png")
    ap.add_argument("--tieu-de", default="Kế hoạch tối ưu SEO toàn diện cho Wealbee")
    ap.add_argument("--mo-ta", default="", help="dòng giới thiệu dưới tiêu đề (bỏ trống: lời giới thiệu kế hoạch)")
    ap.add_argument("--ra", default=str(RA.relative_to(ROOT)), help="đường dẫn gói .enc, tính từ gốc repo")
    a = ap.parse_args(argv)
    nap_env()
    if not os.environ.get("MAT_KHAU_NOI_BO", "").strip():
        raise SystemExit("Thiếu MAT_KHAU_NOI_BO: không ghi bản hở")
    anh = {}
    for x in a.anh:
        k, p = x.split("=", 1)
        anh[k] = "data:image/png;base64," + base64.b64encode(Path(p).read_bytes()).decode()
    goi = {"tieu_de": a.tieu_de, "luc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "md": Path(a.md).read_text(encoding="utf-8"), "anh": anh, **({"mo_ta": a.mo_ta} if a.mo_ta else {})}
    ra = ROOT / a.ra
    ra.parent.mkdir(parents=True, exist_ok=True)
    ra.write_text(json.dumps(ma_hoa.goi(goi), separators=(",", ":")), encoding="utf-8")
    print(f"Đã ghi {ra.relative_to(ROOT)} ({ra.stat().st_size // 1024} KB, {len(anh)} ảnh)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
