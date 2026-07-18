"use client";

import type { LegalQACitation, LegalQAEvidence } from "@/types/legal-qa";

type InlineCitationsProps = {
  answer: string;
  citations: LegalQACitation[];
  evidence: LegalQAEvidence[];
  onSelectEvidence: (evidenceKey?: string) => void;
};

type CitationMarkerData = {
  label: string;
  evidenceKey?: string;
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
  onSelectEvidence,
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
          return (
            <CitationMarker
              key={`${part.value}-${index}`}
              marker={part.marker}
              onSelectEvidence={onSelectEvidence}
            />
          );
        })}
      </p>

      {markers.length > 0 && !hasInlineMarkers ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-muted">Trích dẫn:</span>
          {markers.map((marker) => (
            <CitationMarker
              key={marker.label}
              marker={marker}
              onSelectEvidence={onSelectEvidence}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function CitationMarker({
  marker,
  onSelectEvidence,
}: {
  marker: CitationMarkerData;
  onSelectEvidence: (evidenceKey?: string) => void;
}) {
  return (
    <button
      aria-label={`Mở căn cứ pháp lý ${marker.label}`}
      className="inline-flex rounded-md border border-[#9bd4c9] bg-[#e8f3f1] px-1.5 py-0.5 text-xs font-semibold leading-5 text-primary transition hover:border-primary focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
      onClick={() => onSelectEvidence(marker.evidenceKey)}
      type="button"
    >
      [{marker.label}]
    </button>
  );
}

function buildCitationMarkers(
  citations: LegalQACitation[],
  evidence: LegalQAEvidence[],
): CitationMarkerData[] {
  if (citations.length === 0) {
    return evidence.map((item, index) => ({
      label: item.evidence_id || `E${index + 1}`,
      evidenceKey: item.evidence_id,
    }));
  }

  return citations.map((citation, index) => ({
    label: citation.evidence_id || `E${index + 1}`,
    evidenceKey: citation.evidence_id,
  }));
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
