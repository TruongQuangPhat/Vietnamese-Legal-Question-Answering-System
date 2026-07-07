import { getApiBaseUrl, normalizeApiBaseUrl } from "./api-config";

const CONVERSATIONS_PATH = "/api/v1/conversations";
const SESSION_HEADER = "X-Legal-QA-Session";
const SESSION_STORAGE_KEY = "legal-qa-chat-session";
let serverSessionToken: string | null = null;

export type BackendConversationRole = "user" | "assistant";

export interface BackendConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface BackendConversationMessage {
  id: string;
  role: BackendConversationRole;
  content: string;
  created_at: string;
}

export interface BackendConversationDetail {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: BackendConversationMessage[];
}

export interface BackendConversationMessageCreateRequest {
  role: BackendConversationRole;
  content: string;
}

type ConversationClientOptions = {
  apiBaseUrl?: string;
  fetcher?: typeof fetch;
};

export class ConversationApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly code?: "network_error" | "http_error" | "invalid_json",
  ) {
    super(message);
    this.name = "ConversationApiError";
  }
}

export function listBackendConversations(
  options: ConversationClientOptions = {},
): Promise<BackendConversationSummary[]> {
  return requestJson<BackendConversationSummary[]>(CONVERSATIONS_PATH, {}, options);
}

export function createBackendConversation(
  title: string,
  options: ConversationClientOptions = {},
): Promise<BackendConversationSummary> {
  return requestJson<BackendConversationSummary>(
    CONVERSATIONS_PATH,
    {
      method: "POST",
      body: JSON.stringify({ title }),
    },
    options,
  );
}

export function getBackendConversation(
  conversationId: string,
  options: ConversationClientOptions = {},
): Promise<BackendConversationDetail> {
  return requestJson<BackendConversationDetail>(
    conversationPath(conversationId),
    {},
    options,
  );
}

export function renameBackendConversation(
  conversationId: string,
  title: string,
  options: ConversationClientOptions = {},
): Promise<BackendConversationSummary> {
  return requestJson<BackendConversationSummary>(
    conversationPath(conversationId),
    {
      method: "PATCH",
      body: JSON.stringify({ title }),
    },
    options,
  );
}

export async function deleteBackendConversation(
  conversationId: string,
  options: ConversationClientOptions = {},
): Promise<void> {
  await request(
    conversationPath(conversationId),
    {
      method: "DELETE",
    },
    options,
  );
}

export function addBackendConversationMessage(
  conversationId: string,
  message: BackendConversationMessageCreateRequest,
  options: ConversationClientOptions = {},
): Promise<BackendConversationMessage> {
  return requestJson<BackendConversationMessage>(
    `${conversationPath(conversationId)}/messages`,
    {
      method: "POST",
      body: JSON.stringify(message),
    },
    options,
  );
}

async function requestJson<T>(
  path: string,
  init: RequestInit,
  options: ConversationClientOptions,
): Promise<T> {
  const response = await request(path, init, options);
  try {
    return (await response.json()) as T;
  } catch {
    throw new ConversationApiError(
      "Conversation API returned an invalid response.",
      response.status,
      "invalid_json",
    );
  }
}

async function request(
  path: string,
  init: RequestInit,
  options: ConversationClientOptions,
): Promise<Response> {
  const apiBaseUrl = options.apiBaseUrl
    ? normalizeApiBaseUrl(options.apiBaseUrl)
    : getApiBaseUrl();
  const fetcher = options.fetcher ?? fetch;

  let response: Response;
  try {
    response = await fetcher(`${apiBaseUrl}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        [SESSION_HEADER]: getConversationSessionToken(),
        ...init.headers,
      },
    });
  } catch {
    throw new ConversationApiError(
      "Unable to reach the conversation API.",
      undefined,
      "network_error",
    );
  }

  if (!response.ok) {
    throw new ConversationApiError(
      "Conversation API request failed.",
      response.status,
      "http_error",
    );
  }
  return response;
}

function conversationPath(conversationId: string): string {
  return `${CONVERSATIONS_PATH}/${encodeURIComponent(conversationId)}`;
}

function getConversationSessionToken(): string {
  if (typeof window === "undefined") {
    serverSessionToken ??= createSessionToken(globalThis.crypto);
    return serverSessionToken;
  }
  const existingToken = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (existingToken) {
    return existingToken;
  }
  const token = createSessionToken(window.crypto);
  window.localStorage.setItem(SESSION_STORAGE_KEY, token);
  return token;
}

function createSessionToken(cryptoApi: Crypto | undefined): string {
  if (cryptoApi?.randomUUID) {
    return cryptoApi.randomUUID();
  }
  const values = new Uint8Array(16);
  if (cryptoApi?.getRandomValues) {
    cryptoApi.getRandomValues(values);
    return Array.from(values, (value) => value.toString(16).padStart(2, "0")).join("");
  }
  return `session-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
