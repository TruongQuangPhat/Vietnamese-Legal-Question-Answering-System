import type { LegalQACitation } from "@/types/legal-qa";

type CitationListProps = {
  citations: LegalQACitation[];
};

export function CitationList({ citations }: CitationListProps) {
  if (citations.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted">
        Chưa có trích dẫn trong phản hồi này.
      </p>
    );
  }

  return (
    <ul className="space-y-3">
      {citations.map((citation) => (
        <li
          className="rounded-md border border-border bg-[#f8fafc] p-4"
          key={citation.evidence_id}
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-ink">{citation.citation}</p>
              <p className="mt-1 text-sm text-muted">{citation.law_name}</p>
            </div>
            <span className="rounded-full border border-border bg-surface px-2 py-1 text-xs font-medium text-muted">
              {citation.evidence_id}
            </span>
          </div>
          <dl className="mt-3 grid gap-2 rounded-md bg-surface p-3 text-xs text-muted">
            <div>
              <dt className="font-medium text-ink">Văn bản</dt>
              <dd>{citation.law_id}</dd>
            </div>
            <div>
              <dt className="font-medium text-ink">Mã chunk</dt>
              <dd className="break-all">{citation.chunk_id}</dd>
            </div>
            <div>
              <dt className="font-medium text-ink">Cấp bậc pháp lý</dt>
              <dd>{citation.hierarchy_path}</dd>
            </div>
          </dl>
          <a
            className="mt-3 inline-flex text-sm font-medium text-primary hover:underline"
            href={citation.source_url}
            rel="noreferrer"
            target="_blank"
          >
            Mở nguồn văn bản
          </a>
        </li>
      ))}
    </ul>
  );
}
