# Cách dùng dữ liệu Wealbee

Wealbee Data API cung cấp dữ liệu tài chính doanh nghiệp niêm yết Việt Nam (HOSE, HNX, UPCOM):
danh bạ công ty, báo cáo tài chính (BCTC) quý đã chuẩn hoá và kiểm chứng, file gốc BCTC,
tin tổng hợp từ nhiều báo kèm phân tích, và luồng sự kiện khi dữ liệu thay đổi.

## Kỳ và phạm vi dữ liệu

- Kỳ viết dạng `2026Q3`, nhãn hiển thị `Q3/2026`. Các tool cũng nhận `Q3/2026`, `quý 3/2026`, `9T/2026`. Hiện chỉ có kỳ quý, chưa có kỳ năm.
- Mỗi công ty có `coverage.first_period` và `coverage.latest_period`. Chỉ nói về các kỳ trong khoảng này;
  kỳ ngoài khoảng là chưa có dữ liệu, không phải bằng 0.
- Công ty có `coverage.latest_period = null` là có trong danh bạ nhưng chưa có BCTC.

## Đọc một BCTC

- Số tiền trong API tính bằng **đồng** (`currency: VND`, `original_unit`). Tool `wealbee_statement_summary`
  và `wealbee_compare_companies` đã đổi sang **tỷ đồng**.
- `income_statement`, `cash_flow`: `quarter` là riêng quý, `ytd` là luỹ kế từ đầu năm tài chính
  (`months_ytd` tháng), hậu tố `_prior_year` là cùng kỳ năm trước.
- `balance_sheet`: `end_of_period` là cuối kỳ, `start_of_year` là đầu năm tài chính.
- Tên trường: `revenue` doanh thu thuần, `cost_of_sales` giá vốn, `gross_profit` lợi nhuận gộp,
  `net_profit` lợi nhuận sau thuế, `net_profit_parent` lợi nhuận sau thuế của cổ đông công ty mẹ,
  `total_assets` tổng tài sản, `total_liabilities` nợ phải trả, `borrowings` vay, `equity` vốn chủ sở hữu (gồm cả lợi ích
  cổ đông không kiểm soát), `equity_parent` vốn chủ của cổ đông công ty mẹ, `non_controlling_interest` lợi ích cổ đông không kiểm soát,
  `operating` / `investing` / `financing` lưu chuyển tiền từ hoạt động kinh doanh / đầu tư / tài chính,
  `net_change` lưu chuyển tiền thuần trong kỳ.
- `industry_type`: `corporate` (doanh nghiệp thường), `bank`, `securities`, `insurance`. Ngân hàng, chứng khoán,
  bảo hiểm dùng cùng tên trường nhưng khoản mục gốc theo mẫu BCTC riêng của ngành; khi giải thích các ngành này,
  nói rõ điều đó và dẫn trang gốc.
- `scope`: `consolidated` là BCTC hợp nhất.
- `status`: `verified` là đã qua kiểm chứng; `needs_review` là đang chờ xem lại, lý do nằm ở `review_reasons`.
  Khi dùng số `needs_review` phải nói rõ với người đọc.
- `checks`: các phép kiểm tự động, ví dụ cân đối tài sản cuối kỳ và đầu năm, cộng lưu chuyển tiền,
  khớp số tháng luỹ kế, đối chiếu chéo, đọc độc lập lần hai.
- `derived`: các chỉ tiêu Wealbee tự tính vì BCTC gốc không trình bày sẵn (ví dụ lợi nhuận gộp của công ty chứng khoán).
- `health_score`: điểm sức khoẻ tài chính do Wealbee chấm (`value`/`max`); `missing_points` là phần điểm
  chưa chấm được do thiếu dữ liệu.
- `version`: số lần BCTC được cập nhật. Xem lịch sử bằng `wealbee_statement_versions`; xem số liệu tại một thời điểm
  trong quá khứ bằng tham số `as_of`.
- `provenance`: nguồn gốc số liệu. `document_url` là file PDF gốc, `file_sha256` là mã băm của file,
  `pages` là trang chứa từng bảng, `detected_at` là lúc Wealbee phát hiện file, `ir_url` là trang quan hệ cổ đông.

## Chỉ số do Wealbee MCP tính

- `roe_ytd_pct`, `roe_annualized_pct`: lợi nhuận sau thuế của cổ đông công ty mẹ luỹ kế chia bình quân vốn chủ của cổ đông công ty mẹ
  (đầu năm và cuối kỳ); bản quy năm nhân 12 / `months_ytd`. Khi BCTC chưa có `equity_parent` thì tính lợi nhuận sau thuế / tổng vốn chủ (`roe_basis` ghi rõ cách tính).
- `roa_ytd_pct`, `roa_annualized_pct`: lợi nhuận sau thuế luỹ kế chia bình quân tổng tài sản.
- Bình quân hai thời điểm chỉ xấp xỉ số dư bình quân trong kỳ; khi viết bài, ghi rõ cách tính.
- `missing_fields`: chỉ tiêu Data API chưa có cho BCTC đó (VD doanh thu của ngân hàng), không phải bằng 0.
- `wealbee_industry_benchmark`: trung vị và tứ phân vị theo loại hình (corporate, bank, securities, insurance) cùng kỳ.
  `corporate` gồm mọi ngành, nên đây là mốc chung, chưa phải trung vị từng ngành. Dùng để đặt số cạnh mốc, không để xếp hạng nên mua.
- `wealbee_quarterly_trend`: số riêng từng quý; các quý năm trước lấy từ cột cùng kỳ của BCTC năm sau, có thể đã điều chỉnh hồi tố.

## Tin và sự kiện

- Mỗi bản ghi `news` là một sự kiện gộp nhiều bài báo: `source_count` số bài, `official_source_count` số nguồn chính thức,
  `sources` danh sách bài gốc, `sentiment` sắc thái, `status` (ví dụ `developing` là đang diễn biến).
  Phân tích của Wealbee xem bằng `wealbee_get_news`.
- `events` ghi lại thay đổi: `statement.updated`, `statement.withdrawn`, `news.published`, `news.updated`.

## Quy tắc khi trả lời người dùng

1. Không khuyến nghị mua, bán, nắm giữ một mã; không đưa giá mục tiêu, không dự báo giá.
   Theo Luật Chứng khoán 2019 (Điều 4 khoản 32), khuyến nghị như vậy là tư vấn đầu tư chứng khoán, cần giấy phép.
   Được phép: giải thích chỉ số, mô tả số liệu đã công bố, so sánh với doanh nghiệp cùng ngành.
2. Dẫn nguồn mỗi khi dùng số: tên công ty, kỳ, hợp nhất hay riêng, link `document_url`.
3. Nói rõ khi số liệu đang `needs_review` hoặc là chỉ tiêu `derived`.
4. Không bịa số, không suy ra kỳ ngoài `coverage`. Thiếu dữ liệu thì nói là thiếu.
5. Tin tức: phân biệt điều các báo đã đưa với nhận định; ghi số nguồn và nguồn chính thức.
