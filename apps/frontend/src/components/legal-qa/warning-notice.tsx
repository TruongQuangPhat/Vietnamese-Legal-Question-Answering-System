const SEVERE_WARNING_MESSAGES = new Map([
  [
    "embedding_model_load_timeout",
    "Quá trình tìm căn cứ gặp vấn đề, câu trả lời có thể cần kiểm tra lại.",
  ],
  [
    "query_embedding_timeout",
    "Quá trình tìm căn cứ gặp vấn đề, câu trả lời có thể cần kiểm tra lại.",
  ],
  [
    "qdrant_retrieval_error",
    "Quá trình tìm căn cứ gặp vấn đề, câu trả lời có thể cần kiểm tra lại.",
  ],
  [
    "qdrant_retrieval_timeout",
    "Quá trình tìm căn cứ gặp vấn đề, câu trả lời có thể cần kiểm tra lại.",
  ],
  [
    "dense_retrieval_fallback_used",
    "Quá trình tìm căn cứ gặp vấn đề, câu trả lời có thể cần kiểm tra lại.",
  ],
  [
    "ask_timeout",
    "Quá trình tìm căn cứ gặp vấn đề, câu trả lời có thể cần kiểm tra lại.",
  ],
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
  if (!hasSevereWarning) {
    return null;
  }

  return (
    <div
      className="rounded-md border border-[#f1b4b4] bg-[#fff7f7] p-3 text-sm leading-6 text-[#7d2b2b]"
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
  const messages = deduplicateWarnings(warnings).flatMap((warning) => {
    const message = SEVERE_WARNING_MESSAGES.get(warning);
    return message ? [message] : [];
  });
  return Array.from(new Set(messages));
}

function deduplicateWarnings(warnings: string[]): string[] {
  return Array.from(new Set(warnings.map((warning) => warning.trim()))).filter(
    Boolean,
  );
}
