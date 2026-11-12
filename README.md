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
