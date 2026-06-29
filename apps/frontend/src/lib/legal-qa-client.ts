import { getApiBaseUrl, normalizeApiBaseUrl } from "./api-config";
import type { LegalQARequest, LegalQAResponse } from "@/types/legal-qa";

const LEGAL_QA_ASK_PATH = "/api/v1/legal-qa/ask";

type LegalQAClientOptions = {
  apiBaseUrl?: string;
  fetcher?: typeof fetch;
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

  let response: Response;
  try {
    response = await fetcher(`${apiBaseUrl}${LEGAL_QA_ASK_PATH}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        question: request.question,
        top_k: request.top_k,
        include_evidence: request.include_evidence,
        include_debug: request.include_debug,
      }),
    });
  } catch {
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
