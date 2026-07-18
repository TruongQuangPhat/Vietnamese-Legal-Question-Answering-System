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
          <p className="text-sm font-semibold text-ink">{citation.citation}</p>
          <p className="mt-1 text-sm text-muted">{citation.law_name}</p>
          {citation.hierarchy_path ? (
            <p className="mt-3 rounded-md bg-surface p-3 text-sm leading-6 text-muted">
              {citation.hierarchy_path}
            </p>
          ) : null}
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
