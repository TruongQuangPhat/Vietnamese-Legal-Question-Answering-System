import { getApiBaseUrl, joinApiPath, normalizeApiBaseUrl } from "./api-config";
import {
  CONVERSATION_SESSION_HEADER,
  getOptionalConversationSessionToken,
} from "./conversation-client";
import type { LegalQARequest, LegalQAResponse } from "@/types/legal-qa";

const LEGAL_QA_ASK_PATH = "/api/v1/legal-qa/ask";

type LegalQAClientOptions = {
  apiBaseUrl?: string;
  fetcher?: typeof fetch;
  signal?: AbortSignal;
};

export class ApiRequestError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

export async function askLegalQuestion(
  request: LegalQARequest,
  options: LegalQAClientOptions = {},
): Promise<LegalQAResponse> {
  const apiBaseUrl = options.apiBaseUrl
    ? normalizeApiBaseUrl(options.apiBaseUrl)
    : getApiBaseUrl();
  const fetcher = options.fetcher ?? fetch;
  const sessionToken = getOptionalConversationSessionToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (sessionToken) {
    headers[CONVERSATION_SESSION_HEADER] = sessionToken;
  }

  let response: Response;
  try {
    response = await fetcher(joinApiPath(apiBaseUrl, LEGAL_QA_ASK_PATH), {
      method: "POST",
      headers,
      signal: options.signal,
      body: JSON.stringify({
        question: request.question,
        conversation_id: request.conversation_id,
        conversation_context: request.conversation_context,
        top_k: request.top_k,
        include_evidence: request.include_evidence,
        include_debug: request.include_debug,
      }),
    });
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    throw new ApiRequestError(
      "Unable to reach the Legal QA API.",
      undefined,
      "network_error",
    );
  }

  if (!response.ok) {
    throw new ApiRequestError(
      "Legal QA API request failed.",
      response.status,
      "http_error",
    );
  }

  try {
    return (await response.json()) as LegalQAResponse;
  } catch {
    throw new ApiRequestError(
      "Legal QA API returned an invalid response.",
      response.status,
      "invalid_json",
    );
  }
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
