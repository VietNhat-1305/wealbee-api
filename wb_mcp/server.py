"""Wealbee MCP: đưa Wealbee Data API vào trợ lý AI (Claude, ChatGPT, Gemini, ...) qua Model Context Protocol.

Chạy trên máy (stdio), khoá lấy từ biến môi trường hoặc file .env ở gốc repo
(WEALBEE_API_KEY, nếu không có thì WEALBEE_KEY_DN, rồi WEALBEE_KEY_FREE):

    python wb_mcp/server.py
    python -m wb_mcp

Chạy làm máy chủ từ xa (Streamable HTTP, đường dẫn /mcp). Máy chủ không giữ khoá: mỗi người dùng gửi khoá Wealbee
của mình qua header "Authorization: Bearer <khoá>", máy chủ chuyển tiếp nguyên khoá đó tới data.wealbee.com:

    python -m wb_mcp --http --host 0.0.0.0 --port 8000

Biến môi trường khi chạy từ xa: PORT (cổng), WEALBEE_MCP_ALLOWED_HOSTS (danh sách tên miền được phép, cách bằng dấu phẩy,
VD "mcp.wealbee.com" — bật chống DNS rebinding).

Mọi tool chỉ đọc dữ liệu. Không có tool tạo, sửa, xoá (webhook và các thao tác ghi không được đưa vào).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import ToolAnnotations
from pydantic import Field

PHIEN_BAN = "0.2.0"
API = "https://data.wealbee.com/v1"
TU_DIEN_URL = "https://wealbee.com/api/glossary"
UA = f"wealbee-mcp/{PHIEN_BAN}"
GOC = Path(__file__).resolve().parent
HUONG_DAN = (GOC / "huong_dan.md").read_text(encoding="utf-8")
TY = 1_000_000_000
VN = timezone(timedelta(hours=7))

CHE_DO = {"http": False}          # đặt True khi chạy Streamable HTTP: khi đó bắt buộc khoá từ header của người gọi
_TU_DIEN: dict[str, Any] = {"luc": 0.0, "ds": []}
_MAU: dict[tuple, tuple[float, list]] = {}   # (kỳ, loại hình, chỉ đã kiểm chứng) -> (lúc tải, BCTC); đệm 6 giờ
logging.getLogger("httpx").setLevel(logging.WARNING)   # không ghi từng URL gọi API vào log

CHI_DOC = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)

mcp = MCPServer(
    name="wealbee",
    title="Wealbee",
    description="Báo cáo tài chính đã kiểm chứng, file gốc, tin tổng hợp và sự kiện của doanh nghiệp niêm yết Việt Nam.",
    website_url="https://wealbee.com",
    version=PHIEN_BAN,
    instructions=(
        "Dữ liệu tài chính doanh nghiệp niêm yết Việt Nam (HOSE, HNX, UPCOM) từ Wealbee Data API. "
        "Câu hỏi về kết quả kinh doanh: dùng wealbee_statement_summary trước (đã đổi sang tỷ đồng, có tăng trưởng và nguồn). "
        "Đọc resource wealbee://huong-dan để hiểu các trường dữ liệu. "
        "Không khuyến nghị mua, bán, nắm giữ cổ phiếu, không dự báo giá. Luôn dẫn file gốc (document_url) khi dùng số liệu, "
        "và nói rõ khi BCTC đang ở trạng thái needs_review."
    ),
)


# ---------------------------------------------------------------- khoá và gọi API

def _nap_env() -> None:
    """Đọc .env ở gốc repo (không ghi đè biến đã có). Chỉ dùng khi chạy trên máy."""
    f = GOC.parent / ".env"
    if not f.exists():
        return
    for dong in f.read_text(encoding="utf-8").splitlines():
        dong = dong.strip()
        if dong and not dong.startswith("#") and "=" in dong:
            k, v = dong.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _khoa(ctx: Context | None) -> str:
    if CHE_DO["http"]:
        h = (ctx.headers if ctx is not None else None) or {}
        tri = (h.get("authorization") or "").strip()
        if tri.lower().startswith("bearer "):
            tri = tri[7:].strip()
        tri = tri or (h.get("x-wealbee-key") or "").strip()
        if not tri:
            raise ToolError("Thiếu khoá Wealbee. Thêm header 'Authorization: Bearer <khoá Wealbee Data API>' khi kết nối máy chủ MCP.")
        return tri
    for ten in ("WEALBEE_API_KEY", "WEALBEE_KEY_DN", "WEALBEE_KEY_FREE"):
        if os.environ.get(ten, "").strip():
            return os.environ[ten].strip()
    raise ToolError("Chưa có khoá Wealbee. Đặt biến môi trường WEALBEE_API_KEY hoặc thêm vào file .env ở gốc repo.")


def _loi(r: httpx.Response) -> ToolError:
    try:
        p = r.json()
    except ValueError:
        p = {}
    ma = p.get("code") or ""
    chi_tiet = (p.get("detail") or p.get("title") or r.reason_phrase or "").rstrip(".")
    goi_y = {401: " Khoá sai hoặc đã bị thu hồi.", 403: " Gói hiện tại không có quyền với dữ liệu này.",
             404: " Không tìm thấy; kiểm tra lại mã, kỳ hoặc id.", 429: " Vượt giới hạn tốc độ của gói; thử lại sau ít giây."}
    rid = f" (request_id {p['request_id']})" if p.get("request_id") else ""
    return ToolError(f"Wealbee API trả {r.status_code}{' ' + ma if ma else ''}: {chi_tiet}.{goi_y.get(r.status_code, '')}{rid}")


async def _api(ctx: Context | None, duong_dan: str, params: dict | None = None, http: httpx.AsyncClient | None = None) -> Any:
    q = {k: ("true" if v is True else "false" if v is False else v) for k, v in (params or {}).items() if v not in (None, "")}
    h = {"Authorization": f"Bearer {_khoa(ctx)}", "User-Agent": UA}
    rieng = http is None
    http = http or httpx.AsyncClient(base_url=API, timeout=httpx.Timeout(30.0, connect=10.0))
    try:
        for lan in (1, 2):
            try:
                r = await http.get(duong_dan, params=q, headers=h)
            except httpx.HTTPError as e:
                raise ToolError(f"Không kết nối được Wealbee API: {type(e).__name__}") from None
            if r.status_code == 429 and lan == 1:
                try:
                    cho = float(r.headers.get("retry-after") or 1)
                except ValueError:
                    cho = 1.0
                await asyncio.sleep(min(max(cho, 0.5), 5.0))
                continue
            break
        if r.status_code >= 400:
            raise _loi(r)
        return r.json()
    finally:
        if rieng:
            await http.aclose()


def _chuan_ky(ky: str | None) -> str | None:
    """Nhận các cách viết kỳ hay gặp: 2026Q3, 2026-Q3, Q3/2026, Q3 2026, quý 3/2026, 3/2026, 9T/2026 -> 2026Q3."""
    if ky is None or not str(ky).strip():
        return None
    x = re.sub(r"\s+", "", _bo_dau(str(ky))).upper().replace("QUY", "Q")
    for mau in (r"(?P<y>\d{4})[-_/.]?Q(?P<q>[1-4])", r"Q(?P<q>[1-4])[-_/.]?(?P<y>\d{4})", r"(?P<q>[1-4])[-_/.](?P<y>\d{4})"):
        m = re.fullmatch(mau, x)
        if m:
            return f"{m['y']}Q{m['q']}"
    m = re.fullmatch(r"(?P<t>3|6|9|12)T[-_/.]?(?P<y>\d{4})", x)
    if m:
        return f"{m['y']}Q{int(m['t']) // 3}"
    raise ToolError(f"Kỳ '{ky}' không hợp lệ. Viết dạng 2026Q3 (hoặc Q3/2026, quý 3/2026).")


def _chuan_id(sid: str) -> str:
    """hpg.q3/2026 -> HPG.2026Q3"""
    if "." not in (sid or ""):
        raise ToolError(f"Id BCTC '{sid}' không hợp lệ. Viết dạng MÃ.KỲ, VD FPT.2026Q3.")
    ma, ky = sid.strip().split(".", 1)
    return f"{ma.strip().upper()}.{_chuan_ky(ky)}"


def _json(d: Any) -> str:
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))


def _gioi_han(n: int) -> int:
    return max(1, min(int(n), 100))


# ---------------------------------------------------------------- tóm tắt BCTC (đổi tỷ đồng, tăng trưởng, biên)

def _ty(v):
    return None if v is None else round(v / TY, 1)


def _tang(moi, cu):
    """% thay đổi; không tính khi thiếu số, kỳ so sánh bằng 0 hoặc âm (lỗ), hay khi đổi dấu."""
    if moi is None or cu is None or cu <= 0 or moi < 0:
        return None
    return round((moi / cu - 1) * 100, 1)


def _ty_le(tu, mau):
    if tu is None or not mau:
        return None
    return round(tu / mau * 100, 1)


def tom_tat(s: dict) -> dict:
    kq, cd, lc = s.get("income_statement") or {}, s.get("balance_sheet") or {}, s.get("cash_flow") or {}

    def dong_kq(k):
        x = kq.get(k) or {}
        return {"quarter": _ty(x.get("quarter")), "quarter_prior_year": _ty(x.get("quarter_prior_year")),
                "quarter_growth_pct": _tang(x.get("quarter"), x.get("quarter_prior_year")),
                "ytd": _ty(x.get("ytd")), "ytd_prior_year": _ty(x.get("ytd_prior_year")),
                "ytd_growth_pct": _tang(x.get("ytd"), x.get("ytd_prior_year"))}

    def dong_cd(k):
        x = cd.get(k) or {}
        return {"end_of_period": _ty(x.get("end_of_period")), "start_of_year": _ty(x.get("start_of_year"))}

    def dong_lc(k):
        x = lc.get(k) or {}
        return {"ytd": _ty(x.get("ytd")), "ytd_prior_year": _ty(x.get("ytd_prior_year"))}

    def bq(x):
        """Bình quân đầu năm và cuối kỳ (xấp xỉ số dư bình quân trong kỳ)."""
        a, b = (x or {}).get("start_of_year"), (x or {}).get("end_of_period")
        return None if a is None or b is None or a + b <= 0 else (a + b) / 2

    thang = s.get("months_ytd") or 0
    von_me = cd.get("equity_parent") if (cd.get("equity_parent") or {}).get("end_of_period") is not None else None
    roe_ytd = (_ty_le((kq.get("net_profit_parent") or {}).get("ytd"), bq(von_me)) if von_me
               else _ty_le((kq.get("net_profit") or {}).get("ytd"), bq(cd.get("equity"))))
    roa_ytd = _ty_le((kq.get("net_profit") or {}).get("ytd"), bq(cd.get("total_assets")))
    von = (cd.get("equity") or {}).get("end_of_period")
    no, vay = (cd.get("total_liabilities") or {}).get("end_of_period"), (cd.get("borrowings") or {}).get("end_of_period")
    chi_so = {"liabilities_to_equity": None if not von or no is None else round(no / von, 2),
              "borrowings_to_equity": None if not von or vay is None else round(vay / von, 2),
              "roe_ytd_pct": roe_ytd, "roe_annualized_pct": None if roe_ytd is None or not thang else round(roe_ytd * 12 / thang, 1),
              "roe_basis": "net_profit_parent / equity_parent" if von_me else "net_profit / equity (chưa có vốn chủ công ty mẹ)",
              "roa_ytd_pct": roa_ytd, "roa_annualized_pct": None if roa_ytd is None or not thang else round(roa_ytd * 12 / thang, 1)}
    if s.get("industry_type") == "corporate":
        dt = (kq.get("revenue") or {}).get("quarter")
        chi_so["gross_margin_quarter_pct"] = _ty_le((kq.get("gross_profit") or {}).get("quarter"), dt)
        chi_so["net_margin_quarter_pct"] = _ty_le((kq.get("net_profit") or {}).get("quarter"), dt)
    kiem = s.get("checks") or []
    pv = s.get("provenance") or {}
    kq_gon = {k: dong_kq(k) for k in ("revenue", "gross_profit", "net_profit", "net_profit_parent") if k in kq}
    cd_gon = {k: dong_cd(k) for k in ("total_assets", "total_liabilities", "borrowings", "equity", "equity_parent", "non_controlling_interest")
              if k in cd}
    return {
        "ticker": s.get("ticker"), "statement_id": s.get("id"), "period": s.get("period"), "period_label": s.get("period_label"),
        "months_ytd": s.get("months_ytd"), "scope": s.get("scope"), "industry_type": s.get("industry_type"),
        "status": s.get("status"), "review_reasons": s.get("review_reasons") or [], "version": s.get("version"),
        "health_score": s.get("health_score"), "unit": "tỷ đồng",
        "income_statement": {k: v for k, v in kq_gon.items() if v["quarter"] is not None or v["ytd"] is not None},
        "balance_sheet": {k: v for k, v in cd_gon.items() if v["end_of_period"] is not None or v["start_of_year"] is not None},
        "missing_fields": [k for k, v in {**kq_gon, **cd_gon}.items() if all(x is None for x in v.values())],
        "cash_flow": {k: dong_lc(k) for k in ("operating", "investing", "financing", "net_change") if k in lc},
        "ratios": chi_so,
        "checks": {"passed": sum(1 for c in kiem if c.get("status") == "passed"), "total": len(kiem),
                   "not_passed": [c.get("code") for c in kiem if c.get("status") != "passed"]},
        "derived_fields": [d.get("path") for d in s.get("derived") or []],
        "source": {"document_url": pv.get("document_url"), "file_sha256": pv.get("file_sha256"), "pages": pv.get("pages"),
                   "ir_url": pv.get("ir_url"), "detected_at": pv.get("detected_at"), "updated_at": pv.get("updated_at")},
        "notes": "Số tiền đổi sang tỷ đồng, làm tròn 1 chữ số thập phân. Tăng trưởng % để trống khi kỳ so sánh lỗ, bằng 0 hoặc đổi dấu. "
                 "Biên lợi nhuận chỉ tính cho doanh nghiệp thường. Các chỉ số trong 'ratios' do máy chủ Wealbee MCP tính từ số liệu BCTC: "
                 "ROE = lợi nhuận sau thuế của cổ đông công ty mẹ luỹ kế / bình quân vốn chủ của cổ đông công ty mẹ (đầu năm, cuối kỳ), "
                 "khi BCTC chưa có vốn chủ công ty mẹ thì dùng lợi nhuận sau thuế / tổng vốn chủ (xem roe_basis); "
                 "ROA = lợi nhuận sau thuế luỹ kế / bình quân tổng tài sản; '_annualized' nhân 12 / months_ytd. "
                 "'missing_fields' là chỉ tiêu Data API chưa có cho BCTC này (VD doanh thu của ngân hàng), không phải bằng 0.",
    }


def _bo_dau(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower().strip()


# ---------------------------------------------------------------- tools

Ma = Annotated[str, Field(description="Mã cổ phiếu, VD FPT, VCB, HPG")]
Ky = Annotated[str | None, Field(description="Kỳ tài chính dạng 2026Q3; bỏ trống = mọi kỳ")]
Con = Annotated[str | None, Field(description="next_cursor của trang trước, để lấy trang tiếp theo")]
SoDong = Annotated[int, Field(description="Số bản ghi mỗi trang, 1–100")]


@mcp.tool(title="Gói dữ liệu và hạn mức", annotations=CHI_DOC, structured_output=False)
async def wealbee_account_info(ctx: Context) -> str:
    """Xem gói Wealbee của khoá đang dùng: sản phẩm được phép, sàn, giới hạn tốc độ, hạn dùng, số request đã dùng trong tháng."""
    d = await _api(ctx, "/me")
    d.pop("key_prefix", None)
    han = (d.get("entitlements") or {}).get("valid_until")
    if han:
        con = (datetime.fromisoformat(han) - datetime.now(VN)).days
        d["days_left"] = con
        if con < 14:
            d["warning"] = f"Khoá Wealbee còn {con} ngày (hết hạn {han[:10]}). Cần gia hạn để các luồng không dừng."
    return _json(d)


@mcp.tool(title="Tìm công ty", annotations=CHI_DOC, structured_output=False)
async def wealbee_search_companies(
    ctx: Context,
    query: Annotated[str | None, Field(description="Tìm trong mã và tên công ty, không phân biệt dấu, tối đa 40 ký tự")] = None,
    exchange: Literal["HOSE", "HNX", "UPCOM"] | None = None,
    industry_type: Annotated[Literal["corporate", "bank", "securities", "insurance"] | None,
                             Field(description="corporate = doanh nghiệp thường, bank = ngân hàng, securities = chứng khoán, insurance = bảo hiểm")] = None,
    has_statements: Annotated[bool | None, Field(description="true: chỉ công ty đã có BCTC; false: chỉ công ty chưa có")] = None,
    limit: SoDong = 20,
    cursor: Con = None,
) -> str:
    """Tìm công ty niêm yết theo mã, tên, sàn, loại hình. Mỗi công ty có coverage cho biết khoảng kỳ BCTC đang có."""
    return _json(await _api(ctx, "/companies", {"q": query, "exchange": exchange, "industry_type": industry_type,
                                          "has_statements": has_statements, "limit": _gioi_han(limit), "cursor": cursor}))


@mcp.tool(title="Thông tin công ty", annotations=CHI_DOC, structured_output=False)
async def wealbee_get_company(ticker: Ma, ctx: Context) -> str:
    """Thông tin một công ty: tên, sàn, loại hình, trang quan hệ cổ đông, khoảng kỳ BCTC đang có (coverage)."""
    return _json(await _api(ctx, f"/companies/{ticker.strip().upper()}"))


@mcp.tool(title="Tóm tắt BCTC", annotations=CHI_DOC, structured_output=False)
async def wealbee_statement_summary(ticker: Ma, ctx: Context, period: Ky = None) -> str:
    """Tóm tắt một BCTC quý: doanh thu, lợi nhuận, tài sản, nợ, vốn chủ, lưu chuyển tiền (tỷ đồng), tăng trưởng so với cùng kỳ,
    biên lợi nhuận, trạng thái kiểm chứng và link file gốc. Bỏ trống period để lấy kỳ mới nhất.
    Nên dùng tool này trước tiên cho câu hỏi về kết quả kinh doanh."""
    t, period = ticker.strip().upper(), _chuan_ky(period)
    if period:
        s = await _api(ctx, f"/statements/{t}.{period}")
    else:
        s = await _api(ctx, f"/companies/{t}/statements/latest", {"view": "full"})
    return _json(tom_tat(s))


@mcp.tool(title="So sánh nhiều công ty", annotations=CHI_DOC, structured_output=False)
async def wealbee_compare_companies(
    tickers: Annotated[list[str], Field(description="2–10 mã cổ phiếu, VD [\"VCB\", \"BID\", \"CTG\"]")],
    ctx: Context,
    period: Ky = None,
) -> str:
    """Đặt tóm tắt BCTC của nhiều công ty cạnh nhau (tỷ đồng, tăng trưởng, biên, nợ/vốn chủ, trạng thái kiểm chứng).
    Bỏ trống period để lấy kỳ mới nhất của từng công ty. Chỉ để so sánh số liệu, không xếp hạng nên mua."""
    ds = list(dict.fromkeys(t.strip().upper() for t in tickers if t.strip()))[:10]
    period = _chuan_ky(period)
    if not ds:
        raise ToolError("Cần ít nhất một mã cổ phiếu.")
    async with httpx.AsyncClient(base_url=API, timeout=httpx.Timeout(30.0, connect=10.0)) as http:
        async def mot(t):
            try:
                if period:
                    s = await _api(ctx, f"/statements/{t}.{period}", http=http)
                else:
                    s = await _api(ctx, f"/companies/{t}/statements/latest", {"view": "full"}, http=http)
                g = tom_tat(s)
                kq = g["income_statement"]
                return {"ticker": t, "period": g["period"], "status": g["status"], "industry_type": g["industry_type"],
                        "revenue_quarter": (kq.get("revenue") or {}).get("quarter"),
                        "revenue_growth_pct": (kq.get("revenue") or {}).get("quarter_growth_pct"),
                        "net_profit_parent_quarter": (kq.get("net_profit_parent") or {}).get("quarter"),
                        "net_profit_parent_growth_pct": (kq.get("net_profit_parent") or {}).get("quarter_growth_pct"),
                        "net_profit_parent_ytd": (kq.get("net_profit_parent") or {}).get("ytd"),
                        **g["ratios"], "health_score": g["health_score"], "document_url": g["source"]["document_url"]}
            except ToolError as e:
                return {"ticker": t, "error": str(e)}
        hang = await asyncio.gather(*(mot(t) for t in ds))
    return _json({"unit": "tỷ đồng", "companies": hang,
            "notes": "Tăng trưởng so với cùng kỳ năm trước. Kỳ của từng công ty có thể khác nhau khi không chỉ định period."})


def _mot_ban_moi_ky(ds: list[dict]) -> dict[str, dict]:
    """Mỗi (mã, kỳ) giữ 1 BCTC: ưu tiên hợp nhất, rồi phiên bản mới nhất."""
    out: dict[str, dict] = {}
    for s in ds:
        k = f"{s.get('ticker')}.{s.get('period')}"
        cu = out.get(k)
        diem = (s.get("scope") == "consolidated", s.get("version") or 0)
        if cu is None or diem > (cu.get("scope") == "consolidated", cu.get("version") or 0):
            out[k] = s
    return out


def _ky_truoc(ky: str, buoc: int) -> str:
    """2026Q1 lùi 1 quý -> 2025Q4; lùi 4 quý -> 2025Q1."""
    n = int(ky[:4]) * 4 + int(ky[-1]) - 1 - buoc
    return f"{n // 4}Q{n % 4 + 1}"


@mcp.tool(title="Xu hướng theo quý", annotations=CHI_DOC, structured_output=False)
async def wealbee_quarterly_trend(ticker: Ma, ctx: Context) -> str:
    """Chuỗi số liệu theo quý của một công ty (tỷ đồng): doanh thu, lợi nhuận sau thuế của cổ đông công ty mẹ, biên gộp, biên ròng,
    vốn chủ của cổ đông công ty mẹ; tăng trưởng so với cùng kỳ và so với quý trước. Gồm cả các quý năm trước lấy từ cột
    "cùng kỳ năm trước" trong BCTC. Dùng để vẽ biểu đồ hoặc trả lời "lợi nhuận đang tăng hay giảm"."""
    t = ticker.strip().upper()
    d = await _api(ctx, "/statements", {"ticker": t, "view": "full", "limit": 100})
    theo_ky = {s["period"]: s for s in _mot_ban_moi_ky(d.get("data") or []).values()}
    if not theo_ky:
        raise ToolError(f"Chưa có BCTC nào của {t}.")
    hang: dict[str, dict] = {}

    def q(s, k, cot="quarter"):
        return ((s.get("income_statement") or {}).get(k) or {}).get(cot)

    for ky, s in sorted(theo_ky.items()):
        dt, lg, ln = q(s, "revenue"), q(s, "gross_profit"), q(s, "net_profit_parent")
        hang[ky] = {"period": ky, "source": "statement", "status": s.get("status"), "revenue": _ty(dt), "net_profit_parent": _ty(ln),
                    "gross_margin_pct": _ty_le(lg, dt) if s.get("industry_type") == "corporate" else None,
                    "net_margin_pct": _ty_le(ln, dt) if s.get("industry_type") == "corporate" else None,
                    "equity_parent_end": _ty(((s.get("balance_sheet") or {}).get("equity_parent") or {}).get("end_of_period")),
                    "document_url": (s.get("provenance") or {}).get("document_url")}
        nt = _ky_truoc(ky, 4)
        if nt not in theo_ky and nt not in hang:
            dt0, lg0, ln0 = q(s, "revenue", "quarter_prior_year"), q(s, "gross_profit", "quarter_prior_year"), q(s, "net_profit_parent", "quarter_prior_year")
            hang[nt] = {"period": nt, "source": f"cột cùng kỳ năm trước trong BCTC {ky}", "status": s.get("status"),
                        "revenue": _ty(dt0), "net_profit_parent": _ty(ln0),
                        "gross_margin_pct": _ty_le(lg0, dt0) if s.get("industry_type") == "corporate" else None,
                        "net_margin_pct": _ty_le(ln0, dt0) if s.get("industry_type") == "corporate" else None,
                        "equity_parent_end": None, "document_url": (s.get("provenance") or {}).get("document_url")}
    for ky, h in hang.items():
        for k in ("revenue", "net_profit_parent"):
            nt, qt = hang.get(_ky_truoc(ky, 4)), hang.get(_ky_truoc(ky, 1))
            h[f"{k}_yoy_pct"] = _tang(h[k], nt[k]) if nt else None
            h[f"{k}_qoq_pct"] = _tang(h[k], qt[k]) if qt else None
    return _json({"ticker": t, "unit": "tỷ đồng", "industry_type": next(iter(theo_ky.values())).get("industry_type"),
                  "quarters": [hang[k] for k in sorted(hang)],
                  "notes": "Số riêng từng quý. Quý có source khác 'statement' lấy từ cột cùng kỳ năm trước của BCTC năm sau, "
                           "có thể đã được điều chỉnh hồi tố. Tăng trưởng để trống khi kỳ so sánh lỗ, bằng 0 hoặc đổi dấu."})


def _phan_vi(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    i = (len(xs) - 1) * p
    a, b = int(i), min(int(i) + 1, len(xs) - 1)
    return round(xs[a] + (xs[b] - xs[a]) * (i - a), 2)


CHI_SO_SO_SANH = {
    "revenue_growth_pct": ("Tăng trưởng doanh thu quý so với cùng kỳ (%)", lambda g: (g["income_statement"].get("revenue") or {}).get("quarter_growth_pct")),
    "net_profit_parent_growth_pct": ("Tăng trưởng lợi nhuận công ty mẹ quý so với cùng kỳ (%)",
                                     lambda g: (g["income_statement"].get("net_profit_parent") or {}).get("quarter_growth_pct")),
    "net_profit_parent_ytd_growth_pct": ("Tăng trưởng lợi nhuận công ty mẹ luỹ kế (%)",
                                         lambda g: (g["income_statement"].get("net_profit_parent") or {}).get("ytd_growth_pct")),
    "gross_margin_quarter_pct": ("Biên lợi nhuận gộp quý (%)", lambda g: g["ratios"].get("gross_margin_quarter_pct")),
    "net_margin_quarter_pct": ("Biên lợi nhuận ròng quý (%)", lambda g: g["ratios"].get("net_margin_quarter_pct")),
    "roe_annualized_pct": ("ROE quy năm (%)", lambda g: g["ratios"].get("roe_annualized_pct")),
    "roa_annualized_pct": ("ROA quy năm (%)", lambda g: g["ratios"].get("roa_annualized_pct")),
    "liabilities_to_equity": ("Nợ phải trả / vốn chủ (lần)", lambda g: g["ratios"].get("liabilities_to_equity")),
}


async def _bctc_ky(ctx: Context | None, ky: str, loai: str, chi_kiem_chung: bool) -> list[dict]:
    khoa = (ky, loai, chi_kiem_chung)
    if khoa in _MAU and time.monotonic() - _MAU[khoa][0] < 6 * 3600:
        return _MAU[khoa][1]
    ds, con = [], None
    async with httpx.AsyncClient(base_url=API, timeout=httpx.Timeout(30.0, connect=10.0)) as http:
        for _ in range(40):                                    # tối đa 4.000 BCTC
            d = await _api(ctx, "/statements", {"period": ky, "industry_type": loai, "view": "full", "limit": 100, "cursor": con,
                                                "status": "verified" if chi_kiem_chung else None}, http=http)
            ds += d.get("data") or []
            con = d.get("next_cursor")
            if not con:
                break
    ds = list(_mot_ban_moi_ky(ds).values())
    _MAU[khoa] = (time.monotonic(), ds)
    return ds


@mcp.tool(title="So với trung vị cùng loại hình", annotations=CHI_DOC, structured_output=False)
async def wealbee_industry_benchmark(
    ctx: Context,
    ticker: Annotated[str | None, Field(description="Mã cần đặt cạnh trung vị; bỏ trống thì chỉ trả trung vị của loại hình")] = None,
    industry_type: Annotated[Literal["corporate", "bank", "securities", "insurance"] | None,
                             Field(description="Bỏ trống khi có ticker (lấy theo loại hình của mã)")] = None,
    period: Annotated[str | None, Field(description="Kỳ, VD 2026Q3; bỏ trống = kỳ mới nhất của mã")] = None,
    verified_only: Annotated[bool, Field(description="Chỉ tính BCTC đã kiểm chứng")] = True,
) -> str:
    """Trung vị, tứ phân vị 25% và 75% của các chỉ số (tăng trưởng, biên lợi nhuận, ROE, ROA, nợ/vốn chủ) trên mọi BCTC cùng loại hình
    và cùng kỳ; nếu có ticker thì đặt số của mã cạnh đó, kèm vị trí phần trăm. Dùng cho câu "so với các doanh nghiệp khác thì sao",
    thay cho "mức tốt" theo ý kiến. Lần đầu mỗi kỳ có thể mất vài giây (doanh nghiệp thường có khoảng 1.000 BCTC); kết quả được đệm 6 giờ."""
    period = _chuan_ky(period)
    rieng = None
    if ticker:
        t = ticker.strip().upper()
        s = await (_api(ctx, f"/statements/{t}.{period}") if period else _api(ctx, f"/companies/{t}/statements/latest", {"view": "full"}))
        rieng = tom_tat(s)
        period, industry_type = rieng["period"], rieng["industry_type"]
    if not period or not industry_type:
        raise ToolError("Cần ticker, hoặc cả industry_type và period.")
    ds = [tom_tat(s) for s in await _bctc_ky(ctx, period, industry_type, verified_only)]
    ket = {}
    for k, (ten, lay) in CHI_SO_SO_SANH.items():
        xs = [v for v in (lay(g) for g in ds) if isinstance(v, (int, float))]
        if len(xs) < 5:
            continue
        muc = {"label": ten, "n": len(xs), "p25": _phan_vi(xs, 0.25), "median": _phan_vi(xs, 0.5), "p75": _phan_vi(xs, 0.75)}
        if rieng is not None and isinstance(lay(rieng), (int, float)):
            v = lay(rieng)
            muc.update(company=v, company_percentile=round(sum(1 for x in xs if x <= v) / len(xs) * 100))
        ket[k] = muc
    return _json({"period": period, "industry_type": industry_type, "statements": len(ds), "verified_only": verified_only,
                  **({"ticker": rieng["ticker"], "company_status": rieng["status"]} if rieng else {}), "metrics": ket,
                  "notes": "Loại hình theo Data API (corporate, bank, securities, insurance); 'corporate' gồm mọi ngành sản xuất, thương mại, "
                           "dịch vụ nên trung vị chỉ là mốc chung, chưa phải trung vị từng ngành. ROE của mỗi BCTC tính theo roe_basis riêng "
                           "(vốn chủ công ty mẹ khi có, không thì tổng vốn chủ). company_percentile là phần trăm BCTC có giá trị "
                           "nhỏ hơn hoặc bằng số của mã, chỉ để định vị số liệu, không phải xếp hạng nên mua."})


@mcp.tool(title="BCTC mới nhất (đầy đủ)", annotations=CHI_DOC, structured_output=False)
async def wealbee_get_latest_statement(
    ticker: Ma, ctx: Context,
    view: Annotated[Literal["full", "basic"], Field(description="full: đủ phép kiểm và nguồn; basic: gọn hơn")] = "full",
) -> str:
    """BCTC quý mới nhất của một công ty, nguyên dạng API (số tiền tính bằng đồng), gồm phép kiểm, chỉ tiêu tự tính và nguồn gốc."""
    return _json(await _api(ctx, f"/companies/{ticker.strip().upper()}/statements/latest", {"view": view}))


@mcp.tool(title="Danh sách BCTC", annotations=CHI_DOC, structured_output=False)
async def wealbee_list_statements(
    ctx: Context,
    ticker: Annotated[str | None, Field(description="Một hoặc nhiều mã, cách bằng dấu phẩy (tối đa 100)")] = None,
    period: Ky = None,
    industry_type: Literal["corporate", "bank", "securities", "insurance"] | None = None,
    status: Annotated[Literal["verified", "needs_review"] | None, Field(description="verified = đã kiểm chứng; needs_review = chờ xem lại")] = None,
    updated_since: Annotated[str | None, Field(description="Chỉ BCTC cập nhật từ thời điểm này, RFC 3339, VD 2026-11-01T00:00:00+07:00")] = None,
    as_of: Annotated[str | None, Field(description="Xem số liệu như tại thời điểm này trong quá khứ (point-in-time)")] = None,
    view: Literal["basic", "full"] = "basic",
    limit: SoDong = 20,
    cursor: Con = None,
) -> str:
    """Danh sách BCTC lọc theo mã, kỳ, loại hình, trạng thái, thời điểm cập nhật. Số tiền tính bằng đồng."""
    return _json(await _api(ctx, "/statements", {"ticker": ticker, "period": _chuan_ky(period), "industry_type": industry_type, "status": status,
                                           "updated_since": updated_since, "as_of": as_of, "view": view,
                                           "limit": _gioi_han(limit), "cursor": cursor}))


@mcp.tool(title="Một BCTC theo id", annotations=CHI_DOC, structured_output=False)
async def wealbee_get_statement(
    statement_id: Annotated[str, Field(description="Id BCTC dạng MÃ.KỲ, VD FPT.2026Q3")],
    ctx: Context,
    as_of: Annotated[str | None, Field(description="Phiên bản hiện hành tại thời điểm này (RFC 3339)")] = None,
) -> str:
    """Một BCTC theo id, nguyên dạng API (đồng). Dùng as_of để xem số liệu như đã công bố tại một thời điểm."""
    return _json(await _api(ctx, f"/statements/{_chuan_id(statement_id)}", {"as_of": as_of}))


@mcp.tool(title="Lịch sử phiên bản BCTC", annotations=CHI_DOC, structured_output=False)
async def wealbee_statement_versions(
    statement_id: Annotated[str, Field(description="Id BCTC dạng MÃ.KỲ, VD FPT.2026Q3")],
    ctx: Context,
    version: Annotated[int | None, Field(description="Số phiên bản cần xem chi tiết; bỏ trống = danh sách mọi phiên bản")] = None,
) -> str:
    """Các lần BCTC được cập nhật: lý do, trạng thái, mã băm file gốc, các thay đổi. Truyền version để xem số liệu của một phiên bản."""
    sid = _chuan_id(statement_id)
    if version is not None:
        return _json(await _api(ctx, f"/statements/{sid}/versions/{int(version)}", {"view": "full"}))
    return _json(await _api(ctx, f"/statements/{sid}/versions"))


@mcp.tool(title="File BCTC gốc", annotations=CHI_DOC, structured_output=False)
async def wealbee_list_filings(
    ctx: Context,
    ticker: Annotated[str | None, Field(description="Một hoặc nhiều mã, cách bằng dấu phẩy")] = None,
    period: Ky = None,
    status: Literal["processing", "in_review", "published", "superseded"] | None = None,
    detected_since: Annotated[str | None, Field(description="Chỉ file phát hiện từ thời điểm này (RFC 3339)")] = None,
    limit: SoDong = 20,
    cursor: Con = None,
) -> str:
    """File BCTC gốc mà Wealbee thu thập: link tải, mã băm SHA-256, ngày doanh nghiệp công bố, lúc Wealbee phát hiện, trạng thái xử lý."""
    return _json(await _api(ctx, "/filings", {"ticker": ticker, "period": _chuan_ky(period), "status": status, "detected_since": detected_since,
                                        "limit": _gioi_han(limit), "cursor": cursor}))


@mcp.tool(title="Tin tổng hợp", annotations=CHI_DOC, structured_output=False)
async def wealbee_list_news(
    ctx: Context,
    ticker: Annotated[str | None, Field(description="Một hoặc nhiều mã, cách bằng dấu phẩy")] = None,
    category: Literal["company", "industry", "macro", "market", "commodity", "other"] | None = None,
    published_since: Annotated[str | None, Field(description="Chỉ tin có bài đăng từ thời điểm này (RFC 3339)")] = None,
    updated_since: Annotated[str | None, Field(description="Chỉ tin thay đổi từ thời điểm này (RFC 3339)")] = None,
    days: Annotated[int | None, Field(description="Chỉ tin trong N ngày gần nhất, tính theo giờ Việt Nam (thay cho published_since)")] = None,
    limit: SoDong = 20,
    cursor: Con = None,
) -> str:
    """Tin tổng hợp từ nhiều báo, mới nhất trước. Mỗi tin là một sự kiện gộp nhiều bài: tóm tắt, sắc thái, số nguồn, danh sách bài gốc."""
    if days and not published_since:
        published_since = (datetime.now(VN) - timedelta(days=max(1, min(int(days), 365)))).isoformat(timespec="seconds")
    return _json(await _api(ctx, "/news", {"ticker": ticker, "category": category, "published_since": published_since,
                                     "updated_since": updated_since, "limit": _gioi_han(limit), "cursor": cursor}))


@mcp.tool(title="Chi tiết tin", annotations=CHI_DOC, structured_output=False)
async def wealbee_get_news(news_id: Annotated[str, Field(description="id của tin, lấy từ wealbee_list_news")], ctx: Context) -> str:
    """Chi tiết một tin: các bài báo gốc và phân tích của Wealbee (điểm đồng thuận, khác biệt giữa các nguồn)."""
    return _json(await _api(ctx, f"/news/{news_id.strip()}"))


@mcp.tool(title="Sự kiện thay đổi dữ liệu", annotations=CHI_DOC, structured_output=False)
async def wealbee_list_events(
    ctx: Context,
    event_types: Annotated[str | None, Field(description="Một hoặc nhiều loại, cách bằng dấu phẩy: statement.updated, statement.withdrawn, news.published, news.updated")] = None,
    ticker: Annotated[str | None, Field(description="Mã cổ phiếu")] = None,
    created_since: Annotated[str | None, Field(description="Chỉ sự kiện từ thời điểm này (RFC 3339)")] = None,
    limit: SoDong = 20,
    cursor: Con = None,
) -> str:
    """Luồng sự kiện khi dữ liệu thay đổi (BCTC mới hoặc được sửa, tin mới). Dùng để trả lời 'có gì mới về mã X từ hôm qua'."""
    return _json(await _api(ctx, "/events", {"type": event_types, "ticker": ticker, "created_since": created_since,
                                       "limit": _gioi_han(limit), "cursor": cursor}))


async def _lay_tu_dien() -> list[dict]:
    if _TU_DIEN["ds"] and time.monotonic() - _TU_DIEN["luc"] < 24 * 3600:
        return _TU_DIEN["ds"]
    try:
        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": UA}) as http:
            r = await http.get(TU_DIEN_URL)
            r.raise_for_status()
            j = r.json()
    except (httpx.HTTPError, ValueError):
        if _TU_DIEN["ds"]:
            return _TU_DIEN["ds"]
        raise ToolError("Không tải được từ điển Wealbee lúc này.") from None
    ds = j if isinstance(j, list) else (j.get("items") or j.get("terms") or j.get("data") or [])
    _TU_DIEN.update(luc=time.monotonic(), ds=ds)
    return ds


@mcp.tool(title="Tra từ điển đầu tư", annotations=CHI_DOC, structured_output=False)
async def wealbee_glossary(term: Annotated[str, Field(description="Thuật ngữ cần tra, tiếng Việt hoặc tiếng Anh, VD P/E, ROE, biên lãi ròng")]) -> str:
    """Tra từ điển đầu tư Wealbee (khoảng 490 thuật ngữ): định nghĩa, tên tiếng Anh, ví dụ, thuật ngữ liên quan. Không cần khoá API."""
    q = _bo_dau(term)
    if not q:
        raise ToolError("Cần nhập thuật ngữ.")
    ds = await _lay_tu_dien()

    def diem(t: dict) -> int:
        ten = [_bo_dau(t.get("term") or ""), _bo_dau(t.get("en") or "")] + [_bo_dau(a) for a in t.get("aliases") or []]
        if q in ten:
            return 3
        if any(x.startswith(q) for x in ten):
            return 2
        return 1 if any(q in x for x in ten) else 0

    hop = sorted((t for t in ds if diem(t)), key=lambda t: -diem(t))[:5]
    return _json({"query": term, "matches": [{k: t.get(k) for k in ("term", "en", "topic", "definition", "example", "aliases", "related")} for t in hop],
            "note": None if hop else "Không thấy trong từ điển Wealbee."})


# ---------------------------------------------------------------- resources

@mcp.resource("wealbee://huong-dan", name="huong-dan", title="Cách dùng dữ liệu Wealbee", mime_type="text/markdown",
              description="Ý nghĩa các trường BCTC, trạng thái kiểm chứng, đơn vị, phạm vi kỳ và quy tắc khi trả lời người dùng.")
def tai_lieu_huong_dan() -> str:
    return HUONG_DAN


@mcp.resource("wealbee://tu-dien", name="tu-dien", title="Từ điển đầu tư Wealbee", mime_type="application/json",
              description="Toàn bộ từ điển đầu tư Wealbee: thuật ngữ, tên tiếng Anh, chủ đề, định nghĩa, ví dụ, thuật ngữ liên quan.")
async def tai_lieu_tu_dien() -> str:
    return _json([{k: t.get(k) for k in ("term", "en", "topic", "definition", "example", "aliases", "related")} for t in await _lay_tu_dien()])


# ---------------------------------------------------------------- prompts

QUY_TAC = ("Quy tắc: không khuyến nghị mua, bán, nắm giữ; không giá mục tiêu, không dự báo giá. "
           "Mỗi số liệu ghi kỳ, đơn vị và dẫn link file gốc (document_url). Nói rõ nếu BCTC đang needs_review. "
           "Thuật ngữ lần đầu viết đủ tên tiếng Việt, viết tắt và tên tiếng Anh; tra bằng wealbee_glossary khi cần.")


@mcp.prompt(title="Phân tích BCTC quý gần nhất")
def phan_tich_bctc(ticker: str) -> str:
    """Tóm tắt và giải thích BCTC quý gần nhất của một mã, kèm trạng thái kiểm chứng và nguồn."""
    return (f"Phân tích BCTC quý gần nhất của {ticker.upper()} cho nhà đầu tư cá nhân.\n"
            f"1. Gọi wealbee_statement_summary với ticker={ticker.upper()}.\n"
            "2. Trình bày: doanh thu, lợi nhuận sau thuế của cổ đông công ty mẹ, tăng trưởng so với cùng kỳ (quý và luỹ kế), "
            "biên lợi nhuận nếu có, ROE quy năm (trên vốn chủ của cổ đông công ty mẹ), nợ phải trả và vay so với vốn chủ, dòng tiền kinh doanh.\n"
            f"3. Gọi wealbee_quarterly_trend với ticker={ticker.upper()} để nói lợi nhuận đang tăng hay giảm qua các quý.\n"
            f"4. Gọi wealbee_industry_benchmark với ticker={ticker.upper()} và đặt các chỉ số cạnh trung vị cùng loại hình "
            "(nói rõ đây là mốc chung của loại hình, không phải xếp hạng).\n"
            "5. Nêu các điểm cần đọc kỹ: chỉ tiêu tăng giảm mạnh, dòng tiền kinh doanh âm, phép kiểm không đạt, chỉ tiêu Wealbee tự tính.\n"
            f"6. Gọi wealbee_list_news với ticker={ticker.upper()}, days=30, limit=5 để nêu tin liên quan tới kết quả này, nếu có.\n"
            "7. Kết thúc bằng phần 'Nguồn' có link file gốc.\n" + QUY_TAC)


@mcp.prompt(title="Tin nổi bật của một mã")
def tin_noi_bat(ticker: str, so_ngay: int = 7) -> str:
    """Tóm tắt tin về một mã trong N ngày gần nhất, nêu điểm các báo đưa giống và khác nhau."""
    return (f"Tóm tắt tin về {ticker.upper()} trong {so_ngay} ngày gần nhất.\n"
            f"1. Gọi wealbee_list_news với ticker={ticker.upper()}, days={so_ngay}.\n"
            "2. Với 3 tin có nhiều nguồn nhất, gọi wealbee_get_news để xem phân tích.\n"
            "3. Với mỗi tin: điều đã xảy ra, số nguồn và nguồn chính thức, các báo nói giống và khác nhau ở đâu.\n"
            "4. Phân biệt sự kiện đã công bố với nhận định của báo. Không suy đoán thêm.\n" + QUY_TAC)


@mcp.prompt(title="So sánh doanh nghiệp")
def so_sanh_doanh_nghiep(danh_sach_ma: str) -> str:
    """Đặt số liệu BCTC của vài doanh nghiệp cạnh nhau và giải thích khác biệt, không xếp hạng nên mua."""
    return (f"So sánh BCTC gần nhất của các mã: {danh_sach_ma}.\n"
            "1. Gọi wealbee_compare_companies với danh sách mã này.\n"
            "2. Lập bảng: kỳ, doanh thu quý, tăng trưởng, lợi nhuận công ty mẹ, tăng trưởng, biên lợi nhuận, ROE quy năm, nợ phải trả/vốn chủ, trạng thái.\n"
            "3. Giải thích các khác biệt lớn và lý do có thể (quy mô, mô hình kinh doanh, kỳ khác nhau). Lưu ý khi so doanh nghiệp khác loại hình.\n"
            "4. Không xếp hạng mã nào tốt hơn để mua.\n" + QUY_TAC)


@mcp.prompt(title="Viết bài blog Wealbee")
def viet_blog(chu_de: str, loai_bai: str = "giải thích thuật ngữ", tu_khoa_chinh: str = "") -> str:
    """Viết bài blog theo cẩm nang Wealbee, dùng số liệu thật lấy qua các tool."""
    return (f"Viết bài blog Wealbee. Chủ đề: {chu_de}. Loại bài: {loai_bai}. Từ khoá chính: {tu_khoa_chinh or chu_de}.\n"
            "Lấy số liệu bằng các tool Wealbee (wealbee_statement_summary, wealbee_compare_companies, wealbee_quarterly_trend, "
            "wealbee_industry_benchmark cho trung vị cùng loại hình, wealbee_glossary); "
            "chỉ dùng số tool trả về, thiếu thì ghi [CẦN SỐ LIỆU].\n"
            "Khuôn bài: tiêu đề chứa từ khoá; sapo 2–3 câu trả lời thẳng câu hỏi; bảng 'Nhìn nhanh' nếu có từ 3 chỉ số; "
            "các mục là câu hỏi người đọc gõ vào Google; mỗi chỉ số theo thứ tự định nghĩa, công thức, ví dụ số thật, cách đọc "
            "(so với doanh nghiệp cùng ngành, không đưa 'mức tốt' theo ý kiến), khi nào gây hiểu sai; 'Lưu ý khi dùng'; "
            "4–8 câu hỏi thường gặp; tóm tắt 3 ý; khung cuối bài có ngày kiểm số liệu, câu 'Bài viết có sự hỗ trợ của AI' "
            "và 'Thông tin tham khảo, không phải khuyến nghị đầu tư', danh sách nguồn.\n"
            "Văn phong: câu dưới 25 từ, đoạn tối đa 3 câu, không tiếng lóng, không dùng 'nhất', 'số một', 'chắc chắn'; "
            "không so sánh với sản phẩm khác có tên.\n" + QUY_TAC)


# ---------------------------------------------------------------- chạy

def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Wealbee MCP server")
    ap.add_argument("--http", action="store_true", help="chạy Streamable HTTP thay cho stdio")
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument("--path", default="/mcp")
    a = ap.parse_args(argv)
    if not a.http:
        _nap_env()
        mcp.run("stdio")
        return
    CHE_DO["http"] = True
    an_toan = None
    if os.environ.get("WEALBEE_MCP_ALLOWED_HOSTS", "").strip():
        hosts = [h.strip() for h in os.environ["WEALBEE_MCP_ALLOWED_HOSTS"].split(",") if h.strip()]
        an_toan = TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hosts,
                                            allowed_origins=[f"https://{h}" for h in hosts])
    print(f"Wealbee MCP (HTTP) tại http://{a.host}:{a.port}{a.path}", file=sys.stderr)
    mcp.run("streamable-http", host=a.host, port=a.port, streamable_http_path=a.path, stateless_http=True,
            transport_security=an_toan)


if __name__ == "__main__":
    main()
