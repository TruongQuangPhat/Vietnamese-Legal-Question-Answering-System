"use client";

import type { LegalQAResponse } from "@/types/legal-qa";
import { useState } from "react";
import { InlineCitations } from "./inline-citations";
import { StatusBadge } from "./status-badge";

type AnswerPanelProps = {
  response: LegalQAResponse | null;
  errorMessage: string | null;
  isLoading: boolean;
};

export function AnswerPanel({
  response,
  errorMessage,
  isLoading,
}: AnswerPanelProps) {
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">(
    "idle",
  );

  if (isLoading) {
    return (
      <section className="rounded-md border border-border bg-surface p-5 shadow-sm">
        <p className="text-sm font-medium text-ink">
          Đang tra cứu căn cứ pháp lý...
        </p>
        <p className="mt-2 text-sm text-muted">
          Yêu cầu đang được gửi tới Legal QA API.
        </p>
      </section>
    );
  }

  if (errorMessage) {
    return (
      <section className="rounded-md border border-[#f1b4b4] bg-[#fff7f7] p-5">
        <h2 className="text-lg font-semibold text-[#a93434]">Không gửi được yêu cầu</h2>
        <p className="mt-2 text-sm leading-6 text-[#7d2b2b]">{errorMessage}</p>
      </section>
    );
  }

  if (!response) {
    return (
      <section className="rounded-md border border-border bg-surface p-5 shadow-sm">
        <h2 className="text-lg font-semibold">Câu trả lời</h2>
        <p className="mt-2 text-sm leading-6 text-muted">
          Gửi một câu hỏi pháp lý để xem câu trả lời, trích dẫn, bằng chứng,
          cảnh báo và thông tin phản hồi.
        </p>
      </section>
    );
  }

  const isDemoMode = response.metadata.model === "stub";

  async function copyAnswer() {
    if (!response) {
      return;
    }

    try {
      await navigator.clipboard.writeText(response.answer);
      setCopyStatus("copied");
      window.setTimeout(() => setCopyStatus("idle"), 1600);
    } catch {
      setCopyStatus("failed");
      window.setTimeout(() => setCopyStatus("idle"), 2000);
    }
  }

  return (
    <section className="space-y-5">
      <div className="rounded-md border border-border bg-surface p-5 shadow-sm">
        <div className="flex flex-col gap-3 border-b border-border pb-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-lg font-semibold">Trợ lý pháp lý</h2>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge decision={response.decision} />
            <button
              className="rounded-md border border-border px-3 py-1 text-xs font-semibold text-muted transition hover:border-primary hover:text-primary focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
              onClick={copyAnswer}
              type="button"
            >
              {copyStatus === "copied"
                ? "Đã sao chép"
                : copyStatus === "failed"
                  ? "Không sao chép được"
                  : "Sao chép"}
            </button>
          </div>
        </div>
        {isDemoMode ? <DemoModeNotice /> : null}
        <InlineCitations
          answer={response.answer}
          citations={response.citations}
          evidence={response.evidence}
        />
      </div>

      {response.warnings.length > 0 ? (
        <div className="rounded-md border border-[#f0d58a] bg-[#fff8df] p-4">
          <h3 className="text-sm font-semibold text-[#806100]">Cảnh báo</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-[#806100]">
            {response.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

    </section>
  );
}

function DemoModeNotice() {
  return (
    <div className="mt-4 rounded-md border border-[#badbd5] bg-[#eef8f6] p-3 text-sm leading-6 text-[#215b55]">
      Chế độ demo: phản hồi này đến từ backend fake mode để kiểm tra giao diện
      và API contract.
    </div>
  );
}
