export function ChatEmptyState() {
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center px-4 py-10 text-center">
      <p className="text-sm font-semibold uppercase tracking-wide text-primary">
        VnLaw-QA
      </p>
      <h2 className="mt-3 text-2xl font-semibold text-ink md:text-3xl">
        Hỏi đáp pháp luật Việt Nam
      </h2>
      <p className="mt-3 text-sm leading-7 text-muted md:text-base">
        Nhập câu hỏi pháp lý để nhận câu trả lời kèm trích dẫn và bằng chứng từ
        nguồn pháp luật đáng tin cậy.
      </p>
      <div className="mt-6 rounded-md border border-dashed border-border bg-surface px-4 py-3 text-sm text-muted">
        Chưa có cuộc trò chuyện
      </div>
    </div>
  );
}
