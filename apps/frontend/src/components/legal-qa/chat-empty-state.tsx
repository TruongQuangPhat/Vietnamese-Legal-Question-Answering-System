const SUGGESTED_PROMPTS = [
  "Người lao động được đơn phương chấm dứt hợp đồng trong trường hợp nào?",
  "Điều kiện kết hôn theo pháp luật Việt Nam là gì?",
  "Trẻ em dưới 6 tuổi được hưởng bảo hiểm y tế như thế nào?",
  "Người lao động có bao nhiêu ngày nghỉ hằng năm?",
];

type ChatEmptyStateProps = {
  onSelectPrompt: (prompt: string) => void;
};

export function ChatEmptyState({ onSelectPrompt }: ChatEmptyStateProps) {
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
      <div className="mt-6 grid w-full gap-2 text-left sm:grid-cols-2">
        {SUGGESTED_PROMPTS.map((prompt) => (
          <button
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm leading-6 text-ink transition hover:border-primary hover:text-primary focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
            key={prompt}
            onClick={() => onSelectPrompt(prompt)}
            type="button"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}
