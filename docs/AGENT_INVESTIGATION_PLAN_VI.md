# Investigation API và hiệu năng — kế hoạch thực thi

Baseline: `069fa49a2b9eb500f1fa150775547d3851d2b509`. A–E đã PASS giữ nguyên, chỉ sửa khi tái hiện regression. Không nhúng model/runtime AI. Agent bên ngoài sử dụng MCP; core và CLI vẫn chạy độc lập.

## Findings tại baseline 069fa49a — FACT

- `mcp/server.py` chỉ có dispatcher Python, chưa phải MCP transport hoàn chỉnh; collect/query trả toàn graph và mỗi call dừng service chung.
- `core/engine.py` await từng candidate; `max_parallel_tasks` chưa tạo concurrency. Ledger tổng an toàn bằng lock nhưng request attribution của manager dùng chênh lệch tổng, sẽ sai khi chạy song song.
- `providers/transport.py` tạo client từng lần; replay cache chưa nối vào provider_client. Cần sửa accounting trước khi đổi scheduler.
- `service/projection.py` đã scope theo seed; reuse, không viết lại. Tuy nhiên đang load toàn case trước khi lọc nên payload nhỏ chưa đồng nghĩa DB nhanh.
- `service/review.py` chỉ annotate assertion hiện hữu; chưa có hypothesis độc lập.
- PHONE chỉ nhận dạng số quốc tế, chưa có pipeline tìm public candidates. ORGANIZATION chưa có nhánh validate explicit. URL/ACCOUNT/CIDR có syntax nhưng thiếu workflow thực.
- IPv6 adapter RDAP chấp nhận nhưng registry capability chưa khai báo IPv6: regression có thể tái hiện bằng catalogue test.

## Phản biện và quyết định

1. Không thay scheduler bằng telemetry khi chưa có sample count, phiên bản, dataset và accounting đáng tin. Cold start dùng luật tĩnh minh bạch; telemetry ban đầu chỉ quan sát.
2. Không đánh đồng prefix điện thoại với nhà mạng hiện tại: chuyển mạng giữ số. Lưu `original_allocation`, `current_carrier=UNKNOWN`; loại thuê bao không suy từ tên người đăng.
3. Signed-in Cốc Cốc là capability chính thức, nhưng không export cookie/password, không đóng tab của người dùng. CAPTCHA/login/rate-limit tạo partial hoặc chờ người dùng, không tự thành kết quả âm.
4. Không mở rộng mọi CIDR ra từng IP. Transform phải có preview số request/entity và giới hạn explicit.
5. PHONE mention là liên hệ công khai, không là ownership. Không OTP/SMS/gọi/contact-sync/breach lookup; không tương tác chủ số.
6. Không ADOPT nguồn chỉ vì nhiều site. Tách mức hỗ trợ khỏi `verified`, nguồn thiếu benchmark ở trạng thái EXPERIMENT.

## Thứ tự triển khai và acceptance criteria

### M1 — Investigation read API và baseline benchmark (P0)

Phạm vi 3, 6, 7, 12, 14: thêm case digest, evidence lookup theo seed, action/run history và run comparison có phân trang. Digest trả counts, evidence IDs, unknowns và cursor; không raw artifact hay toàn graph. Sửa service lifecycle cho dispatcher, giữ collect/query tương thích.

PASS: cross-case/cross-seed IDs bị từ chối; page <=100 records, text giới hạn; cursor ổn định khi đọc cùng snapshot; service đang chạy không bị call read dừng; serialized bytes và p50/p95 trên fixture được ghi. Chưa tuyên bố tiết kiệm token nếu chỉ đo byte.

### M2 — MCP transport và graph transforms (P0)

Schema tool có version, read/write classification, limits và structured errors; stdio transport theo SDK chính thức sau kiểm tra dependency. Tools: list_capabilities, digest, evidence, graph_neighbors, create_hypothesis, annotate_evidence, run_capability, compare_runs, cancel_run. Mọi mutation có action_id/idempotency, case/seed/question, parent observation và audit receipt. Pivot xác minh observation thuộc seed và thực sự chứa typed entity; không nhận lineage tùy ý từ Agent.

PASS: Agent stdio smoke test; duplicate action không dispatch lần hai; tool unknown không tạo DB; capability sai input không chạy; candidate không được nâng thành identity verified. API dịch vụ dùng lại ở UI/CLI.

### M3 — Concurrent execution và data plane (P0)

Phạm vi 8–10: đo sequential fixture trước; sửa request attribution theo task, global/provider/origin semaphore, bounded queue, cancellation và backpressure. Dùng task-local transport receipts; observation resolution theo deterministic batch order. Shared pool theo credential scope, không cross-account cache. Coalescing phân biệt physical HTTP request với nhiều consumer; mỗi consumer vẫn có evidence lineage. Replay có TTL/schema/version/account isolation, no-store và bounded memory.

PASS: cùng fixture 1/2/4 worker cho cùng evidence/graph; không vượt budget kể cả redirect/retry/control; cancel kết thúc task và flush SQLite; queue không tăng vô hạn; 429 backoff theo origin; publish wall-clock, requests, queue wait, p50/p95 và peak memory. Chỉ bật default concurrency khi gate này PASS.

### M4 — Browser investigation first-class (P1)

Phạm vi 4–6, 13, 18: session → tab → query → read → linked pivot; mỗi bước có action_id, parent observation, sanitized URL, timestamp, content hash, result state. Dùng profile đã đăng nhập, tối đa 3 tab do SPIDER sở hữu; origin limit độc lập. Resume giữ partial; không replay side effects. Detect login wall/CAPTCHA/429/parser drift; chờ có lý do rõ.

PASS: fixture navigation/pivot/cancel/resume; đóng đúng tab sở hữu; không đưa cookie/token/URL query nhạy cảm vào response/log/artifact. Benchmark 1 và 3 tab với negative controls; tốc độ chỉ được báo cho điều kiện đo tương ứng.

### M5 — PHONE public candidates (P1)

Phạm vi 16–30: xác minh quy hoạch số VN từ cơ quan quản lý/ITU trước khi pin metadata. Normalize E.164 ở mọi boundary (UI/CLI/MCP/ingest), giữ raw seed; explicit PHONE cho số nội địa, ambiguous numeric không silently đổi loại. Validate mobile/fixed/service/unknown; số không hợp lệ không auto sửa.

Pipeline PHONE → literal public mention → candidate facts → dependency clusters → competing hypotheses → digest. Nguồn nghiên cứu: search Google/Cốc Cốc, public Facebook/Zalo, Telegram public, forum, doanh nghiệp, rao vặt/danh bạ. Mỗi nguồn phải có điều kiện truy cập, schema, controls và adoption record; không mặc định rằng Zalo có public reverse search.

Quan hệ PHONE↔NAME/ACCOUNT/ORGANIZATION/URL/LOCATION_TEXT giữ observation gốc. Evidence classes: PUBLIC_SELF_PUBLISHED, THIRD_PARTY_MENTION, BUSINESS_CONTACT, DIRECTORY_ENTRY, SEARCH_SNIPPET, USER_CONFIRMED. USER_CONFIRMED là annotation, không sửa bằng chứng nguồn. Snippet cần follow-up trang gốc trước khi tăng hạng.

Rank lexicographic theo directness, quality, independence được chứng minh, freshness; trả từng lý do. Mirror có hash/explicit attribution; domain khác chưa chứng minh độc lập. Temporal first/last observed tách published/captured; stale không đồng nghĩa đổi chủ. Nhiều tên/số doanh nghiệp/tái sử dụng giữ cạnh tranh, không ép chọn chủ hiện tại.

PASS: tập số kiểm soát/consented, train/holdout riêng, macro precision name/account, false attribution, decision coverage, request, latency và freshness. Không có tập consented thì chỉ PASS fixture, live accuracy NOT YET VERIFIED. UI hỏi “Ai/đơn vị nào có bằng chứng công khai liên quan?” và giải thích ranking. Digest tối đa page size quy định, có contradictions/unknown/next action; evidence-linked pivot bắt buộc.

### M6 — Reasoning, telemetry và investigation UX (P1)

Phạm vi 9, 11–15, 23–26: contradiction theo claim type; dependency/mirror, temporal/stale và unknown thống nhất service. Next-best-action trả rule/reason/cost estimate, không probability giả. Telemetry theo provider+version+input+outcome; useful evidence được định nghĩa là evidence mới có source và liên quan question, không đếm seed/duplicate.

UI: case → question → evidence → graph/timeline → transform → coverage; task đang chạy và nguyên nhân thiếu dữ liệu hiện trực tiếp. Input catalogue lấy từ backend; unsupported disable có lý do. URL fetch phải có SSRF/redirect/DNS guard; ACCOUNT cần namespace; ORGANIZATION không biến thành keyword wildcard vô hạn.

PASS: hostile URL/pivot bị chặn; graph neighborhood và UI latency đo với dataset cố định; telemetry không có secret/identifier; replay không được tính là network cost; recommendation không gây dispatch. Mọi claim giữ FACT / HYPOTHESIS / EXPERIMENT RESULT / NOT YET VERIFIED.

## Benchmark protocol chung

Pin seed synthetic, version, hardware/runtime, budget và cache cold/warm. Chạy tối thiểu 20 lần/fixture, report median/p95 và sample count; correctness trước timing. So baseline/worktree trên cùng fixture, chỉ benchmark live với consent và quota explicit. Không so fixture với Internet rồi kết luận speedup. Lưu kết quả không chứa credential hoặc target cá nhân. Mỗi milestone ghi PASS/FAIL/NOT YET VERIFIED và bỏ proposal không giảm chi phí/thời gian hoặc tăng năng lực thực.

## Trạng thái

Increment 1–3 đã triển khai; xem `AGENT_INVESTIGATION_INCREMENT_1.md`,
`AGENT_INVESTIGATION_INCREMENT_2.md` và `AGENT_INVESTIGATION_INCREMENT_3.md`.
Gate hiện hành nằm trong `memory/NEXT.md`.

- M1 PARTIAL: scoped digest/evidence/graph, compare/coverage, benchmark có dữ liệu. Snapshot/delta và continuation của history/graph/run comparison đã có; traversal chỉ đọc branch reachable thay vì toàn case. Hard bound cho reachable branch còn thiếu.
- M2 PASS FIXTURE / NOT YET VERIFIED LIVE: 15 tool stdio, discovery case/target, evidence-linked capability dispatch, annotation, action status/cancellation và UUID receipts. Chưa có graph action controls trên UI; không coi fixture là xác minh provider ngoài Internet.
- M3 PASS FIXTURE / NOT YET VERIFIED LIVE: parent permit trước I/O cho Maigret/Uncover, shared hard cap và attribution theo task; default 2 provider, giới hạn global/provider/origin, cancel/drain và ingest theo thứ tự. Pool theo credential scope, anonymous replay/coalescing trong run có TTL/no-store/giới hạn bộ nhớ. Benchmark 20 lượt cho 1/2/4 nguồn được ghi ở increment 3; không suy ra tốc độ Internet hoặc UI. MCP action queue vẫn serial.
- M4 PARTIAL: browser có owned-tab limit, sanitized step trace qua MCP và resume explicit; chưa có live session navigation/pivot benchmark.
- M5 PARTIAL: E.164/metadata offline, public-candidate digest, mirror-aware ranking và UI wording đã có. Chưa có collector ADOPT hoặc consented live accuracy benchmark. Số user cho phép chỉ đã dùng kiểm thử normalization, không ghi vào repo.
- M6 PARTIAL: catalogue backend khóa lựa chọn UI chưa hỗ trợ; telemetry có latency/request/useful-evidence sample counts và coverage có next-best-action deterministic, không dispatch. Reasoning/UX đầy đủ và calibrated reliability còn PLANNED.

P0 tiếp theo: hoàn thiện hard bound/replay cho reachable branch trong M1, tránh Agent phải đọc lại hoặc nạp toàn bộ dữ liệu cũ. M3 đã thay post-dispatch receipts bằng parent reservation trước I/O; scope giới hạn là một service process. Giữ rõ PARTIAL khi request cap làm thiếu coverage; không hứa cùng graph khi các nguồn tranh ngân sách cuối. Không sửa API-key schema để giải quyết accounting.

Không có nguồn mới được ADOPT. Chỉ báo chênh lệch thời gian trên fixture đã đo;
không tuyên bố khả năng tìm danh tính tốt hơn điều tra thủ công.

## Yêu cầu ad-hoc — ngôn ngữ báo cáo (đã triển khai)

Áp dụng `REPORT_LANGUAGE_VI.md`: một bộ câu chữ VI/EN cho UI, Markdown tải về,
JSON/bundle, CLI và phần diễn giải MCP. Phân biệt dữ liệu đã ghi nhận, nhận định,
kết quả thử nghiệm và điều chưa kiểm chứng; giải thích căn cứ và giới hạn trước
khi đưa ra bước tiếp theo. 388 test ngoại tuyến PASS; không coi đây là hoàn tất M6.
