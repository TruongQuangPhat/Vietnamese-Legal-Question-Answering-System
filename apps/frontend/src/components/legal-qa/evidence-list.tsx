import type { LegalQACitation, LegalQAEvidence } from "@/types/legal-qa";

type EvidenceListProps = {
  citations: LegalQACitation[];
  evidence: LegalQAEvidence[];
};

export function EvidenceList({ citations, evidence }: EvidenceListProps) {
  if (evidence.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted">
        Không có căn cứ pháp lý để hiển thị.
      </p>
    );
  }

  return (
    <ul className="space-y-3">
      {evidence.map((item) => {
        const matchingCitation = citations.find(
          (citation) => citation.evidence_id === item.evidence_id,
        );

        return (
          <li
            className="rounded-md border border-border bg-[#fbfcfe] p-4"
            key={item.evidence_id}
          >
            <details className="group">
              <summary className="flex cursor-pointer list-none items-start gap-3">
                <span
                  aria-hidden="true"
                  className="mt-0.5 inline-block shrink-0 text-base leading-5 text-primary transition-transform group-open:rotate-90"
                >
                  ›
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-ink">{item.citation}</p>
                  <p className="mt-1 text-xs leading-5 text-muted">
                    {item.law_name}
                  </p>
                </div>
              </summary>
              {matchingCitation?.hierarchy_path ? (
                <p className="mt-3 rounded-md bg-[#eef8f6] p-3 text-sm leading-6 text-[#215b55]">
                  {matchingCitation.hierarchy_path}
                </p>
              ) : null}
              <p className="mt-3 max-h-56 overflow-auto whitespace-pre-wrap rounded-md bg-[#f8fafc] p-3 text-sm leading-6 text-ink">
                {item.text || "Nội dung căn cứ chưa có trong phản hồi."}
              </p>
            </details>
          </li>
        );
      })}
    </ul>
  );
}
