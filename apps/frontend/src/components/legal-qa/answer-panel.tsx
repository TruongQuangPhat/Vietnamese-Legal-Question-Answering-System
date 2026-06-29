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
      <section className="rounded-md border border-border bg-surface p-5 shadow-panel">
        <p className="text-sm font-medium text-ink">Loading answer...</p>
        <p className="mt-2 text-sm text-muted">
          The Legal QA API request is in progress.
        </p>
      </section>
    );
  }

  if (errorMessage) {
    return (
      <section className="rounded-md border border-[#f1b4b4] bg-[#fff7f7] p-5">
        <h2 className="text-lg font-semibold text-[#a93434]">Request failed</h2>
        <p className="mt-2 text-sm leading-6 text-[#7d2b2b]">{errorMessage}</p>
      </section>
    );
  }

  if (!response) {
    return (
      <section className="rounded-md border border-border bg-surface p-5 shadow-panel">
        <h2 className="text-lg font-semibold">Answer</h2>
        <p className="mt-2 text-sm leading-6 text-muted">
          Submit a legal question to see the answer, citations, evidence,
          warnings, and response metadata.
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-5">
      <div className="rounded-md border border-border bg-surface p-5 shadow-panel">
        <div className="flex flex-col gap-3 border-b border-border pb-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-lg font-semibold">Answer</h2>
            <p className="mt-1 text-sm text-muted">Request {response.request_id}</p>
          </div>
          <StatusBadge decision={response.decision} />
        </div>
        <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-ink">
          {response.answer}
        </p>
      </div>

      {response.warnings.length > 0 ? (
        <div className="rounded-md border border-[#f0d58a] bg-[#fff8df] p-4">
          <h3 className="text-sm font-semibold text-[#806100]">Warnings</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-[#806100]">
            {response.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="rounded-md border border-border bg-surface p-5 shadow-panel">
        <h3 className="text-base font-semibold">Citations</h3>
        <div className="mt-3">
          <CitationList citations={response.citations} />
        </div>
      </div>

      <div className="rounded-md border border-border bg-surface p-5 shadow-panel">
        <h3 className="text-base font-semibold">Evidence</h3>
        <div className="mt-3">
          <EvidenceList evidence={response.evidence} />
        </div>
      </div>

      <div className="rounded-md border border-border bg-surface p-5 shadow-panel">
        <h3 className="text-base font-semibold">Metadata</h3>
        <dl className="mt-3 grid gap-3 text-sm md:grid-cols-3">
          <div>
            <dt className="font-medium text-muted">Latency</dt>
            <dd className="mt-1 text-ink">{response.metadata.latency_ms} ms</dd>
          </div>
          <div>
            <dt className="font-medium text-muted">Retrieval</dt>
            <dd className="mt-1 text-ink">
              {response.metadata.retrieval_strategy}
            </dd>
          </div>
          <div>
            <dt className="font-medium text-muted">Model</dt>
            <dd className="mt-1 text-ink">{response.metadata.model ?? "none"}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
