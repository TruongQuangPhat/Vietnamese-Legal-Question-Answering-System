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
      className="space-y-5"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div>
        <div className="mb-2 flex items-center justify-between gap-3">
          <label className="text-sm font-medium text-ink" htmlFor="question">
            Legal question
          </label>
          <span
            className={`text-xs ${isOverLimit ? "text-[#a93434]" : "text-muted"}`}
          >
            {characterCount}/{MAX_QUESTION_LENGTH}
          </span>
        </div>
        <textarea
          id="question"
          className="min-h-44 w-full resize-y rounded-md border-border text-sm leading-6 text-ink placeholder:text-[#8b95a5] focus:border-primary focus:ring-primary"
          disabled={isLoading}
          maxLength={MAX_QUESTION_LENGTH + 200}
          onChange={(event) => onQuestionChange(event.target.value)}
          placeholder="Người lao động được quyền đơn phương chấm dứt hợp đồng lao động khi nào?"
          value={question}
        />
        {validationError ? (
          <p className="mt-2 text-sm text-[#a93434]">{validationError}</p>
        ) : null}
      </div>

      <div className="grid gap-4 md:grid-cols-[160px_minmax(0,1fr)]">
        <div>
          <label className="mb-2 block text-sm font-medium text-ink" htmlFor="top-k">
            Evidence limit
          </label>
          <input
            id="top-k"
            className="w-full rounded-md border-border text-sm focus:border-primary focus:ring-primary"
            disabled={isLoading}
            max={20}
            min={1}
            onChange={(event) => onTopKChange(Number(event.target.value))}
            type="number"
            value={topK}
          />
        </div>

        <label className="flex items-center gap-3 self-end rounded-md border border-border bg-[#f8fafc] px-4 py-3 text-sm text-ink">
          <input
            checked={includeEvidence}
            className="rounded border-border text-primary focus:ring-primary"
            disabled={isLoading}
            onChange={(event) => onIncludeEvidenceChange(event.target.checked)}
            type="checkbox"
          />
          Include selected evidence
        </label>
      </div>

      <button
        className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#0c625b] disabled:cursor-not-allowed disabled:opacity-60"
        disabled={isLoading}
        type="submit"
      >
        {isLoading ? "Asking..." : "Ask question"}
      </button>
    </form>
  );
}
