import type { LegalQACitation, LegalQAEvidence } from "@/types/legal-qa";

type EvidenceListProps = {
  citations: LegalQACitation[];
  evidence: LegalQAEvidence[];
};

export function EvidenceList({ citations, evidence }: EvidenceListProps) {
  if (evidence.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted">
        Không có bằng chứng được trả về cho phản hồi này.
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
              <summary className="flex cursor-pointer list-none items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-ink">{item.citation}</p>
                  <p className="mt-1 text-sm text-muted">{item.law_name}</p>
                  <p className="mt-1 text-xs text-muted">{item.evidence_id}</p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="rounded-full border border-border bg-[#f8fafc] px-2 py-1 text-xs font-medium text-muted">
                    score {item.score.toFixed(3)}
                  </span>
                  <span className="text-xs font-medium text-primary group-open:hidden">
                    Mở
                  </span>
                  <span className="hidden text-xs font-medium text-primary group-open:inline">
                    Thu gọn
                  </span>
                </div>
              </summary>
              <dl className="mt-3 grid gap-2 rounded-md bg-surface p-3 text-xs text-muted md:grid-cols-2">
                <div>
                  <dt className="font-medium text-ink">Mã evidence</dt>
                  <dd>{item.evidence_id}</dd>
                </div>
                <div>
                  <dt className="font-medium text-ink">Mã chunk</dt>
                  <dd className="break-all">{item.chunk_id}</dd>
                </div>
                <div>
                  <dt className="font-medium text-ink">Văn bản</dt>
                  <dd>{item.law_id}</dd>
                </div>
                <div>
                  <dt className="font-medium text-ink">Cấp bậc pháp lý</dt>
                  <dd>
                    {matchingCitation?.hierarchy_path ?? "Không có trong phản hồi"}
                  </dd>
                </div>
              </dl>
              <p className="mt-3 max-h-56 overflow-auto whitespace-pre-wrap rounded-md bg-[#f8fafc] p-3 text-sm leading-6 text-ink">
                {item.text}
              </p>
            </details>
          </li>
        );
      })}
    </ul>
  );
}
