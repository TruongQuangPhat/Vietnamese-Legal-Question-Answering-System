import { AnswerPanel } from "./answer-panel";
import type { ChatMessage } from "./chat-types";

type ChatMessageListProps = {
  messages: ChatMessage[];
};

export function ChatMessageList({ messages }: ChatMessageListProps) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-5">
      {messages.map((message) => {
        if (message.role === "user") {
          return (
            <div className="flex justify-end" key={message.id}>
              <div className="max-w-[min(88%,680px)] rounded-md bg-primary px-4 py-3 text-sm leading-6 text-white shadow-sm">
                {message.content}
              </div>
            </div>
          );
        }

        return (
          <div className="flex justify-start" key={message.id}>
            <div className="w-full max-w-[min(100%,760px)]">
              <AnswerPanel
                errorMessage={message.errorMessage ?? null}
                isLoading={message.status === "loading"}
                response={message.response ?? null}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
