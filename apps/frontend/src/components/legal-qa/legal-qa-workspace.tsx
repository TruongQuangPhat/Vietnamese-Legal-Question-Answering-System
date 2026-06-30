"use client";

import { useState } from "react";
import { ApiRequestError, askLegalQuestion } from "@/lib/legal-qa-client";
import type { LegalQAResponse } from "@/types/legal-qa";
import { AnswerPanel } from "./answer-panel";
import { AskForm } from "./ask-form";
import { ChatEmptyState } from "./chat-empty-state";
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
  const [requestError, setRequestError] = useState<string | null>(null);
  const [response, setResponse] = useState<LegalQAResponse | null>(null);
  const [submittedQuestion, setSubmittedQuestion] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function submitQuestion() {
    const trimmedQuestion = question.trim();
    const validationMessage = validateQuestion(trimmedQuestion, question.length, topK);
    if (validationMessage) {
      setValidationError(validationMessage);
      return;
    }

    setValidationError(null);
    setRequestError(null);
    setSubmittedQuestion(trimmedQuestion);
    setResponse(null);
    setIsLoading(true);

    try {
      const answer = await askLegalQuestion({
        question: trimmedQuestion,
        top_k: topK,
        include_evidence: includeEvidence,
        include_debug: false,
      });
      setResponse(answer);
    } catch (error) {
      setRequestError(toUserFacingError(error));
    } finally {
      setIsLoading(false);
    }
  }

  function startNewChat() {
    setQuestion("");
    setValidationError(null);
    setRequestError(null);
    setResponse(null);
    setSubmittedQuestion(null);
  }

  const hasConversation = Boolean(
    submittedQuestion || response || requestError || isLoading,
  );

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
              <div className="mx-auto flex w-full max-w-3xl flex-col gap-5">
                {submittedQuestion ? (
                  <div className="flex justify-end">
                    <div className="max-w-[min(88%,680px)] rounded-md bg-primary px-4 py-3 text-sm leading-6 text-white shadow-sm">
                      {submittedQuestion}
                    </div>
                  </div>
                ) : null}

                <div className="flex justify-start">
                  <div className="w-full max-w-[min(100%,760px)]">
                    <AnswerPanel
                      errorMessage={requestError}
                      isLoading={isLoading}
                      response={response}
                    />
                  </div>
                </div>
              </div>
            ) : (
              <ChatEmptyState />
            )}
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
      return "Không thể kết nối backend. Kiểm tra API server và NEXT_PUBLIC_API_BASE_URL.";
    }
    if (error.code === "http_error") {
      return "Backend trả về lỗi. Vui lòng thử lại.";
    }
    if (error.code === "invalid_json") {
      return "Phản hồi backend không hợp lệ.";
    }
  }
  return "Đã xảy ra lỗi không xác định.";
}
