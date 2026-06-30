import type { LegalQAResponse } from "@/types/legal-qa";

export type ChatMessage =
  | {
      id: string;
      role: "user";
      content: string;
      createdAt: string;
    }
  | {
      id: string;
      role: "assistant";
      content: string;
      createdAt: string;
      status: "loading" | "complete" | "error";
      response?: LegalQAResponse;
      errorMessage?: string;
    };

export type Conversation = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: ChatMessage[];
};
