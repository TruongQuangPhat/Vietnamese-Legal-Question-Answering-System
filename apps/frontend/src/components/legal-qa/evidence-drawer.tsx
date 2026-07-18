"use client";

import { useEffect, useMemo, useRef } from "react";
import type { LegalQACitation, LegalQAEvidence } from "@/types/legal-qa";

type EvidenceDrawerProps = {
  citations: LegalQACitation[];
  evidence: LegalQAEvidence[];
  highlightedEvidenceKey?: string;
  isOpen: boolean;
  onClose: () => void;
};

type LegalBasisItem = {
  key: string;
  title: string;
  lawName: string;
  legalPosition?: string;
  text?: string;
  sourceUrl?: string;
};

export function EvidenceDrawer({
  citations,
  evidence,
  highlightedEvidenceKey,
  isOpen,
  onClose,
}: EvidenceDrawerProps) {
  const items = useMemo(
    () => buildLegalBasisItems(citations, evidence),
    [citations, evidence],
  );
  const highlightedRef = useRef<HTMLLIElement | null>(null);
  const evidenceCount = getLegalBasisCount(citations, evidence);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !highlightedEvidenceKey) {
      return;
    }
    window.setTimeout(() => {
      highlightedRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }, 50);
  }, [highlightedEvidenceKey, isOpen]);

  if (!isOpen) {
    return null;
  }

  return (
    <div
      aria-label="Căn cứ pháp lý"
      aria-modal="true"
      className="fixed inset-0 z-50"
      role="dialog"
    >
      <button
        aria-label="Đóng căn cứ pháp lý"
        className="absolute inset-0 h-full w-full cursor-default bg-ink/25"
        onClick={onClose}
        type="button"
      />
      <aside className="absolute inset-x-0 bottom-0 flex max-h-[88vh] flex-col rounded-t-md border border-border bg-surface shadow-panel md:inset-x-auto md:bottom-0 md:right-0 md:top-0 md:h-full md:max-h-none md:w-[420px] md:rounded-l-md md:rounded-tr-none">
        <div className="flex items-start justify-between gap-4 border-b border-border p-4">
          <div>
            <h2 className="text-lg font-semibold text-ink">Căn cứ pháp lý</h2>
            <p className="mt-1 text-sm text-muted">
              {evidenceCount > 0
                ? `${evidenceCount} căn cứ được sử dụng`
                : "Không có căn cứ pháp lý để hiển thị."}
            </p>
          </div>
          <button
            aria-label="Đóng"
            className="rounded-md border border-border px-2.5 py-1 text-sm font-semibold text-muted transition hover:border-primary hover:text-primary focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
            onClick={onClose}
            type="button"
          >
            Đóng
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {items.length > 0 ? (
            <ol className="space-y-3">
              {items.map((item, index) => {
                const isHighlighted = item.key === highlightedEvidenceKey;
                return (
                  <li
                    className={`rounded-md border bg-[#fbfcfe] p-4 transition ${
                      isHighlighted
                        ? "border-primary shadow-[0_0_0_3px_rgba(15,118,110,0.16)]"
                        : "border-border"
                    }`}
                    data-highlighted={isHighlighted ? "true" : undefined}
                    key={item.key}
                    ref={isHighlighted ? highlightedRef : undefined}
                  >
                    <p className="text-xs font-semibold uppercase tracking-wide text-primary">
                      Căn cứ {index + 1}
                    </p>
                    <h3 className="mt-2 text-sm font-semibold leading-6 text-ink">
                      {item.title}
                    </h3>
                    <p className="mt-1 text-sm leading-6 text-muted">
                      {item.lawName}
                    </p>
                    {item.legalPosition ? (
                      <p className="mt-2 rounded-md bg-[#eef8f6] px-3 py-2 text-sm leading-6 text-[#215b55]">
                        {item.legalPosition}
                      </p>
                    ) : null}
                    <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-ink">
                      {item.text ?? "Nội dung căn cứ chưa có trong phản hồi."}
                    </p>
                    {item.sourceUrl ? (
                      <a
                        className="mt-3 inline-flex text-sm font-semibold text-primary hover:underline focus:outline-none focus:ring-2 focus:ring-primary/30"
                        href={item.sourceUrl}
                        rel="noreferrer"
                        target="_blank"
                      >
                        Xem nguồn
                      </a>
                    ) : null}
                  </li>
                );
              })}
            </ol>
          ) : citations.length > 0 ? (
            <p className="rounded-md border border-dashed border-border p-4 text-sm leading-6 text-muted">
              Câu trả lời có trích dẫn, nhưng nội dung căn cứ chưa được tải
              trong phản hồi này.
            </p>
          ) : (
            <p className="rounded-md border border-dashed border-border p-4 text-sm leading-6 text-muted">
              Không có căn cứ pháp lý để hiển thị.
            </p>
          )}
        </div>
      </aside>
    </div>
  );
}

export function getLegalBasisCount(
  citations: LegalQACitation[],
  evidence: LegalQAEvidence[],
): number {
  return evidence.length > 0 ? evidence.length : citations.length;
}

function buildLegalBasisItems(
  citations: LegalQACitation[],
  evidence: LegalQAEvidence[],
): LegalBasisItem[] {
  const citationsByEvidenceId = new Map(
    citations.map((citation) => [citation.evidence_id, citation] as const),
  );

  if (evidence.length > 0) {
    return evidence.map((item, index) => {
      const citation = citationsByEvidenceId.get(item.evidence_id);
      return {
        key: item.evidence_id || `basis-${index + 1}`,
        title: item.citation || citation?.citation || `Căn cứ ${index + 1}`,
        lawName: item.law_name || citation?.law_name || "Văn bản pháp luật",
        legalPosition: citation?.hierarchy_path,
        text: item.text || undefined,
        sourceUrl: item.source_url || citation?.source_url || undefined,
      };
    });
  }

  return citations.map((citation, index) => ({
    key: citation.evidence_id || `basis-${index + 1}`,
    title: citation.citation || `Căn cứ ${index + 1}`,
    lawName: citation.law_name || "Văn bản pháp luật",
    legalPosition: citation.hierarchy_path || undefined,
    sourceUrl: citation.source_url || undefined,
  }));
}
