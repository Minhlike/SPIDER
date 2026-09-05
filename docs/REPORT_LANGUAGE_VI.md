# Quy ước ngôn ngữ báo cáo SPIDER

Yêu cầu ad-hoc: mọi báo cáo hướng tới người dùng dùng một cách diễn đạt thống nhất,
giải thích dữ liệu, căn cứ, giới hạn và bước tiếp theo. Không dùng model AI trong core.
Nguồn câu chữ dùng chung: `src/spider/service/reporting.py` (VI/EN, phiên bản 1).

## Cấu trúc bắt buộc

1. Kết quả hiện có, theo đúng mục tiêu và lượt kiểm tra đang hiển thị.
2. Căn cứ: bản ghi và liên kết nào đã có; có bao nhiêu bước còn chưa rõ.
3. Cách xử lý: chuẩn hóa đầu vào, theo đường liên hệ về mục tiêu, đối chiếu nguồn/lịch sử.
4. Điều chưa biết, bằng chứng không thống nhất và phạm vi chưa kiểm tra được.
5. Bước tiếp theo phù hợp với trạng thái: chọn mục tiêu, chờ tiến trình hoặc đối chiếu nguồn.

Mỗi phát hiện trong bản tải có mã bằng chứng để truy lại. Bản đọc ngắn giới hạn
50 phát hiện; thông báo khi rút gọn. JSON/gói bằng chứng giữ trường máy đọc và
thêm cùng phần diễn giải; không đổi nghĩa trạng thái để làm báo cáo có vẻ tốt hơn.

## Từ ngữ và giới hạn kết luận

| Mã kỹ thuật | Cách hiểu cho người dùng |
| --- | --- |
| FACT | Dữ liệu đã ghi nhận |
| HYPOTHESIS | Nhận định cần kiểm chứng |
| EXPERIMENT RESULT | Kết quả thử nghiệm |
| NOT YET VERIFIED | Chưa được kiểm chứng |
| COMPLETED | Đã kết thúc lượt kiểm tra; không phải xác minh danh tính |
| CONFIRMED | Đã ghi nhận dữ liệu từ nguồn; không phải xác nhận cùng chủ sở hữu |
| NOT_FOUND | Không thấy trên nguồn đã kiểm tra; không đại diện toàn Internet |
| BLOCKED / RATE_LIMITED / TIMEOUT | Chưa đọc/kiểm tra đầy đủ; kết quả vẫn chưa biết |
| PARSER_DRIFT | Trang đã thay đổi, công cụ chưa đọc chính xác được |
| NO_ARCHIVED_OBSERVATION | Chưa có bản lưu; không suy rằng nội dung đã biến mất |

Không trình bày trọng số kỹ thuật như xác suất đúng. Tên giống nhau, trang dẫn
tới nhau và nhiều trang sao chép một nội dung không tự chứng minh danh tính.
DNS của dịch vụ email không xác định người dùng email. Vị trí IP không phải
địa chỉ nhà. Lỗi thô, thông tin đăng nhập và nội dung nguồn không được ghép vào
câu giải thích. HTML/Markdown từ nguồn phải được coi là văn bản.

## Các đường xuất hiện tại

- UI: khối “Kết quả và cách hiểu”, trạng thái nguồn/bằng chứng được diễn đạt lại.
- “Tải báo cáo dễ đọc”: Markdown qua `GET /api/cases/{case_id}/report`;
  `language=vi|en`, `target_id`, `question`. Không tự bật server hoặc chạy nguồn.
- JSON và evidence bundle: `reader_report` dùng cùng dữ liệu/câu chữ với UI.
- CLI investigate: báo cáo dễ đọc; `--json` giữ dữ liệu có cấu trúc kèm diễn giải.
- CLI/MCP explain, evidence và hypothesis: giải thích giới hạn kết luận đi kèm.
- Cấu trúc kỹ thuật phục vụ Agent, ID, hash và chẩn đoán vận hành vẫn được giữ.

## Gate 2026-09-05

388 passed, 1 deselected trong 69.43s (bộ ngoại tuyến; bao gồm UI Chromium).
Đã kiểm tra báo cáo UI/JSON/bundle nhất quán, Markdown tải được, VI/EN,
không diễn giải blocked thành absent, không gán identity, chống chèn HTML/link,
và không lấy trạng thái lần chạy của mục tiêu khác. Listener E2E và các bài
live-provider không chạy. Đây là nâng cấp cách báo cáo, không phải bằng chứng
rằng năng lực tìm danh tính hoặc tốc độ thu thập đã tăng.
