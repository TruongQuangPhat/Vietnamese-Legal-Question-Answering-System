"use client";

import { useEffect, useRef, useState } from "react";
import {
  addBackendConversationMessage,
  ConversationApiError,
  createBackendConversation,
  deleteBackendConversation,
  renameBackendConversation,
  type BackendConversationRole,
} from "@/lib/conversation-client";
import { ApiRequestError, askLegalQuestion } from "@/lib/legal-qa-client";
import type { LegalQAContextMessage } from "@/types/legal-qa";
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
const MAX_ASK_CONTEXT_MESSAGES = 6;
const MAX_ASK_CONTEXT_MESSAGE_LENGTH = 2000;
const CHAT_CONTENT_CONTAINER = "mx-auto w-full max-w-[760px]";

export function LegalQAWorkspace() {
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(DEFAULT_TOP_K);
  const [includeEvidence, setIncludeEvidence] = useState(true);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [hasLoadedStorage, setHasLoadedStorage] = useState(false);
  const messageScrollRef = useRef<HTMLDivElement | null>(null);
  const backendConversationIdsRef = useRef(new Map<string, string>());
  const backendCreationPromisesRef = useRef(
    new Map<string, Promise<string | null>>(),
  );
  const backendMessageQueuesRef = useRef(new Map<string, Promise<void>>());
  const deletedConversationIdsRef = useRef(new Set<string>());

  useEffect(() => {
    const storedConversations = loadConversations();
    for (const conversation of storedConversations) {
      if (conversation.backendConversationId) {
        backendConversationIdsRef.current.set(
          conversation.id,
          conversation.backendConversationId,
        );
      }
    }
    setConversations(storedConversations);
    setActiveConversationId(storedConversations[0]?.id ?? null);
    setHasLoadedStorage(true);
  }, []);

  useEffect(() => {
    messageScrollRef.current?.scrollTo({
      behavior: "smooth",
      top: messageScrollRef.current.scrollHeight,
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
    const conversationTitle =
      activeConversation?.title ?? createConversationTitle(trimmedQuestion);
    const conversationContext = prepareRecentConversationContext(activeMessages);
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
    queueMessageSync(
      conversationId,
      conversationTitle,
      activeConversation?.backendConversationId,
      "user",
      userMessage.content,
    );

    try {
      const answer = await askLegalQuestion({
        question: trimmedQuestion,
        conversation_id: activeConversation?.backendConversationId,
        conversation_context:
          conversationContext.length > 0 ? conversationContext : undefined,
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
      queueMessageSync(
        conversationId,
        conversationTitle,
        activeConversation?.backendConversationId,
        "assistant",
        answer.answer,
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

  function deleteConversation(conversationId: string) {
    deletedConversationIdsRef.current.add(conversationId);
    const backendConversationId =
      backendConversationIdsRef.current.get(conversationId) ??
      conversations.find((conversation) => conversation.id === conversationId)
        ?.backendConversationId;
    backendConversationIdsRef.current.delete(conversationId);

    setConversations((currentConversations) => {
      const remainingConversations = currentConversations.filter(
        (conversation) => conversation.id !== conversationId,
      );

      if (conversationId === activeConversationId) {
        setQuestion("");
        setValidationError(null);
        setActiveConversationId(remainingConversations[0]?.id ?? null);
      }

      return remainingConversations;
    });

    if (backendConversationId) {
      void deleteBackendConversation(backendConversationId).catch(() => {
        warnBackendSyncFailure("delete");
      });
    }
  }

  function renameConversation(conversationId: string, title: string) {
    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      return;
    }
    const nextTitle = createConversationTitle(trimmedTitle);
    const backendConversationId =
      backendConversationIdsRef.current.get(conversationId) ??
      conversations.find((conversation) => conversation.id === conversationId)
        ?.backendConversationId;

    setConversations((currentConversations) =>
      sortConversations(
        currentConversations.map((conversation) => {
          if (conversation.id !== conversationId) {
            return conversation;
          }
          return {
            ...conversation,
            title: nextTitle,
            updatedAt: new Date().toISOString(),
          };
        }),
      ),
    );

    if (backendConversationId) {
      void renameBackendConversation(backendConversationId, nextTitle).catch(
        () => {
          warnBackendSyncFailure("rename");
        },
      );
    }
  }

  function queueMessageSync(
    conversationId: string,
    title: string,
    existingBackendConversationId: string | undefined,
    role: BackendConversationRole,
    content: string,
  ): void {
    const previousSync =
      backendMessageQueuesRef.current.get(conversationId) ?? Promise.resolve();
    const nextSync = previousSync.then(() =>
      syncMessageToBackend(
        conversationId,
        title,
        existingBackendConversationId,
        role,
        content,
      ),
    );
    backendMessageQueuesRef.current.set(conversationId, nextSync);
    void nextSync.then(() => {
      if (backendMessageQueuesRef.current.get(conversationId) === nextSync) {
        backendMessageQueuesRef.current.delete(conversationId);
      }
    });
  }

  async function syncMessageToBackend(
    conversationId: string,
    title: string,
    existingBackendConversationId: string | undefined,
    role: BackendConversationRole,
    content: string,
  ): Promise<void> {
    const backendConversationId = await ensureBackendConversation(
      conversationId,
      title,
      existingBackendConversationId,
    );
    if (!backendConversationId) {
      return;
    }

    try {
      await addBackendConversationMessage(backendConversationId, {
        role,
        content,
      });
    } catch (error) {
      if (isMissingBackendConversation(error)) {
        detachBackendConversationId(conversationId, backendConversationId);
        const replacementBackendConversationId =
          await ensureBackendConversation(conversationId, title, undefined);
        if (replacementBackendConversationId) {
          try {
            await addBackendConversationMessage(
              replacementBackendConversationId,
              { role, content },
            );
            return;
          } catch {
            warnBackendSyncFailure("message");
            return;
          }
        }
      }
      warnBackendSyncFailure("message");
    }
  }

  function detachBackendConversationId(
    conversationId: string,
    backendConversationId: string,
  ): void {
    if (
      backendConversationIdsRef.current.get(conversationId) ===
      backendConversationId
    ) {
      backendConversationIdsRef.current.delete(conversationId);
    }
    setConversations((currentConversations) =>
      removeBackendConversationId(
        currentConversations,
        conversationId,
        backendConversationId,
      ),
    );
  }

  async function ensureBackendConversation(
    conversationId: string,
    title: string,
    existingBackendConversationId: string | undefined,
  ): Promise<string | null> {
    const knownBackendConversationId =
      backendConversationIdsRef.current.get(conversationId) ??
      existingBackendConversationId;
    if (knownBackendConversationId) {
      return knownBackendConversationId;
    }

    const pendingCreation =
      backendCreationPromisesRef.current.get(conversationId);
    if (pendingCreation) {
      return pendingCreation;
    }

    const creation = createAndAttachBackendConversation(conversationId, title);
    backendCreationPromisesRef.current.set(conversationId, creation);
    try {
      return await creation;
    } finally {
      backendCreationPromisesRef.current.delete(conversationId);
    }
  }

  async function createAndAttachBackendConversation(
    conversationId: string,
    title: string,
  ): Promise<string | null> {
    try {
      const backendConversation = await createBackendConversation(title);
      if (deletedConversationIdsRef.current.has(conversationId)) {
        void deleteBackendConversation(backendConversation.id).catch(() => {
          warnBackendSyncFailure("delete");
        });
        return null;
      }

      backendConversationIdsRef.current.set(
        conversationId,
        backendConversation.id,
      );
      setConversations((currentConversations) =>
        attachBackendConversationId(
          currentConversations,
          conversationId,
          backendConversation.id,
        ),
      );
      return backendConversation.id;
    } catch {
      warnBackendSyncFailure("create");
      return null;
    }
  }

  function selectConversation(conversationId: string) {
    setQuestion("");
    setValidationError(null);
    setActiveConversationId(conversationId);
  }

  function selectSuggestedPrompt(prompt: string) {
    setQuestion(prompt);
    setValidationError(null);
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
    <div className="flex h-full min-h-0 flex-1 overflow-hidden rounded-md border border-border bg-surface shadow-panel">
      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <ChatSidebar
          activeConversationId={activeConversationId}
          conversations={conversations}
          onDeleteConversation={deleteConversation}
          onNewChat={startNewChat}
          onRenameConversation={renameConversation}
          onSelectConversation={selectConversation}
        />

        <section className="flex min-h-0 flex-1 flex-col overflow-hidden bg-[#fbfcfe]">
          <div
            className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-5 pb-8 [scrollbar-gutter:stable] md:px-6"
            data-message-scroll
            ref={messageScrollRef}
          >
            <div className={CHAT_CONTENT_CONTAINER}>
              {hasConversation ? (
                <ChatMessageList messages={activeMessages} />
              ) : (
                <ChatEmptyState onSelectPrompt={selectSuggestedPrompt} />
              )}
            </div>
          </div>

          <div className="shrink-0 overflow-y-auto border-t border-border bg-surface px-4 py-2.5 [scrollbar-gutter:stable] md:px-6">
            <div className={CHAT_CONTENT_CONTAINER}>
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

function attachBackendConversationId(
  conversations: Conversation[],
  conversationId: string,
  backendConversationId: string,
): Conversation[] {
  return conversations.map((conversation) =>
    conversation.id === conversationId
      ? { ...conversation, backendConversationId }
      : conversation,
  );
}

function removeBackendConversationId(
  conversations: Conversation[],
  conversationId: string,
  backendConversationId: string,
): Conversation[] {
  return conversations.map((conversation) => {
    if (
      conversation.id !== conversationId ||
      conversation.backendConversationId !== backendConversationId
    ) {
      return conversation;
    }
    return { ...conversation, backendConversationId: undefined };
  });
}

function createUserMessage(content: string): ChatMessage {
  return {
    id: createMessageId(),
    role: "user",
    content,
    createdAt: new Date().toISOString(),
  };
}

function prepareRecentConversationContext(
  messages: ChatMessage[],
): LegalQAContextMessage[] {
  try {
    return messages
      .filter(
        (message) =>
          message.role === "user" ||
          (message.role === "assistant" && message.status === "complete"),
      )
      .slice(-MAX_ASK_CONTEXT_MESSAGES)
      .map((message) => ({
        role: message.role,
        content: message.content.slice(0, MAX_ASK_CONTEXT_MESSAGE_LENGTH),
        created_at: message.createdAt,
      }));
  } catch {
    console.warn("Unable to prepare recent conversation context.");
    return [];
  }
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

function warnBackendSyncFailure(
  operation: "create" | "message" | "rename" | "delete",
): void {
  console.warn(`Conversation backend sync failed during ${operation}.`);
}

function isMissingBackendConversation(error: unknown): boolean {
  return error instanceof ConversationApiError && error.status === 404;
}
