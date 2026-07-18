const CAUTION_WARNING_MESSAGES = new Map([
  [
    "caution_evidence_selected",
    "Một số căn cứ cần được xem xét thận trọng.",
  ],
  [
    "auxiliary_parent_context_included",
    "Một số ngữ cảnh bổ trợ đã được dùng để hiểu căn cứ.",
  ],
  [
    "all_selected_evidence_caution",
    "Tất cả căn cứ được chọn đều cần xem xét thận trọng.",
  ],
]);

const SEVERE_WARNING_MESSAGES = new Map([
  [
    "embedding_model_load_timeout",
    "Quá trình chuẩn bị mô hình tìm kiếm căn cứ gặp vấn đề.",
  ],
  [
    "query_embedding_timeout",
    "Quá trình tìm căn cứ mất quá nhiều thời gian.",
  ],
  ["qdrant_retrieval_error", "Kho dữ liệu tìm kiếm căn cứ gặp lỗi."],
  [
    "qdrant_retrieval_timeout",
    "Kho dữ liệu tìm kiếm căn cứ phản hồi quá chậm.",
  ],
  [
    "dense_retrieval_fallback_used",
    "Hệ thống phải dùng chế độ dự phòng khi tìm căn cứ.",
  ],
  ["ask_timeout", "Yêu cầu mất quá nhiều thời gian để hoàn tất."],
]);

type WarningNoticeProps = {
  warnings: string[];
};

export function WarningNotice({ warnings }: WarningNoticeProps) {
  const messages = getFriendlyWarningMessages(warnings);
  if (messages.length === 0) {
    return null;
  }

  const hasSevereWarning = deduplicateWarnings(warnings).some((warning) =>
    SEVERE_WARNING_MESSAGES.has(warning),
  );

  return (
    <div
      className={`rounded-md border p-3 text-sm leading-6 ${
        hasSevereWarning
          ? "border-[#f1b4b4] bg-[#fff7f7] text-[#7d2b2b]"
          : "border-[#d7ebe7] bg-[#f2faf8] text-[#215b55]"
      }`}
    >
      <p className="font-semibold">Lưu ý</p>
      <ul className="mt-1 space-y-1">
        {messages.map((message) => (
          <li key={message}>{message}</li>
        ))}
      </ul>
    </div>
  );
}

export function getFriendlyWarningMessages(warnings: string[]): string[] {
  return deduplicateWarnings(warnings).flatMap((warning) => {
    const message =
      SEVERE_WARNING_MESSAGES.get(warning) ?? CAUTION_WARNING_MESSAGES.get(warning);
    return message ? [message] : [];
  });
}

function deduplicateWarnings(warnings: string[]): string[] {
  return Array.from(new Set(warnings.map((warning) => warning.trim()))).filter(
    Boolean,
  );
}
