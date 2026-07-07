import type { LegalQADecision } from "@/types/legal-qa";

const STATUS_LABELS: Record<LegalQADecision, string> = {
  answered: "Đã trả lời",
  answered_with_caution: "Trả lời thận trọng",
  fallback: "Fallback an toàn",
  error: "Lỗi",
};

const STATUS_STYLES: Record<LegalQADecision, string> = {
  answered: "border-[#9bd4c9] bg-[#e8f3f1] text-primary",
  answered_with_caution: "border-[#f0d58a] bg-[#fff8df] text-[#806100]",
  fallback: "border-[#f0d58a] bg-[#fff8df] text-[#806100]",
  error: "border-[#f1b4b4] bg-[#fff0f0] text-[#a93434]",
};

type StatusBadgeProps = {
  decision: LegalQADecision;
};

export function StatusBadge({ decision }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold ${STATUS_STYLES[decision]}`}
    >
      {STATUS_LABELS[decision]}
    </span>
  );
}
