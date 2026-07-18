"use client";

import { useEffect, useMemo, useState } from "react";
import type { LegalQAResponseMetadata } from "@/types/legal-qa";

type AnswerProcessPanelProps = {
  isLoading?: boolean;
  metadata?: LegalQAResponseMetadata;
  warnings?: string[];
};

type ProcessStage = {
  key: string;
  label: string;
  loadingLabel: string;
};

const PROCESS_STAGES: ProcessStage[] = [
  {
    key: "receive",
    label: "Tiếp nhận câu hỏi",
    loadingLabel: "Đang tiếp nhận câu hỏi...",
  },
  {
    key: "analyze",
    label: "Phân tích yêu cầu pháp lý",
    loadingLabel: "Đang phân tích yêu cầu pháp lý...",
  },
  {
    key: "retrieve",
    label: "Tìm căn cứ pháp lý liên quan",
    loadingLabel: "Đang tìm căn cứ pháp lý liên quan...",
  },
  {
    key: "select",
    label: "Chọn căn cứ phù hợp",
    loadingLabel: "Đang chọn căn cứ phù hợp...",
  },
  {
    key: "draft",
    label: "Tạo câu trả lời",
    loadingLabel: "Đang tạo câu trả lời...",
  },
  {
    key: "check",
    label: "Kiểm tra trích dẫn",
    loadingLabel: "Đang kiểm tra trích dẫn...",
  },
];

const CAUTION_WARNINGS = new Set([
  "caution_evidence_selected",
  "auxiliary_parent_context_included",
  "all_selected_evidence_caution",
]);

const SEVERE_WARNINGS = new Set([
  "embedding_model_load_timeout",
  "query_embedding_timeout",
  "qdrant_retrieval_error",
  "qdrant_retrieval_timeout",
  "dense_retrieval_fallback_used",
  "ask_timeout",
]);

export function AnswerProcessPanel({
  isLoading = false,
  metadata,
  warnings = [],
}: AnswerProcessPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const activeStageIndex = useLoadingStageIndex(isLoading);
  const details = useMemo(
    () => buildProcessDetails(metadata, warnings),
    [metadata, warnings],
  );

  if (isLoading) {
    const activeStage = PROCESS_STAGES[activeStageIndex];
    return (
      <section className="rounded-md border border-border bg-surface p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <Spinner />
          <div>
            <p className="text-sm font-semibold text-ink">Đang xử lý câu hỏi</p>
            <p
              className="mt-1 text-sm text-muted"
              data-active-stage="true"
            >
              {activeStage.loadingLabel}
            </p>
          </div>
        </div>
        <button
          aria-expanded={isExpanded}
          className="mt-3 text-xs font-semibold text-primary underline-offset-4 hover:underline focus:outline-none focus:ring-2 focus:ring-primary/30"
          onClick={() => setIsExpanded((current) => !current)}
          type="button"
        >
          {isExpanded ? "Thu gọn" : "Xem quá trình"}
        </button>
        {isExpanded ? (
          <Timeline activeStageIndex={activeStageIndex} isLoading />
        ) : null}
      </section>
    );
  }

  return (
    <section className="mt-4 rounded-md border border-border bg-[#fbfcfe] p-3">
      <button
        aria-expanded={isExpanded}
        className="flex w-full items-center justify-between gap-3 text-left"
        onClick={() => setIsExpanded((current) => !current)}
        type="button"
      >
        <span>
          <span className="block text-sm font-semibold text-ink">
            Đã tìm căn cứ pháp lý và tạo câu trả lời.
          </span>
          {metadata?.latency_ms && metadata.latency_ms > 0 ? (
            <span className="mt-1 block text-xs text-muted">
              Hoàn tất trong khoảng {formatLatency(metadata.latency_ms)}.
            </span>
          ) : null}
        </span>
        <span className="shrink-0 rounded-md border border-border px-2.5 py-1 text-xs font-semibold text-muted">
          {isExpanded ? "Thu gọn" : "Xem quá trình"}
        </span>
      </button>

      {isExpanded ? (
        <div className="mt-4 border-t border-border pt-4">
          <Timeline activeStageIndex={PROCESS_STAGES.length - 1} />
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

function Timeline({
  activeStageIndex,
  isLoading = false,
}: {
  activeStageIndex: number;
  isLoading?: boolean;
}) {
  return (
    <ol className="mt-4 space-y-3 text-sm leading-6 text-ink">
      {PROCESS_STAGES.map((stage, index) => {
        const isActive = isLoading && index === activeStageIndex;
        const isCompleted = !isLoading || index < activeStageIndex;
        return (
          <li className="flex items-start gap-3" key={stage.key}>
            <span
              aria-hidden="true"
              className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs ${
                isActive
                  ? "border-primary text-primary"
                  : isCompleted
                    ? "border-primary bg-primary text-white"
                    : "border-border text-muted"
              }`}
            >
              {isActive ? <Spinner compact /> : isCompleted ? "✓" : ""}
            </span>
            <span className={isActive ? "font-semibold text-ink" : ""}>
              {isActive ? stage.loadingLabel : stage.label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function Spinner({ compact = false }: { compact?: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block animate-spin rounded-full border-2 border-primary border-t-transparent ${
        compact ? "h-3 w-3" : "h-5 w-5"
      }`}
      data-testid="process-spinner"
    />
  );
}

function useLoadingStageIndex(isLoading: boolean): number {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    if (!isLoading) {
      setElapsedSeconds(0);
      return;
    }

    const startedAt = Date.now();
    const interval = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 700);

    return () => {
      window.clearInterval(interval);
    };
  }, [isLoading]);

  if (elapsedSeconds < 2) {
    return 0;
  }
  if (elapsedSeconds < 5) {
    return 1;
  }
  if (elapsedSeconds < 10) {
    return 2;
  }
  if (elapsedSeconds < 16) {
    return 3;
  }
  if (elapsedSeconds < 24) {
    return 4;
  }
  return 5;
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
    details.push("Không dùng chế độ dự phòng.");
  } else if (
    metadata.fallback_used === true ||
    metadata.dense_retrieval_fallback_used === true
  ) {
    details.push("Hệ thống đã dùng chế độ dự phòng khi tìm căn cứ.");
  }
  if (hasCautionWarning(warnings)) {
    details.push("Một số căn cứ cần được xem xét thận trọng.");
  }
  if (hasSevereWarning(warnings)) {
    details.push("Quá trình tìm căn cứ gặp vấn đề và cần được kiểm tra lại.");
  }
  return details;
}

function formatLatency(latencyMs: number): string {
  if (latencyMs < 1000) {
    return `${latencyMs} ms`;
  }
  return `${Math.round(latencyMs / 100) / 10} giây`;
}

function hasCautionWarning(warnings: string[]): boolean {
  return warnings.some((warning) => CAUTION_WARNINGS.has(warning));
}

function hasSevereWarning(warnings: string[]): boolean {
  return warnings.some((warning) => SEVERE_WARNINGS.has(warning));
}
