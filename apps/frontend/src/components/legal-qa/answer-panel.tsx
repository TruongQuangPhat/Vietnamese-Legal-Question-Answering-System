import type { LegalQAResponse } from "@/types/legal-qa";
import { CitationList } from "./citation-list";
import { EvidenceList } from "./evidence-list";
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

  return (
    <section className="space-y-5">
      <div className="rounded-md border border-border bg-surface p-5 shadow-sm">
        <div className="flex flex-col gap-3 border-b border-border pb-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-lg font-semibold">Trợ lý pháp lý</h2>
            <p className="mt-1 text-xs text-muted">
              request_id: {response.request_id}
            </p>
          </div>
          <StatusBadge decision={response.decision} />
        </div>
        {isDemoMode ? <DemoModeNotice /> : null}
        <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-ink">
          {response.answer}
        </p>
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

      <div className="rounded-md border border-border bg-surface p-5 shadow-sm">
        <h3 className="text-base font-semibold">Trích dẫn</h3>
        <div className="mt-3">
          <CitationList citations={response.citations} />
        </div>
      </div>

      <div className="rounded-md border border-border bg-surface p-5 shadow-sm">
        <h3 className="text-base font-semibold">Bằng chứng</h3>
        <div className="mt-3">
          <EvidenceList
            citations={response.citations}
            evidence={response.evidence}
          />
        </div>
      </div>

      <div className="rounded-md border border-border bg-surface p-5 shadow-sm">
        <h3 className="text-base font-semibold">Thông tin phản hồi</h3>
        <dl className="mt-3 grid gap-3 text-sm md:grid-cols-4">
          <div>
            <dt className="font-medium text-muted">latency_ms</dt>
            <dd className="mt-1 text-ink">{response.metadata.latency_ms} ms</dd>
          </div>
          <div>
            <dt className="font-medium text-muted">retrieval_strategy</dt>
            <dd className="mt-1 text-ink">
              {response.metadata.retrieval_strategy}
            </dd>
          </div>
          <div>
            <dt className="font-medium text-muted">model</dt>
            <dd className="mt-1 text-ink">{response.metadata.model ?? "none"}</dd>
          </div>
          <div>
            <dt className="font-medium text-muted">reranking_used</dt>
            <dd className="mt-1 text-ink">
              {response.metadata.reranking_used ? "true" : "false"}
            </dd>
          </div>
        </dl>
      </div>
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
