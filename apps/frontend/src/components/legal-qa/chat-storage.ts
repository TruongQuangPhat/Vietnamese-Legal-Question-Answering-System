import type { ChatMessage, Conversation } from "./chat-types";
import type { LegalQAResponse } from "@/types/legal-qa";

export const CHAT_STORAGE_KEY = "legal-qa-chat-conversations";
const STALE_LOADING_ERROR =
  "Không thể nhận câu trả lời lúc này. Vui lòng thử lại.";

type StoredChatState = {
  version: 1;
  conversations: Conversation[];
};

export function loadConversations(): Conversation[] {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const rawValue = window.localStorage.getItem(CHAT_STORAGE_KEY);
    if (!rawValue) {
      return [];
    }

    const parsedValue = JSON.parse(rawValue) as unknown;
    if (!isStoredChatState(parsedValue)) {
      return [];
    }

    return sortConversations(parsedValue.conversations.map(sanitizeConversation));
  } catch {
    return [];
  }
}

export function saveConversations(conversations: Conversation[]) {
  if (typeof window === "undefined") {
    return;
  }

  try {
    const storedState: StoredChatState = {
      version: 1,
      conversations: sortConversations(conversations),
    };
    window.localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(storedState));
  } catch {
    console.warn("Conversation local persistence failed.");
  }
}

export function sortConversations(conversations: Conversation[]): Conversation[] {
  return [...conversations].sort((left, right) =>
    right.updatedAt.localeCompare(left.updatedAt),
  );
}

function isStoredChatState(value: unknown): value is StoredChatState {
  if (!isRecord(value)) {
    return false;
  }
  if (value.version !== 1 || !Array.isArray(value.conversations)) {
    return false;
  }
  return value.conversations.every(isConversation);
}

function isConversation(value: unknown): value is Conversation {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.id === "string" &&
    (!("backendConversationId" in value) ||
      value.backendConversationId === undefined ||
      typeof value.backendConversationId === "string") &&
    typeof value.title === "string" &&
    typeof value.createdAt === "string" &&
    typeof value.updatedAt === "string" &&
    Array.isArray(value.messages) &&
    value.messages.every(isChatMessage)
  );
}

function isChatMessage(value: unknown): value is ChatMessage {
  if (!isRecord(value)) {
    return false;
  }
  if (
    typeof value.id !== "string" ||
    typeof value.role !== "string" ||
    typeof value.content !== "string" ||
    typeof value.createdAt !== "string"
  ) {
    return false;
  }
  if (value.role === "user") {
    return true;
  }
  if (value.role !== "assistant") {
    return false;
  }
  if (
    value.status !== "loading" &&
    value.status !== "complete" &&
    value.status !== "error"
  ) {
    return false;
  }
  if (
    "response" in value &&
    value.response !== undefined &&
    !isLegalQAResponse(value.response)
  ) {
    return false;
  }
  return !("errorMessage" in value) || typeof value.errorMessage === "string";
}

function sanitizeConversation(conversation: Conversation): Conversation {
  return {
    ...conversation,
    messages: conversation.messages.map((message) => {
      if (message.role !== "assistant" || message.status !== "loading") {
        return message;
      }

      return {
        ...message,
        content: STALE_LOADING_ERROR,
        status: "error",
        errorMessage: STALE_LOADING_ERROR,
      };
    }),
  };
}

function isLegalQAResponse(value: unknown): value is LegalQAResponse {
  if (!isRecord(value) || !isRecord(value.metadata)) {
    return false;
  }

  return (
    typeof value.request_id === "string" &&
    typeof value.decision === "string" &&
    typeof value.answer === "string" &&
    Array.isArray(value.citations) &&
    Array.isArray(value.evidence) &&
    Array.isArray(value.warnings) &&
    typeof value.metadata.retrieval_strategy === "string" &&
    (typeof value.metadata.model === "string" || value.metadata.model === null) &&
    typeof value.metadata.reranking_used === "boolean" &&
    typeof value.metadata.latency_ms === "number"
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
