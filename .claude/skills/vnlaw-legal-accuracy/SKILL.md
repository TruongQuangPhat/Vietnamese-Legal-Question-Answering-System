---
name: vnlaw-legal-accuracy
description: Use for any task involving legal answers, citations, legal document hierarchy, legal validity dates, confidence fallback, hallucination prevention, or Vietnamese legal QA safety.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, MultiEdit, Write
---

# Legal Accuracy Skill

Use this skill whenever correctness of legal output matters more than speed or convenience.

## Grounding Rules

- Answer only from the trusted corpus (`thuvienphapluat.vn`).
- Cite legal sources at the level of **Point → Clause → Article → Law → Year / consolidated version**.
- Resolve the legally effective version of a document based on the query date.
- Clearly state that the system supports legal research and **does not replace professional legal counsel**.
- Never fabricate laws, articles, clauses, points, penalties, procedures, or citations.

## Citation Format

Required citation style in generated answers:

```text
Theo Khoản {X}, Điều {Y}, {Law Name} {Year or Consolidated Version}:
"{quoted legal content}"
```

For parent-child chunking context:

```text
Luật {law_name}, Điều {article_number}, Khoản {clause_number}, Điểm {point_label}
```

Omit `Khoản`/`Điểm` when the level does not apply. Always use Vietnamese legal terminology, never English "Article/Clause/Point".

## Confidence and Fallback

If confidence is below the configured threshold (default `0.75`), the system must fall back:

```text
Tôi không tìm thấy quy định cụ thể về vấn đề này trong kho văn bản pháp luật hiện tại.
Vui lòng kiểm tra trực tiếp trên thuvienphapluat.vn hoặc tham khảo ý kiến luật sư.
```

The system must never guess or extrapolate legal provisions when evidence is insufficient.

## Hierarchy Preservation

Legal chunks must preserve Vietnamese legal hierarchy:

```text
Phần → Chương → Mục → Điều → Khoản → Điểm
```

Rules:

- Never split a legal clause or point across chunks.
- Never merge separate clauses or points into one chunk.
- Parent context must be the full Article text.
- Offsets must trace back to `normalized_text` in `normalized.json`.

## Validity and Versioning

- Prefer VBHN consolidated documents when available.
- If no VBHN exists, represent original document and amendments in chronological order with accurate `effective_date`, `expiry_date`, and `status` metadata.
- Time-aware retrieval must filter by `effective_date` at query time.
- Never mix expired and active law versions without explaining validity.

## Anti-Hallucination Rules

- Do not let the LLM invent citations.
- Do not let the LLM infer legal provisions not present in retrieved context.
- Do not let the LLM paraphrase as if it were quoting.
- Distinguish quoted legal text from analytical text in answers.
- Validate every citation against retrieved evidence before presenting to user.

## Review Checklist

- [ ] Every legal claim has a citation.
- [ ] Citations match retrieved evidence.
- [ ] Hierarchy is preserved (no broken clauses/points).
- [ ] Source URL and law version are traceable.
- [ ] Fallback is triggered when evidence is below threshold.
- [ ] No fabricated provisions, penalties, or procedures.
- [ ] Query date is respected for law version resolution.
- [ ] Vietnamese terminology is used throughout.

## Do Not

- Do not answer legal questions without retrieved evidence.
- Do not present paraphrased text as quoted law.
- Do not mix law versions without validity explanation.
- Do not skip citation validation.
- Do not hide low confidence from the user.
