"""Mã hoá dữ liệu nội bộ (gói Free chỉ được dùng nội bộ + báo cáo hiệu suất): AES-256-GCM, khoá từ mật khẩu qua
PBKDF2-HMAC-SHA256. Cùng định dạng với WebCrypto trong trình duyệt (docs/assets/khoa.js) để web giải mã bằng mật khẩu.

- Gói (file web):  {"v":1,"salt":b64,"iter":N,"iv":b64,"ct":b64}  (ct gồm cả tag GCM ở cuối, giống WebCrypto)
- Dòng (dữ liệu đo, chỉ nối thêm -> git lưu gọn): base64(iv 12 byte + ct), khoá dẫn từ muối cố định trong data/muoi.txt
"""
from __future__ import annotations

import base64
import json
import os
from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ROOT = Path(__file__).resolve().parent.parent
LAP = 210_000
MUOI = ROOT / "data" / "muoi.txt"


def mat_khau() -> str:
    mk = os.environ.get("MAT_KHAU_NOI_BO", "").strip()
    if not mk:
        raise RuntimeError("Thiếu MAT_KHAU_NOI_BO (file .env hoặc GitHub secret)")
    return mk


@lru_cache(maxsize=256)
def _khoa(mk: str, muoi: bytes, lap: int = LAP) -> bytes:
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=muoi, iterations=lap).derive(mk.encode("utf-8"))


_MUOI_LUOT = os.urandom(16)                     # 1 muối cho mọi gói của 1 lượt chạy: dẫn khoá 1 lần (web cũng nhớ khoá theo muối)


def goi(obj, mk: str | None = None) -> dict:
    """Mã hoá 1 đối tượng JSON thành gói cho web."""
    mk = mk or mat_khau()
    muoi, iv = _MUOI_LUOT, os.urandom(12)
    ct = AESGCM(_khoa(mk, muoi)).encrypt(iv, json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), None)
    b = lambda x: base64.b64encode(x).decode()                                  # noqa: E731
    return {"v": 1, "salt": b(muoi), "iter": LAP, "iv": b(iv), "ct": b(ct)}


def mo_goi(g: dict, mk: str | None = None):
    mk = mk or mat_khau()
    d = lambda k: base64.b64decode(g[k])                                        # noqa: E731
    return json.loads(AESGCM(_khoa(mk, d("salt"), int(g.get("iter", LAP)))).decrypt(d("iv"), d("ct"), None))


def _muoi_dong() -> bytes:
    if not MUOI.exists():
        MUOI.parent.mkdir(parents=True, exist_ok=True)
        MUOI.write_text(base64.b64encode(os.urandom(16)).decode(), encoding="utf-8")
    return base64.b64decode(MUOI.read_text(encoding="utf-8").strip())


def dong(obj, mk: str | None = None) -> str:
    iv = os.urandom(12)
    ct = AESGCM(_khoa(mk or mat_khau(), _muoi_dong())).encrypt(iv, json.dumps(obj, ensure_ascii=False).encode("utf-8"), None)
    return base64.b64encode(iv + ct).decode()


def mo_dong(s: str, mk: str | None = None):
    b = base64.b64decode(s)
    return json.loads(AESGCM(_khoa(mk or mat_khau(), _muoi_dong())).decrypt(b[:12], b[12:], None))
