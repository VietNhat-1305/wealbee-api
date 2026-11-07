# Wealbee Data API: 2 web tra cứu (Free / Doanh nghiệp) + quét hiệu suất mỗi giờ

- **docs/free/**: web tra cứu BCTC dùng khoá **gói Free**. Điều khoản gói Free chỉ cho dùng nội bộ, nên dữ liệu được mã hoá (AES-GCM) và người xem phải nhập mật khẩu nhóm.
- **docs/doanh-nghiep/**: web tra cứu y hệt nhưng dùng khoá **gói Doanh nghiệp**. Gói này được phép hiển thị cho khách hàng, nên web công khai.
- **docs/bao-cao/**: báo cáo đánh giá hiệu suất Wealbee API theo các tiêu chí của một API doanh nghiệp, so sánh 2 gói. Có mật khẩu.
- Giá cổ phiếu lấy từ API công khai miễn phí của VNDirect, trình duyệt gọi thẳng.

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
`wb_api/client.py` gọi API và đo thời gian. `quet.py` là bộ đo. `dong_bo.py` lấy dữ liệu tăng dần cho 2 web. `bao_cao.py` tổng hợp và chấm điểm. `ma_hoa.py` lo phần mã hoá.
