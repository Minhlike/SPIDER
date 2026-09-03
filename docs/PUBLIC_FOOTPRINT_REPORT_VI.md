# SPIDER — kết quả phát triển dấu vết công khai

Cập nhật ngày 03/09/2026. Đã triển khai và kiểm thử tại máy; chưa commit/push các
thay đổi mới. Bản phát hành `v2.0.0` và HEAD/remote `a3c2a5e` được giữ nguyên.

## Chạy thử

Mở **http://127.0.0.1:8765**, hoặc nhấp đúp `run_spider.bat` trong thư mục
`D:\PhanMem_Tools\SPIDER`. Dừng bằng `stop_spider.bat`.

Chọn **Cuộc điều tra mới**, nhập email hoặc username. Phạm vi username có ba mức:
50, 500 hoặc tất cả website phù hợp trong danh mục. Bản danh mục đã kiểm tra có
2.557 mục phù hợp; số này không đồng nghĩa tất cả đều truy cập được hoặc có tài
khoản. Khi hết thời gian, kết quả đã thu được được giữ lại và đánh dấu một phần.

## Những gì đã sửa và bổ sung

| Vấn đề cũ | Hành vi hiện tại |
|---|---|
| Chỉ gọi 15 website, đọc nhầm stdout của Maigret | Worker riêng đọc kết quả có cấu trúc của Maigret; mức 50/500/toàn danh mục |
| Chỉ có URL cũng bị coi là tìm thấy | Phải có trạng thái phát hiện hợp lệ; URL của kết quả âm/lỗi không tạo tài khoản |
| Trang trả 200 cho mọi username có thể gây báo sai | Dùng username đối chứng ngẫu nhiên cho kết quả dựa vào mã HTTP/không có dấu hiệu hiện diện; nếu cả hai đều dương tính thì chưa kết luận |
| Kết quả username thiếu nội dung | Đọc tên/tiêu đề và mô tả công khai từ HTML đã tải; không thêm lượt tải để lấy các trường này |
| Email chỉ hiện hạ tầng Gmail/tên miền | Đối chiếu email được đăng công khai trong hồ sơ GitHub; hồ sơ và hạ tầng thư có khu vực riêng |
| Trùng username dễ bị hiểu là cùng người | Ghi rõ ứng viên chưa xác minh; không tạo kết luận cùng một người |
| Giới hạn thời gian trên giao diện bị bỏ qua | Ngân sách giao diện truyền tới engine và worker; loại bỏ giới hạn cứng 20/30 giây của luồng Maigret |
| Nguồn lỗi vẫn có thể kết thúc COMPLETED | Lưu RUNNING, PARTIAL, FAILED, thời gian, lỗi và số website đã xử lý |

Tên/tiêu đề trang, mô tả và email công khai là thông tin do nguồn đăng tải. Chúng
không tự chứng minh tên pháp lý hay danh tính của người sở hữu. Khi hồ sơ GitHub
đăng email trùng khớp, username công khai của hồ sơ có thể được mở rộng ở độ sâu
tiếp theo; không suy đoán username từ phần đứng trước dấu `@`.

## Kiểm thử bằng email đã được chủ sở hữu cho phép

Đã chạy tra cứu trực tiếp và lưu một vụ án cục bộ tên
**Kiem thu dau vet cong khai cua toi**. Nguồn GitHub trả về **0 hồ sơ công khai**;
các nguồn hạ tầng vẫn có kết quả riêng. Đây không phải kết luận rằng email không
có tài khoản trên các nền tảng khác. Email thật, vụ án và kết quả thô được giữ
ngoài Git, tài liệu benchmark và bộ dữ liệu kiểm thử.

## Benchmark có thể chạy lại

So sánh SPIDER với Maigret **0.6.5** và Sherlock **0.16.0** trên cùng bảy website
giả lập cục bộ; ba lần lặp, đổi thứ tự chạy. Đo cuối lúc 08:01 UTC ngày 03/09/2026,
không chạy đồng thời bộ pytest hoặc điều tra trực tiếp.

| Chỉ tiêu | SPIDER | Maigret | Sherlock |
|---|---:|---:|---:|
| Dương tính đúng | 1 | 1 | 1 |
| Dương tính giả | 0 | 1 | 1 |
| Bỏ sót hồ sơ dương tính đã biết | 0 | 0 | 0 |
| Precision trên các ca đã biết | 100% | 50% | 50% |
| Recall trên các ca đã biết | 100% | 100% | 100% |
| F1 trên các ca đã biết | 1,00 | 0,67 | 0,67 |
| Có kết luận trên bốn ca đã biết | 3/4 | 4/4 | 4/4 |
| Ghi đúng chưa xác định trên ba ca bị chặn/giới hạn/chậm | 3/3 | 3/3 | 1/3 |
| Lượt HTTP mỗi lần đo | 9 | 7 | 7 |
| Thời gian trung vị, gồm khởi động tiến trình | 5,979 giây | 5,306 giây | 4,754 giây |

**Cách đọc:** SPIDER tránh được ca báo sai trên trang trả 200 cho mọi username
bằng cách không kết luận. Nó không biến ca đó thành một kết quả âm đã xác minh.
Precision tăng đi kèm tỷ lệ có kết luận thấp hơn, thêm lượt truy cập và thời gian
chạy dài hơn. Hai công cụ đối chiếu dùng luồng search thông thường, không chạy
chế độ tự kiểm tra danh mục tùy chọn. Bộ sáu ca ban đầu chưa có trang wildcard
cho kết quả phát hiện ngang nhau; ca thứ bảy bổ sung kiểm tra điểm yếu HTTP 200.

**Chưa có bằng chứng vượt toàn diện** về độ phủ hoặc độ chính xác trên Internet.
Đây là cải thiện có kiểm chứng ở một tình huống báo sai cụ thể, trên bộ ca nhỏ.

Phiên bản và dấu vết tái lập:

- Fixture SHA-256: `ec29d7fc6674e4f54362e30e99e0bffacbfdf73fc9042866227a8fdc8e9f72f8`.
- Maigret engine SHA-256: `638a645d8320f8a0324f90439feba1e24abef51e5c1c5556cf8543848dcfd789`.
- Sherlock engine SHA-256: `18d34ea6fb5d7f6adb182584a438e6bd2f061442adb58f302532d7243feb8c49`.
- Quy trình, cấu hình và mã đo: thư mục `benchmarks/`.
- Số đo từng lần: `test-results/public-footprint-benchmark/results.json` (không đưa vào Git).
- Giấy phép đối chiếu: [Maigret MIT](https://github.com/soxoj/maigret/blob/main/LICENSE)
  và [Sherlock MIT](https://github.com/sherlock-project/sherlock/blob/master/LICENSE).

## Các cổng kiểm tra

- **Pytest:** 103 passed, 158,14 giây ở lần chạy toàn bộ cuối.
- **Browser:** 6 ca qua trong suite: luồng chính, kết quả rỗng, username, email
  trùng khớp, nguồn chỉ chạy được một phần, và email có hạ tầng nhưng thiếu hồ sơ.
- **Worker:** kiểm tra HTTP thật trên máy, đọc metadata, giữ kết quả khi hết giờ,
  đối chứng chống báo sai và thu hồi đúng tiến trình khi hủy.
- **Bảo mật:** kiểm thử DPAPI tiếp tục qua; không có giá trị khóa trong settings
  công khai; không có email kiểm thử thật trong các file có thể đưa vào Git.
- **Launcher:** dừng đúng PID 15756, khởi động bản mới PID 12056; gọi mở lại vẫn
  dùng PID 12056. Health xác nhận HEALTHY và PID trùng trạng thái launcher.
- **Git:** không có runtime, DB, kho DPAPI hoặc settings chứa khóa được theo dõi.

## Giới hạn và bước phát triển tiếp theo

1. Email hiện đối chiếu hồ sơ qua **GitHub công khai**. Muốn đánh giá độ phủ email
   rộng hơn cần các nguồn bổ sung có giao diện ổn định và dữ liệu đối chiếu được
   chủ sở hữu cho phép; không suy rộng từ kết quả GitHub sang mọi mạng xã hội.
2. Danh mục Maigret có thể thay đổi/hỏng; loại bỏ nguồn cần kích hoạt token,
   giao thức ngoài HTTP và tìm username gần giống. Không hứa tìm hết Internet.
3. Metadata trang chỉ có khi trang trả HTML phù hợp; không có nghĩa mọi hồ sơ đều
   cung cấp tên hoặc mô tả. Worker có cầu nối nội bộ cho Maigret 0.6.5 và kiểm thử
   hợp đồng HTTP; phải kiểm tra lại khi nâng phiên bản Maigret.
4. Kiểm tra đối chứng có thể chưa kết luận do giới hạn truy cập hoặc hết giờ.
   Kết quả một phần và các ứng viên chưa đối chứng được phải tiếp tục đối chiếu.
5. Muốn công bố thắng benchmark rộng hơn cần bộ dữ liệu đa nền tảng có nhãn,
   nhiều ca dương/âm thực sự, đo lặp và báo cáo cả kết quả không thể kiểm tra.
6. Không thay đổi release tag và chưa phát hành các thay đổi phát triển này.
