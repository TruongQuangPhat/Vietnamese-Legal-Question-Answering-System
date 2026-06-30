"use client";

import { useEffect, useRef, useState } from "react";
import { ApiRequestError, askLegalQuestion } from "@/lib/legal-qa-client";
import { AskForm } from "./ask-form";
import { ChatEmptyState } from "./chat-empty-state";
import { ChatMessageList, type ChatMessage } from "./chat-message-list";
import { ChatSidebar } from "./chat-sidebar";

const MAX_QUESTION_LENGTH = 4000;
const DEFAULT_TOP_K = 10;

type LegalQAWorkspaceProps = {
  apiBaseUrl: string;
};

export function LegalQAWorkspace({ apiBaseUrl }: LegalQAWorkspaceProps) {
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(DEFAULT_TOP_K);
  const [includeEvidence, setIncludeEvidence] = useState(true);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const latestMessageRef = useRef<HTMLDivElement | null>(null);
  const chatVersionRef = useRef(0);

  useEffect(() => {
    latestMessageRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "end",
    });
  }, [messages]);

  async function submitQuestion() {
    const trimmedQuestion = question.trim();
    const validationMessage = validateQuestion(trimmedQuestion, question.length, topK);
    if (validationMessage) {
      setValidationError(validationMessage);
      return;
    }

    setValidationError(null);
    setQuestion("");
    setIsLoading(true);

    const userMessage = createUserMessage(trimmedQuestion);
    const assistantMessage = createAssistantLoadingMessage();
    const chatVersion = chatVersionRef.current;
    setMessages((currentMessages) => [
      ...currentMessages,
      userMessage,
      assistantMessage,
    ]);

    try {
      const answer = await askLegalQuestion({
        question: trimmedQuestion,
        top_k: topK,
        include_evidence: includeEvidence,
        include_debug: false,
      });
      if (chatVersion !== chatVersionRef.current) {
        return;
      }
      setMessages((currentMessages) =>
        updateAssistantMessage(currentMessages, assistantMessage.id, {
          content: answer.answer,
          status: "complete",
          response: answer,
        }),
      );
    } catch (error) {
      if (chatVersion !== chatVersionRef.current) {
        return;
      }
      const errorMessage = toUserFacingError(error);
      setMessages((currentMessages) =>
        updateAssistantMessage(currentMessages, assistantMessage.id, {
          content: errorMessage,
          status: "error",
          errorMessage,
        }),
      );
    } finally {
      if (chatVersion === chatVersionRef.current) {
        setIsLoading(false);
      }
    }
  }

  function startNewChat() {
    chatVersionRef.current += 1;
    setQuestion("");
    setValidationError(null);
    setMessages([]);
    setIsLoading(false);
  }

  const hasConversation = messages.length > 0;

  return (
    <div className="flex min-h-[calc(100vh-1.5rem)] flex-1 overflow-hidden rounded-md border border-border bg-surface shadow-panel md:min-h-[calc(100vh-2.5rem)]">
      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <ChatSidebar onNewChat={startNewChat} />

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
              <ChatMessageList messages={messages} />
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
