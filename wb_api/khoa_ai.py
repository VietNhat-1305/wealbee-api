"""Đưa khoá Gemini (API miễn phí của Google) lên web cho trợ lý AI phân tích đầu tư (docs/assets/ai.js).

Khoá lấy ở https://aistudio.google.com/apikey (miễn phí), ghi vào .env:  GEMINI_API_KEY=AIza...
Script kiểm khoá với Google, thử các model Flash xem model nào còn lượt miễn phí, rồi mã hoá khoá bằng MAT_KHAU_NOI_BO
-> docs/ai/khoa.json. Trên web, ai biết mật khẩu nhóm mới mở được khoá; người khác dán khoá Gemini riêng của họ.

    python -m wb_api.khoa_ai            # tạo / cập nhật docs/ai/khoa.json (rồi commit + push)
    python -m wb_api.khoa_ai --xoa      # gỡ khoá nhóm khỏi web

Nên giới hạn khoá trong Google Cloud Console (APIs & Services -> Credentials -> khoá -> Website restrictions):
chỉ cho https://vietnhat-1305.github.io/* gọi, để khoá lỡ lộ cũng không dùng được ở nơi khác.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone

import httpx

from .chay import ROOT, nap_env
from .ma_hoa import goi

API = "https://generativelanguage.googleapis.com/v1beta"
OUT = ROOT / "docs" / "ai" / "khoa.json"
WEB = "https://vietnhat-1305.github.io/"          # gửi kèm Referer: khoá đã giới hạn theo website vẫn kiểm được


def _ver(n: str) -> float:
    m = re.match(r"gemini-(\d+(?:\.\d+)?)", n)
    return float(m.group(1)) if m else 0.0


def kiem(khoa: str) -> list[str]:
    h = {"x-goog-api-key": khoa, "Referer": WEB, "User-Agent": "wealbee-api-khoa-ai"}
    r = httpx.get(f"{API}/models", params={"pageSize": 1000}, headers=h, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"Google từ chối khoá ({r.status_code}): {r.text[:300]}")
    ten = [m["name"].split("/", 1)[1] for m in r.json().get("models", [])
           if "generateContent" in m.get("supportedGenerationMethods", [])]
    thu = [n for n in ("gemini-flash-latest", "gemini-flash-lite-latest") if n in ten]
    thu += sorted((n for n in ten if re.fullmatch(r"gemini-\d+(\.\d+)?-flash(-lite)?", n)), key=_ver, reverse=True)[:3]
    dung = []
    for n in dict.fromkeys(thu):
        r = httpx.post(f"{API}/models/{n}:generateContent", headers=h, timeout=60,
                       json={"contents": [{"role": "user", "parts": [{"text": "Trả lời đúng 1 từ: OK"}]}]})
        if r.status_code == 200:
            dung.append(n)
            print(f"  ✓ {n}")
        else:
            msg = (r.json().get("error", {}).get("message", "") if "json" in r.headers.get("content-type", "") else r.text)
            print(f"  ✗ {n}: {r.status_code} {msg[:120]}")
    print(f"Khoá hợp lệ: {len(ten)} model; dùng được ngay: {', '.join(dung) or 'chưa model nào (có thể đang hết lượt phút)'}")
    return dung


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xoa", action="store_true", help="gỡ khoá nhóm khỏi web")
    a = ap.parse_args()
    nap_env()
    if a.xoa:
        OUT.unlink(missing_ok=True)
        print("Đã gỡ docs/ai/khoa.json (nhớ commit + push)")
        return
    khoa = os.environ.get("GEMINI_API_KEY", "").strip()
    if not khoa:
        raise SystemExit("Chưa có GEMINI_API_KEY trong .env (lấy miễn phí ở https://aistudio.google.com/apikey)")
    kiem(khoa)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(goi({"khoa": khoa, "luc": datetime.now(timezone.utc).isoformat(timespec="seconds")})),
                   encoding="utf-8")
    print(f"Đã ghi {OUT.relative_to(ROOT)} (mã hoá bằng MAT_KHAU_NOI_BO)")


if __name__ == "__main__":
    main()
