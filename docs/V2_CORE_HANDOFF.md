# SPIDER V2 CORE HANDOFF & CONTINUATION REPORT (GIAI ĐOẠN 1)

## 1. Tóm tắt tiến độ đã hoàn thành (Progress Overview)

### A. Hạ tầng & Môi trường thực tế (Real Runtime Runtimes)
- **SpiderFoot v4.0.0**: 
  - Toàn bộ source code SpiderFoot v4.0.0 đã được cài đặt và thiết lập tại `tools/spiderfoot/`.
  - Cài đặt đầy đủ các package phụ thuộc (`dnspython`, `pyOpenSSL`, `python-docx`, `python-pptx`, `netaddr==0.10.1`, `cryptography`, `cherrypy`).
  - Kiểm tra thực chiến `sf.py -V` và chạy scan thực tế trên Windows qua subprocess, output JSON stream hoạt động 100%.
  - Giữ vững ranh giới giấy phép **GPL-2.0** cô lập qua subprocess STDIO. Không import module SpiderFoot vào core SPIDER.
- **Maigret v0.6.5**:
  - Cài đặt `maigret==0.6.5` vào Python venv.
  - Sửa lỗi crash UTF-8 trên Windows console (ký tự Unicode `\u2665` / `cp1252`) bằng biến môi trường `PYTHONIOENCODING=utf-8` và cờ `--no-color`, `--dns-resolver threaded`.
  - Hỗ trợ format ndjson và simple json.
- **Native Zero-Key OSINT Baseline**:
  - `NativeDnsAdapter` (`src/spider/providers/native/dns.py`): Phân giải A, AAAA, MX, NS, TXT, SOA, PTR và phân tách Email -> Domain -> Mail servers -> IPs.
  - `NativeRdapAdapter` (`src/spider/providers/native/rdap.py`): Tra cứu ASN, CIDR, Organization qua RDAP công khai & BGPView fallback.
  - `NativeCtAdapter` (`src/spider/providers/native/ct.py`): Tra cứu subdomain qua crt.sh Certificate Transparency JSON.

### B. Core Architecture & Composition Root
- **Centralized Classifier** (`src/spider/models/classifier.py`): Single source of truth cho `EMAIL`, `DOMAIN`, `HOSTNAME`, `IP_ADDRESS`, `IPV6_ADDRESS`, `CIDR`, `ASN`, `PHONE`, `ACCOUNT`, `URL`, `USERNAME`. Sửa triệt để bug email `.vn`, `.io`, `.net`.
- **Production Composition Root** (`src/spider/core/factory.py`): `create_spider_service(mode="production"|"test")`. Trong production mode: 0 fake provider, nạp đủ 8 adapter thực chiến (`native_dns`, `native_rdap`, `native_ct`, `subfinder`, `metabigor`, `spiderfoot`, `maigret`, `uncover`).
- **FastAPI Lifespan & Non-Blocking Async Runner** (`src/spider/web/app.py`, `src/spider/web/api/investigate.py`): Single long-lived `SpiderService` instance cho web app, investigation chạy background non-blocking và stream event qua WebSocket `/ws`.
- **Safety Timeouts**: Giới hạn thời gian tối đa 25s - 30s cho từng task provider trong Engine để đảm bảo hệ thống không bao giờ bị treo bởi request mạng bên ngoài.

---

## 2. Trạng thái các file và cấu trúc dự án (Artifact Map)
- `src/spider/core/factory.py` (Mới: Production Composition Root)
- `src/spider/models/classifier.py` (Mới: Centralized Target Classifier)
- `src/spider/providers/native/` (Mới: DNS, RDAP, CT Adapters)
- `src/spider/providers/spiderfoot/adapter.py` (Cập nhật: Upstream JSON parser, GPL isolation, safety timeout)
- `src/spider/providers/maigret/adapter.py` (Cập nhật: UTF-8 Windows fix, NDJSON parser, safety timeout)
- `src/spider/web/app.py` & `src/spider/web/api/` (Cập nhật: FastAPI Lifespan, background runner, classifier endpoint)
- `docs/THIRD_PARTY_LICENSES.md` (Mới: Báo cáo kiểm toán giấy phép bên thứ ba)
- `docs/V2_CORE_REALITY_AUDIT.md` (Mới: Báo cáo kiểm toán thực chiến chi tiết)

---

## 3. Kế hoạch phiên làm việc tiếp theo (Next Session Action Plan)
1. **Kiểm thử tích hợp nhanh (Fast Test Run)**: Chạy test suite với mock external network cho CI/CD để xác nhận 100% test pass trong vài giây.
2. **Tiến sang Giai đoạn 2 (Web UI)**: Sau khi backend data plane đã chuẩn chỉ và verified, tiến hành phát triển Local Web UI trực quan, biểu đồ quan hệ đồ thị (Cytoscape/ECharts/D3), timeline sự kiện, và báo cáo điều tra dễ hiểu cho người dùng.