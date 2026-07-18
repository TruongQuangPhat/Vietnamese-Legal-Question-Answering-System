const MAX_QUESTION_LENGTH = 4000;

type AskFormProps = {
  question: string;
  isLoading: boolean;
  validationError: string | null;
  onQuestionChange: (value: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
};

export function AskForm({
  question,
  isLoading,
  validationError,
  onQuestionChange,
  onCancel,
  onSubmit,
}: AskFormProps) {
  return (
    <form
      className="flex items-start gap-2 rounded-md border border-border bg-surface p-2 shadow-sm"
      onSubmit={(event) => {
        event.preventDefault();
        if (isLoading) {
          onCancel();
          return;
        }
        onSubmit();
      }}
    >
      <div className="min-w-0 flex-1">
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

      <button
        aria-label={isLoading ? "Dừng tạo câu trả lời" : "Gửi câu hỏi"}
        className={`min-w-16 shrink-0 self-start rounded-md px-4 py-1.5 text-sm font-semibold text-white transition ${
          isLoading
            ? "bg-[#8a3b3b] hover:bg-[#743232]"
            : "bg-primary hover:bg-[#0c625b]"
        }`}
        type="submit"
      >
        {isLoading ? "Dừng" : "Gửi"}
      </button>
    </form>
  );
}
