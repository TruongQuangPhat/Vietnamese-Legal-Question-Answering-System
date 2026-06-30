export type LegalQADecision = "answered" | "fallback" | "error";

export interface LegalQAContextMessage {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
}

export interface LegalQARequest {
  question: string;
  conversation_id?: string;
  conversation_context?: LegalQAContextMessage[];
  top_k?: number;
  include_evidence?: boolean;
  include_debug?: boolean;
}

export interface LegalQACitation {
  evidence_id: string;
  chunk_id: string;
  law_id: string;
  law_name: string;
  citation: string;
  source_url: string;
  hierarchy_path: string;
}

export interface LegalQAEvidence {
  evidence_id: string;
  chunk_id: string;
  law_id: string;
  law_name: string;
  citation: string;
  text: string;
  source_url: string;
  score: number;
}

export interface LegalQAResponseMetadata {
  retrieval_strategy: string;
  model: string | null;
  reranking_used: boolean;
  latency_ms: number;
  conversation_context_used: boolean;
  conversation_context_message_count: number;
  follow_up_detected: boolean;
  retrieval_question_prepared: boolean;
}

export interface LegalQAResponse {
  request_id: string;
  decision: LegalQADecision;
  answer: string;
  citations: LegalQACitation[];
  evidence: LegalQAEvidence[];
  warnings: string[];
  metadata: LegalQAResponseMetadata;
}
