const MAX_QUESTION_LENGTH = 4000;

type AskFormProps = {
  question: string;
  topK: number;
  includeEvidence: boolean;
  isLoading: boolean;
  validationError: string | null;
  onQuestionChange: (value: string) => void;
  onTopKChange: (value: number) => void;
  onIncludeEvidenceChange: (value: boolean) => void;
  onSubmit: () => void;
};

export function AskForm({
  question,
  topK,
  includeEvidence,
  isLoading,
  validationError,
  onQuestionChange,
  onTopKChange,
  onIncludeEvidenceChange,
  onSubmit,
}: AskFormProps) {
  const characterCount = question.length;
  const isOverLimit = characterCount > MAX_QUESTION_LENGTH;

  return (
    <form
      className="rounded-md border border-border bg-surface p-2 shadow-sm"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div>
        <label className="sr-only" htmlFor="question">
          Câu hỏi pháp lý
        </label>
        <textarea
          id="question"
          className="h-12 max-h-36 w-full resize-none overflow-y-auto border-0 p-0 text-sm leading-6 text-ink placeholder:text-[#8b95a5] focus:ring-0"
          disabled={isLoading}
          maxLength={MAX_QUESTION_LENGTH + 200}
          onChange={(event) => onQuestionChange(event.target.value)}
          onKeyDown={(event) => {
            if (
              event.key !== "Enter" ||
              event.shiftKey ||
              event.nativeEvent.isComposing
            ) {
              return;
            }
            if (isLoading || !question.trim()) {
              return;
            }
            event.preventDefault();
            onSubmit();
          }}
          placeholder="Nhập câu hỏi pháp lý..."
          value={question}
        />
        {validationError ? (
          <p className="mt-2 text-sm text-[#a93434]">{validationError}</p>
        ) : null}
      </div>

      <div className="mt-1.5 flex flex-col gap-1.5 border-t border-border pt-1.5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`text-xs ${isOverLimit ? "text-[#a93434]" : "text-muted"}`}
          >
            {characterCount}/{MAX_QUESTION_LENGTH}
          </span>

          <label
            className="flex items-center gap-2 text-xs font-medium text-muted"
            htmlFor="top-k"
          >
            Bằng chứng
            <input
              id="top-k"
              className="h-7 w-14 rounded-md border-border px-2 py-1 text-sm focus:border-primary focus:ring-primary"
              disabled={isLoading}
              max={20}
              min={1}
              onChange={(event) => onTopKChange(Number(event.target.value))}
              type="number"
              value={topK}
            />
          </label>

          <label className="flex items-center gap-2 text-xs font-medium text-muted">
            <input
              checked={includeEvidence}
              className="rounded border-border text-primary focus:ring-primary"
              disabled={isLoading}
              onChange={(event) => onIncludeEvidenceChange(event.target.checked)}
              type="checkbox"
            />
            Hiển thị bằng chứng
          </label>
        </div>

        <button
          className="rounded-md bg-primary px-4 py-1.5 text-sm font-semibold text-white transition hover:bg-[#0c625b] disabled:cursor-not-allowed disabled:opacity-60"
          disabled={isLoading}
          type="submit"
        >
          {isLoading ? "Đang gửi..." : "Gửi"}
        </button>
      </div>
    </form>
  );
}
