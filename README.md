# Wealbee Data API: 2 web tra cứu (Free / Doanh nghiệp) + quét hiệu suất mỗi giờ

- **docs/free/**: web tra cứu BCTC dùng khoá **gói Free**. Điều khoản gói Free chỉ cho dùng nội bộ, nên dữ liệu được mã hoá (AES-GCM) và người xem phải nhập mật khẩu nhóm.
- **docs/doanh-nghiep/**: web tra cứu y hệt nhưng dùng khoá **gói Doanh nghiệp**. Gói này được phép hiển thị cho khách hàng, nên web công khai.
- **docs/bao-cao/**: báo cáo đánh giá hiệu suất Wealbee API theo các tiêu chí của một API doanh nghiệp, so sánh 2 gói. Có mật khẩu.
- Web bản Free dùng thêm **API miễn phí của Vietstock**: giá theo ngày từ API biểu đồ `api.vietstock.vn/tvnew` và tin từ RSS. API dữ liệu chính thức của Vietstock là DataFeed, phải mua. Web Doanh nghiệp lấy giá từ VNDirect, trình duyệt gọi thẳng.
- **Tin tức:** Wealbee Data API **không có endpoint tin tức**: thử `/news`, `/articles`, `/feed`… đều 404, còn `/events` chỉ có `filing.detected` và `statement.published`. Vì vậy tin lấy từ API tin của app Wealbee (`wealbee.com/api/insights/for-you`, `/api/symbols/{mã}/insights`), công khai, không cần khoá. API này không cho trình duyệt gọi thẳng (không CORS), nên mỗi giờ được lấy về và xuất thành endpoint tĩnh:
  - `docs/tin/moi.json`: 60 tin mới nhất; `docs/tin/ma/<MÃ>.json`: tin theo mã; `docs/tin/chi_muc.json`: số tin theo mã
  - `docs/vietstock/tin_moi.json`, `docs/vietstock/tin_ma/<MÃ>.json`, `docs/vietstock/gia/<MÃ>.json`
- Báo cáo so sánh thêm hiệu suất API Wealbee với API miễn phí của Vietstock và API tin của app Wealbee.
- Quyền gói **tính theo tài khoản**: nâng tài khoản lên hợp đồng thì mọi khoá cũ của tài khoản đó cũng thành gói Doanh nghiệp. Bộ quét tự kiểm gói của từng khoá qua `/v1/me` và bỏ qua khoá sai gói để số liệu 2 gói không lẫn.

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
