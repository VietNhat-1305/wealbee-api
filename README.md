# Wealbee Data API: 2 web tra cứu (Free / Doanh nghiệp) + quét hiệu suất mỗi giờ

- **docs/free/**: web tra cứu BCTC dùng khoá **gói Free**. Điều khoản gói Free chỉ cho dùng nội bộ, nên dữ liệu được mã hoá (AES-GCM) và người xem phải nhập mật khẩu nhóm.
- **docs/doanh-nghiep/**: web tra cứu y hệt nhưng dùng khoá **gói Doanh nghiệp**. Gói này được phép hiển thị cho khách hàng, nên web công khai.
- **docs/bao-cao/**: báo cáo đánh giá Wealbee Data API theo 11 tiêu chí của một API doanh nghiệp, gồm kết luận, vấn đề cần trao đổi với Wealbee, điểm mạnh, bảng chấm và phương pháp. Có mật khẩu. Từ 12/11/2026, lỗi mạng phía máy đo không còn bị tính thành lỗi API; độ tươi và chất lượng tính trên toàn bộ BCTC đã đồng bộ.
- Web bản Free dùng thêm **API miễn phí của Vietstock**: giá theo ngày từ API biểu đồ `api.vietstock.vn/tvnew` và tin từ RSS. API dữ liệu chính thức của Vietstock là DataFeed, phải mua. Web Doanh nghiệp lấy giá từ VNDirect, trình duyệt gọi thẳng.
- **Tin tức:** từ 11/2026 Data API đã có `/news` (gói Doanh nghiệp, bộ đo có đo). Trước đó Data API **không có endpoint tin tức**: thử `/news`, `/articles`, `/feed`… đều 404, còn `/events` chỉ có `filing.detected` và `statement.published`. Vì vậy tin lấy từ API tin của app Wealbee (`wealbee.com/api/insights/for-you`, `/api/symbols/{mã}/insights`), công khai, không cần khoá. API này không cho trình duyệt gọi thẳng (không CORS), nên mỗi giờ được lấy về và xuất thành endpoint tĩnh:
  - `docs/tin/moi.json`: 60 tin mới nhất; `docs/tin/ma/<MÃ>.json`: tin theo mã; `docs/tin/chi_muc.json`: số tin theo mã
  - `docs/vietstock/tin_moi.json`, `docs/vietstock/tin_ma/<MÃ>.json`, `docs/vietstock/gia/<MÃ>.json`
- Báo cáo so sánh thêm hiệu suất API Wealbee với API miễn phí của Vietstock và API tin của app Wealbee.
- Quyền gói **tính theo tài khoản**: nâng tài khoản lên hợp đồng thì mọi khoá cũ của tài khoản đó cũng thành gói Doanh nghiệp. Bộ quét tự kiểm gói của từng khoá qua `/v1/me` và bỏ qua khoá sai gói để số liệu 2 gói không lẫn.

## Trợ lý AI phân tích đầu tư (Gemini, miễn phí)
Nút **✦ Hỏi AI** trên 2 web tra cứu, và nút **✦ AI phân tích <MÃ>** ở trang từng mã. Trợ lý dùng Gemini API (gói miễn phí của Google) và chạy hẳn trên trình duyệt (`docs/assets/ai.js`), không cần máy chủ. Gemini tự gọi các công cụ sau để lấy dữ liệu:
- `bao_cao_tai_chinh`: BCTC Wealbee của web đang xem, gồm các quý gần nhất và tỷ lệ tính sẵn (biên lợi nhuận, tăng trưởng, ROE/ROA năm hoá, nợ/VCSH, LCTT/LNST)
- `tin_tuc`: tin Wealbee theo mã hoặc toàn thị trường (web Free có thêm Vietstock)
- `gia_co_phieu`: giá, biến động 1 tuần đến 12 tháng, đỉnh/đáy 52 tuần (Vietstock hoặc VNDirect)
- `loc_co_phieu`: lọc và xếp hạng theo điểm sức khoẻ, doanh thu, LNST, biên LNST
- `tim_cong_ty`: tìm mã theo tên

Khoá Gemini lấy ở https://aistudio.google.com/apikey, ghi vào `.env` (`GEMINI_API_KEY`), rồi chạy `python -m wb_api.khoa_ai`. Script kiểm khoá, thử model và ghi `docs/ai/khoa.json` đã mã hoá bằng `MAT_KHAU_NOI_BO`. Sau đó commit và push.
- Trên web Free: sau khi nhập mật khẩu nhóm, AI tự dùng khoá nhóm.
- Trên web Doanh nghiệp: nhập mật khẩu nhóm trong khung AI. Người ngoài nhóm có thể dán khoá Gemini riêng; khoá này chỉ lưu trong trình duyệt của họ.
- Model được chọn tự động: Flash mới nhất, hết lượt miễn phí thì chuyển sang Flash-Lite. Có thể chọn tay ở nút ⚙.
- Nên giới hạn khoá theo website (Google Cloud Console → Credentials → Website restrictions: `https://vietnhat-1305.github.io/*`).

## Theo dõi sức khoẻ SEO wealbee.com (`wb_seo/`, `docs/seo/`)
GitHub Actions `seo.yml` chạy mỗi ngày lúc 08:15 giờ Việt Nam. Mỗi lần chạy gồm:
- 19 phép kiểm trong 5 nhóm: khả năng được tìm thấy, thẻ trên trang, tốc độ di động (Chrome giả lập điện thoại), link nguồn trích dẫn, bảo mật.
- Chấm điểm 0–100, lưu lịch sử mã hoá vào `data/seo/`, dựng trang `docs/seo/` (cần mật khẩu nội bộ).
- Khi có chỉ số chuyển sang Lỗi hoặc điểm tụt từ 5 trở lên, mở hoặc bình luận issue "Cảnh báo sức khoẻ SEO" (nhãn `seo-canh-bao`).

Chạy tay: `python -m wb_seo.chay` (thêm `--khong-toc-do` để chạy nhanh). Ngưỡng và căn cứ từng chỉ số: `wb_seo/chi_so.py`.

## Phân tích đầu tư chủ động (docs/dau-tu)
Trang [dau-tu/](https://vietnhat-1305.github.io/wealbee-api/dau-tu/) giúp ra quyết định đầu tư thay vì chỉ tra cứu. `wb_api/dau_tu.py` chạy mỗi giờ sau bước đồng bộ trên GitHub Actions và dựng `docs/dau-tu/data/` từ ba nguồn: BCTC đã đồng bộ, `/statements?updated_since=` và `/news` của Data API (gói Doanh nghiệp). Tin được giữ tăng dần 30 ngày trong `data/dau_tu_tin.json`.
- **Điểm 5 yếu tố (0-100):** mỗi chỉ số được xếp phân vị trong cùng nhóm ngành (doanh nghiệp, ngân hàng, chứng khoán, bảo hiểm). Điểm yếu tố là trung bình phân vị các chỉ số có số liệu.
  - Tăng trưởng: DT/LNST quý và luỹ kế so với cùng kỳ. Ngân hàng không có doanh thu nên dùng thu nhập hoạt động.
  - Hiệu quả: ROE, ROA năm hoá, biên gộp, biên ròng (biên chỉ tính cho doanh nghiệp thường).
  - An toàn tài chính: nợ phải trả/VCSH, vay/VCSH, điểm sức khoẻ Wealbee.
  - Chất lượng lợi nhuận: LCTT kinh doanh / LNST luỹ kế (chỉ doanh nghiệp thường).
  - Tin tức: sắc thái tin 30 ngày, xếp trên toàn thị trường.
  - Điểm tổng có trọng số 25 / 25 / 20 / 15 / 15, chuẩn hoá lại khi thiếu yếu tố.
- **Tín hiệu (30 ngày, mới nhất trước):**
  - LNST quý ±30% so với cùng kỳ (nền ≥ 5 tỷ); chuyển lãi/lỗ;
  - điểm sức khoẻ đổi ≥ 2;
  - có lãi nhưng LCTT kinh doanh âm hơn 50% LNST;
  - vay nợ tăng ≥ 50% và ≥ 200 tỷ từ đầu năm;
  - tin tích cực hoặc tiêu cực gắn mã trong 3 ngày.
  - Mỗi tín hiệu có một câu giải thích kèm số và link nguồn.
- **Trang có ba tab:**
  - Tín hiệu (lọc theo mức độ, loại, nguồn, mã đang theo dõi).
  - Bộ lọc: các preset Tăng trưởng mạnh, Chất lượng cao, An toàn tài chính, Tin tức tích cực, hoặc tuỳ chỉnh từng yếu tố. Có thêm giá 3 tháng từ VNDirect.
  - Danh mục theo dõi, lưu trên trình duyệt.
  - Bấm vào một mã sẽ mở thẻ quyết định: 5 yếu tố so với trung vị ngành, điểm mạnh và rủi ro kèm số, giá 12 tháng, tín hiệu, tin, và nút trợ lý AI. Trợ lý AI có thêm công cụ `diem_dau_tu`.
- Chạy tay: `python -m wb_api.dau_tu` (thêm `--khong-api` để chỉ dựng lại từ dữ liệu sẵn có).

## Chạy tự động
| Ở đâu | Khi nào | Việc |
|---|---|---|
| GitHub Actions (`.github/workflows/quet.yml`) | mỗi giờ, kể cả khi tắt máy | quét hiệu suất (đo từ Mỹ), đồng bộ dữ liệu 2 web, dựng báo cáo |
| Máy ở Việt Nam (`dat_lich_may.cmd`, chạy 1 lần để tạo lịch) | mỗi giờ khi máy bật | quét hiệu suất (đo từ Việt Nam), đẩy dữ liệu đo lên GitHub |

## Cấu hình
`.env` (máy) và GitHub Secrets (Actions) gồm 3 biến:
- `WEALBEE_KEY_FREE`: khoá gói Free
- `WEALBEE_KEY_DN`: khoá gói Doanh nghiệp
- `MAT_KHAU_NOI_BO`: mật khẩu xem web Free và báo cáo

Không đưa `.env` lên GitHub.

```
python -m wb_api.chay --nguon may-vn                # 1 lượt quét từ máy
python -m wb_api.chay --nguon may-vn --dong-bo      # quét + đồng bộ dữ liệu 2 web
```

## Mã nguồn
`wb_api/client.py` gọi API và đo thời gian. `quet.py` là bộ đo. `dong_bo.py` lấy dữ liệu tăng dần cho 2 web. `tin_tuc.py` lấy tin Wealbee. `vietstock.py` lấy giá và tin Vietstock. `bao_cao.py` tổng hợp và chấm điểm. `ma_hoa.py` lo phần mã hoá.
