import type { LegalQAEvidence } from "@/types/legal-qa";

type EvidenceListProps = {
  evidence: LegalQAEvidence[];
};

export function EvidenceList({ evidence }: EvidenceListProps) {
  if (evidence.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted">
        No evidence returned for this response.
      </p>
    );
  }

  return (
    <ul className="space-y-3">
      {evidence.map((item) => (
        <li className="rounded-md border border-border p-4" key={item.evidence_id}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-ink">{item.citation}</p>
              <p className="mt-1 text-sm text-muted">{item.law_name}</p>
            </div>
            <span className="rounded-full border border-border bg-[#f8fafc] px-2 py-1 text-xs font-medium text-muted">
              Score {item.score.toFixed(3)}
            </span>
          </div>
          <p className="mt-3 max-h-40 overflow-auto whitespace-pre-wrap rounded-md bg-[#f8fafc] p-3 text-sm leading-6 text-ink">
            {item.text}
          </p>
        </li>
      ))}
    </ul>
  );
}
