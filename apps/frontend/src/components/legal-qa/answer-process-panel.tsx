"use client";

import { useMemo, useState } from "react";
import type { LegalQAResponseMetadata } from "@/types/legal-qa";

type AnswerProcessPanelProps = {
  isLoading?: boolean;
  metadata?: LegalQAResponseMetadata;
  warnings?: string[];
};

const BASE_COMPLETED_STEPS = [
  "Tiếp nhận câu hỏi",
  "Chuẩn hóa câu hỏi nếu cần",
  "Tìm kiếm căn cứ pháp lý liên quan",
  "Chọn các căn cứ phù hợp nhất",
  "Tạo câu trả lời dựa trên căn cứ",
  "Kiểm tra cảnh báo và trích dẫn nếu có",
];

export function AnswerProcessPanel({
  isLoading = false,
  metadata,
  warnings = [],
}: AnswerProcessPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const details = useMemo(
    () => buildProcessDetails(metadata, warnings),
    [metadata, warnings],
  );

  if (isLoading) {
    return (
      <section className="rounded-md border border-border bg-surface p-4 shadow-sm">
        <p className="text-sm font-semibold text-ink">Quá trình xử lý</p>
        <p className="mt-2 text-sm text-muted">Đang tìm căn cứ pháp lý...</p>
        <ol className="mt-3 space-y-2 text-sm text-muted">
          <li>1. Đang tiếp nhận câu hỏi...</li>
          <li>2. Đang tìm căn cứ pháp lý...</li>
          <li>3. Đang soạn câu trả lời...</li>
        </ol>
      </section>
    );
  }

  return (
    <section className="rounded-md border border-border bg-[#fbfcfe] p-4">
      <button
        aria-expanded={isExpanded}
        className="flex w-full items-center justify-between gap-3 text-left"
        onClick={() => setIsExpanded((current) => !current)}
        type="button"
      >
        <span>
          <span className="block text-sm font-semibold text-ink">
            Quá trình xử lý
          </span>
          <span className="mt-1 block text-sm text-muted">
            Đã tìm căn cứ pháp lý và tạo câu trả lời.
          </span>
        </span>
        <span className="shrink-0 rounded-md border border-border px-2.5 py-1 text-xs font-semibold text-muted">
          {isExpanded ? "Thu gọn" : "Xem thêm"}
        </span>
      </button>

      {isExpanded ? (
        <div className="mt-4 border-t border-border pt-4">
          <ol className="space-y-2 text-sm leading-6 text-ink">
            {BASE_COMPLETED_STEPS.map((step, index) => (
              <li className="flex gap-2" key={step}>
                <span className="font-semibold text-primary">{index + 1}.</span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
          {details.length > 0 ? (
            <ul className="mt-4 space-y-2 text-sm leading-6 text-muted">
              {details.map((detail) => (
                <li key={detail}>{detail}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function buildProcessDetails(
  metadata: LegalQAResponseMetadata | undefined,
  warnings: string[],
): string[] {
  const details: string[] = [];
  if (!metadata) {
    return details;
  }

  if (metadata.retrieval_mode === "hybrid") {
    details.push("Đã dùng chế độ tìm kiếm kết hợp.");
  }
  if (metadata.conversation_context_used) {
    details.push("Đã dùng ngữ cảnh cuộc trò chuyện để hiểu câu hỏi.");
  } else if (metadata.follow_up_detected === false) {
    details.push("Câu hỏi được xử lý như một câu hỏi độc lập.");
  }
  if (metadata.reranking_used) {
    details.push("Đã sắp xếp lại căn cứ để chọn nội dung phù hợp hơn.");
  }
  if (metadata.fallback_used === false) {
    details.push("Không cần dùng chế độ dự phòng khi tìm căn cứ.");
  } else if (metadata.fallback_used === true) {
    details.push("Hệ thống phải dùng chế độ dự phòng khi tìm căn cứ.");
  }
  if (metadata.latency_ms > 0) {
    details.push(`Thời gian xử lý khoảng ${formatLatency(metadata.latency_ms)}.`);
  }
  if (hasSevereWarning(warnings)) {
    details.push("Có cảnh báo kỹ thuật trong quá trình tìm hoặc tạo câu trả lời.");
  }
  return details;
}

function formatLatency(latencyMs: number): string {
  if (latencyMs < 1000) {
    return `${latencyMs} ms`;
  }
  return `${Math.round(latencyMs / 100) / 10} giây`;
}

function hasSevereWarning(warnings: string[]): boolean {
  return warnings.some((warning) =>
    [
      "embedding_model_load_timeout",
      "query_embedding_timeout",
      "qdrant_retrieval_error",
      "qdrant_retrieval_timeout",
      "dense_retrieval_fallback_used",
      "ask_timeout",
    ].includes(warning),
  );
}
