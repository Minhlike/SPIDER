"""Shared, deterministic reader language. Never invents findings or calls a model."""
import html

VOCABULARY = {
    "NOT_STARTED": ("Chưa có lượt kiểm tra", "No check has started"),
    "UNKNOWN_AFTER_RESTART": ("Mất liên kết với lượt chạy; chưa xác định kết quả, không tự chạy lại", "Run is detached; outcome is uncertain and will not be replayed automatically"),
    "READY": ("Sẵn sàng kiểm tra", "Ready to check"),
    "READY_LIMITED": ("Có thể kiểm tra trong phạm vi giới hạn", "Ready for limited checks"),
    "FOUND": ("Có hồ sơ cần đối chiếu", "A profile needs comparison"),
    "CANDIDATE": ("Có hồ sơ cần đối chiếu", "A profile needs comparison"),
    "CLAIMED": ("Có hồ sơ cần đối chiếu", "A profile needs comparison"),
    "UNPROCESSED": ("Chưa kiểm tra", "Not checked yet"),
    "MISSING_CREDENTIAL": ("Cần cấu hình khóa truy cập cho nguồn này", "An access key is needed for this source"),
    "FACT": ("Dữ liệu đã ghi nhận", "Recorded information"),
    "HYPOTHESIS": ("Nhận định cần kiểm chứng", "Interpretation to check"),
    "EXPERIMENT RESULT": ("Kết quả thử nghiệm", "Experimental result"),
    "NOT YET VERIFIED": ("Chưa được kiểm chứng", "Not yet verified"),
    "NOT_YET_VERIFIED": ("Chưa được kiểm chứng", "Not yet verified"),
    "UNKNOWN": ("Chưa đủ thông tin để kết luận", "Not enough information to conclude"),
    "PENDING": ("Đang chờ xử lý", "Waiting to start"),
    "QUEUED": ("Đã xếp hàng, đang chờ đến lượt", "Queued, waiting for a turn"),
    "RUNNING": ("Đang kiểm tra các nguồn", "Checking sources"),
    "COMPLETED": ("Đã kết thúc lượt kiểm tra", "This check has finished"),
    "PARTIAL": ("Đã có kết quả một phần", "Partial results available"),
    "CANCELLED": ("Đã dừng theo yêu cầu", "Stopped on request"),
    "FAILED": ("Lượt kiểm tra gặp lỗi", "The check encountered an error"),
    "ERROR": ("Nguồn dữ liệu gặp lỗi", "The source encountered an error"),
    "SUCCESS": ("Đã ghi nhận dữ liệu từ nguồn", "Information recorded from this source"),
    "CONFIRMED": ("Đã ghi nhận dữ liệu từ nguồn", "Information recorded from this source"),
    "NO_FINDINGS": ("Chưa có dữ liệu bổ sung", "No additional information collected"),
    "NOT_FOUND": ("Không thấy trên nguồn đã kiểm tra", "Not found on the checked source"),
    "ATTEMPTED": ("Đã thử kiểm tra, chưa có kết luận", "Check attempted, outcome still unknown"),
    "RATE_LIMITED": ("Nguồn đang giới hạn lượt truy cập", "The source is limiting requests"),
    "RATE_LIMIT": ("Nguồn đang giới hạn lượt truy cập", "The source is limiting requests"),
    "BLOCKED": ("Nguồn yêu cầu kiểm tra truy cập, chưa đọc được dữ liệu", "Access check required; data could not be read"),
    "LOGIN_REQUIRED": ("Cần đăng nhập để đọc tiếp", "Sign-in required to continue"),
    "TIMEOUT": ("Nguồn chưa trả lời trong thời gian cho phép", "The source did not respond in time"),
    "NETWORK_ERROR": ("Chưa kết nối được tới nguồn", "Could not connect to the source"),
    "BROWSER_NETWORK_UNAVAILABLE": ("Phiên Cốc Cốc không truy cập được Internet; chưa kiểm tra bất kỳ website nào", "The Cốc Cốc session could not reach the Internet; no websites were checked"),
    "SEARCH_ENGINE_UNAVAILABLE": ("Cốc Cốc Search chưa trả lời; kết quả trên website này chưa xác định", "Cốc Cốc Search did not respond; this website remains unknown"),
    "COCCOC_SEARCH_RESULT": ("Ứng viên từ kết quả tìm kiếm Cốc Cốc; cần mở và đối chiếu", "Candidate from Cốc Cốc Search; open and corroborate"),
    "UNSUPPORTED": ("Nguồn này chưa hỗ trợ cách kiểm tra cần thiết", "This source does not support the required check"),
    "BROKEN_PROVIDER": ("Công cụ thu thập chưa hoạt động đúng", "The collection tool did not work correctly"),
    "SKIPPED_BUDGET": ("Chưa kiểm tra tiếp trong lượt này", "Not checked further in this run"),
    "SKIPPED": ("Chưa chạy nguồn này", "This source was not run"),
    "NOT_SCHEDULED": ("Chưa xếp lịch kiểm tra nguồn này", "This source has not been scheduled"),
    "NOT_APPLICABLE": ("Không phù hợp với mục tiêu đang tìm", "Not relevant to this target"),
    "UNMETERED_PROVIDER": ("Tạm dừng vì chưa kiểm soát được số lượt truy cập", "Paused because request usage cannot be controlled"),
    "BLOCKED_UNMETERED": ("Tạm dừng vì chưa kiểm soát được số lượt truy cập", "Paused because request usage cannot be controlled"),
    "CT_LOG_UNAVAILABLE": ("Nhật ký chứng chỉ chưa trả lời được; chưa thể kết luận về tên miền phụ", "The certificate log did not respond; subdomains remain unknown"),
    "DNS_PARTIAL_RESPONSE": ("Một số loại bản ghi DNS chưa trả lời được; dữ liệu đang có vẫn được giữ", "Some DNS record types did not respond; available records were retained"),
    "REQUEST_LIMIT": ("Đã dùng hết số lượt truy cập cho phép", "The allowed request count has been used"),
    "ENTITY_LIMIT": ("Đã đạt giới hạn dữ liệu cho lượt này", "The data limit for this run was reached"),
    "QUARANTINED": ("Nguồn tạm ngừng vì chưa vượt qua kiểm tra chất lượng", "Source paused until quality checks pass"),
    "PARSER_DRIFT": ("Trang đã thay đổi, công cụ chưa đọc chính xác được", "The page changed; the tool cannot read it reliably"),
    "REVIEW_REQUIRED": ("Cần đối chiếu thêm trước khi kết luận", "More comparison is needed before concluding"),
    "COMPETING_EVIDENCE": ("Có bằng chứng chưa thống nhất", "The evidence does not fully agree"),
    "LINK_EVIDENCE_ONLY": ("Mới có bằng chứng về liên hệ", "Evidence of a link only"),
    "SUPPORTING_EVIDENCE": ("Bằng chứng ủng hộ nhận định", "Evidence supporting the interpretation"),
    "CONTRADICTING_EVIDENCE": ("Bằng chứng không phù hợp với nhận định", "Evidence conflicting with the interpretation"),
    "UNKNOWN_DEPENDENCY": ("Chưa biết các nguồn có sao chép nhau không", "Source independence has not been established"),
    "SELF_ASSERTED_LINK": ("Trang tự công bố liên kết này", "The page publishes this link"),
    "RECIPROCAL_LINK": ("Hai trang có dẫn liên kết tới nhau", "The two pages link to each other"),
    "PUBLIC_SELF_PUBLISHED": ("Thông tin do trang công khai tự giới thiệu", "Information published by the public page itself"),
    "CURRENT_OBSERVATION": ("Lần kiểm tra hiện có", "Available observation"),
    "ARCHIVED": ("Bản lưu từ trước", "Archived copy"),
    "OBSERVED": ("Đã ghi nhận nội dung", "Content observed"),
    "CHANGED": ("Nội dung khác lần ghi nhận trước", "Content differs from the previous observation"),
    "DISAPPEARED": ("Nguồn có dấu hiệu cụ thể cho thấy nội dung đã mất", "The source provided a specific absence signal"),
    "NO_ARCHIVED_OBSERVATION": ("Chưa có bản lưu; chưa biết nội dung trước đây ra sao", "No archived observation; earlier content remains unknown"),
    "LOCAL_ONLY": ("Chỉ xử lý dữ liệu trên máy trong phạm vi đã ghi nhận", "Local processing only within the recorded scope"),
    "EGRESS_ATTEMPTED": ("Đã thử gửi thông tin tới nguồn bên ngoài để kiểm tra", "Information was submitted to external sources for checking"),
    "DIRECT": ("Từ mục tiêu bạn nhập", "From your entered target"),
    "DERIVED": ("Từ dữ liệu tìm được ở bước trước", "From information found in an earlier step"),
    "CREDENTIALED": ("Dùng khóa hoặc phiên đăng nhập đã cấu hình", "Using a configured key or signed-in session"),
    "ANONYMOUS": ("Không dùng thông tin đăng nhập", "Without sign-in credentials"),
    "UNCALIBRATED": ("Cần đối chiếu; chưa có xác suất đúng đã kiểm định", "Needs comparison; no validated probability of correctness"),
}


# Provider-specific aliases share the same reader meaning.
for alias, meaning in {
    "AVAILABLE": "NOT_FOUND", "SCHEDULED": "QUEUED", "SKIPPED_SITE_BUDGET": "SKIPPED_BUDGET",
    "INELIGIBLE": "UNSUPPORTED", "NOT_IN_CATALOG": "UNSUPPORTED",
    "ACCESS_DENIED": "BLOCKED", "UPSTREAM_ERROR": "ERROR",
    "NETWORK_OR_RESPONSE_ERROR": "NETWORK_ERROR",
}.items():
    VOCABULARY[alias] = VOCABULARY[meaning]


def vocabulary(language="vi"):
    if language not in {"vi", "en"}:
        raise ValueError("Unsupported report language")
    return {key: values[language == "en"] for key, values in VOCABULARY.items()}


def label(code, language="vi"):
    terms = vocabulary(language)
    return terms.get(code, terms["UNKNOWN"]) if isinstance(code, str) else terms["UNKNOWN"]


def evidence_note(language="vi"):
    return ("Đây là dữ liệu đã ghi nhận từ nguồn, không phải xác nhận danh tính. "
            "Hãy đối chiếu nguồn và thời điểm trước khi sử dụng nhận định."
            if language == "vi" else
            "This is information recorded from a source, not identity verification. "
            "Compare the source and observation time before relying on an interpretation.")


def reader_report(insights, language="vi"):
    terms = vocabulary(language)
    vi = language == "vi"
    choose = lambda a, b: a if vi else b
    coverage = insights.get("coverage_report") or {}
    scope = insights.get("scope") or {}
    observed = insights.get("observations_count", 0)
    profiles = len(insights.get("public_profiles") or [])
    unresolved = coverage.get("unknown", 0)
    running = insights.get("status") in {"PENDING", "QUEUED", "RUNNING"}
    if scope.get("selection_required"):
        conclusion = choose("Hãy chọn một mục tiêu để đọc kết quả riêng của mục tiêu đó.", "Select a target to read its own results.")
    elif not insights.get("run_id") and not observed:
        conclusion = choose("Chưa có dữ liệu kiểm tra cho mục tiêu này.", "No check data is available for this target yet.")
    elif running:
        conclusion = choose("Đang kiểm tra. Những dữ liệu đang hiển thị chưa phải kết luận cuối cùng.", "Checks are running. The displayed information is not a final conclusion.")
    elif profiles:
        conclusion = choose(f"Có {profiles} hồ sơ công khai có dấu hiệu liên quan. Chưa đủ cơ sở xác định cùng một người.", f"{profiles} public profiles may be related. This does not establish that they belong to the same person.")
    elif insights.get("target_type") in {"EMAIL", "USERNAME", "PHONE"} and observed:
        conclusion = choose("Đã ghi nhận dữ liệu liên quan, nhưng chưa có hồ sơ công khai đủ căn cứ để xác định người đứng sau mục tiêu.", "Related information was recorded, but no sufficiently supported public profile identifies the person behind the target.")
    elif observed:
        conclusion = choose("Đã ghi nhận thông tin có liên hệ với mục tiêu. Hãy xem nguồn và thời điểm để biết thông tin này chứng minh được điều gì.", "Information linked to the target was recorded. Check its source and time to understand what it establishes.")
    elif unresolved:
        conclusion = choose("Chưa thu được bằng chứng bổ sung; một số nguồn chưa kiểm tra được đầy đủ. Không thể kết luận rằng thông tin hoặc tài khoản không tồn tại.", "No additional evidence was collected; some sources could not be fully checked. This does not establish that information or accounts do not exist.")
    else:
        conclusion = choose("Chưa thu được bằng chứng bổ sung trong phạm vi đã kiểm tra. Kết quả này không đại diện cho toàn bộ Internet.", "No additional evidence was collected within the checked scope. This result does not cover the entire Internet.")
    sections = [
        {"key": "basis", "title": choose("Căn cứ đang có", "Available basis"), "items": [
            choose(f"Đã lưu {observed} bản ghi bằng chứng và {insights.get('assertions_count', 0)} liên kết có căn cứ cho mục tiêu đã chọn.",
                   f"{observed} evidence records and {insights.get('assertions_count', 0)} supported links are stored for the selected target."),
            choose(f"Trong lượt đang hiển thị: {coverage.get('decided', 0)} bước có kết quả xác định; {unresolved} bước còn chưa rõ. Đây không phải tỷ lệ xác minh danh tính.",
                   f"In the displayed run, {coverage.get('decided', 0)} steps have a determined outcome; {unresolved} remain unclear. This is not identity accuracy.") ]},
        {"key": "method", "title": choose("Phần mềm đi đến nhận định này như thế nào?", "How was this interpretation reached?"), "items": [
            choose("Đọc loại mục tiêu bạn chọn và chuẩn hóa cách viết; giữ lại đầu vào gốc để đối chiếu.", "Read your selected target type and normalize its format, retaining the original input."),
            choose("Dùng những bản ghi có đường liên hệ về đúng mục tiêu. Đầu vào của bạn không được đếm thành phát hiện mới.", "Use records linked back to this target. Your input is not counted as a new finding."),
            choose("Đối chiếu liên kết và lịch sử đã lưu. Tên giống nhau hoặc trang dẫn tới nhau chỉ là dấu hiệu liên hệ, không tự chứng minh cùng chủ sở hữu.", "Compare stored links and history. Matching names or cross-links suggest a relationship, not common ownership.")]},
        {"key": "limits", "title": choose("Điều chưa thể kết luận", "What remains unknown"), "items": [
            evidence_note(language),
            choose("Nguồn bị chặn, cần đăng nhập, hết thời gian hoặc hết lượt truy cập vẫn là chưa biết; không được coi là không tìm thấy.", "Blocked sources, login requirements, timeouts and exhausted requests remain unknown, not negative findings."),
            choose("Nhiều trang có thể sao chép cùng một nội dung. Số lượng bằng chứng và trọng số kỹ thuật không phải xác suất kết luận đúng.", "Pages may copy the same content. Evidence counts and technical weights are not probabilities of correctness.")]},
        {"key": "next", "title": choose("Nên kiểm tra tiếp điều gì?", "What should be checked next?"), "items": [
            choose("Xem nguồn nào chưa kiểm tra được và nguyên nhân trước khi chạy lại.", "Review unresolved sources and their reasons before retrying.") if unresolved else
            choose("Mở bằng chứng gốc, đối chiếu ngày ghi nhận và tìm nguồn độc lập trước khi kết luận về một người.", "Inspect the original evidence, compare its date, and seek independent sources before concluding anything about a person.")]},
    ]
    sections[0]["items"].insert(0, choose("Trạng thái lượt kiểm tra: ", "Check status: ") + label(insights.get("status"), language) + ".")
    if scope.get("selection_required"):
        sections[3]["items"] = [choose("Chọn mục tiêu cần đọc trong hồ sơ này.", "Select the target you want to review in this case.")]
    elif running:
        sections[3]["items"] = [choose("Theo dõi tiến trình; dữ liệu có thể được bổ sung khi các nguồn còn lại trả lời.", "Follow progress; more information may arrive from remaining sources.")]
    elif not insights.get("run_id") and not observed:
        sections[3]["items"] = [choose("Kiểm tra loại mục tiêu rồi bắt đầu lượt thu thập nếu nguồn phù hợp đã sẵn sàng.", "Review the target type, then start collection when relevant sources are ready.")]
    if insights.get("status") in {"PARTIAL", "FAILED", "CANCELLED"}:
        sections[2]["items"].append(choose("Lượt kiểm tra này chưa hoàn tất đầy đủ. Dữ liệu đã có vẫn được giữ để bạn xem lại.", "This check did not finish fully. Available information is retained for review."))
    conflicting = [h for h in (insights.get("evidence_analysis") or {}).get("hypotheses", [])
                   if h.get("CONTRADICTING_EVIDENCE")]
    if conflicting:
        sections[2]["items"].append(choose(f"Có {len(conflicting)} nhận định với bằng chứng chưa thống nhất; chưa nên chọn một kết luận duy nhất.", f"{len(conflicting)} interpretations have conflicting evidence; do not select a single conclusion yet."))
    if insights.get("target_type") == "EMAIL":
        sections[2]["items"].append(choose("Máy chủ thư và IP của dịch vụ email mô tả hạ tầng của nhà cung cấp, không phải IP hay danh tính người dùng email.", "Mail servers and email-service IPs describe the provider's infrastructure, not the email user's IP or identity."))
    if insights.get("target_type") in {"IP_ADDRESS", "IPV6_ADDRESS"}:
        sections[2]["items"].append(choose("Vị trí IP là thông tin ước lượng của nguồn; không xác định địa chỉ nhà hoặc vị trí chính xác của một người.", "IP location is a source estimate; it does not establish a person's home address or exact position."))
    return {"version": "1", "language": language,
            "title": choose("Kết quả và cách hiểu", "Results and how to read them"),
            "conclusion": conclusion, "sections": sections,
            "target": insights.get("target", ""),
            "findings": insights.get("reader_findings", []),
            "findings_truncated": insights.get("reader_findings_truncated", False),
            "sources": [{"provider": step["provider_id"], "state": step["state"],
                         "message": terms.get(step.get("reason"), label(step["state"], language))
                         if isinstance(step.get("reason"), str) else label(step["state"], language)}
                        for step in coverage.get("steps", [])],
            "evidence_ids": (scope.get("evidence_ids") or [])[:50],
            "evidence_references_truncated": len(scope.get("evidence_ids") or []) > 50}


def markdown_report(report):
    # External strings never become executable HTML or Markdown links.
    def safe(value):
        value = html.escape(str(value)).replace("\n", " ").replace("\r", " ")
        for char in "\\`*_[]()#!|":
            value = value.replace(char, "\\" + char)
        return value
    lines = ["# " + safe(report["title"]), "", safe(report["conclusion"]), ""]
    if report.get("target"):
        lines.extend([("Mục tiêu: " if report["language"] == "vi" else "Target: ") + safe(report["target"]), ""])
    if report.get("findings"):
        lines.extend(["## " + ("Thông tin có căn cứ liên hệ" if report["language"] == "vi" else "Information with supporting links"), ""])
        for finding in report["findings"]:
            lines.append("- " + safe(finding["value"]) + " — " +
                ("Bằng chứng: " if report["language"] == "vi" else "Evidence: ") +
                ", ".join(safe(value) for value in finding["evidence_ids"]))
        if report.get("findings_truncated"):
            lines.append("\n" + ("Danh sách rút gọn; xem toàn bộ trong ứng dụng." if report["language"] == "vi" else "Shortened list; see all findings in the app."))
        lines.append("")
    for section in report["sections"]:
        lines.extend(["## " + safe(section["title"]), ""])
        lines.extend("- " + safe(item) for item in section["items"])
        lines.append("")
    lines.extend(["## " + ("Kết quả từng nguồn" if report["language"] == "vi" else "Source outcomes"), ""])
    lines.extend("- " + safe(source["provider"]) + ": " + safe(source["message"]) for source in report["sources"])
    lines.extend(["", "## " + ("Mã bằng chứng để đối chiếu" if report["language"] == "vi" else "Evidence references"), ""])
    lines.extend("- " + safe(ref) for ref in report["evidence_ids"])
    if report["evidence_references_truncated"]:
        lines.append("\n" + ("Danh sách rút gọn; xem gói bằng chứng đầy đủ." if report["language"] == "vi" else "Shortened list; consult the full evidence bundle."))
    return "\n".join(lines) + "\n"
