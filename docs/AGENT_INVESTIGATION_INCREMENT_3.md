# Investigation increment 3 — 2026-09-06

Baseline của increment: `7e92711`; baseline kế hoạch vẫn là `069fa49a`.
A–E được giữ nguyên. Increment này hoàn thành phần thực thi M3 trên fixture;
không phải tuyên bố hoàn tất M1–M6 hoặc xác minh độ chính xác ngoài Internet.

## FACT — thay đổi có thể sử dụng

- Mặc định chạy tối đa **2 provider độc lập** cho cùng observable; cho phép 1–4.
  Giới hạn trong một service: 4 provider đang chạy, 1 lượt/provider,
  8 yêu cầu đang xử lý và 2 yêu cầu/hostname. Quá 128 hostname dùng chung
  một nhóm dự phòng. Nhiều seed/frontier vẫn được xử lý theo thứ tự.
- Worker Maigret và private Uncover cần parent cấp phép trước mỗi lần gửi.
  Redirect, retry và negative control đều phải xin phép; DNS tính cả TCP fallback.
  Ledger dùng chung trong run, attribution theo task. Một permit đã cấp là một
  **lần thử gửi**, không chứng minh máy chủ đã nhận hoặc trả lời. Crash sau ACK
  được giữ ở trạng thái chưa rõ, không hoàn ngân sách để rồi gửi quá giới hạn.
- Network có thể hoàn tất khác thứ tự; admission entity, observation và graph
  commit theo thứ tự scheduler. Hủy dừng đúng process/task, giải phóng lượt chờ,
  giữ dữ liệu đã commit, ghi CANCELLED và drain writer SQLite có queue tối đa 128.
- HTTP tái sử dụng kết nối theo provider và credential scope, tối đa 16 pool.
  GET ẩn danh cùng run/version có thể dùng lại kết quả tối đa 30 giây, tôn trọng
  TTL ngắn hơn, no-store/no-cache/private, Set-Cookie và Vary:*. Không cache request
  có credential ở header hoặc tham số key/token; không dùng lại giữa các run.
  Cache tối đa 128 response, mỗi body không quá 64 KiB; đây không phải giới hạn
  tổng RAM tiến trình hoặc kích thước mọi response tải về.
- Request trùng đang chạy được ghép; consumer vẫn tạo observation/lineage riêng,
  cache hit không tính thêm network request hoặc giả tạo lần egress mới.
  Metadata phân biệt thời gian chờ provider, thực thi, chờ commit và cache hit.
- HTTP 429 tạo thời gian chờ theo hostname, Retry-After tối đa 30 giây;
  worker/browser chưa có header thì chờ mặc định 1 giây, không tự retry vô hạn.
  Hết ngân sách SPIDER báo SKIPPED_BUDGET/REQUEST_LIMIT, không báo nhầm quota API.
- Shutdown đóng pool thuộc service; chạy lại tạo các giới hạn mới.
  Không thay credential schema, không thêm provider hoặc AI runtime.

## EXPERIMENT RESULT — so sánh có kiểm soát

`python -m benchmarks.provider_concurrency`: Python 3.12.8, Windows AMD64,
4 provider giả lập, mỗi nguồn chờ 80 ms, DB mới mỗi lượt, 20 lượt/cấu hình.
So sánh cùng pipeline ở chế độ tuần tự và song song, không phải checkout
baseline cũ so với Internet. Bật tracemalloc trong tất cả lượt đo.

| Số nguồn đồng thời | Wall p50/p95 (ms) | Graph read p50/p95 (ms) | Tổng chờ DB p50 (ms) | Queue cao nhất |
| --- | --- | --- | --- | --- |
| 1 | 685.521 / 767.178 | 8.310 / 10.131 | 3.647 | 1 |
| 2 | 505.342 / 547.046 | 8.432 / 10.237 | 67.406 | 2 |
| 4 | 403.211 / 466.998 | 8.840 / 10.511 | 198.128 | 4 |

Mọi lượt: 4 lần thử request mô phỏng, 4 observation hữu ích theo truth fixture,
decision coverage 4/4; cùng entity và graph semantic. Peak Python allocation
delta lớn nhất lần lượt 2,954,008 / 737,328 / 767,989 byte. Cấu hình 1 chạy trước
và chịu chi phí khởi tạo thư viện; không dùng số này để kết luận giảm RAM.
Tổng thời gian transaction DB p50: 308.581 / 348.010 / 352.051 ms.
Graph read là truy vấn service, **không phải độ trễ render UI**.

Kiểm thử riêng xác nhận: reverse completion không đổi graph; entity cap nhận
theo schedule; request cap không bị vượt; giới hạn provider dùng chung qua hai
run; hủy khi đang chạy và khi worker đang chờ origin không treo. Hai Maigret
process thật gọi server localhost chứng minh parent đã đếm trước khi server nhận.
Private Go runner với key giả bị từ chối trước transport, không gọi Internet.

## NOT YET VERIFIED / giới hạn

- Tốc độ/độ chính xác với website thật và UI latency chưa được đo ở increment này.
  Request cap quá chặt có thể khiến race giữa các nguồn quyết định nguồn nào được
  cấp phép trước; kết quả phải PARTIAL, không hứa cùng graph cho mọi lần như vậy.
- Giới hạn dùng chung trong một service process, không phải điều phối nhiều backend.
  MCP action queue vẫn serial; browser session/tab/resume M4 chưa hoàn thành.
- Hủy giữ dữ liệu đã commit; không cam kết giữ response còn nằm trong worker.
- Scheduler telemetry mới là quan sát, chưa thay thứ tự bằng điểm chi phí/lợi ích.
- M1 snapshot/delta, M4 browser workflow, M5 PHONE candidates và M6 reasoning/UX
  còn việc. Live PHONE accuracy cần tập kiểm soát/được phép có ground truth.

Gate tổng cuối cùng được ghi trong `memory/NEXT.md` và `memory/STATE.json`.
