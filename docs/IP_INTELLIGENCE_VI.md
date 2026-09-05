# Điều tra địa chỉ IP trong SPIDER

## Mục tiêu

SPIDER hợp nhất các nguồn theo vai trò thay vì sao chép giao diện của một website:

- WhatIsMyIP API: IP công khai hiện tại, vị trí gần đúng, ISP, ASN và dấu hiệu proxy/VPN/datacenter.
- RDAP toàn cầu: tổ chức đăng ký, RIR, dải địa chỉ, trạng thái, mốc thời gian và liên hệ vận hành công khai.
- BGPView: ASN và prefix đang được quảng bá trên Internet.
- Native DNS: reverse DNS và hostname liên quan khi có bằng chứng.

Mọi giá trị trong báo cáo giữ nguồn, thời điểm quan sát và độ tin cậy. Vị trí IP là ước lượng cấp mạng; không được trình bày như danh tính cá nhân hay địa chỉ nhà.

## Luồng người dùng

1. Vào **Cài đặt hệ thống → WhatIsMyIP**, dán API key, rồi chọn **Lưu và thử kết nối**.
2. Trạng thái `VALID` chỉ xuất hiện khi endpoint tài khoản trả một IP công khai hợp lệ.
3. Ở **Cuộc điều tra mới**, chọn `IPv4` hoặc `IPv6`. Khi ô mục tiêu còn trống, SPIDER tự điền IP công khai nhưng không tự chạy điều tra.
4. Người dùng kiểm tra IP rồi bấm bắt đầu. Báo cáo IP hiển thị dữ liệu hợp nhất và bảng nguồn.

## Bảo mật và quota

- Khóa chỉ nằm trong Windows DPAPI vault `data/api-keys.dpapi`; `data/settings.json` không chứa plaintext.
- Khóa chỉ được gửi trong header `X-API-KEY`, không nằm trong URL, log, HTTP response, exception hoặc artifact.
- Request có credential không được đưa vào replay cache.
- Private/reserved IP không được gửi ra nhà cung cấp.
- Tự điền IP dùng một request và cache trong 60 giây. Một lần enrich đầy đủ dùng tối đa hai request: lookup và proxy check. Nếu hết budget sau lookup, SPIDER giữ phần dữ liệu đã có và đánh dấu partial.

## Trạng thái và giới hạn

- `MISSING_CREDENTIAL`, `INVALID_KEY`, `DISABLED_KEY`, `QUOTA_LIMIT`, `NETWORK_ERROR` và `PARSER_DRIFT` được phân biệt mà không phản hồi lại nội dung khóa.
- Không tự động scrape website WhatIsMyIP; integration chỉ dùng API chính thức.
- Không suy ra người đứng sau IP. NAT, VPN, mobile carrier và cơ sở dữ liệu định vị có thể làm vị trí khác thực tế.
