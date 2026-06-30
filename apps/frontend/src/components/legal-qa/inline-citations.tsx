import type { LegalQACitation, LegalQAEvidence } from "@/types/legal-qa";

type InlineCitationsProps = {
  answer: string;
  citations: LegalQACitation[];
  evidence: LegalQAEvidence[];
};

type CitationMarkerData = {
  label: string;
  citation?: LegalQACitation;
  evidence?: LegalQAEvidence;
};

type AnswerPart =
  | {
      type: "text";
      value: string;
    }
  | {
      type: "marker";
      value: string;
      marker: CitationMarkerData;
    };

export function InlineCitations({
  answer,
  citations,
  evidence,
}: InlineCitationsProps) {
  const markers = buildCitationMarkers(citations, evidence);
  const answerParts = splitAnswerByMarkers(answer, markers);
  const hasInlineMarkers = answerParts.some((part) => part.type === "marker");

  return (
    <div className="mt-4 text-sm leading-7 text-ink">
      <p className="whitespace-pre-wrap">
        {answerParts.map((part, index) => {
          if (part.type === "text") {
            return <span key={`${part.type}-${index}`}>{part.value}</span>;
          }
          return <CitationMarker key={`${part.value}-${index}`} marker={part.marker} />;
        })}
      </p>

      {markers.length > 0 && !hasInlineMarkers ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-muted">Căn cứ:</span>
          {markers.map((marker) => (
            <CitationMarker key={marker.label} marker={marker} />
          ))}
        </div>
      ) : null}

      {markers.length === 0 ? (
        <p className="mt-3 rounded-md border border-dashed border-border px-3 py-2 text-xs text-muted">
          Không có trích dẫn hoặc bằng chứng được trả về cho phản hồi này.
        </p>
      ) : null}
    </div>
  );
}

function CitationMarker({ marker }: { marker: CitationMarkerData }) {
  return (
    <span className="group relative inline-flex align-baseline">
      <button
        aria-label={`Xem căn cứ ${marker.label}`}
        className="inline-flex rounded-md border border-[#9bd4c9] bg-[#e8f3f1] px-1.5 py-0.5 text-xs font-semibold leading-5 text-primary transition hover:border-primary focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
        type="button"
      >
        [{marker.label}]
      </button>
      <EvidencePopover marker={marker} />
    </span>
  );
}

function EvidencePopover({ marker }: { marker: CitationMarkerData }) {
  const { citation, evidence } = marker;
  const citationLabel = citation?.citation || evidence?.citation || marker.label;
  const lawName = citation?.law_name || evidence?.law_name || "Không có tên văn bản";
  const hierarchyPath = citation?.hierarchy_path || "Không có cấp bậc pháp lý";
  const evidenceId = citation?.evidence_id || evidence?.evidence_id || marker.label;
  const chunkId = evidence?.chunk_id || citation?.chunk_id || "Không có";
  const sourceUrl = evidence?.source_url || citation?.source_url;

  return (
    <span className="invisible absolute left-0 top-7 z-20 w-[min(82vw,24rem)] rounded-md border border-border bg-surface p-4 text-left text-xs leading-5 text-ink opacity-0 shadow-panel transition group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100">
      <span className="block text-sm font-semibold text-ink">{citationLabel}</span>
      <span className="mt-1 block text-muted">{lawName}</span>
      <span className="mt-2 block rounded-md bg-[#f8fafc] p-2 text-muted">
        {hierarchyPath}
      </span>
      <span className="mt-3 grid gap-2 text-muted sm:grid-cols-2">
        <span>
          <span className="block font-medium text-ink">Evidence ID</span>
          <span className="break-all">{evidenceId}</span>
        </span>
        <span>
          <span className="block font-medium text-ink">Chunk ID</span>
          <span className="break-all">{chunkId}</span>
        </span>
        {evidence ? (
          <span>
            <span className="block font-medium text-ink">Score</span>
            <span>{evidence.score.toFixed(3)}</span>
          </span>
        ) : null}
      </span>
      <span className="mt-3 block max-h-40 overflow-auto whitespace-pre-wrap rounded-md bg-[#fbfcfe] p-3 text-sm leading-6">
        {evidence?.text || "Chưa có đoạn bằng chứng chi tiết cho trích dẫn này."}
      </span>
      {sourceUrl ? (
        <a
          className="mt-3 inline-flex font-medium text-primary hover:underline"
          href={sourceUrl}
          rel="noreferrer"
          target="_blank"
        >
          Mở nguồn văn bản
        </a>
      ) : null}
    </span>
  );
}

function buildCitationMarkers(
  citations: LegalQACitation[],
  evidence: LegalQAEvidence[],
): CitationMarkerData[] {
  const evidenceById = new Map(
    evidence.map((item) => [item.evidence_id, item] as const),
  );

  if (citations.length === 0) {
    return evidence.map((item, index) => ({
      label: item.evidence_id || `E${index + 1}`,
      evidence: item,
    }));
  }

  return citations.map((citation, index) => {
    const label = citation.evidence_id || `E${index + 1}`;
    return {
      label,
      citation,
      evidence: evidenceById.get(citation.evidence_id),
    };
  });
}

function splitAnswerByMarkers(
  answer: string,
  markers: CitationMarkerData[],
): AnswerPart[] {
  if (markers.length === 0) {
    return [{ type: "text", value: answer }];
  }

  const markerByLabel = new Map(markers.map((marker) => [marker.label, marker]));
  const markerPattern = markers.map((marker) => escapeRegExp(marker.label)).join("|");
  const regex = new RegExp(`\\[(${markerPattern})\\]`, "g");
  const parts: AnswerPart[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(answer)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: "text", value: answer.slice(lastIndex, match.index) });
    }

    const marker = markerByLabel.get(match[1]);
    if (marker) {
      parts.push({ type: "marker", value: match[0], marker });
    } else {
      parts.push({ type: "text", value: match[0] });
    }
    lastIndex = regex.lastIndex;
  }

  if (lastIndex < answer.length) {
    parts.push({ type: "text", value: answer.slice(lastIndex) });
  }

  return parts.length > 0 ? parts : [{ type: "text", value: answer }];
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
