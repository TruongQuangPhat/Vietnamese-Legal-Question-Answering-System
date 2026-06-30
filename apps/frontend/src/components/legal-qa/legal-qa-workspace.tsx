"use client";

import { useEffect, useRef, useState } from "react";
import { ApiRequestError, askLegalQuestion } from "@/lib/legal-qa-client";
import { AskForm } from "./ask-form";
import { ChatEmptyState } from "./chat-empty-state";
import {
  loadConversations,
  saveConversations,
  sortConversations,
} from "./chat-storage";
import { ChatMessageList } from "./chat-message-list";
import { ChatSidebar } from "./chat-sidebar";
import type { ChatMessage, Conversation } from "./chat-types";

const MAX_QUESTION_LENGTH = 4000;
const DEFAULT_TOP_K = 10;
const DEFAULT_CONVERSATION_TITLE = "Cuộc trò chuyện mới";
const TITLE_MAX_LENGTH = 56;

type LegalQAWorkspaceProps = {
  apiBaseUrl: string;
};

export function LegalQAWorkspace({ apiBaseUrl }: LegalQAWorkspaceProps) {
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(DEFAULT_TOP_K);
  const [includeEvidence, setIncludeEvidence] = useState(true);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [hasLoadedStorage, setHasLoadedStorage] = useState(false);
  const latestMessageRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const storedConversations = loadConversations();
    setConversations(storedConversations);
    setActiveConversationId(storedConversations[0]?.id ?? null);
    setHasLoadedStorage(true);
  }, []);

  useEffect(() => {
    latestMessageRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "end",
    });
  }, [activeConversationId, conversations]);

  useEffect(() => {
    if (!hasLoadedStorage) {
      return;
    }
    saveConversations(conversations);
  }, [conversations, hasLoadedStorage]);

  async function submitQuestion() {
    const trimmedQuestion = question.trim();
    const validationMessage = validateQuestion(trimmedQuestion, question.length, topK);
    if (validationMessage) {
      setValidationError(validationMessage);
      return;
    }

    setValidationError(null);
    setQuestion("");

    const userMessage = createUserMessage(trimmedQuestion);
    const assistantMessage = createAssistantLoadingMessage();
    const conversationId = activeConversationId ?? createMessageId();
    const timestamp = new Date().toISOString();

    setActiveConversationId(conversationId);
    setConversations((currentConversations) =>
      appendMessagesToConversation(
        currentConversations,
        conversationId,
        [userMessage, assistantMessage],
        timestamp,
      ),
    );

    try {
      const answer = await askLegalQuestion({
        question: trimmedQuestion,
        top_k: topK,
        include_evidence: includeEvidence,
        include_debug: false,
      });
      setConversations((currentConversations) =>
        updateConversationMessage(
          currentConversations,
          conversationId,
          assistantMessage.id,
          {
            content: answer.answer,
            status: "complete",
            response: answer,
          },
        ),
      );
    } catch (error) {
      const errorMessage = toUserFacingError(error);
      setConversations((currentConversations) =>
        updateConversationMessage(
          currentConversations,
          conversationId,
          assistantMessage.id,
          {
            content: errorMessage,
            status: "error",
            errorMessage,
          },
        ),
      );
    }
  }

  function startNewChat() {
    setQuestion("");
    setValidationError(null);
    setActiveConversationId(null);
  }

  function selectConversation(conversationId: string) {
    setQuestion("");
    setValidationError(null);
    setActiveConversationId(conversationId);
  }

  const activeConversation = activeConversationId
    ? conversations.find((conversation) => conversation.id === activeConversationId)
    : null;
  const activeMessages = activeConversation?.messages ?? [];
  const hasConversation = activeMessages.length > 0;
  const isLoading = activeMessages.some(
    (message) => message.role === "assistant" && message.status === "loading",
  );

  return (
    <div className="flex min-h-[calc(100vh-1.5rem)] flex-1 overflow-hidden rounded-md border border-border bg-surface shadow-panel md:min-h-[calc(100vh-2.5rem)]">
      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <ChatSidebar
          activeConversationId={activeConversationId}
          conversations={conversations}
          onNewChat={startNewChat}
          onSelectConversation={selectConversation}
        />

        <section className="flex min-h-0 flex-1 flex-col bg-[#fbfcfe]">
          <div className="flex items-center justify-between border-b border-border bg-surface px-4 py-3">
            <div className="min-w-0">
              <h2 className="truncate text-base font-semibold text-ink">
                Cuộc trò chuyện hiện tại
              </h2>
              <p className="mt-1 truncate text-xs text-muted">
                API: <span className="font-medium text-ink">{apiBaseUrl}</span>
              </p>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">
            {hasConversation ? (
              <ChatMessageList messages={activeMessages} />
            ) : (
              <ChatEmptyState />
            )}
            <div ref={latestMessageRef} />
          </div>

          <div className="border-t border-border bg-surface px-4 py-4 md:px-6">
            <div className="mx-auto w-full max-w-3xl">
              <AskForm
                includeEvidence={includeEvidence}
                isLoading={isLoading}
                onIncludeEvidenceChange={setIncludeEvidence}
                onQuestionChange={(value) => {
                  setQuestion(value);
                  if (validationError) {
                    setValidationError(null);
                  }
                }}
                onSubmit={submitQuestion}
                onTopKChange={setTopK}
                question={question}
                topK={topK}
                validationError={validationError}
              />
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function appendMessagesToConversation(
  conversations: Conversation[],
  conversationId: string,
  messages: ChatMessage[],
  updatedAt: string,
): Conversation[] {
  const existingConversation = conversations.find(
    (conversation) => conversation.id === conversationId,
  );

  if (!existingConversation) {
    const firstUserMessage = messages.find((message) => message.role === "user");
    return sortConversations([
      ...conversations,
      {
        id: conversationId,
        title:
          firstUserMessage?.role === "user"
            ? createConversationTitle(firstUserMessage.content)
            : DEFAULT_CONVERSATION_TITLE,
        createdAt: updatedAt,
        updatedAt,
        messages,
      },
    ]);
  }

  return sortConversations(
    conversations.map((conversation) => {
      if (conversation.id !== conversationId) {
        return conversation;
      }

      const nextMessages = [...conversation.messages, ...messages];
      return {
        ...conversation,
        title: resolveConversationTitle(conversation, nextMessages),
        updatedAt,
        messages: nextMessages,
      };
    }),
  );
}

function updateConversationMessage(
  conversations: Conversation[],
  conversationId: string,
  messageId: string,
  updates: Partial<Extract<ChatMessage, { role: "assistant" }>>,
): Conversation[] {
  const updatedAt = new Date().toISOString();

  return sortConversations(
    conversations.map((conversation) => {
      if (conversation.id !== conversationId) {
        return conversation;
      }

      return {
        ...conversation,
        updatedAt,
        messages: updateAssistantMessage(conversation.messages, messageId, updates),
      };
    }),
  );
}

function createUserMessage(content: string): ChatMessage {
  return {
    id: createMessageId(),
    role: "user",
    content,
    createdAt: new Date().toISOString(),
  };
}

function createAssistantLoadingMessage(): ChatMessage {
  return {
    id: createMessageId(),
    role: "assistant",
    content: "Đang tra cứu căn cứ pháp lý...",
    createdAt: new Date().toISOString(),
    status: "loading",
  };
}

function updateAssistantMessage(
  messages: ChatMessage[],
  messageId: string,
  updates: Partial<Extract<ChatMessage, { role: "assistant" }>>,
): ChatMessage[] {
  return messages.map((message) => {
    if (message.id !== messageId || message.role !== "assistant") {
      return message;
    }
    return {
      ...message,
      ...updates,
    };
  });
}

function resolveConversationTitle(
  conversation: Conversation,
  messages: ChatMessage[],
): string {
  if (conversation.title && conversation.title !== DEFAULT_CONVERSATION_TITLE) {
    return conversation.title;
  }

  const firstUserMessage = messages.find((message) => message.role === "user");
  return firstUserMessage?.role === "user"
    ? createConversationTitle(firstUserMessage.content)
    : DEFAULT_CONVERSATION_TITLE;
}

function createConversationTitle(question: string): string {
  const normalizedQuestion = question.trim().replace(/\s+/g, " ");
  if (!normalizedQuestion) {
    return DEFAULT_CONVERSATION_TITLE;
  }
  if (normalizedQuestion.length <= TITLE_MAX_LENGTH) {
    return normalizedQuestion;
  }
  return `${normalizedQuestion.slice(0, TITLE_MAX_LENGTH - 1)}...`;
}

function createMessageId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function validateQuestion(
  trimmedQuestion: string,
  questionLength: number,
  topK: number,
): string | null {
  if (!trimmedQuestion) {
    return "Vui lòng nhập câu hỏi pháp luật.";
  }
  if (questionLength > MAX_QUESTION_LENGTH) {
    return "Câu hỏi vượt quá giới hạn 4000 ký tự.";
  }
  if (!Number.isInteger(topK) || topK < 1 || topK > 20) {
    return "Số bằng chứng tối đa phải nằm trong khoảng 1-20.";
  }
  return null;
}

function toUserFacingError(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.code === "network_error") {
      return "Không thể nhận câu trả lời lúc này. Vui lòng thử lại.";
    }
    if (error.code === "http_error") {
      return "Không thể nhận câu trả lời lúc này. Vui lòng thử lại.";
    }
    if (error.code === "invalid_json") {
      return "Không thể nhận câu trả lời lúc này. Vui lòng thử lại.";
    }
  }
  return "Không thể nhận câu trả lời lúc này. Vui lòng thử lại.";
}
