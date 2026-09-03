# SPIDER — kế hoạch nghiên cứu nâng cấp có kiểm chứng

Ngày cập nhật: 03/09/2026. Đây là **kế hoạch nghiên cứu**, không phải báo cáo tính năng đã triển khai. Không thay đổi hoặc mô tả lại luồng API key đang được thực hiện song song. Không chạy email, username hay hồ sơ người thật trong giai đoạn này.

## Mục tiêu và nguyên tắc quyết định

SPIDER chỉ mở rộng khi cải thiện được ít nhất một trong: kết luận đúng hơn, false merge thấp hơn, provenance rõ hơn, accounting phần chưa biết tốt hơn, hoặc chi phí/request thấp hơn ở cùng chất lượng quyết định.

| Nhãn | Nghĩa |
|---|---|
| **FACT** | Có nguồn hoặc hành vi mã nguồn đã kiểm tra. |
| **HYPOTHESIS** | Dự đoán cần benchmark của SPIDER để xác minh. |
| **EXPERIMENT RESULT** | Chỉ ghi sau khi có protocol, dữ liệu và kết quả tái lập. |
| **NOT YET VERIFIED** | Chưa đủ bằng chứng, gồm license tại commit ghim, TOS, ổn định parser và hiệu quả. |

Không coi `exists=true`, trùng username, avatar, bio, văn phong, email-domain context hoặc một `sameAs` đơn lẻ là xác minh danh tính. Không đưa vào MVP: profiling tâm lý, face recognition, suy vị trí, breach/password hunting, credential dump, EXIF GPS deanonymization, CAPTCHA/rate-limit bypass, proxy rotation, mass enumeration, hay LLM tự quyết `SAME_PERSON`.

## A — Email account existence

**Vấn đề.** Một email có thể có tài khoản ở dịch vụ công khai; kết quả không được suy thành danh tính hay quyền sở hữu mailbox.

**FACT.** [Holehe](https://github.com/megadose/holehe) có các module dịch vụ; [Socialscan](https://github.com/iojw/socialscan) là baseline thứ hai. Cả hai phải được ghim commit trước mọi benchmark. License, số module còn hoạt động, recovery information và TOS của từng module: **NOT YET VERIFIED** tại commit ghim.

**Đề xuất EXPERIMENT.** Xây adapter thử nghiệm sau A/B, chỉ với tập dịch vụ giao nhau giữa Holehe và Socialscan, timeout/rate-limit riêng từng dịch vụ. Output chuẩn:

`CONFIRMED_EXISTS | CONFIRMED_NOT_EXISTS | RATE_LIMITED | UNKNOWN | ERROR`

`CONFIRMED_NOT_EXISTS` chỉ được phát khi module có tín hiệu phủ định đặc hiệu và fixture kiểm chứng; login wall, soft-404, CAPTCHA, timeout hoặc đổi giao diện đều là `UNKNOWN`/`RATE_LIMITED`. Không gửi reset email, không bypass CAPTCHA, không proxy rotation.

| Hạng mục đánh giá | Protocol | Acceptance để ADOPT |
|---|---|---|
| Độ đúng | Canary accounts do người dùng kiểm soát: tồn tại, không tồn tại, login wall, soft-404, rate-limit. Tách theo service và thời gian. | Cải thiện decision coverage ở cùng hoặc tốt hơn precision/recall baseline; không tăng false positive vượt ngưỡng chốt trước. |
| Độ ổn định | Chạy nhiều ngày và lưu version module/parser, trạng thái recovery. | Drift phát hiện được; service suy giảm bị quarantine thay vì trả kết luận âm tính. |
| Chi phí | Request, p50/p95, retry, 429. | Không retry xác thực/rate-limit bừa bãi; budget rõ cho từng service. |

Quyết định hiện tại: **EXPERIMENT, P1**. Không ADOPT trước benchmark/license review.

## B — Username và bằng chứng liên kết công khai

**FACT.** [WhatsMyName](https://github.com/WebBreacher/WhatsMyName) là catalogue site cộng đồng: `wmn-data.json` mô tả URI và điều kiện phát hiện. Đây phù hợp làm catalogue phiên bản hóa và benchmark source hơn là mặc định thêm engine mới. Độ chính xác từng rule và license tại commit ghim: **NOT YET VERIFIED**.

**Đề xuất.** Thu thập `Explicit Link Proof` từ profile field website, outbound profile link, `rel="me"`, JSON-LD `sameAs`, và WebFinger khi resource phù hợp. Tạo cạnh có hướng và loại:

`PUBLICLY_LINKS_TO`, `SELF_ASSERTED_LINK`, `RECIPROCAL_LINK`.

`A → B` là tự công bố; `A ↔ B` là liên kết hai chiều. Cả hai không được tự nâng thành `SAME_PERSON`.

**Benchmark.** So sánh username-only với username + explicit link trên cặp khó: cùng username khác chủ thể, username khác nhưng có liên kết công khai, link một chiều, link chết và trang mirror. Chỉ số chính: false merge rate; phụ: precision, recall, review-needed rate, request/claim.

Quyết định hiện tại: Explicit Link Proof **EXPERIMENT, P1**; WhatsMyName catalogue **EXPERIMENT, P2**.

## C — Supporting, contradicting và dependency evidence

**Vấn đề.** Confidence cộng một chiều biến bản sao và dữ kiện mâu thuẫn thành “nhiều xác nhận”.

**Đề xuất mô hình.** Mỗi hypothesis liên kết hồ sơ lưu tập `SUPPORTING_EVIDENCE`, `CONTRADICTING_EVIDENCE`, `UNKNOWN`, không chỉ một điểm số. Mỗi evidence còn mang dependency:

`INDEPENDENT_SOURCE | DERIVED_SOURCE | MIRRORED_SOURCE | UNKNOWN_DEPENDENCY`.

Hai site có cùng dữ kiện/nguồn gốc chỉ là một cụm dependency cho đến khi chứng minh độc lập. W3C [PROV-O](https://www.w3.org/TR/prov-o/) là tài liệu nền cho thiết kế entity/activity/agent; tính phù hợp đầy đủ với schema SPIDER là **HYPOTHESIS**.

**Benchmark.** Fixture có các nguồn mirror, link bị xóa, dữ kiện trái ngược và same-name hard negative. Báo false merge rate trước tiên, sau đó calibration/review rate. Acceptance: giảm false merge trên holdout mà không che giảm coverage bằng cách trả `UNKNOWN` mọi ca.

Quyết định hiện tại: Contradiction Engine **EXPERIMENT, P1**; Evidence Dependency Graph **EXPERIMENT, P2**.

## D — Temporal evidence và provider drift

**FACT.** Memento được chuẩn hóa tại [RFC 7089](https://www.rfc-editor.org/rfc/rfc7089); Wayback, Memento và [Common Crawl index](https://commoncrawl.org/cc-index-table) là nguồn lịch sử có thể truy vấn. Chúng phản ánh thời điểm quan sát/archive, không chứng minh trạng thái hiện tại hoặc danh tính.

**Đề xuất temporal model.** Claim/evidence lưu `FIRST_SEEN`, `LAST_SEEN`, `OBSERVED_AT`, `ARCHIVED_AT`, cùng event `CHANGED`, `DISAPPEARED`, `HANDLE_CHANGED`, `LINK_CHANGED`. UI tách “current observation” với “archived observation”; archive cũ không là current state.

**Provider Drift Monitor.** Canary accounts do người dùng kiểm soát, nhãn `EXISTS`, `NOT_EXISTS`, `SOFT_404`, `RATE_LIMIT`, `LOGIN_WALL`; ghi parser version, provider version, latency và recovery. Khi sai lệch vượt ngưỡng pre-registered: `DEGRADED → QUARANTINED`. Ngưỡng, lịch chạy và retention: **NOT YET VERIFIED**.

Quyết định hiện tại: Drift Monitor **EXPERIMENT, P1**; Temporal Evidence **EXPERIMENT, P2**.

## E — Coverage, unknown accounting và next-best-action

SPIDER phải trả lời được: đã kiểm tra gì, chưa kiểm tra gì, và vì sao. Chuẩn hóa trạng thái bước thu thập:

`ATTEMPTED | CONFIRMED | NOT_FOUND | RATE_LIMITED | BLOCKED | TIMEOUT | UNSUPPORTED | SKIPPED_BUDGET | BROKEN_PROVIDER`.

`NOT_FOUND` không được sinh ra từ `TIMEOUT`, `BLOCKED`, `UNSUPPORTED` hay `SKIPPED_BUDGET`.

**Investigation Coverage Report.** Theo case/question: expected sources, attempted, decided, unknown, reason unknown, provider/parser version, budget đã dùng/còn lại. Metric `decision coverage` báo riêng với precision; unknown không bị tính là negative.

**HYPOTHESIS — cost-aware scheduler.** Chọn source tiếp theo theo:

`expected information gain / (request cost + quota cost + latency + reliability penalty)`.

Không dùng ML nếu chưa có dữ liệu audit. So `STATIC ORDER` với `COST-AWARE ORDER` trên cùng target, budget, cache state và provider health. Đo useful claims/request, useful claims/second, API credits/useful claim, decision coverage, false positive. Acceptance: cải thiện holdout có khoảng bất định, không tăng false merge hoặc bỏ qua unknown.

Quyết định hiện tại: Coverage/Unknown **EXPERIMENT, P1**; Cost-Aware **EXPERIMENT, P3**.

## F — Passive intelligence, reproducibility và giới hạn

| Nhánh | FACT / giới hạn | Output được phép | Quyết định |
|---|---|---|---|
| urlscan.io | [Search API](https://docs.urlscan.io/apis/urlscan-openapi/search) tìm scan lịch sử; [tài liệu API](https://urlscan.io/docs/api/) yêu cầu tôn trọng quota, 429 và lưu ý PII. | redirect, technology, resource, related host, historical observation từ scan đã tồn tại. Không submit target riêng tư. | **EXPERIMENT, P3** nếu benchmark chứng minh giá trị. |
| Email Domain Context | Email → domain → MX/SPF/DMARC/domain status là context hạ tầng. | `EMAIL_DOMAIN_CONTEXT`; không SMTP VRFY/RCPT, gửi mail hay suy người đứng sau mailbox. | **EXPERIMENT, P3**. |
| Public Web Mention Discovery | Common Crawl/search/archive chỉ là literal mention. | `PUBLIC_MENTION`; không `ACCOUNT_EXISTS` hay `SAME_PERSON`. | **EXPERIMENT, P3**. |
| Reproducible Evidence Bundle | Claim phải truy được evidence và collection method. | case manifest, claim IDs, source URL, timestamp, tool/provider/parser version, config profile, budget, artifact SHA-256, graph edges, review status. Không credential. | **EXPERIMENT, P2**. |

## Milestone và gates

| Mốc | Phạm vi | Gate trước khi sang mốc tiếp |
|---|---|---|
| A | Entity key có type/namespace, lineage đúng, budget accounting. | Domain/username cùng chuỗi không merge; budget dừng chính xác. |
| B | Host/Origin/SSRF, credential boundary, provenance tối thiểu. | Không secret trong log/DB/artifact; failure state không thành success. |
| C | Coverage/Unknown và Provider Drift Monitor. | Unknown explanation đúng với fixture, canary có quarantine. |
| D | Explicit Link Proof + supporting/contradicting. | False merge benchmark đạt gate đã đăng ký trước. |
| E | Temporal/dependency/reproducible bundle. | Claim truy ngược qua evidence/version/time; mirror không double-count. |
| F | Holehe/Socialscan, WhatsMyName, passive sources, cost-aware thử nghiệm. | Mỗi nhánh vượt baseline trên holdout ở cùng ngân sách; license/TOS review PASS. |

Mọi proposal phải có trước khi **ADOPT**: (1) vấn đề, (2) nguồn đã đọc, (3) gap hiện hữu, (4) input/output, (5) FP/FN/privacy/legal/TOS/rate-limit/drift/license risk, (6) cost, (7) milestone, (8) benchmark protocol, (9) acceptance criteria, (10) quyết định ADOPT/EXPERIMENT/DEFER/REJECT.

## Baseline và quyết định hiện tại

**EXPERIMENT RESULT (đã có, giới hạn).** Benchmark hiện hữu chỉ gồm 7 website tổng hợp, 3 lần lặp; không chứng minh ưu thế trên Internet thực hoặc identity resolution. Kết quả phải được tái lập trên fixture và holdout mới trước khi dùng làm lý do ADOPT.

**P1:** Holehe + Socialscan baseline; Explicit Link Proof; Contradiction Engine; Coverage/Unknown Accounting; Provider Drift Monitor.

**P2:** WhatsMyName catalogue; Temporal Evidence; Evidence Dependency Graph; Reproducible Evidence Bundle.

**P3:** Cost-Aware Acquisition; passive urlscan; Email Domain Context; Public Web Mention Discovery.

Blackbird chỉ có thể là baseline coverage nếu cần; không phải bằng chứng để đưa behavioral profiling vào MVP. Không proposal nào trong tài liệu này được coi là đã triển khai hoặc được phép chạy với dữ liệu người thật.
