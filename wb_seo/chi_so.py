"""Bộ chỉ số sức khoẻ SEO: mỗi chỉ số có ngưỡng, trọng số và căn cứ (vì sao nó ảnh hưởng tới thứ hạng / việc được trích dẫn).

Xếp hạng: dat (100%) · canh_bao (50%) · loi (0%) · chua_do (không tính). Điểm sức khoẻ = trung bình có trọng số, 0–100.
Ngưỡng tốc độ theo Core Web Vitals của Google (web.dev/articles/vitals): LCP ≤ 2,5 s tốt, > 4 s kém; CLS ≤ 0,1 tốt,
> 0,25 kém; INP ≤ 200 ms tốt, > 500 ms kém (đo phòng thí nghiệm bằng TBT: ≤ 200 ms tốt, > 600 ms kém như Lighthouse).
"""
from __future__ import annotations

from urllib.parse import urlparse

NHOM = {"index": "Khả năng được tìm thấy", "onpage": "Thẻ trên trang", "toc_do": "Tốc độ (di động)", "link": "Liên kết",
        "bao_mat": "Bảo mật"}

# id: (nhóm, tên, trọng số, ngưỡng hiển thị, căn cứ)
DINH_NGHIA = {
    "trang_200": ("index", "Trang chính trả 200", 6, "mọi trang = 200",
                  "Trang lỗi 4xx/5xx bị Google loại khỏi chỉ mục; trang chủ sập = mất toàn bộ lượt tìm kiếm."),
    "soft_404": ("index", "URL không tồn tại trả 404", 6, "404 hoặc 410",
                 "Google báo soft 404 trong Search Console và phí ngân sách thu thập vào trang rác trùng trang chủ."),
    "robots": ("index", "robots.txt không chặn bot tìm kiếm", 5, "không chặn Googlebot, Bingbot, bot tìm kiếm AI",
               "Một dòng Disallow sai có thể xoá cả site khỏi Google và khỏi ChatGPT / Perplexity."),
    "sitemap": ("index", "Sitemap có bài viết, URL đều sống", 7, "có URL bài viết, mẫu 40 URL trả 200",
                "Sitemap là cách chính để Google và Bing biết bài mới; site tin tức cần bài mới được biết trong vài phút."),
    "canonical_bai": ("index", "Canonical của bài trỏ về chính bài", 6, "không trỏ về trang chủ",
                      "Canonical trỏ về trang chủ khiến Google gộp mọi bài vào trang chủ, bài không bao giờ được index."),
    "noi_dung_html": ("index", "Nội dung bài có trong HTML gốc", 10, "≥ 1.500 ký tự (cảnh báo ≥ 500)",
                      "Bot tìm kiếm AI như OAI-SearchBot, PerplexityBot đọc HTML gốc, không chạy JavaScript; Google render JS chậm và có hạn mức."),
    "title_bai": ("onpage", "Tiêu đề riêng cho từng bài", 5, "khác trang chủ, 30–70 ký tự",
                  "Thẻ title là tín hiệu xếp hạng và là dòng hiển thị trên kết quả tìm kiếm; trùng title = trùng nội dung."),
    "description": ("onpage", "Meta description riêng từng trang", 4, "có, 70–170 ký tự, bài không dùng lại mô tả trang chủ",
                    "Không trực tiếp xếp hạng nhưng quyết định đoạn mô tả hiển thị, ảnh hưởng tỷ lệ bấm (CTR)."),
    "h1": ("onpage", "H1 trong HTML gốc của bài", 3, "đúng 1 thẻ H1",
           "H1 nói cho bot biết chủ đề chính của trang khi không chạy JavaScript."),
    "jsonld": ("onpage", "Dữ liệu cấu trúc NewsArticle", 4, "bài có NewsArticle / Article",
               "Điều kiện để vào Top stories, hiện ngày đăng, ảnh; giúp AI xác định tác giả, ngày và nguồn."),
    "llms_txt": ("onpage", "Có llms.txt", 2, "/llms.txt trả text/plain",
                 "Chuẩn đề xuất để chỉ cho AI các trang quan trọng; hiệu quả chưa chứng minh nên trọng số thấp."),
    "lcp": ("toc_do", "LCP: nội dung chính hiện ra", 8, "≤ 2,5 s (kém > 4 s)",
            "Core Web Vitals là tín hiệu xếp hạng của Google; LCP đo lúc người đọc thấy nội dung chính."),
    "cls": ("toc_do", "CLS: bố cục không xê dịch", 5, "≤ 0,1 (kém > 0,25)", "Core Web Vitals: đo độ nhảy bố cục khi tải."),
    "tbt": ("toc_do", "TBT: độ ì khi bấm (thay cho INP)", 7, "≤ 200 ms (kém > 600 ms)",
            "INP là Core Web Vitals về độ phản hồi khi tương tác; ngoài người dùng thật, TBT là chỉ số đại diện (Lighthouse)."),
    "link_nguon": ("link", "Link nguồn trích dẫn còn sống", 8, "hỏng ≤ 1% (cảnh báo ≤ 5%)",
                   "Link gãy làm giảm độ tin cậy với người đọc và với AI khi kiểm nguồn; tin tổng hợp sống nhờ trích dẫn đúng."),
    "https": ("bao_mat", "HTTPS + HSTS", 3, "TLS ≥ 1.2, http → https 301, có HSTS", "HTTPS là tín hiệu xếp hạng; HSTS chặn hạ cấp sang http."),
    "chung_chi": ("bao_mat", "Chứng chỉ TLS còn hạn", 4, "≥ 21 ngày (cảnh báo ≥ 7)", "Chứng chỉ hết hạn = trình duyệt chặn truy cập, bot ngừng thu thập."),
    "header": ("bao_mat", "Header bảo mật", 3, "CSP đầy đủ, chống nhúng, nosniff, Referrer-Policy",
               "Giảm rủi ro XSS và nhúng trái phép; trang bị chèn mã độc sẽ bị Google gắn cảnh báo."),
    "www": ("bao_mat", "www chuyển về tên miền chính qua Cloudflare", 4, "301 về wealbee.com, đi qua Cloudflare",
            "Hai tên miền cùng nội dung chia tín hiệu xếp hạng; host đi thẳng vào máy chủ gốc bỏ qua tường lửa và chống DDoS."),
}


def _x(dat: bool, canh_bao: bool = False) -> str:
    return "dat" if dat else "canh_bao" if canh_bao else "loi"


def _ms(x) -> str:
    return "—" if x is None else f"{x / 1000:.1f} s".replace(".", ",") if x >= 1000 else f"{round(x)} ms"


def cham(kq: dict) -> tuple[list[dict], float | None]:
    t = kq.get("trang") or {}
    chu, bai = t.get("trang_chu") or {}, t.get("bai_viet") or {}
    bm, rb, sm = kq.get("bao_mat") or {}, kq.get("robots") or {}, kq.get("sitemap") or {}
    td = kq.get("toc_do") or {}
    r = {}

    chinh = {k: v for k, v in t.items() if k != "bai_chia_se"}
    hong = [k for k, v in chinh.items() if v.get("status") != 200]
    r["trang_200"] = (_x(not hong), "đều 200" if not hong else "lỗi: " + ", ".join(f"{k} {chinh[k].get('status') or chinh[k].get('loi')}" for k in hong))
    s404 = (kq.get("soft_404") or {}).get("status")
    r["soft_404"] = (_x(s404 in (404, 410)), f"trả {s404}")
    if not rb.get("co"):
        r["robots"] = ("loi", "không đọc được robots.txt")
    else:
        chan = rb.get("chan_bot_tim_kiem") or []
        r["robots"] = (_x(not chan), "chặn " + ", ".join(chan) if chan else "không chặn bot tìm kiếm")
    if sm.get("so_url") is not None:
        ok = sm.get("co_bai_viet") and not sm.get("url_khong_200")
        r["sitemap"] = (_x(ok, sm.get("co_bai_viet")), f"{sm['so_url']} URL" + ("" if sm.get("co_bai_viet") else ", không có bài viết")
                        + (f", {len(sm['url_khong_200'])} URL lỗi" if sm.get("url_khong_200") else ""))
    if bai.get("status") == 200:
        can = (bai.get("canonical") or [""])[0]
        ve_chu = urlparse(can).path in ("", "/") and not urlparse(can).query
        r["canonical_bai"] = (_x(bool(can) and not ve_chu), f"canonical = {can or 'không có'}")
        n = bai.get("so_ky_tu") or 0
        r["noi_dung_html"] = (_x(n >= 1500, n >= 500), f"{n:,} ký tự".replace(",", "."))
        tt = bai.get("title") or ""
        r["title_bai"] = (_x(tt != chu.get("title") and 30 <= len(tt) <= 70, tt != chu.get("title")),
                          "trùng trang chủ" if tt == chu.get("title") else f"{len(tt)} ký tự")
        h1 = bai.get("h1") or []
        r["h1"] = (_x(len(h1) == 1, len(h1) > 1), f"{len(h1)} thẻ H1")
        ld = bai.get("jsonld") or []
        r["jsonld"] = (_x(any(x in ld for x in ("NewsArticle", "Article", "BlogPosting"))), ", ".join(ld) or "không có")
    mo_ta = [(k, len(v.get("description") or "")) for k, v in (("trang chủ", chu), ("bài", bai)) if v]
    thieu = [k for k, n in mo_ta if not n]
    trung = bool(bai.get("description")) and bai.get("description") == chu.get("description")      # bài dùng lại mô tả trang chủ
    r["description"] = (_x(not thieu and not trung and all(70 <= n <= 170 for _, n in mo_ta), not thieu),
                        "thiếu ở " + ", ".join(thieu) if thieu else "bài dùng lại mô tả của trang chủ" if trung
                        else ", ".join(f"{k} {n} ký tự" for k, n in mo_ta))
    r["llms_txt"] = (_x((kq.get("llms_txt") or {}).get("la_van_ban")), "có" if (kq.get("llms_txt") or {}).get("la_van_ban") else "chưa có")

    if td:
        trang_do = [v for k, v in td.items() if isinstance(v, dict)]
        if trang_do:
            lcp, cls, tbt = max(v["lcp"] for v in trang_do), max(v["cls"] for v in trang_do), max(v["tbt"] for v in trang_do)
            ten = lambda k: max((v for v in trang_do), key=lambda v: v[k]).get("url", "")  # noqa: E731
            r["lcp"] = (_x(lcp <= 2500, lcp <= 4000), f"{_ms(lcp)} ({'bài viết' if '?a=' in ten('lcp') else 'trang chủ'})")
            r["cls"] = (_x(cls <= 0.1, cls <= 0.25), f"{cls:.3f}".replace(".", ","))
            r["tbt"] = (_x(tbt <= 200, tbt <= 600), _ms(tbt))
    ln = kq.get("link_nguon") or {}
    if ln.get("tong"):
        r["link_nguon"] = (_x(ln["ty_le_hong"] <= 1, ln["ty_le_hong"] <= 5), f"{ln['hong']}/{ln['tong']} gãy (404/410)"
                           + (f", {ln['chua_kiem_duoc']} báo phản hồi chậm chưa kiểm được" if ln.get("chua_kiem_duoc") else ""))
    if bm.get("tls") or bm.get("tls_loi"):
        r["https"] = (_x(bm.get("tls") in ("TLSv1.2", "TLSv1.3") and bm.get("http_sang_https") and bm.get("hsts")),
                      f"{bm.get('tls') or bm.get('tls_loi')}, HSTS {'có' if bm.get('hsts') else 'không'}")
        d = bm.get("chung_chi_con_ngay")
        r["chung_chi"] = (_x(d is not None and d >= 21, d is not None and d >= 7), f"còn {d} ngày" if d is not None else "không đọc được")
        du = bm.get("csp_day_du") and bm.get("x_frame") and bm.get("nosniff") and bm.get("referrer_policy")
        r["header"] = (_x(du, bm.get("x_frame") and bm.get("nosniff")), "đủ" if du else "CSP chưa đầy đủ" if not bm.get("csp_day_du") else "thiếu header")
        r["www"] = (_x(bm.get("www_chuyen_ve_goc") and bm.get("www_qua_cloudflare"), bm.get("www_chuyen_ve_goc")),
                    ("chuyển về gốc" if bm.get("www_chuyen_ve_goc") else "không chuyển về gốc") + (", qua Cloudflare" if bm.get("www_qua_cloudflare") else ", không qua Cloudflare"))

    ds, tong, diem = [], 0, 0
    for k, (nhom, ten, ts, nguong, can_cu) in DINH_NGHIA.items():
        xep, gia_tri = r.get(k, ("chua_do", "chưa đo"))
        ds.append({"id": k, "nhom": nhom, "ten": ten, "xep": xep, "gia_tri": gia_tri, "trong_so": ts, "nguong": nguong, "can_cu": can_cu})
        if xep != "chua_do":
            tong += ts
            diem += ts * {"dat": 1, "canh_bao": 0.5, "loi": 0}[xep]
    return ds, (round(100 * diem / tong, 1) if tong else None)
